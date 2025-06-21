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
        if not self.cleanup_enabled:
            return

        base_dir = self.backup_path
        today = datetime.date.today()
        log = lambda msg: self._create_log("warning", msg)

        # 1) recolectar ZIPs con fecha
        dated_files = []
        for root, _, files in os.walk(base_dir):
            for f in files:
                m = _DATE_RGX.match(f)
                if not m:
                    continue
                y, mth, d = map(int, m.groups())
                try:
                    f_date = datetime.date(y, mth, d)
                except ValueError:
                    continue
                dated_files.append((f_date, os.path.join(root, f)))

        if not dated_files:
            return

        # 2) buckets G-F-S parametrizables
        daily_n   = max(self.daily_keep_for_days, 0)
        weekly_n  = max(self.weekly_keep_for_weeks, 0)
        monthly_n = max(self.monthly_keep_for_months, 0)

        keep_daily   = defaultdict(list)
        keep_weekly  = defaultdict(list)
        keep_monthly = defaultdict(list)
        delete_list  = []

        for f_date, f_path in dated_files:
            age_days = (today - f_date).days

            if daily_n and age_days < daily_n:
                keep_daily[f_date].append((f_date, f_path))
                continue

            if weekly_n and age_days < weekly_n * 7:
                keep_weekly[f_date.isocalendar()[:2]].append((f_date, f_path))
                continue

            if monthly_n and age_days < monthly_n * 30:
                keep_monthly[(f_date.year, f_date.month)].append((f_date, f_path))
                continue

            delete_list.append(f_path)

        def olders(bucket):
            for _, lst in bucket.items():
                lst.sort()
                yield from (p for _, p in lst[:-1])

        delete_list.extend(olders(keep_daily))
        delete_list.extend(olders(keep_weekly))
        delete_list.extend(olders(keep_monthly))

        # 3) eliminar
        for fp in delete_list:
            try:
                os.remove(fp)
                log(_("Eliminado: %s") % fp)
            except Exception as exc:
                log(_("Error al eliminar %s: %s") % (fp, exc))

        # 4) directorios > monthly_n meses (seguridad extra)
        cutoff_month = today - datetime.timedelta(days=monthly_n * 30 if monthly_n else 3650)
        for dname in os.listdir(base_dir):
            if dname <= cutoff_month.strftime("%Y_%m"):
                dpath = os.path.join(base_dir, dname)
                if os.path.isdir(dpath):
                    shutil.rmtree(dpath)
                    log(_("Eliminado dir antiguo: %s") % dpath)

    # cron diario (XML → modelo.cron_clean_backups())
    @api.model
    def cron_clean_backups(self):
        for rec in self.search([("backup_enabled", "=", True)]):
            rec.cleanup_backups()
