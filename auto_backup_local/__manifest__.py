# -*- coding: utf-8 -*-
{
    'name': 'Automatic Local Backup',
    'version': '17.0.1.0.0',
    'summary': 'Backups automáticos en local de la base de datos y filestore con limpieza y logs.',
    'description': """
Este módulo permite generar y administrar backups automáticos locales de Odoo.
Incluye funcionalidades para definir la frecuencia, ruta de almacenamiento,
retención de backups antiguos y registro de logs. Totalmente compatible con entornos Docker.
    """,
    'author': 'Nicolás Moroni',
    'website': 'https://github.com/nicoMoroni348/auto_backup_local',
    'license': 'LGPL-3',
    'category': 'Tools',
    'depends': ['base'],

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
