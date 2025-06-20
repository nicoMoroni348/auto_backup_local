# -*- coding: utf-8 -*-
from odoo import fields, models  # type: ignore

class BackupLog(models.Model):
    """
    Modelo que registra el resultado de cada intento de backup.
    Incluye fecha, estado, mensaje, y tamaño del archivo generado (si aplica).
    """
    _name = "backup.log"
    _description = "Registro de ejecuciones de backups"
    _order = "create_date desc"

    config_id = fields.Many2one("backup.config", string="Configuración asociada", ondelete="set null")
    status = fields.Selection([("success", "Éxito"), ("error", "Error")], string="Estado", required=True)
    message = fields.Text(string="Mensaje")
    file_path = fields.Char(string="Archivo generado")
    file_size = fields.Char(string="Tamaño")
    create_date = fields.Datetime(string="Fecha", readonly=True)
