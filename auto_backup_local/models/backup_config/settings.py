# -*- coding: utf-8 -*-
"""
settings.py –  Definición del modelo «backup.config»
• Campos de configuración
• Utilidades de cifrado Fernet
• Validaciones y CRUD overrides
"""

from __future__ import annotations

import base64
import logging
import os
import re

from typing import List

from cryptography.fernet import Fernet  # type: ignore
from odoo import _, api, fields, models  # type: ignore
from odoo.exceptions import ValidationError  # type: ignore
from odoo.service import db  # type: ignore

_logger = logging.getLogger(__name__)
_HOUR_RGX = re.compile(r"^(\d|1\d|2[0-3])(,\s*(\d|1\d|2[0-3]))*$")


class BackupConfig(models.Model):
    _name = "backup.config"
    _description = "Configuración de backups automáticos"
    _rec_name = "backup_path"

    # ───────────────────────────────────────────────────────────────
    #  Campos principales
    # ───────────────────────────────────────────────────────────────
    backup_path = fields.Char(string="Ruta de destino", required=True)
    backup_enabled = fields.Boolean(string="Backups activos", default=True)

    # Programación centralizada
    schedule_mode = fields.Selection(
        [
            ("daily", "Diario (1 vez)"),
            ("weekly", "Semanal"),
            ("monthly", "Mensual"),
            ("hours", "Varias horas fijas"),
        ],
        default="daily",
        required=True,
    )
    run_hours = fields.Char(
        string="Horas (HH,HH,HH)",
        help=(
            "Lista de horas en formato 0-23 separadas por comas."
            "Ej.: 0,5,8,17,21"
            "Se usa sólo cuando el Modo de programación es «Varias horas fijas»."
        )
    )

    last_execution_date = fields.Datetime(string="Última ejecución", readonly=True)

    # Retención parametrizable
    cleanup_enabled         = fields.Boolean(string="Limpiar backups", default=True)
    daily_keep_for_days     = fields.Integer(string="Conservar diarios (días)",   default=7)
    weekly_keep_for_weeks   = fields.Integer(string="Conservar semanales (sem.)", default=4)
    monthly_keep_for_months = fields.Integer(string="Conservar mensuales (meses)", default=12)

    # Contraseña maestra (cifrada)
    master_password_input  = fields.Char(string="Contraseña maestra", store=False)
    master_password_token  = fields.Char(string="Contraseña cifrada", readonly=True, copy=False)

    # Clave Fernet global
    _KEY_PARAM = "auto_backup_local.fernet_key"

    # ───────────────────────────────────────────────────────────────
    #  Utilidades de cifrado
    # ───────────────────────────────────────────────────────────────
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

    # ───────────────────────────────────────────────────────────────
    #  Validaciones y CRUD
    # ───────────────────────────────────────────────────────────────
    @api.constrains("backup_path")
    def _check_backup_path(self):
        """
        • Debe ser una ruta absoluta.
        • Debe existir físicamente.
        • Debe ser escribible por el proceso de Odoo.
        """
        for rec in self:
            path = rec.backup_path

            # 1) absoluta
            if not path or not path.startswith("/"):
                raise ValidationError(_("La ruta debe ser absoluta (ej.: /mnt/backups)."))

            # 2) existe
            if not os.path.isdir(path):
                raise ValidationError(_(
                    "La ruta '%s' no existe. Cree el directorio manualmente y "
                    "asegúrese de montarlo como volumen si usa Docker."
                ) % path)

            # 3) permisos de escritura
            if not os.access(path, os.W_OK):
                raise ValidationError(_(
                    "Odoo no tiene permisos de escritura en '%s'. "
                    "Cambie la ruta o ajuste los permisos (chown / chmod)."
                ) % path)

    @api.constrains("run_hours", "schedule_mode")
    def _check_run_hours(self):
        """
        • Sólo se valida cuando schedule_mode == 'hours'.
        • Formato permitido: números 0-23 separados por coma.
        • No se permiten duplicados.
        """
        for rec in self:
            if rec.schedule_mode != "hours":
                continue

            if not rec.run_hours:
                raise ValidationError(_("Debe indicar al menos una hora."))

            if not _HOUR_RGX.match(rec.run_hours.strip()):
                raise ValidationError(_(
                    "Formato de horas no válido. Use números 0-23 separados por comas, "
                    "por ejemplo: 0,5,8,17,21"
                ))

            # verificar duplicados
            hours = [int(h.strip()) for h in rec.run_hours.split(",")]
            if len(set(hours)) != len(hours):
                raise ValidationError(_("Las horas no deben repetirse."))


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

    # ───────────────────────────────────────────────────────────────
    #  Registro de resultados
    # ───────────────────────────────────────────────────────────────
    def _create_log(self, status: str, message: str, path: str | None = None, size: str | None = None):
        self.env["backup.log"].sudo().create({
            "config_id": self.id,
            "status": status,
            "message": message,
            "file_path": path,
            "file_size": size,
        })
