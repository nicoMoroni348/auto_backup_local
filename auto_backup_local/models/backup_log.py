# -*- coding: utf-8 -*-
"""
backup_log.py
=============

Modelo de historial para los backups automáticos.
"""

from odoo import api, fields, models  # type: ignore


class BackupLog(models.Model):
    _name = "backup.log"
    _description = "Registro de ejecuciones de backups"
    _order = "create_date desc"

    # ---------------------------------------------------------------
    #  Relaciones
    # ---------------------------------------------------------------
    config_id = fields.Many2one(
        "backup.config",
        string="Configuración",
        ondelete="set null",
        index=True,
    )
    name = fields.Char(
        string="Descripción de la configuración",
        related="config_id.name",
        store=True,
        readonly=True,
    )

    # ---------------------------------------------------------------
    #  Datos del evento
    # ---------------------------------------------------------------
    status = fields.Selection(
        [
            ("success", "Éxito"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        string="Estado",
        required=True,
        index=True,
    )
    message = fields.Text(string="Mensaje")
    file_path = fields.Char(string="Archivo")
    file_size = fields.Char(string="Tamaño")
    create_date = fields.Datetime(string="Fecha", readonly=True)
