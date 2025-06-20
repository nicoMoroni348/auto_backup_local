# -*- coding: utf-8 -*-
from odoo import fields, models, api, _  # type: ignore
import os
import subprocess
import datetime
from dateutil.relativedelta import relativedelta # type: ignore

class BackupConfig(models.Model):
    """
    Modelo de configuración general del sistema de backups.
    Define la ruta, frecuencia, limpieza automática y otras opciones.
    """
    _name = "backup.config"
    _description = "Configuración de backups automáticos"
    _rec_name = "backup_path"

    backup_path = fields.Char(
        string="Ruta de destino del backup",
        required=True,
        help="Ruta absoluta donde se guardarán los backups generados. En entornos Docker, esta ruta debe estar montada como volumen."
    )

    backup_enabled = fields.Boolean(
        string="Activar backups automáticos",
        default=True,
        help="Habilita o deshabilita la ejecución automática de backups según la configuración definida."
    )

    frequency = fields.Selection(
        selection=[
            ("daily", "Diario"),
            ("weekly", "Semanal"),
            ("monthly", "Mensual"),
        ],
        string="Frecuencia del backup",
        default="daily",
        required=True
    )

    cleanup_enabled = fields.Boolean(
        string="Activar limpieza automática",
        default=True,
        help="Elimina automáticamente backups antiguos según política de retención."
    )

    retention_days = fields.Integer(
        string="Días de retención",
        default=7,
        help="Cantidad de días que se conservarán los backups antes de ser eliminados. Aplica solo si la limpieza está activada."
    )

    notes = fields.Text(
        string="Advertencia para entornos Docker",
        readonly=True,
        default=lambda self: _(
            "Si estás utilizando Odoo en un contenedor Docker, asegurate de montar la ruta especificada en 'backup_path' como volumen externo del contenedor."
        )
    )

    last_execution_date = fields.Datetime(
        string="Última ejecución",
        readonly=True
    )


    @api.constrains("backup_path")
    def _check_backup_path(self):
        """
        Verifica que la ruta ingresada sea válida.
        En entornos reales puede no existir aún, pero debe ser una ruta absoluta válida.
        """
        for record in self:
            if not record.backup_path or not record.backup_path.startswith("/"):
                raise ValueError(_("La ruta del backup debe ser una ruta absoluta válida del sistema de archivos (ej: /mnt/backups)."))


    def execute_backup(self):
        """
        Ejecuta un backup llamando a la API de Odoo con curl.
        Genera un archivo .zip en la ruta definida en 'backup_path'.
        Registra éxito o error en backup.log.
        """
        for config in self:
            if not config.backup_enabled:
                continue

            db_name = self.env.cr.dbname
            master_pwd = self.env["ir.config_parameter"].sudo().get_param("admin_passwd")
            if not master_pwd:
                config._create_log("error", "Contraseña maestra no definida en admin_passwd.")
                continue

            now = datetime.datetime.now()
            date_str = now.strftime("%Y_%m_%d_%H%M%S")
            filename = f"db_backup_{db_name}_{date_str}.zip"
            output_dir = config.backup_path.rstrip("/")
            filepath = f"{output_dir}/{filename}"

            curl_command = [
                "curl", "-X", "POST",
                "-F", f"master_pwd={master_pwd}",
                "-F", f"name={db_name}",
                "-F", "backup_format=zip",
                "-o", filepath,
                "http://localhost:8069/web/database/backup"
            ]

            try:
                result = subprocess.run(curl_command, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    config._create_log("error", f"Fallo de ejecución CURL: {result.stderr}")
                    continue

                if not os.path.isfile(filepath):
                    config._create_log("error", f"Archivo no generado: {filepath}")
                    continue

                size = os.path.getsize(filepath)
                size_mb = f"{round(size / (1024 * 1024), 2)} MB"
                config._create_log("success", "Backup generado correctamente.", filepath, size_mb)

            except Exception as e:
                config._create_log("error", f"Excepción durante el backup: {str(e)}")

    def _create_log(self, status, message, path=None, size=None):
        self.env["backup.log"].create({
            "config_id": self.id,
            "status": status,
            "message": message,
            "file_path": path,
            "file_size": size,
        })


    def _should_execute_today(self, now):
        """
        Determina si se debe ejecutar el backup hoy, en función de la frecuencia.
        """
        for rec in self:
            if not rec.last_execution_date:
                return True  # Nunca ejecutado

            delta = relativedelta(now, rec.last_execution_date)
            if rec.frequency == "daily":
                return delta.days >= 1
            elif rec.frequency == "weekly":
                return delta.days >= 7
            elif rec.frequency == "monthly":
                return delta.months >= 1
        return False

    @api.model
    def cron_execute_backups(self):
        """
        Método ejecutado por el cron. Recorre todas las configuraciones activas
        y ejecuta el backup si corresponde por frecuencia.
        """
        now = fields.Datetime.now()
        configs = self.search([("backup_enabled", "=", True)])
        for config in configs:
            if config._should_execute_today(now):
                config.execute_backup()
                config.last_execution_date = now
