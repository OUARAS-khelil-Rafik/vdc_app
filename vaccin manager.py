# vaccins_manager.py
# -*- coding: utf-8 -*-
"""
Gestion des Vaccinations – QtPy + SQLite (single file, copy‑paste ready)

Ce programme permet à une secrétaire de gérer les échéances de vaccination
pour les techniciens : saisie/import, suivi coloré (OK / Bientôt dû / Expiré),
rappels automatiques par email, historique des injections, export CSV.

Dépendances minimales (Windows/macOS/Linux) :
  pip install QtPy PyQt5 pandas openpyxl xlrd==1.2.0

• Status : OK / Bientôt dû (≤ N jours, configurable) / Expiré (échéance passée)
• Envoi email : SMTP TLS/SSL (configurable) vers l'adresse de la secrétaire
• Import Excel : .xlsx (openpyxl) ou .xls (xlrd 1.2.0) + mappage de colonnes
• DB : vaccins.db (auto-créé)

Astuce : si votre fichier est .xls et que xlrd n'est pas installé, 
convertissez-le en .xlsx via Excel puis importez.
"""
from __future__ import annotations
import os
import sys
import csv
import base64
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# QtPy s'adapte à PyQt5/PySide2 etc. Installez au moins PyQt5.
from qtpy import QtCore, QtGui, QtWidgets


# Données & Email
import pandas as pd
import smtplib
import ssl
from email.message import EmailMessage

DATE_FMT = "%Y-%m-%d"
STATUS_COLORS = {"OK": "#28a745", "Bientôt dû": "#ffc107", "Expiré": "#dc3545"}
DEFAULT_REMINDER_DAYS = 30

# --------------------------- Utilitaires date ---------------------------

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


def compute_next_due(last_date: Optional[str], validity_months: Optional[int]) -> Optional[str]:
    if not last_date or not validity_months or validity_months <= 0:
        return None
    try:
        d = datetime.strptime(last_date, DATE_FMT)
        nxt = add_months(d, validity_months)
        return nxt.strftime(DATE_FMT)
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


# --------------------------- Base de données ---------------------------

