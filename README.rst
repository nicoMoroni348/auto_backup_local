Auto Backup Local
=================
**Versión 17.0.1.0.0 - compatible con Odoo 17 Community & Enterprise**

Este addon automatiza la creación de copias de seguridad de la base de
datos local y permite definir una política de retención **totalmente
personalizable** (G-F-S):

* **Backups** en formato ZIP almacenados en una ruta local.
* **Programación**:
  * Diario
  * Semanal
  * Mensual
  * Varias horas fijas (p. ej. 0,5,8,17,21)
* **Retención paramétrica**
  * Conservar diarios *N* días
  * Conservar semanales *N* semanas
  * Conservar mensuales *N* meses
  * 0 = desactiva la capa correspondiente
* **Limpieza automática** - eladdon elimina los archivos que
  exceden los parámetros de retención, manteniendo siempre el último
  backup del período.
* **Cron jobs** listos para usar (definidos en `data/ir.cron.xml`).

Instalación
-----------
1. Copiar la carpeta ``auto_backup_local`` al directorio de
   addons personalizados.
2. Instalar desde *Apps > Actualizar lista > Buscar*
   **Auto Backup Local**.
3. Configurar al menos:
   * Ruta de destino (montada y escribible).
   * Contraseña maestra de Odoo.
   * Política de retención deseada.

Uso
---
* **Menú → Backups → Configuración**: crear una o más configuraciones.
* **Menú → Backups → Historial**: visualizar resultado de cada intento.

Créditos
--------
*Desarrollado por Nicolás Moroni.*

Licencia
--------
LGPL-3.0
