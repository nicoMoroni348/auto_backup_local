# -*- coding: utf-8 -*-
"""
retention.py –  Lógica de limpieza configurable y cron_daily
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import shutil
from collections import defaultdict

from odoo import api, models, _  # type: ignore

_logger = logging.getLogger(__name__)

_DATE_RGX = re.compile(r"db_backup_.*?_(\d{4})_(\d{2})_(\d{2})_\d{6}\.zip$")


class BackupConfigRetention(models.Model):
    _inherit = "backup.config"

    # ───────────────────────────────────────────────────────────────
    #  LIMPIEZA
    # ───────────────────────────────────────────────────────────────
    def cleanup_backups(self):
        for rec in self:
                
            if not rec.cleanup_enabled:
                return

            base_dir = rec.backup_path
            today = datetime.date.today()
            _logger.info("Limpieza de backups en %s (%s)", base_dir, rec.name)

            # 1) recolectar ZIPs con fecha -------------------------------
            dated_files = []
            for root, _, files in os.walk(base_dir):
                for fname in files:
                    m = _DATE_RGX.match(fname)
                    if m:
                        y, mth, d = map(int, m.groups())
                        try:
                            f_date = datetime.date(y, mth, d)
                        except ValueError:
                            continue
                        dated_files.append((f_date, os.path.join(root, fname)))

            if not dated_files:
                _logger.info("No hay backups para limpiar.")
                return

            # 2) buckets G-F-S ------------------------------------------
            daily_n   = max(rec.daily_keep_for_days, 0)
            weekly_n  = max(rec.weekly_keep_for_weeks, 0)
            monthly_n = max(rec.monthly_keep_for_months, 0)

            keep_daily   = defaultdict(list)
            keep_weekly  = defaultdict(list)
            keep_monthly = defaultdict(list)
            delete_list  = []

            for f_date, f_path in dated_files:
                age_days = (today - f_date).days
                if daily_n and age_days < daily_n:
                    keep_daily[f_date].append((f_date, f_path));  continue
                if weekly_n and age_days < weekly_n * 7:
                    keep_weekly[f_date.isocalendar()[:2]].append((f_date, f_path));  continue
                if monthly_n and age_days < monthly_n * 30:
                    keep_monthly[(f_date.year, f_date.month)].append((f_date, f_path));  continue
                delete_list.append(f_path)

            def _others(bucket):
                for _, lst in bucket.items():
                    lst.sort()
                    yield from (p for _, p in lst[:-1])

            delete_list.extend(_others(keep_daily))
            delete_list.extend(_others(keep_weekly))
            delete_list.extend(_others(keep_monthly))

            _logger.info("Archivos a eliminar: %s", len(delete_list))

            # 3) eliminar -----------------------------------------------
            for fp in delete_list:
                try:
                    os.remove(fp)
                except Exception as exc:
                    _logger.warning(f"Error al eliminar {fp}: {exc}")


    # cron diario (XML → modelo.cron_clean_backups())
    @api.model
    def cron_clean_backups(self):
        for rec in self.search([("backup_enabled", "=", True)]):
            _logger.info("LIMPIEZA de backups para %s", rec.name)
            rec.cleanup_backups()
