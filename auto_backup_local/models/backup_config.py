# -*- coding: utf-8 -*-
"""
backup_config.py  –  Módulo de backups automáticos (Odoo 17)
"""

from __future__ import annotations

import base64
import datetime
import logging
import os
import subprocess
from typing import List

from cryptography.fernet import Fernet  # type: ignore
from dateutil.relativedelta import relativedelta  # type: ignore
from odoo import _, api, fields, models  # type: ignore
from odoo.exceptions import ValidationError  # type: ignore
from odoo.service import db  # type: ignore

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  MODELO PRINCIPAL
# ---------------------------------------------------------------------------


class BackupConfig(models.Model):
    """
    Configuración de las copias de seguridad automáticas.
    """
    _name = "backup.config"
    _description = "Configuración de backups automáticos"
    _rec_name = "backup_path"

    # ---------------------------------------------------------------------
    #  Campos
    # ---------------------------------------------------------------------
    backup_path = fields.Char(
        string="Ruta de destino",
        required=True,
    )
    backup_enabled = fields.Boolean(
        string="Backups activos",
        default=True,
    )
    frequency = fields.Selection(
        [("daily", "Diario"), ("weekly", "Semanal"), ("monthly", "Mensual")],
        string="Frecuencia",
        default="daily",
        required=True,
    )
    cleanup_enabled = fields.Boolean(
        string="Limpiar backups antiguos",
        default=True,
    )
    retention_days = fields.Integer(
        string="Días de retención",
        default=7,
    )
    last_execution_date = fields.Datetime(
        string="Última ejecución",
        readonly=True,
    )

    # --------- contraseña maestra ---------------------------------------
    master_password_input = fields.Char(
        string="Contraseña maestra",
        store=False,
        password="1",
    )
    master_password_token = fields.Char(
        string="Contraseña cifrada",
        readonly=True,
        copy=False,
    )

    # ---------------------------------------------------------------------
    #  Utilidades Fernet (clave en ir.config_parameter)
    # ---------------------------------------------------------------------
    _KEY_PARAM = "auto_backup_local.fernet_key"

    def _get_fernet(self) -> Fernet:
        """Obtiene (o crea) la clave Fernet y retorna un objeto Fernet."""
        Param = self.env["ir.config_parameter"].sudo()
        key_b64 = Param.get_param(self._KEY_PARAM)
        if not key_b64:
            random_bytes = os.urandom(32)
            key_b64 = base64.urlsafe_b64encode(random_bytes).decode()
            Param.set_param(self._KEY_PARAM, key_b64)
            _logger.info("Se generó nueva FERNET_KEY y se guardó en ir.config_parameter.")
        return Fernet(key_b64.encode())

    # ---------------------------------------------------------------------
    #  Validación & cifrado de la master password
    # ---------------------------------------------------------------------
    @staticmethod
    def _validate_master(pwd: str) -> None:
        try:
            db.check_super(pwd)
        except Exception:
            raise ValidationError(_("La contraseña maestra ingresada no es válida."))

    def _encrypt_pwd(self, clear_pwd: str) -> str:
        return base64.b64encode(self._get_fernet().encrypt(clear_pwd.encode())).decode()

    def _decrypt_pwd(self, token_b64: str) -> str:
        encrypted = base64.b64decode(token_b64.encode())
        return self._get_fernet().decrypt(encrypted).decode()

    # ---------------------------------------------------------------------
    #  CRUD overrides
    # ---------------------------------------------------------------------
    @api.constrains("backup_path")
    def _check_backup_path(self):
        for rec in self:
            if not rec.backup_path.startswith("/"):
                raise ValidationError(_("La ruta del backup debe ser absoluta."))
            os.makedirs(rec.backup_path, exist_ok=True)

    @api.model_create_multi
    def create(self, vals_list: List[dict]):
        for vals in vals_list:
            pwd = vals.pop("master_password_input", False)
            if pwd:
                self._validate_master(pwd)
                vals["master_password_token"] = self._encrypt_pwd(pwd)
        return super().create(vals_list)

    def write(self, vals):
        pwd = vals.pop("master_password_input", False)
        if pwd:
            self._validate_master(pwd)
            vals["master_password_token"] = self._encrypt_pwd(pwd)
        return super().write(vals)

    # ---------------------------------------------------------------------
    #  Ejecución de backup
    # ---------------------------------------------------------------------
    def execute_backup(self):
        for rec in self.filtered("backup_enabled"):
            if not rec.master_password_token:
                rec._create_log("error", _("No hay contraseña maestra configurada."))
                continue
            try:
                master_pwd = rec._decrypt_pwd(rec.master_password_token)
                self._validate_master(master_pwd)
            except Exception as exc:
                rec._create_log("error", _("Error al validar contraseña: %s") % exc)
                continue

            db_name = self.env.cr.dbname
            now = datetime.datetime.now()
            filename = f"db_backup_{db_name}_{now.strftime('%Y_%m_%d_%H%M%S')}.zip"
            filepath = os.path.join(rec.backup_path, filename)

            curl_cmd = [
                "curl", "--silent", "--fail", "--show-error",
                "-X", "POST",
                "-F", f"master_pwd={master_pwd}",
                "-F", f"name={db_name}",
                "-F", "backup_format=zip",
                "-o", filepath,
                "http://localhost:8069/web/database/backup",
            ]

            try:
                res = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=120)
                if res.returncode != 0:
                    rec._create_log("error", _("Fallo CURL: %s") % res.stderr.strip())
                    continue

                if not os.path.isfile(filepath):
                    rec._create_log("error", _("No se generó el archivo esperado."))
                    continue

                size_mb = f"{round(os.path.getsize(filepath)/1024**2, 2)} MB"
                rec._create_log("success", _("Backup generado correctamente."), filepath, size_mb)
                rec.last_execution_date = fields.Datetime.now()

            except Exception as exc:
                rec._create_log("error", _("Excepción durante el backup: %s") % exc)

    # ---------------------------------------------------------------------
    #  Planificador
    # ---------------------------------------------------------------------
    def _should_execute_today(self, now: datetime.datetime) -> bool:
        if not self.last_execution_date:
            return True
        delta = relativedelta(now, self.last_execution_date)
        return (
            (self.frequency == "daily" and delta.days >= 1) or
            (self.frequency == "weekly" and delta.days >= 7) or
            (self.frequency == "monthly" and delta.months >= 1)
        )

    @api.model
    def cron_execute_backups(self):
        _logger.info("Iniciando cron de backups automáticos…")
        now = fields.Datetime.now()
        for rec in self.search([("backup_enabled", "=", True)]):
            if rec._should_execute_today(now):
                rec.execute_backup()

    # ---------------------------------------------------------------------
    #  Registro de resultados
    # ---------------------------------------------------------------------
    def _create_log(self, status: str, message: str, path: str | None = None, size: str | None = None):
        self.env["backup.log"].sudo().create({
            "config_id": self.id,
            "status": status,
            "message": message,
            "file_path": path,
            "file_size": size,
        })
