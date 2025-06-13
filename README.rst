Automatic Local Backup for Odoo 17 (DB + Filestore)
====================================================

Este módulo permite realizar backups automáticos de la base de datos y del filestore de Odoo,
guardándolos en una ruta local configurable, con limpieza automática y logs incluidos.
Ideal para entornos productivos, especialmente cuando se trabaja con contenedores Docker.

Características principales
----------------------------

* Backups automáticos de base de datos vía API HTTP de Odoo (`/web/database/backup`).
* Copia del filestore incluido en el ZIP.
* Configuración de frecuencia y activación desde la interfaz de Odoo.
* Limpieza automática de backups antiguos:
  * Diaria: conserva solo el último backup del día anterior.
  * Semanal: borra todos los días de la semana pasada.
  * Mensual: conserva solo el último del mes anterior y elimina directorios > 6 meses.
* Logs detallados de cada acción, accesibles desde Odoo.
* Compatible con contenedores Docker.

Requisitos
-----------

* Tener instalado `curl` en el contenedor o entorno donde corre Odoo.
* En caso de usar Docker, se recomienda montar un volumen externo para almacenar los backups:

  .. code-block:: bash

    docker run -v /home/odoo/backups:/mnt/odoo_backups odoo:17

* El módulo permite indicar `/mnt/odoo_backups` como ruta destino desde la configuración.

Capturas de pantalla
---------------------

(Si querés agregar capturas de configuración o logs desde la interfaz de Odoo, se incluyen aquí)

Licencia
--------

Este módulo está licenciado bajo la **GNU Lesser General Public License v3.0 (LGPL-3.0)**

Copyright (C) 2025 - Nicolás Moroni

Colaboraciones y mejoras son bienvenidas mediante Pull Requests.