class DB:
    def __init__(self, path: str = "vaccins.db"):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.initialize()

    def initialize(self):
        c = self.conn.cursor()
        # Paramètres globaux (une seule ligne)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                secretary_email TEXT,
                smtp_host TEXT,
                smtp_port INTEGER,
                smtp_user TEXT,
                smtp_password_b64 TEXT,
                use_tls INTEGER DEFAULT 1,
                use_ssl INTEGER DEFAULT 0,
                reminder_days INTEGER DEFAULT 30,
                cc_emails TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Techniciens
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS technicians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                service TEXT,
                role TEXT,
                phone TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Vaccins (paramètres par type)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS vaccines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                code TEXT,
                validity_months INTEGER,
                default_reminder_days INTEGER,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Injections (l'historique par technicien & vaccin)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS injections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                technician_id INTEGER NOT NULL REFERENCES technicians(id) ON DELETE CASCADE,
                vaccine_id INTEGER NOT NULL REFERENCES vaccines(id) ON DELETE CASCADE,
                dose_no INTEGER,
                last_dose_date TEXT,     -- YYYY-MM-DD
                validity_months INTEGER, -- peut surcharger vaccine.validity_months
                next_due_date TEXT,
                certificate_path TEXT,
                status TEXT,             -- OK / Bientôt dû / Expiré
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Index utiles
        c.execute("CREATE INDEX IF NOT EXISTS idx_injections_next_due ON injections(next_due_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_injections_status ON injections(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_inj_tech ON injections(technician_id)")
        self.conn.commit()

        # s'assurer qu'une ligne settings existe
        cur = self.conn.execute("SELECT 1 FROM settings WHERE id=1").fetchone()
        if not cur:
            now = today_str()
            self.conn.execute(
                """
                INSERT INTO settings(id, secretary_email, smtp_host, smtp_port, smtp_user, smtp_password_b64,
                                     use_tls, use_ssl, reminder_days, cc_emails, created_at, updated_at)
                VALUES(1, '', '', 587, '', '', 1, 0, ?, '', ?, ?)
                """,
                (DEFAULT_REMINDER_DAYS, now, now)
            )
            self.conn.commit()

    # ---------------- Settings ----------------
    def get_settings(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM settings WHERE id=1").fetchone()

    def update_settings(self, data: Dict[str, Any]):
        now = today_str()
        keys = [
            "secretary_email", "smtp_host", "smtp_port", "smtp_user", "smtp_password_b64",
            "use_tls", "use_ssl", "reminder_days", "cc_emails"
        ]
        placeholders = ", ".join([f"{k} = :{k}" for k in keys])
        with self.conn:
            self.conn.execute(
                f"UPDATE settings SET {placeholders}, updated_at=:updated_at WHERE id=1",
                dict({k: data.get(k) for k in keys}, updated_at=now)
            )

    # ---------------- Technicians ----------------
    def add_technician(self, data: Dict[str, Any]) -> int:
        now = today_str()
        with self.conn:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO technicians(first_name,last_name,email,service,role,phone,notes,created_at,updated_at)
                VALUES(:first_name,:last_name,:email,:service,:role,:phone,:notes,:created_at,:updated_at)
                """,
                dict(data, created_at=now, updated_at=now)
            )
            return cur.lastrowid

    def update_technician(self, tid: int, data: Dict[str, Any]):
        now = today_str()
        keys = ["first_name","last_name","email","service","role","phone","notes"]
        with self.conn:
            self.conn.execute(
                f"UPDATE technicians SET {', '.join([k+'=:'+k for k in keys])}, updated_at=:updated_at WHERE id=:id",
                dict({k: data.get(k) for k in keys}, updated_at=now, id=tid)
            )

    def list_technicians(self, search: str = "") -> List[sqlite3.Row]:
        q = "SELECT * FROM technicians WHERE 1=1"
        params: List[Any] = []
        if search.strip():
            like = f"%{search.strip()}%"
            q += " AND (first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR service LIKE ? OR role LIKE ?)"
            params += [like, like, like, like, like]
        q += " ORDER BY last_name ASC, first_name ASC"
        return list(self.conn.execute(q, params))

    def get_technician(self, tid: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM technicians WHERE id=?", (tid,)).fetchone()

    # ---------------- Vaccines ----------------
    def add_vaccine(self, data: Dict[str, Any]) -> int:
        now = today_str()
        with self.conn:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO vaccines(name, code, validity_months, default_reminder_days, notes, created_at, updated_at)
                VALUES(:name,:code,:validity_months,:default_reminder_days,:notes,:created_at,:updated_at)
                """,
                dict(data, created_at=now, updated_at=now)
            )
            return cur.lastrowid

    def update_vaccine(self, vid: int, data: Dict[str, Any]):
        now = today_str()
        keys = ["name","code","validity_months","default_reminder_days","notes"]
        with self.conn:
            self.conn.execute(
                f"UPDATE vaccines SET {', '.join([k+'=:'+k for k in keys])}, updated_at=:updated_at WHERE id=:id",
                dict({k: data.get(k) for k in keys}, updated_at=now, id=vid)
            )

    def list_vaccines(self, search: str = "") -> List[sqlite3.Row]:
        q = "SELECT * FROM vaccines"
        params: List[Any] = []
        if search.strip():
            like = f"%{search.strip()}%"
            q += " WHERE (name LIKE ? OR code LIKE ?)"; params += [like, like]
        q += " ORDER BY name ASC"
        return list(self.conn.execute(q, params))

    def get_vaccine(self, vid: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM vaccines WHERE id=?", (vid,)).fetchone()

    # ---------------- Injections ----------------
    def _compute_status(self, next_due: Optional[str], reminder_days: int) -> str:
        if not next_due:
            return "OK"
        dd = days_until(next_due)
        if dd is None:
            return "OK"
        if dd < 0:
            return "Expiré"
        if dd <= reminder_days:
            return "Bientôt dû"
        return "OK"

    def add_injection(self, data: Dict[str, Any]) -> int:
        now = today_str()
        # Calcul automatique next_due & status
        last_date = data.get("last_dose_date")
        validity_months = data.get("validity_months") or 0
        next_due = compute_next_due(last_date, int(validity_months))
        settings = self.get_settings()
        reminder_days = int(settings["reminder_days"] or DEFAULT_REMINDER_DAYS)
        status = self._compute_status(next_due, reminder_days)
        with self.conn:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO injections(technician_id, vaccine_id, dose_no, last_dose_date, validity_months,
                                       next_due_date, certificate_path, status, notes, created_at, updated_at)
                VALUES(:technician_id,:vaccine_id,:dose_no,:last_dose_date,:validity_months,
                       :next_due_date,:certificate_path,:status,:notes,:created_at,:updated_at)
                """,
                dict(data, next_due_date=next_due, status=status, created_at=now, updated_at=now)
            )
            return cur.lastrowid

    def update_injection(self, iid: int, data: Dict[str, Any]):
        now = today_str()
        row = self.get_injection(iid)
        if not row:
            return
        merged = dict(row)
        merged.update(data)
        next_due = compute_next_due(merged.get("last_dose_date"), int(merged.get("validity_months") or 0))
        settings = self.get_settings()
        reminder_days = int(settings["reminder_days"] or DEFAULT_REMINDER_DAYS)
        status = self._compute_status(next_due, reminder_days)
        update_data = dict(data)
        update_data.update({"next_due_date": next_due, "status": status})
        keys = ["technician_id","vaccine_id","dose_no","last_dose_date","validity_months",
                "next_due_date","certificate_path","status","notes"]
        with self.conn:
            self.conn.execute(
                f"UPDATE injections SET {', '.join([k+'=:'+k for k in keys])}, updated_at=:updated_at WHERE id=:id",
                dict({k: update_data.get(k, row[k]) for k in keys}, updated_at=now, id=iid)
            )

    def get_injection(self, iid: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM injections WHERE id=?", (iid,)).fetchone()

    def list_injections(self,
                        vaccine_id: Optional[int] = None,
                        status: Optional[str] = None,
                        search: str = "") -> List[sqlite3.Row]:
        q = (
            "SELECT i.*, t.first_name, t.last_name, t.email, t.service, v.name AS vaccine_name, v.code AS vaccine_code "
            "FROM injections i "
            "JOIN technicians t ON t.id = i.technician_id "
            "JOIN vaccines v ON v.id = i.vaccine_id WHERE 1=1"
        )
        params: List[Any] = []
        if vaccine_id:
            q += " AND i.vaccine_id=?"; params.append(vaccine_id)
        if status and status != "Tous":
            q += " AND i.status=?"; params.append(status)
        if search.strip():
            like = f"%{search.strip()}%"
            q += " AND (t.first_name LIKE ? OR t.last_name LIKE ? OR t.email LIKE ? OR t.service LIKE ? OR v.name LIKE ? OR v.code LIKE ?)"
            params += [like, like, like, like, like, like]
        q += (
            " ORDER BY CASE i.status WHEN 'Expiré' THEN 3 WHEN 'Bientôt dû' THEN 2 WHEN 'OK' THEN 1 ELSE 0 END DESC,"
            " i.next_due_date ASC, t.last_name ASC, t.first_name ASC"
        )
        return list(self.conn.execute(q, params))

    def recompute_all_statuses(self):
        settings = self.get_settings()
        reminder_days = int(settings["reminder_days"] or DEFAULT_REMINDER_DAYS)
        rows = self.conn.execute("SELECT id, last_dose_date, validity_months FROM injections").fetchall()
        with self.conn:
            for r in rows:
                next_due = compute_next_due(r["last_dose_date"], int(r["validity_months"] or 0))
                status = self._compute_status(next_due, reminder_days)
                self.conn.execute(
                    "UPDATE injections SET next_due_date=?, status=?, updated_at=? WHERE id=?",
                    (next_due, status, today_str(), r["id"])
                )

    # ---------------- Due selection ----------------
    def select_due_items(self) -> List[sqlite3.Row]:
        settings = self.get_settings()
        reminder_days = int(settings["reminder_days"] or DEFAULT_REMINDER_DAYS)
        max_date = (datetime.now() + timedelta(days=reminder_days)).strftime(DATE_FMT)
        q = (
            "SELECT i.*, t.first_name, t.last_name, t.email, t.service, v.name AS vaccine_name, v.code AS vaccine_code "
            "FROM injections i "
            "JOIN technicians t ON t.id = i.technician_id "
            "JOIN vaccines v ON v.id = i.vaccine_id "
            "WHERE i.next_due_date IS NOT NULL AND i.next_due_date <= ?"
        )
        return list(self.conn.execute(q, (max_date,)))

    # ---------------- Export ----------------
    def export_injections_csv(self, path: str, rows: Optional[List[sqlite3.Row]] = None):
        if rows is None:
            rows = self.list_injections()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([
                "id","tech_first_name","tech_last_name","email","service",
                "vaccine","dose_no","last_dose_date","validity_months","next_due_date","status","certificate_path","notes"
            ])
            for r in rows:
                w.writerow([
                    r["id"], r["first_name"], r["last_name"], r["email"], r["service"],
                    r["vaccine_name"], r["dose_no"], r["last_dose_date"], r["validity_months"], r["next_due_date"], r["status"], r["certificate_path"],
                    (r["notes"] or "").replace("\n", " ")
                ])


# --------------------------- Dialogues ---------------------------

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Paramètres & Emails")
        self.resize(640, 420)

        form = QtWidgets.QFormLayout(self)
        s = self.db.get_settings()

        self.ed_secretary = QtWidgets.QLineEdit(s["secretary_email"] or "")
        self.ed_cc = QtWidgets.QLineEdit(s["cc_emails"] or "")
        self.ed_host = QtWidgets.QLineEdit(s["smtp_host"] or "")
        self.sp_port = QtWidgets.QSpinBox(); self.sp_port.setRange(1, 65535); self.sp_port.setValue(int(s["smtp_port"] or 587))
        self.ed_user = QtWidgets.QLineEdit(s["smtp_user"] or "")
        self.ed_pass = QtWidgets.QLineEdit(); self.ed_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        if s["smtp_password_b64"]:
            try:
                self.ed_pass.setText(base64.b64decode(s["smtp_password_b64"]).decode("utf-8"))
            except Exception:
                pass
        self.cb_tls = QtWidgets.QCheckBox("TLS")
        self.cb_ssl = QtWidgets.QCheckBox("SSL")
        self.cb_tls.setChecked(bool(int(s["use_tls"] or 0)))
        self.cb_ssl.setChecked(bool(int(s["use_ssl"] or 0)))
        self.sp_remind = QtWidgets.QSpinBox(); self.sp_remind.setRange(1, 365); self.sp_remind.setValue(int(s["reminder_days"] or DEFAULT_REMINDER_DAYS))

        # Rendre TLS/SSL mutuellement exclusifs
        def toggle_exclusive():
            if self.sender() is self.cb_tls and self.cb_tls.isChecked():
                self.cb_ssl.setChecked(False)
            elif self.sender() is self.cb_ssl and self.cb_ssl.isChecked():
                self.cb_tls.setChecked(False)
        self.cb_tls.clicked.connect(toggle_exclusive)
        self.cb_ssl.clicked.connect(toggle_exclusive)

        form.addRow("Email secrétaire", self.ed_secretary)
        form.addRow("CC (séparés par ;)", self.ed_cc)
        form.addRow("SMTP Host", self.ed_host)
        form.addRow("SMTP Port", self.sp_port)
        form.addRow("SMTP User", self.ed_user)
        form.addRow("SMTP Password", self.ed_pass)
        row = QtWidgets.QWidget(); hl = QtWidgets.QHBoxLayout(row); hl.setContentsMargins(0,0,0,0)
        hl.addWidget(self.cb_tls); hl.addWidget(self.cb_ssl); hl.addStretch(1)
        form.addRow("Sécurité", row)
        form.addRow("Jours d'avertissement", self.sp_remind)

        btns = QtWidgets.QHBoxLayout()
        b_test = QtWidgets.QPushButton("Envoyer un email de test")
        b_test.clicked.connect(self.on_test)
        b_save = QtWidgets.QPushButton("Enregistrer")
        b_save.clicked.connect(self.accept)
        b_cancel = QtWidgets.QPushButton("Annuler")
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_test); btns.addStretch(1); btns.addWidget(b_save); btns.addWidget(b_cancel)
        form.addRow(btns)

    def on_test(self):
        self._save_temp()
        try:
            send_test_email(self.db)
            QtWidgets.QMessageBox.information(self, "Test", "Email de test envoyé (consultez votre boîte).")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Test", f"Échec de l'envoi : {e}")

    def _save_temp(self):
        data = self.data()
        self.db.update_settings(data)

    def data(self) -> Dict[str, Any]:
        pwd_b64 = base64.b64encode(self.ed_pass.text().encode("utf-8")).decode("ascii") if self.ed_pass.text() else ""
        return {
            "secretary_email": self.ed_secretary.text().strip(),
            "cc_emails": self.ed_cc.text().strip(),
            "smtp_host": self.ed_host.text().strip(),
            "smtp_port": int(self.sp_port.value()),
            "smtp_user": self.ed_user.text().strip(),
            "smtp_password_b64": pwd_b64,
            "use_tls": 1 if self.cb_tls.isChecked() else 0,
            "use_ssl": 1 if self.cb_ssl.isChecked() else 0,
            "reminder_days": int(self.sp_remind.value()),
        }


class TechnicianDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, preset: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("Technicien")
        self.resize(560, 380)
        self.preset = preset or {}

        form = QtWidgets.QFormLayout(self)
        self.first_name = QtWidgets.QLineEdit(self.preset.get("first_name", ""))
        self.last_name = QtWidgets.QLineEdit(self.preset.get("last_name", ""))
        self.email = QtWidgets.QLineEdit(self.preset.get("email", ""))
        self.service = QtWidgets.QLineEdit(self.preset.get("service", ""))
        self.role = QtWidgets.QLineEdit(self.preset.get("role", ""))
        self.phone = QtWidgets.QLineEdit(self.preset.get("phone", ""))
        self.notes = QtWidgets.QPlainTextEdit(self.preset.get("notes", ""))

        form.addRow("Prénom", self.first_name)
        form.addRow("Nom", self.last_name)
        form.addRow("Email", self.email)
        form.addRow("Service", self.service)
        form.addRow("Rôle", self.role)
        form.addRow("Téléphone", self.phone)
        form.addRow("Notes", self.notes)

        btns = QtWidgets.QHBoxLayout()
        b_ok = QtWidgets.QPushButton("Enregistrer"); b_ok.clicked.connect(self.accept)
        b_cancel = QtWidgets.QPushButton("Annuler"); b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

    def data(self) -> Dict[str, Any]:
        return {
            "first_name": self.first_name.text().strip(),
            "last_name": self.last_name.text().strip(),
            "email": self.email.text().strip(),
            "service": self.service.text().strip(),
            "role": self.role.text().strip(),
            "phone": self.phone.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class VaccineDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, preset: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("Vaccin")
        self.resize(560, 320)
        self.preset = preset or {}

        form = QtWidgets.QFormLayout(self)
        self.name = QtWidgets.QLineEdit(self.preset.get("name", ""))
        self.code = QtWidgets.QLineEdit(self.preset.get("code", ""))
        self.validity = QtWidgets.QSpinBox(); self.validity.setRange(0, 600); self.validity.setValue(int(self.preset.get("validity_months") or 12))
        self.remind = QtWidgets.QSpinBox(); self.remind.setRange(1, 365); self.remind.setValue(int(self.preset.get("default_reminder_days") or DEFAULT_REMINDER_DAYS))
        self.notes = QtWidgets.QPlainTextEdit(self.preset.get("notes", ""))

        form.addRow("Nom", self.name)
        form.addRow("Code", self.code)
        form.addRow("Validité (mois)", self.validity)
        form.addRow("Alerte par défaut (jours)", self.remind)
        form.addRow("Notes", self.notes)

        btns = QtWidgets.QHBoxLayout()
        b_ok = QtWidgets.QPushButton("Enregistrer"); b_ok.clicked.connect(self.accept)
        b_cancel = QtWidgets.QPushButton("Annuler"); b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

    def data(self) -> Dict[str, Any]:
        return {
            "name": self.name.text().strip(),
            "code": self.code.text().strip(),
            "validity_months": int(self.validity.value()),
            "default_reminder_days": int(self.remind.value()),
            "notes": self.notes.toPlainText().strip(),
        }


class InjectionDialog(QtWidgets.QDialog):
    def __init__(self, db: DB, technician_id: Optional[int] = None, preset: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.technician_id = technician_id
        self.preset = preset or {}
        self.setWindowTitle("Injection")
        self.resize(620, 420)

        form = QtWidgets.QFormLayout(self)

        # Choix du technicien et vaccin
        self.cb_tech = QtWidgets.QComboBox()
        self._tech_map: List[Tuple[str,int]] = []
        for t in self.db.list_technicians():
            label = f"{t['last_name']} {t['first_name']}".strip()
            self.cb_tech.addItem(label, t['id'])
            self._tech_map.append((label, t['id']))
        if self.technician_id:
            idx = self.cb_tech.findData(self.technician_id)
            if idx >= 0:
                self.cb_tech.setCurrentIndex(idx)

        self.cb_vac = QtWidgets.QComboBox()
        self._vac_map: Dict[int, sqlite3.Row] = {}
        for v in self.db.list_vaccines():
            label = f"{v['name']} ({v['code']})" if v['code'] else v['name']
            self.cb_vac.addItem(label, v['id'])
            self._vac_map[v['id']] = v

        self.sp_dose = QtWidgets.QSpinBox(); self.sp_dose.setRange(1, 20); self.sp_dose.setValue(int(self.preset.get("dose_no") or 1))
        self.ed_last = QtWidgets.QDateEdit(calendarPopup=True); self.ed_last.setDisplayFormat("yyyy-MM-dd")
        if self.preset.get("last_dose_date"):
            self.ed_last.setDate(QtCore.QDate.fromString(self.preset["last_dose_date"], "yyyy-MM-dd"))
        else:
            self.ed_last.setDate(QtCore.QDate.currentDate())

        self.sp_valid = QtWidgets.QSpinBox(); self.sp_valid.setRange(0, 600)
        self.sp_valid.setToolTip("0 = utiliser la validité du vaccin")
        self.sp_valid.setValue(int(self.preset.get("validity_months") or 0))

        self.ed_cert = QtWidgets.QLineEdit(self.preset.get("certificate_path", ""))
        btn_cert = QtWidgets.QPushButton("Joindre certificat…")
        btn_cert.clicked.connect(self._choose_cert)

        self.notes = QtWidgets.QPlainTextEdit(self.preset.get("notes", ""))

        form.addRow("Technicien", self.cb_tech)
        form.addRow("Vaccin", self.cb_vac)
        form.addRow("Dose n°", self.sp_dose)
        form.addRow("Date dernière dose", self.ed_last)
        form.addRow("Validité (mois)", self.sp_valid)
        row = QtWidgets.QWidget(); hl = QtWidgets.QHBoxLayout(row); hl.setContentsMargins(0,0,0,0)
        hl.addWidget(self.ed_cert); hl.addWidget(btn_cert)
        form.addRow("Certificat (PDF)", row)
        form.addRow("Notes", self.notes)

        btns = QtWidgets.QHBoxLayout()
        b_ok = QtWidgets.QPushButton("Enregistrer"); b_ok.clicked.connect(self.accept)
        b_cancel = QtWidgets.QPushButton("Annuler"); b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

        # Autofill validité en fonction du vaccin si 0
        def on_vac_changed():
            vid = self.cb_vac.currentData()
            v = self._vac_map.get(vid)
            if v and self.sp_valid.value() == 0:
                self.sp_valid.setToolTip(f"0 = {v['validity_months']} mois (vaccin)")
        self.cb_vac.currentIndexChanged.connect(on_vac_changed)
        on_vac_changed()

    def _choose_cert(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choisir le certificat (PDF)", "", "PDF (*.pdf);;Tous (*.*)")
        if path:
            self.ed_cert.setText(path)

    def data(self) -> Dict[str, Any]:
        return {
            "technician_id": int(self.cb_tech.currentData()),
            "vaccine_id": int(self.cb_vac.currentData()),
            "dose_no": int(self.sp_dose.value()),
            "last_dose_date": self.ed_last.date().toString("yyyy-MM-dd"),
            "validity_months": int(self.sp_valid.value()),
            "certificate_path": self.ed_cert.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class ImportDialog(QtWidgets.QDialog):
    """Assistant d'import Excel avec mappage de colonnes."""
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Importer depuis Excel")
        self.resize(820, 520)
        self.df: Optional[pd.DataFrame] = None

        lay = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.ed_path = QtWidgets.QLineEdit()
        btn_browse = QtWidgets.QPushButton("Parcourir…")
        btn_browse.clicked.connect(self._browse)
        top.addWidget(self.ed_path, 1); top.addWidget(btn_browse)
        lay.addLayout(top)

        self.lbl_info = QtWidgets.QLabel("Sélectionnez un fichier .xlsx/.xls.")
        self.lbl_info.setStyleSheet("color:#555")
        lay.addWidget(self.lbl_info)

        # Zone de mappage
        grid = QtWidgets.QGridLayout()
        self.cb_name = QtWidgets.QComboBox()
        self.cb_email = QtWidgets.QComboBox()
        self.cb_service = QtWidgets.QComboBox()
        self.cb_vaccine = QtWidgets.QComboBox()
        self.cb_last = QtWidgets.QComboBox()
        self.cb_valid = QtWidgets.QComboBox()
        self.cb_dose = QtWidgets.QComboBox()
        self.cb_cert = QtWidgets.QComboBox()

        for i, (label, cb) in enumerate([
            ("Nom complet", self.cb_name),
            ("Email", self.cb_email),
            ("Service", self.cb_service),
            ("Vaccin", self.cb_vaccine),
            ("Date dernière dose", self.cb_last),
            ("Validité (mois)", self.cb_valid),
            ("Dose n°", self.cb_dose),
            ("Certificat (chemin)", self.cb_cert),
        ]):
            grid.addWidget(QtWidgets.QLabel(label), i, 0)
            grid.addWidget(cb, i, 1)
        lay.addLayout(grid)

        self.date_fmt = QtWidgets.QLineEdit("%Y-%m-%d")
        lay.addWidget(QtWidgets.QLabel("Format de date (ex: %Y-%m-%d, %d/%m/%Y, etc.)"))
        lay.addWidget(self.date_fmt)

        btns = QtWidgets.QHBoxLayout()
        b_import = QtWidgets.QPushButton("Importer")
        b_import.clicked.connect(self.on_import)
        b_cancel = QtWidgets.QPushButton("Annuler")
        b_cancel.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(b_import); btns.addWidget(b_cancel)
        lay.addLayout(btns)

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choisir un fichier Excel", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        self.ed_path.setText(path)
        try:
            df, engine = read_excel_any(path)
            self.df = df
            cols = [str(c) for c in df.columns]
            for cb in [self.cb_name, self.cb_email, self.cb_service, self.cb_vaccine, self.cb_last, self.cb_valid, self.cb_dose, self.cb_cert]:
                cb.clear(); cb.addItem("— (ignorer)")
                cb.addItems(cols)
            self.lbl_info.setText(f"Colonnes détectées ({engine}) : {', '.join(cols[:10])}{' …' if len(cols)>10 else ''}")
        except Exception as e:
            self.lbl_info.setText(f"Erreur de lecture : {e}")
            self.df = None

    def on_import(self):
        if self.df is None:
            QtWidgets.QMessageBox.warning(self, "Import", "Veuillez sélectionner un fichier valide.")
            return
        fmt = self.date_fmt.text().strip() or "%Y-%m-%d"
        name_col = self.cb_name.currentText() if self.cb_name.currentIndex()>0 else None
        vac_col = self.cb_vaccine.currentText() if self.cb_vaccine.currentIndex()>0 else None
        last_col = self.cb_last.currentText() if self.cb_last.currentIndex()>0 else None
        valid_col = self.cb_valid.currentText() if self.cb_valid.currentIndex()>0 else None
        dose_col = self.cb_dose.currentText() if self.cb_dose.currentIndex()>0 else None
        email_col = self.cb_email.currentText() if self.cb_email.currentIndex()>0 else None
        svc_col = self.cb_service.currentText() if self.cb_service.currentIndex()>0 else None
        cert_col = self.cb_cert.currentText() if self.cb_cert.currentIndex()>0 else None

        if not (name_col and vac_col and last_col):
            QtWidgets.QMessageBox.warning(self, "Import", "Au minimum : Nom, Vaccin, Date dernière dose.")
            return

        count = 0
        for _, row in self.df.iterrows():
            try:
                name = str(row[name_col]).strip()
                if not name or name.lower() in {"nan","none"}:
                    continue
                first, last = split_name(name)
                email = (str(row[email_col]).strip() if email_col else "") or ""
                svc = (str(row[svc_col]).strip() if svc_col else "") or ""
                tech = find_or_create_technician(self.db, first, last, email=email, service=svc)

                vac_name = str(row[vac_col]).strip()
                vac = find_or_create_vaccine(self.db, vac_name)

                last_date = parse_any_date(str(row[last_col]).strip(), fmt)
                valid_months = safe_int(row.get(valid_col)) if valid_col else vac["validity_months"] or 0
                dose_no = safe_int(row.get(dose_col)) if dose_col else 1
                cert = str(row[cert_col]).strip() if cert_col else ""

                self.db.add_injection({
                    "technician_id": tech["id"],
                    "vaccine_id": vac["id"],
                    "dose_no": dose_no or 1,
                    "last_dose_date": last_date,
                    "validity_months": valid_months or vac["validity_months"] or 0,
                    "certificate_path": cert,
                    "notes": "(import)",
                })
                count += 1
            except Exception:
                # on ignore la ligne problématique
                continue
        QtWidgets.QMessageBox.information(self, "Import", f"Import terminé : {count} enregistrements ajoutés.")
        self.accept()


# --------------------------- Fenêtre principale ---------------------------

class VaccinsWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestion des Vaccinations")
        self.resize(1280, 760)
        self.db = DB()

        # --- Barre supérieure (filtres & actions) ---
        top = QtWidgets.QWidget(); tl = QtWidgets.QHBoxLayout(top)
        self.cb_vaccine = QtWidgets.QComboBox(); self.cb_vaccine.addItem("Tous", None)
        for v in self.db.list_vaccines():
            self.cb_vaccine.addItem(v["name"], v["id"])
        self.cb_status = QtWidgets.QComboBox(); self.cb_status.addItems(["Tous", "OK", "Bientôt dû", "Expiré"])
        self.search = QtWidgets.QLineEdit(); self.search.setPlaceholderText("Recherche (nom/email/service/vaccin)…")
        b_newtech = QtWidgets.QPushButton("Nouveau technicien…"); b_newtech.clicked.connect(self.on_new_technician)
        b_newvac = QtWidgets.QPushButton("Nouveau vaccin…"); b_newvac.clicked.connect(self.on_new_vaccine)
        b_newinj = QtWidgets.QPushButton("Nouvelle injection…"); b_newinj.clicked.connect(self.on_new_injection)
        b_import = QtWidgets.QPushButton("Importer Excel…"); b_import.clicked.connect(self.on_import)
        b_export = QtWidgets.QPushButton("Export CSV"); b_export.clicked.connect(self.on_export)
        b_settings = QtWidgets.QPushButton("Paramètres…"); b_settings.clicked.connect(self.on_settings)
        b_refresh = QtWidgets.QPushButton("↻"); b_refresh.clicked.connect(self.reload)

        for w in [QtWidgets.QLabel("Vaccin"), self.cb_vaccine, QtWidgets.QLabel("Statut"), self.cb_status, self.search,
                  b_newtech, b_newvac, b_newinj, b_import, b_export, b_settings, b_refresh]:
            tl.addWidget(w)
        self.cb_vaccine.currentIndexChanged.connect(self.reload)
        self.cb_status.currentTextChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)

        # --- Résumés de statut ---
        chips = QtWidgets.QWidget(); cl = QtWidgets.QHBoxLayout(chips); cl.setContentsMargins(0,0,0,0)
        self.chip_ok = QtWidgets.QLabel(); self._style_chip(self.chip_ok, "OK")
        self.chip_due = QtWidgets.QLabel(); self._style_chip(self.chip_due, "Bientôt dû")
        self.chip_exp = QtWidgets.QLabel(); self._style_chip(self.chip_exp, "Expiré")
        cl.addWidget(self.chip_ok); cl.addWidget(self.chip_due); cl.addWidget(self.chip_exp); cl.addStretch(1)

        # --- Table principale ---
        self.table = QtWidgets.QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Statut", "Nom", "Service", "Email", "Vaccin", "Dose",
            "Dernière dose", "Prochaine échéance", "Jours restants", "Certificat", "Notes"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        # --- Panneau de droite : détails & actions ---
        right = QtWidgets.QGroupBox("Détails")
        rf = QtWidgets.QFormLayout(right)
        self.det_status = QtWidgets.QLabel("—")
        self.det_person = QtWidgets.QLabel("—")
        self.det_vaccine = QtWidgets.QLabel("—")
        self.det_last = QtWidgets.QLabel("—")
        self.det_next = QtWidgets.QLabel("—")
        self.det_notes = QtWidgets.QPlainTextEdit(); self.det_notes.setReadOnly(True)
        self.btn_open_cert = QtWidgets.QPushButton("Ouvrir certificat")
        self.btn_open_cert.clicked.connect(self.on_open_cert)
        self.btn_send_now = QtWidgets.QPushButton("Envoyer rappels maintenant")
        self.btn_send_now.clicked.connect(self.on_send_reminders)

        rf.addRow("Statut", self.det_status)
        rf.addRow("Technicien", self.det_person)
        rf.addRow("Vaccin", self.det_vaccine)
        rf.addRow("Dernière dose", self.det_last)
        rf.addRow("Prochaine échéance", self.det_next)
        rf.addRow("Notes", self.det_notes)
        rf.addRow(self.btn_open_cert)
        rf.addRow(self.btn_send_now)

        # --- Guide ---
        guide = QtWidgets.QGroupBox("Guide d'usage")
        gl = QtWidgets.QVBoxLayout(guide)
        gtxt = QtWidgets.QLabel(
            "• Filtrez par vaccin/statut, recherchez par nom/email/service.\n"
            "• Ajoutez techniciens, vaccins, et enregistrez les injections.\n"
            "• Les statuts et échéances sont calculés automatiquement.\n"
            "• Configurez l'email de la secrétaire et le SMTP via Paramètres.\n"
            "• 'Envoyer rappels maintenant' envoie un email récapitulatif des items arrivant à échéance."
        )
        gtxt.setWordWrap(True); gl.addWidget(gtxt)

        # --- Layout central avec splitter ---
        center = QtWidgets.QWidget(); main_v = QtWidgets.QVBoxLayout(center)
        main_v.addWidget(top)
        main_v.addWidget(chips)
        split = QtWidgets.QSplitter()
        split.setOrientation(QtCore.Qt.Horizontal)
        leftw = QtWidgets.QWidget(); lv = QtWidgets.QVBoxLayout(leftw); lv.addWidget(self.table, 1); lv.addWidget(guide)
        split.addWidget(leftw)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        main_v.addWidget(split, 1)
        self.setCentralWidget(center)

        self.table.itemSelectionChanged.connect(self._on_sel_change)

        # Timer de vérification périodique (toutes les 6h)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._periodic_check)
        self.timer.start(6 * 60 * 60 * 1000)

        # Initial load
        self.db.recompute_all_statuses()
        self.reload()
        # Vérification immédiate au démarrage (sans envoi auto)
        self._update_chips()

    # --- Helpers UI ---
    def _style_chip(self, lbl: QtWidgets.QLabel, text: str):
        col = STATUS_COLORS.get(text, "#777")
        lbl.setText(f"{text}: 0")
        lbl.setStyleSheet(f"QLabel {{ background:{col}; color:white; padding:2px 8px; border-radius:10px; }}")

    def _set_pill(self, label: QtWidgets.QLabel, status: Optional[str]):
        if not status:
            label.setText("—")
            label.setStyleSheet("QLabel { background:#999; color:white; padding:4px 8px; border-radius:10px; }")
            return
        color = STATUS_COLORS.get(status, "#17a2b8")
        label.setText(status)
        label.setStyleSheet(f"QLabel {{ background:{color}; color:white; padding:4px 8px; border-radius:10px; }}")

    def _selected_id(self) -> Optional[int]:
        sel = self.table.selectedItems()
        if not sel:
            return None
        row = sel[0].row()
        try:
            return int(self.table.item(row, 0).text())
        except Exception:
            return None

    def _load_row(self, r: sqlite3.Row):
        row = self.table.rowCount()
        self.table.insertRow(row)
        days = days_until(r["next_due_date"]) if r["next_due_date"] else None
        vals = [
            str(r["id"]), r["status"] or "", f"{r['last_name']} {r['first_name']}", r["service"] or "",
            r["email"] or "", r["vaccine_name"], str(r["dose_no"] or 1), r["last_dose_date"] or "",
            r["next_due_date"] or "", ("" if days is None else str(days)), r["certificate_path"] or "", r["notes"] or ""
        ]
        for c, v in enumerate(vals):
            item = QtWidgets.QTableWidgetItem(v)
            if c == 1 and v:
                col = STATUS_COLORS.get(v)
                if col:
                    item.setBackground(QtGui.QColor(col))
                    item.setForeground(QtGui.QColor("#ffffff"))
            self.table.setItem(row, c, item)

    def _update_chips(self):
        counts = {"OK":0, "Bientôt dû":0, "Expiré":0}
        rows = self.db.list_injections(self.cb_vaccine.currentData(), self.cb_status.currentText(), self.search.text())
        for r in rows:
            s = r["status"] or "OK"
            if s in counts:
                counts[s] += 1
        self.chip_ok.setText(f"OK: {counts['OK']}")
        self.chip_due.setText(f"Bientôt dû: {counts['Bientôt dû']}")
        self.chip_exp.setText(f"Expiré: {counts['Expiré']}")

    # --- Actions
    def reload(self):
        self.table.setRowCount(0)
        rows = self.db.list_injections(self.cb_vaccine.currentData(), self.cb_status.currentText(), self.search.text())
        for r in rows:
            self._load_row(r)
        self._update_chips()
        self._on_sel_change()

    def on_new_technician(self):
        dlg = TechnicianDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.add_technician(dlg.data())
            QtWidgets.QMessageBox.information(self, "Technicien", "Créé.")
            self.reload()

    def on_new_vaccine(self):
        dlg = VaccineDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.add_vaccine(dlg.data())
            QtWidgets.QMessageBox.information(self, "Vaccin", "Créé.")
            # Recharger la liste de filtres vaccin
            self.cb_vaccine.clear(); self.cb_vaccine.addItem("Tous", None)
            for v in self.db.list_vaccines():
                self.cb_vaccine.addItem(v["name"], v["id"])
            self.reload()

    def on_new_injection(self):
        dlg = InjectionDialog(self.db, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.add_injection(dlg.data())
            QtWidgets.QMessageBox.information(self, "Injection", "Enregistrée.")
            self.reload()

    def on_import(self):
        dlg = ImportDialog(self.db, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.reload()

    def on_export(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exporter en CSV", "vaccins.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self.db.list_injections(self.cb_vaccine.currentData(), self.cb_status.currentText(), self.search.text())
        self.db.export_injections_csv(path, rows)
        QtWidgets.QMessageBox.information(self, "Export", f"Exporté : {path}")

    def on_settings(self):
        dlg = SettingsDialog(self.db, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.update_settings(dlg.data())
            QtWidgets.QMessageBox.information(self, "Paramètres", "Enregistrés.")
            self.db.recompute_all_statuses()
            self.reload()

    def on_open_cert(self):
        iid = self._selected_id()
        if not iid:
            QtWidgets.QMessageBox.information(self, "Certificat", "Sélectionnez une ligne.")
            return
        row = self.db.get_injection(iid)
        if not row:
            return
        path = row["certificate_path"]
        if not path or not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Certificat", "Aucun fichier trouvé.")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def on_send_reminders(self):
        try:
            send_due_email(self.db)
            QtWidgets.QMessageBox.information(self, "Rappels", "Email de rappel envoyé.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Rappels", f"Échec : {e}")

    def _on_double_click(self, *_):
        # Double‑clic -> éditer l'injection
        iid = self._selected_id()
        if not iid:
            return
        row = self.db.get_injection(iid)
        if not row:
            return
        preset = {k: row[k] for k in row.keys()}
        dlg = InjectionDialog(self.db, technician_id=row["technician_id"], preset=preset, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.update_injection(iid, dlg.data())
            QtWidgets.QMessageBox.information(self, "Injection", "Mise à jour.")
            self.reload()

    def _on_sel_change(self):
        iid = self._selected_id()
        if not iid:
            self._fill_details(None)
            return
        row = self.db.get_injection(iid)
        self._fill_details(row)

    def _fill_details(self, r: Optional[sqlite3.Row]):
        if not r:
            self._set_pill(self.det_status, None)
            self.det_person.setText("—")
            self.det_vaccine.setText("—")
            self.det_last.setText("—")
            self.det_next.setText("—")
            self.det_notes.setPlainText("")
            return
        tech = self.db.get_technician(r["technician_id"]) if r else None
        vac = self.db.get_vaccine(r["vaccine_id"]) if r else None
        self._set_pill(self.det_status, r["status"])
        self.det_person.setText(f"{tech['last_name']} {tech['first_name']} – {tech['email']} – {tech['service']}")
        self.det_vaccine.setText(f"{vac['name']} ({vac['code']})  •  Dose {r['dose_no']}")
        self.det_last.setText(r["last_dose_date"] or "—")
        self.det_next.setText(r["next_due_date"] or "—")
        self.det_notes.setPlainText(r["notes"] or "")

    def _periodic_check(self):
        # Recalcul + pas d'envoi auto ici (préférez le bouton manuel).
        self.db.recompute_all_statuses()
        self.reload()


# --------------------------- Email ---------------------------

def _smtp_context(use_ssl: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def _get_settings(db: DB) -> Dict[str, Any]:
    s = db.get_settings()
    pwd = base64.b64decode(s["smtp_password_b64"]).decode("utf-8") if s["smtp_password_b64"] else ""
    return {
        "to": (s["secretary_email"] or "").strip(),
        "cc": [e.strip() for e in (s["cc_emails"] or "").split(";") if e.strip()],
        "host": (s["smtp_host"] or "").strip(),
        "port": int(s["smtp_port"] or 0),
        "user": (s["smtp_user"] or "").strip(),
        "password": pwd,
        "use_tls": bool(int(s["use_tls"] or 0)),
        "use_ssl": bool(int(s["use_ssl"] or 0)),
    }


def send_test_email(db: DB):
    cfg = _get_settings(db)
    if not cfg["to"]:
        raise RuntimeError("Renseignez l'email de la secrétaire dans Paramètres.")
    msg = EmailMessage()
    msg["Subject"] = "[TEST] Vaccinations – configuration SMTP"
    msg["From"] = cfg["user"] or cfg["to"]
    msg["To"] = cfg["to"]
    if cfg["cc"]:
        msg["Cc"] = ", ".join(cfg["cc"]) 
    msg.set_content("Ceci est un email de test envoyé par l'application de gestion des vaccinations.")
    _smtp_send(cfg, msg)


def build_due_email_body(rows: List[sqlite3.Row], reminder_days: int) -> str:
    if not rows:
        return (
            "Bonjour,\n\n"
            "Aucun rappel de vaccination à envoyer aujourd'hui.\n\n"
            "Cordialement."
        )
    lines = [
        "Bonjour,\n",
        f"Vous trouverez ci-dessous les vaccinations à échéance dans les {reminder_days} prochains jours (et expirées).\n",
        "\n",
        "Technicien;Service;Email;Vaccin;Dose;Dernière dose;Prochaine échéance;Jours restants;Statut",
    ]
    for r in rows:
        dd = days_until(r["next_due_date"]) if r["next_due_date"] else None
        lines.append(";".join([
            f"{r['last_name']} {r['first_name']}", r["service"] or "", r["email"] or "",
            r["vaccine_name"], str(r["dose_no"] or 1), r["last_dose_date"] or "",
            r["next_due_date"] or "", ("" if dd is None else str(dd)), r["status"] or ""
        ]))
    lines.append("\nCordialement,")
    return "\n".join(lines)


def send_due_email(db: DB):
    cfg = _get_settings(db)
    if not cfg["to"]:
        raise RuntimeError("Renseignez l'email de la secrétaire dans Paramètres.")
    due = db.select_due_items()
    s = db.get_settings()
    reminder_days = int(s["reminder_days"] or DEFAULT_REMINDER_DAYS)
    body = build_due_email_body(due, reminder_days)

    msg = EmailMessage()
    msg["Subject"] = f"Rappels vaccinations – {today_str()}"
    msg["From"] = cfg["user"] or cfg["to"]
    msg["To"] = cfg["to"]
    if cfg["cc"]:
        msg["Cc"] = ", ".join(cfg["cc"]) 
    msg.set_content(body)

    # Joindre un CSV des items à échéance
    csv_data = [
        ["Technicien","Service","Email","Vaccin","Dose","Dernière dose","Prochaine échéance","Jours restants","Statut"]
    ]
    for r in due:
        dd = days_until(r["next_due_date"]) if r["next_due_date"] else None
        csv_data.append([
            f"{r['last_name']} {r['first_name']}", r["service"] or "", r["email"] or "",
            r["vaccine_name"], str(r["dose_no"] or 1), r["last_dose_date"] or "",
            r["next_due_date"] or "", ("" if dd is None else str(dd)), r["status"] or ""
        ])
    csv_bytes = "\n".join([";".join(map(str, row)) for row in csv_data]).encode("utf-8")
    msg.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=f"rappels_vaccins_{today_str()}.csv")

    _smtp_send(cfg, msg)


def _smtp_send(cfg: Dict[str, Any], msg: EmailMessage):
    if cfg["use_ssl"]:
        context = _smtp_context(True)
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context) as s:
            if cfg["user"] and cfg["password"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            s.ehlo()
            if cfg["use_tls"]:
                s.starttls(context=_smtp_context(False))
            if cfg["user"] and cfg["password"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


# --------------------------- Helpers import ---------------------------

def read_excel_any(path: str) -> Tuple[pd.DataFrame, str]:
    ext = os.path.splitext(path.lower())[1]
    if ext == ".xlsx":
        df = pd.read_excel(path, engine="openpyxl")
        return df, "openpyxl"
    if ext == ".xls":
        # xlrd >=2 ne supporte plus .xls – installer xlrd==1.2.0
        df = pd.read_excel(path, engine="xlrd")
        return df, "xlrd"
    # fallback : laisser pandas décider
    df = pd.read_excel(path)
    return df, "auto"


def parse_any_date(s: str, fmt: str) -> str:
    s = (s or "").strip()
    if not s or s.lower() in {"nan","none","nat"}:
        return today_str()
    # Essayer d'abord le format utilisateur
    try:
        return datetime.strptime(s, fmt).strftime(DATE_FMT)
    except Exception:
        pass
    # Essayer via pandas
    try:
        d = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(d):
            return today_str()
        return d.strftime(DATE_FMT)
    except Exception:
        return today_str()


def split_name(fullname: str) -> Tuple[str, str]:
    parts = [p for p in str(fullname).replace(",", " ").split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def safe_int(x: Any) -> Optional[int]:
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    try:
        return int(str(x).strip())
    except Exception:
        return None


def find_or_create_technician(db: DB, first: str, last: str, email: str = "", service: str = "") -> sqlite3.Row:
    row = db.conn.execute(
        "SELECT * FROM technicians WHERE lower(first_name)=? AND lower(last_name)=?",
        (first.lower(), last.lower())
    ).fetchone()
    if row:
        return row
    tid = db.add_technician({
        "first_name": first, "last_name": last, "email": email, "service": service, "role": "", "phone": "", "notes": "(import)"
    })
    return db.get_technician(tid)


def find_or_create_vaccine(db: DB, name: str) -> sqlite3.Row:
    row = db.conn.execute("SELECT * FROM vaccines WHERE lower(name)=?", (name.lower(),)).fetchone()
    if row:
        return row
    vid = db.add_vaccine({
        "name": name, "code": "", "validity_months": 12, "default_reminder_days": DEFAULT_REMINDER_DAYS, "notes": "(import)"
    })
    return db.get_vaccine(vid)


# --------------------------- Entrée d'appli ---------------------------

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Vaccins Manager")
    win = VaccinsWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
