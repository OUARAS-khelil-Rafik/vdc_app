# models/standardmanager.py
# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

DATE_FMT = "%Y-%m-%d"
DUE_SOON_DAYS = 30

STATUS_OK = "OK"
STATUS_SOON = "Bientôt dû"
STATUS_BLOCKED = "Bloqué"

CATEGORIES = [
    "Anémomètre", "Balomètre", "Température", "Humidité",
    "Pression diff.", "Pression absolue", "Débit (air)",
    "Particules (OPC)", "Thermo-hygromètre", "Manomètre", "Autre"
]

def today_str() -> str:
    return datetime.now().strftime(DATE_FMT)

def add_months(d: datetime, months: int) -> datetime:
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(d.day, [31,
        29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return datetime(y, m, day)

def compute_next_due(last_date: Optional[str], interval_months: int) -> Optional[str]:
    if not last_date or interval_months <= 0:
        return None
    try:
        d = datetime.strptime(last_date, DATE_FMT)
        return add_months(d, interval_months).strftime(DATE_FMT)
    except Exception:
        return None

def days_until(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str, DATE_FMT)
        return (d.date() - datetime.now().date()).days
    except Exception:
        return None


class StandardManager:
    """
    Manager des étalons & calibrations, branché sur la connexion SQLite
    fournie par VDC_APP (Database.conn).
    """
    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    # ---------- schéma ----------
    def _init_schema(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS standards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial TEXT,
            name TEXT,
            category TEXT,
            manufacturer TEXT,
            model TEXT,
            location TEXT,
            owner TEXT,
            tags TEXT,
            interval_months INTEGER,
            last_cal_date TEXT,
            next_cal_date TEXT,
            status TEXT,          -- OK / Bientôt dû / Bloqué
            blocked INTEGER,      -- 0/1 (manuel)
            block_reason TEXT,
            certificate_path TEXT,
            certificate_id TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            standard_id INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
            cal_date TEXT,
            due_date TEXT,
            on_site INTEGER,
            method TEXT,
            certificate_id TEXT,
            certificate_path TEXT,
            pass_fail INTEGER,   -- 1/0 informatif
            results_json TEXT,
            notes TEXT,
            created_at TEXT
        )""")
        self.conn.commit()

    # ---------- logique statut ----------
    def _compute_status_rowlike(self, r: Dict[str, Any]) -> str:
        # Blocage manuel prioritaire
        if int(r.get("blocked") or 0) == 1:
            return STATUS_BLOCKED
        # Échéance dépassée => Bloqué automatique
        nxt = r.get("next_cal_date")
        if nxt:
            dd = days_until(nxt)
            if dd is not None and dd < 0:
                return STATUS_BLOCKED
            if dd is not None and dd <= DUE_SOON_DAYS:
                return STATUS_SOON
        return STATUS_OK

    # ---------- standards ----------
    def add_standard(self, data: Dict[str, Any]) -> int:
        now = today_str()
        data = data.copy()
        data.setdefault("tags", "")
        data.setdefault("certificate_path", "")
        data.setdefault("certificate_id", "")
        data["created_at"] = now
        data["updated_at"] = now
        data["next_cal_date"] = compute_next_due(
            data.get("last_cal_date"), int(data.get("interval_months") or 0)
        )
        data["blocked"] = 1 if data.get("blocked") else 0
        data["status"] = self._compute_status_rowlike(data)
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO standards(serial, name, category, manufacturer, model,
                                      location, owner, tags, interval_months,
                                      last_cal_date, next_cal_date, status,
                                      blocked, block_reason, certificate_path, certificate_id,
                                      notes, created_at, updated_at)
                VALUES(:serial, :name, :category, :manufacturer, :model,
                       :location, :owner, :tags, :interval_months,
                       :last_cal_date, :next_cal_date, :status,
                       :blocked, :block_reason, :certificate_path, :certificate_id,
                       :notes, :created_at, :updated_at)
            """, data)
            return cur.lastrowid

    def update_standard(self, sid: int, data: Dict[str, Any]):
        now = today_str()
        data = data.copy()
        data["updated_at"] = now
        row = self.get_standard(sid)
        if not row:
            return
        if "last_cal_date" in data or "interval_months" in data:
            last = data.get("last_cal_date", row["last_cal_date"])
            interval = int(data.get("interval_months", row["interval_months"] or 0))
            data["next_cal_date"] = compute_next_due(last, interval)
        merged = dict(row)
        merged.update(data)
        data["status"] = self._compute_status_rowlike(merged)
        keys = ", ".join(f"{k}=:{k}" for k in data.keys())
        data["id"] = sid
        with self.conn:
            self.conn.execute(f"UPDATE standards SET {keys} WHERE id=:id", data)

    def get_standard(self, sid: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM standards WHERE id=?", (sid,)).fetchone()

    def list_standards(self, category: Optional[str], status: Optional[str], search: str) -> List[sqlite3.Row]:
        q = "SELECT * FROM standards WHERE 1=1"
        params: List[Any] = []
        if category and category != "Toutes":
            q += " AND category=?"; params.append(category)
        if status and status != "Tous":
            q += " AND status=?"; params.append(status)
        if search.strip():
            like = f"%{search.strip()}%"
            q += " AND (serial LIKE ? OR name LIKE ? OR tags LIKE ?)"
            params += [like, like, like]
        q += """
        ORDER BY
          CASE status
            WHEN 'Bloqué' THEN 3
            WHEN 'Bientôt dû' THEN 2
            WHEN 'OK' THEN 1
            ELSE 0
          END DESC,
          CASE WHEN next_cal_date IS NULL OR next_cal_date='' THEN 1 ELSE 0 END,
          next_cal_date ASC,
          id DESC
        """
        return list(self.conn.execute(q, params))

    def set_block(self, sid: int, block: bool, reason: str = ""):
        with self.conn:
            row = self.get_standard(sid)
            if not row:
                return
            status = STATUS_BLOCKED if block else self._compute_status_rowlike(dict(row, blocked=0))
            self.conn.execute(
                "UPDATE standards SET blocked=?, block_reason=?, status=?, updated_at=? WHERE id=?",
                (1 if block else 0, reason, status, today_str(), sid)
            )

    def recompute_status_all(self):
        rows = self.conn.execute("SELECT * FROM standards").fetchall()
        with self.conn:
            for r in rows:
                status = self._compute_status_rowlike(dict(r))
                self.conn.execute(
                    "UPDATE standards SET status=?, updated_at=?, next_cal_date=? WHERE id=?",
                    (status, today_str(),
                     compute_next_due(r["last_cal_date"], r["interval_months"] or 0),
                     r["id"])
                )

    # ---------- calibrations ----------
    def add_calibration(self, sid: int, data: Dict[str, Any]):
        now = today_str()
        data = data.copy()
        data["created_at"] = now
        std = self.get_standard(sid)
        if not std:
            return
        interval = int(std["interval_months"] or 0)
        due = compute_next_due(data.get("cal_date"), interval)
        data["due_date"] = due
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO calibrations(standard_id, cal_date, due_date, on_site, method,
                                         certificate_id, certificate_path, pass_fail,
                                         results_json, notes, created_at)
                VALUES(:standard_id, :cal_date, :due_date, :on_site, :method,
                       :certificate_id, :certificate_path, :pass_fail,
                       :results_json, :notes, :created_at)
            """, dict(data, standard_id=sid))
            upd = {
                "last_cal_date": data.get("cal_date"),
                "next_cal_date": due,
                "certificate_id": data.get("certificate_id") or std["certificate_id"],
                "certificate_path": data.get("certificate_path") or std["certificate_path"],
            }
            merged = dict(std); merged.update(upd)
            status = self._compute_status_rowlike(dict(merged, blocked=std["blocked"]))
            self.conn.execute("""
                UPDATE standards
                   SET last_cal_date=:last_cal_date,
                       next_cal_date=:next_cal_date,
                       certificate_id=:certificate_id,
                       certificate_path=:certificate_path,
                       status=:status,
                       updated_at=:updated_at
                 WHERE id=:id
            """, dict(upd, status=status, updated_at=now, id=sid))

    def list_calibrations(self, sid: int) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM calibrations WHERE standard_id=? ORDER BY cal_date DESC, id DESC", (sid,)
        ))
