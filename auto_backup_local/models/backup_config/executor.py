# -*- coding: utf-8 -*-
"""
executor.py –  Métodos de generación de backups y cron_hourly
"""

from __future__ import annotations

import datetime
import logging
import os
import subprocess
from typing import Set

from dateutil.relativedelta import relativedelta  # type: ignore
from odoo import api, fields, models, _  # type: ignore

_logger = logging.getLogger(__name__)


class BackupConfigExecutor(models.Model):
    _inherit = "backup.config"

    # ───────────────────────────────────────────────────────────────
    #  EJECUCIÓN DE BACKUP
    # ───────────────────────────────────────────────────────────────
    def execute_backup(self):
        for rec in self.filtered("backup_enabled"):
            if not rec.master_password_token:
                rec._create_log("error", _("Sin contraseña maestra configurada."))
                continue
            try:
                master_pwd = rec._decrypt_pwd(rec.master_password_token)
                self._validate_master(master_pwd)
            except Exception as exc:
                rec._create_log("error", _("Contraseña inválida: %s") % exc)
                continue

            db_name = self.env.cr.dbname
            now = datetime.datetime.now()
            filename = f"db_backup_{db_name}_{now.strftime('%Y_%m_%d_%H%M%S')}.zip"
            filepath = os.path.join(rec.backup_path, filename)

            cmd = [
                "curl", "--silent", "--fail", "--show-error",
                "-X", "POST",
                "-F", f"master_pwd={master_pwd}",
                "-F", f"name={db_name}",
                "-F", "backup_format=zip",
                "-o", filepath,
                "http://localhost:8069/web/database/backup",
            ]

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode != 0:
                    rec._create_log("error", _("Fallo CURL: %s") % res.stderr.strip())
                    continue

                if not os.path.isfile(filepath):
                    rec._create_log("error", _("Archivo no generado."))
                    continue

                size_mb = f"{round(os.path.getsize(filepath)/1024**2,2)} MB"
                rec._create_log("success", _("Backup OK"), filepath, size_mb)
                rec.last_execution_date = fields.Datetime.now()

            except Exception as exc:
                rec._create_log("error", _("Excepción: %s") % exc)

    # ───────────────────────────────────────────────────────────────
    #  PLANIFICACIÓN (cron_hourly en XML)
    # ───────────────────────────────────────────────────────────────
    def _parse_run_hours(self) -> Set[int]:
        out: Set[int] = set()
        for tok in (self.run_hours or "").split(","):
            tok = tok.strip()
            if tok.isdigit():
                n = int(tok)
                if 0 <= n <= 23:
                    out.add(n)
        return out

    def _should_execute_now(self, now: datetime.datetime) -> bool:
        if self.schedule_mode == "hours":
            hours = self._parse_run_hours()
            if not hours or now.hour not in hours:
                return False
            last = self.last_execution_date
            return not last or not (last.date() == now.date() and last.hour == now.hour)

        if not self.last_execution_date:
            return True
        delta = relativedelta(now, self.last_execution_date)
        return (
            (self.schedule_mode == "daily"   and delta.days   >= 1) or
            (self.schedule_mode == "weekly"  and delta.days   >= 7) or
            (self.schedule_mode == "monthly" and delta.months >= 1)
        )

    @api.model
    def cron_execute_backups(self):
        now = fields.Datetime.now()
        for rec in self.search([("backup_enabled", "=", True)]):
            if not rec._should_execute_now(now):
                _logger.info(f"BackupConfigExecutor: No ejecutar aún backup para {rec.name} ({rec.id})")
                continue
            rec.execute_backup()
