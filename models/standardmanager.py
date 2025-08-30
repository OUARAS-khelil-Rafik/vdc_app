# models/standardmanager.py
# -*- coding: utf-8 -*-
"""
Gestion des Étalons (Standards) – modèle SQLite
Empêche la duplication via contrainte UNIQUE sur serial.
"""

import sqlite3
from datetime import datetime


class StandardManager:
    def __init__(self, db_path="vdc.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    # ---------------- CRUD Standards ---------------- #

    def add_standard(self, data: dict):
        now = datetime.now().isoformat()
        data.setdefault("created_at", now)
        data["updated_at"] = now

        with self.conn:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO standards(
                    serial, name, category, manufacturer, model,
                    location, owner_id, tags, interval_months,
                    last_cal_date, next_cal_date, status,
                    blocked, block_reason, certificate_path, certificate_id,
                    notes, created_at, updated_at
                )
                VALUES(:serial, :name, :category, :manufacturer, :model,
                    :location, :owner_id, :tags, :interval_months,
                    :last_cal_date, :next_cal_date, :status,
                    :blocked, :block_reason, :certificate_path, :certificate_id,
                    :notes, :created_at, :updated_at)
                ON CONFLICT(serial) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    manufacturer=excluded.manufacturer,
                    model=excluded.model,
                    location=excluded.location,
                    owner_id=excluded.owner_id,
                    tags=excluded.tags,
                    interval_months=excluded.interval_months,
                    last_cal_date=excluded.last_cal_date,
                    next_cal_date=excluded.next_cal_date,
                    status=excluded.status,
                    blocked=excluded.blocked,
                    block_reason=excluded.block_reason,
                    certificate_path=excluded.certificate_path,
                    certificate_id=excluded.certificate_id,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
            """, data)

            return cur.lastrowid

    def get_standard(self, standard_id: int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM standards WHERE id=?", (standard_id,))
        return c.fetchone()

    def get_all_standards(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM standards ORDER BY created_at DESC")
        return c.fetchall()

    def delete_standard(self, standard_id: int):
        with self.conn:
            self.conn.execute("DELETE FROM standards WHERE id=?", (standard_id,))

    # ---------------- CRUD Calibrations ---------------- #

    def add_calibration(self, data: dict):
        now = datetime.now().isoformat()
        data.setdefault("created_at", now)
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO calibrations(
                    standard_id, cal_date, due_date, on_site,
                    method, certificate_id, certificate_path,
                    pass_fail, results_json, notes, created_at
                )
                VALUES(:standard_id, :cal_date, :due_date, :on_site,
                       :method, :certificate_id, :certificate_path,
                       :pass_fail, :results_json, :notes, :created_at)
            """, data)
            return cur.lastrowid

    def get_calibrations_for_standard(self, standard_id: int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM calibrations WHERE standard_id=? ORDER BY cal_date DESC", (standard_id,))
        return c.fetchall()

    def get_owner_names(self, owner_ids):
        """
        Retourne tous les noms des responsables (users) pour une liste d'IDs ou une chaîne CSV.
        """
        if not owner_ids:
            return ""
        if isinstance(owner_ids, int):
            ids = [owner_ids]
        elif isinstance(owner_ids, str):
            ids = [int(x) for x in owner_ids.split(",") if x.strip().isdigit()]
        else:
            ids = []
        if not ids:
            return ""
        q = f"SELECT full_name FROM users WHERE id IN ({','.join(['?']*len(ids))})"
        res = self.conn.execute(q, ids).fetchall()
        return ", ".join([row["full_name"] for row in res])
