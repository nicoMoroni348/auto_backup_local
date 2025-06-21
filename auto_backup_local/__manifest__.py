# -*- coding: utf-8 -*-
{
    'name': 'Automatic Local Backup',
    'version': '17.0.1.0.0',
    "summary": "Backups automáticos con retención diaria, semanal y mensual configurable",
    "price": 0,
    "currency": "EUR",
    "description": """
Auto Backup Local (Odoo 17)
===========================

Módulo que permite programar copias de seguridad locales **con política
G-F-S completamente parametrizable**:

* Ejecución diaria, semanal, mensual o en horas fijas (ej.: 0,5,8,17,21).
* Retención:
  - Conservar diarios *N* días (mantiene el último de cada día).
  - Conservar semanales *N* semanas (mantiene el último de cada semana ISO).
  - Conservar mensuales *N* meses (mantiene el último de cada mes).
* Limpieza automática vía *cron*.
* Cifrado seguro de la contraseña maestra con Fernet.
* Validaciones de ruta, permisos y formato de horas.
* Registro detallado de cada intento en **backup.log**.

""",
    'author': 'Nicolás Moroni',
    'website': 'https://github.com/nicoMoroni348/auto_backup_local',
    'license': 'LGPL-3',
    'category': 'Tools',
    'depends': ['base'],
    "images": [
        "images/main_screenshot.png",   # thumbnail mostrado en Apps
    ],


    'external_dependencies': {
        'python': ['cryptography'],
    },

    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/backup_config_view.xml',
        'views/backup_log_view.xml',
    ],
    'installable': True,
    'application': True,
}
