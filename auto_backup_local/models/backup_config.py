# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import datetime
import logging
import os
import shutil
import subprocess
from typing import List, Set

from cryptography.fernet import Fernet  # type: ignore
from dateutil.relativedelta import relativedelta  # type: ignore
from odoo import _, api, fields, models  # type: ignore
from odoo.exceptions import ValidationError  # type: ignore
from odoo.service import db  # type: ignore

_logger = logging.getLogger(__name__)

# ==============================================================
#  MODELO PRINCIPAL
# ==============================================================

class BackupConfig(models.Model):
    """
    Modelo principal que define dónde, cuándo y cómo generar/limpiar backups.
    """
    _name = "backup.config"
    _description = "Configuración de backups automáticos"
    _rec_name = "backup_path"


    # ------------------------------------------------------------------
    #  RUTA Y ESTADO
    # ------------------------------------------------------------------
    backup_path = fields.Char(string="Ruta de destino", required=True)
    backup_enabled = fields.Boolean(string="Backups activos", default=True)
    last_execution_date = fields.Datetime(string="Última ejecución", readonly=True)

    # ------------------------------------------------------------------
    #  PROGRAMACIÓN CENTRALIZADA
    # ------------------------------------------------------------------
    schedule_mode = fields.Selection(
        [
            ("daily", "Diario (una vez)"),
            ("weekly", "Semanal"),
            ("monthly", "Mensual"),
            ("hours", "Varias horas fijas"),
        ],
        string="Modo de programación",
        default="daily",
        required=True,
    )
    run_hours = fields.Char(
        string="Horas (HH,HH,HH)",
        help="Sólo para modo «Varias horas fijas». Ej.: 3,13,17,21",
        invisible="schedule_mode != 'hours'",
    )


    # ------------------------------------------------------------------
    #  POLÍTICA DE LIMPIEZA
    # ------------------------------------------------------------------
    cleanup_enabled = fields.Boolean(string="Limpiar backups antiguos", default=True)
    retention_days = fields.Integer(string="Días de retención simple", default=7)

    daily_keep_last = fields.Boolean(string="Mantener último backup diario", default=True)
    weekly_cleanup = fields.Boolean(string="Limpieza semanal", default=True)
    monthly_cleanup = fields.Boolean(string="Limpieza mensual", default=True)
    months_to_keep = fields.Integer(string="Meses a conservar", default=6)

    # ------------------------------------------------------------------
    #  CONTRASEÑA MAESTRA CIFRADA
    # ------------------------------------------------------------------
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

    # ==============================================================
    #  Utilidades Fernet (clave en ir.config_parameter)
    # ==============================================================
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

    # ==============================================================
    #  Validación & cifrado de la master password
    # ==============================================================
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

    # ==============================================================
    #  CRUD overrides
    # ==============================================================
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

    # ==============================================================
    #  Ejecución de backup
    # ==============================================================
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

    # ==============================================================
    #  Planificador
    # ==============================================================
    def _parse_run_hours(self) -> Set[int]:
        hours: Set[int] = set()
        for token in (self.run_hours or "").split(","):
            token = token.strip()
            if token.isdigit():
                h = int(token)
                if 0 <= h <= 23:
                    hours.add(h)
        return hours

    def _should_execute_now(self, now: datetime.datetime) -> bool:
        if self.schedule_mode == "hours":
            hours = self._parse_run_hours()
            _logger.debug("Horas programadas: %s", hours)
            _logger.debug("Hora actual: %s", now.hour)

            if not hours or now.hour not in hours:
                return False
            # El cron corre cada 1 h; basta con controlar que no haya corrido en esta hora.
            last = self.last_execution_date
            return not last or not (last.date() == now.date() and last.hour == now.hour)

        # Modos daily / weekly / monthly
        if not self.last_execution_date:
            return True
        delta = relativedelta(now, self.last_execution_date)
        return (
            (self.schedule_mode == "daily" and delta.days >= 1)
            or (self.schedule_mode == "weekly" and delta.days >= 7)
            or (self.schedule_mode == "monthly" and delta.months >= 1)
        )

    # ---- cron llamado cada hora ---------------------------------
    @api.model
    def cron_execute_backups(self):
        now = fields.Datetime.now()
        for rec in self.search([("backup_enabled", "=", True)]):
            if rec._should_execute_now(now):
                rec.execute_backup()


    # ==============================================================
    #  Limpieza
    # ==============================================================
    def cleanup_backups(self):
        if not self.cleanup_enabled:
            return

        base_dir = self.backup_path
        today = datetime.date.today()
        log = lambda msg: self._create_log("warning", msg)

        def _iterate_zips(dir_path, prefix):
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.startswith(prefix) and f.endswith(".zip"):
                        yield os.path.join(root, f)

        # Retención simple
        cutoff_dt = datetime.datetime.now() - datetime.timedelta(days=self.retention_days)
        for root, _, files in os.walk(base_dir):
            for f in files:
                if f.endswith(".zip"):
                    fp = os.path.join(root, f)
                    if datetime.datetime.fromtimestamp(os.path.getmtime(fp)) < cutoff_dt:
                        os.remove(fp)
        log(_("Aplicada retención simple de %s días.") % self.retention_days)

        # Mantener último backup de ayer
        if self.daily_keep_last:
            yest = today - datetime.timedelta(days=1)
            pat = yest.strftime("db_backup_%Y_%m_%d")
            ddir = os.path.join(base_dir, yest.strftime("%Y_%m"))
            if os.path.isdir(ddir):
                zips = sorted(_iterate_zips(ddir, pat))
                for z in zips[:-1]:
                    os.remove(z)
                log(_("Limpieza diaria aplicada (%s).") % yest.strftime("%Y-%m-%d"))

        # Limpieza semanal (lunes-sábado anteriores)
        if self.weekly_cleanup:
            w_start = today - relativedelta(weeks=1, weekday=0)
            for d in (w_start + datetime.timedelta(i) for i in range(6)):
                pat = d.strftime("db_backup_%Y_%m_%d")
                ddir = os.path.join(base_dir, d.strftime("%Y_%m"))
                if os.path.isdir(ddir):
                    for z in _iterate_zips(ddir, pat):
                        os.remove(z)
            log(_("Limpieza semanal aplicada."))

        # Limpieza mensual
        if self.monthly_cleanup:
            prev_last = (today.replace(day=1) - datetime.timedelta(days=1))
            pdir = os.path.join(base_dir, prev_last.strftime("%Y_%m"))
            if os.path.isdir(pdir):
                keep_pat = prev_last.strftime("db_backup_%Y_%m_%d")
                for z in _iterate_zips(pdir, f"db_backup_{prev_last.strftime('%Y_%m')}"):
                    if keep_pat not in z:
                        os.remove(z)
                log(_("Limpieza mensual aplicada (%s).") % prev_last.strftime("%Y-%m"))

        # Directorios antiguos
        cutoff_month = today - relativedelta(months=self.months_to_keep)
        for dname in os.listdir(base_dir):
            if dname <= cutoff_month.strftime("%Y_%m"):
                dpath = os.path.join(base_dir, dname)
                if os.path.isdir(dpath):
                    shutil.rmtree(dpath)
                    log(_("Eliminado dir antiguo: %s.") % dpath)

    # ---- cron diario -------------------------------------------
    @api.model
    def cron_clean_backups(self):
        for rec in self.search([("backup_enabled", "=", True)]):
            rec.cleanup_backups()




    # ==============================================================
    #  Registro de resultados
    # ==============================================================
    def _create_log(self, status: str, message: str, path: str | None = None, size: str | None = None):
        self.env["backup.log"].sudo().create({
            "config_id": self.id,
            "status": status,
            "message": message,
            "file_path": path,
            "file_size": size,
        })
