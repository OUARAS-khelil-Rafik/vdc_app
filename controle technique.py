# controltech_matrix.py
# -*- coding: utf-8 -*-
"""
Rappels de Contrôle Technique – **Matrice** (QtPy + SQLite, 1 fichier)
But : remplacer l'Excel de la secrétaire par une UI matricielle,
avec rappels par e‑mail à la secrétaire **et** aux responsables.

Concept (analogue à la matrice vaccins → adapté « contrôle technique »)
---------------------------------------------------------------------
• Lignes = **Actifs** (véhicules/équipements) : Nom, Immatriculation, VIN, Site/Service,
  Responsable (nom + e‑mail)
• Colonnes = **Types de contrôle** (ex. Contrôle technique, Assurance, Entretien périodique,
  Extincteurs, Calibrations… — librement configurables)
• Cellule = pastille couleur + **prochaine échéance** et **J‑X** ; double‑clic pour
  enregistrer un contrôle (date, validité, pièce jointe, notes)
• Filtres adaptés à la matrice : Site/Service, Catégorie, Statut, Type de contrôle, Recherche,
  horizon d’alerte, « Colonnes avec rappels seulement »
• Import Excel **matriciel** (XLS/XLSX) : colonnes fixes + colonnes‑contrôles (détection auto),
  mode **Cellules = dernière intervention** (calc prochaine échéance) OU **Cellules = prochaine échéance**
• E‑mails : récap CSV à la **secrétaire** + e‑mail personnalisé par **responsable** listant ses actifs à échéance
• Mode batch (sans UI) : `python controltech_matrix.py --send-reminders`

Installation
------------
    pip install QtPy PyQt5 pandas openpyxl xlrd==1.2.0
    python controltech_matrix.py

Base de données : `controltech.db` (auto‑créée)
Tables : `settings`, `assets`, `check_types`, `checks`
"""
from __future__ import annotations
import os
import sys
import csv
import ssl
import json
import base64
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import smtplib
from email.message import EmailMessage

from qtpy import QtCore, QtGui, QtWidgets

# --------------------------- Constantes ---------------------------
DATE_FMT = "%Y-%m-%d"
STATUS_OK, STATUS_SOON, STATUS_EXPIRED = "OK", "Bientôt dû", "Expiré"
STATUS_COLORS = {STATUS_OK: "#28a745", STATUS_SOON: "#ffc107", STATUS_EXPIRED: "#dc3545"}
DEFAULT_REMINDER_DAYS = 30
DEFAULT_VALIDITY_MONTHS = 12

# --------------------------- Utils Dates -------------------------

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
        return add_months(d, int(validity_months)).strftime(DATE_FMT)
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

# --------------------------- DB Layer ----------------------------
class DB:
    def __init__(self, path: str = "controltech.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.initialize()

    def initialize(self):
        c = self.conn.cursor()
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
                mail_responsibles INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                plate TEXT,         -- immatriculation
                vin TEXT,
                category TEXT,      -- véhicule utilitaire, VL, machine, etc.
                site TEXT,          -- site / service
                responsible_name TEXT,
                responsible_email TEXT,
                phone TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS check_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                code TEXT,
                validity_months INTEGER,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                check_type_id INTEGER NOT NULL REFERENCES check_types(id) ON DELETE CASCADE,
                last_check_date TEXT,
                next_due_date TEXT,
                validity_months INTEGER,
                status TEXT,
                document_path TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Index
        c.execute("CREATE INDEX IF NOT EXISTS idx_checks_next ON checks(next_due_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_checks_stat ON checks(status)")
        self.conn.commit()
        # Settings default
        cur = self.conn.execute("SELECT 1 FROM settings WHERE id=1").fetchone()
        if not cur:
            now = today_str()
            self.conn.execute(
                """
                INSERT INTO settings(id, secretary_email, smtp_host, smtp_port, smtp_user, smtp_password_b64,
                                     use_tls, use_ssl, reminder_days, cc_emails, mail_responsibles, created_at, updated_at)
                VALUES(1, '', '', 587, '', '', 1, 0, ?, '', 1, ?, ?)
                """,
                (DEFAULT_REMINDER_DAYS, now, now)
            )
            self.conn.commit()

    # Settings
    def get_settings(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM settings WHERE id=1").fetchone()

    def update_settings(self, data: Dict[str, Any]):
        now = today_str()
        keys = [
            "secretary_email","smtp_host","smtp_port","smtp_user","smtp_password_b64",
            "use_tls","use_ssl","reminder_days","cc_emails","mail_responsibles"
        ]
        self.conn.execute(
            f"UPDATE settings SET {', '.join([k+'=:'+k for k in keys])}, updated_at=:updated_at WHERE id=1",
            dict({k: data.get(k) for k in keys}, updated_at=now)
        )
        self.conn.commit()

    # Assets
    def add_asset(self, data: Dict[str, Any]) -> int:
        now = today_str()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO assets(name,plate,vin,category,site,responsible_name,responsible_email,phone,notes,created_at,updated_at)
            VALUES(:name,:plate,:vin,:category,:site,:responsible_name,:responsible_email,:phone,:notes,:created_at,:updated_at)
            """,
            dict(data, created_at=now, updated_at=now)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_asset(self, aid: int, data: Dict[str, Any]):
        now = today_str()
        keys = ["name","plate","vin","category","site","responsible_name","responsible_email","phone","notes"]
        self.conn.execute(
            f"UPDATE assets SET {', '.join([k+'=:'+k for k in keys])}, updated_at=:updated_at WHERE id=:id",
            dict({k: data.get(k) for k in keys}, updated_at=now, id=aid)
        )
        self.conn.commit()

    def get_asset(self, aid: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()

    def list_sites(self) -> List[str]:
        rows = self.conn.execute("SELECT DISTINCT COALESCE(site,'') AS s FROM assets ORDER BY s").fetchall()
        return [r["s"] for r in rows if (r["s"] or "").strip()]

    def list_categories(self) -> List[str]:
        rows = self.conn.execute("SELECT DISTINCT COALESCE(category,'') AS c FROM assets ORDER BY c").fetchall()
        return [r["c"] for r in rows if (r["c"] or "").strip()]

    # Check types
    def add_check_type(self, data: Dict[str, Any]) -> int:
        now = today_str()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO check_types(name, code, validity_months, notes, created_at, updated_at)
            VALUES(:name,:code,:validity_months,:notes,:created_at,:updated_at)
            """,
            dict(data, created_at=now, updated_at=now)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_check_type(self, cid: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM check_types WHERE id=?", (cid,)).fetchone()

    def list_check_types(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM check_types ORDER BY name"))

    def ensure_check_types(self, name_to_validity: Dict[str,int]) -> Dict[str,int]:
        existing = {r["name"]: r["id"] for r in self.list_check_types()}
        for name, val in name_to_validity.items():
            if name not in existing:
                ct_id = self.add_check_type({
                    "name": name, "code": "", "validity_months": int(val or DEFAULT_VALIDITY_MONTHS), "notes": "(import)"
                })
                existing[name] = ct_id
        return existing

    # Checks
    def latest_check_for(self, asset_id: int, ct_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM checks WHERE asset_id=? AND check_type_id=? ORDER BY last_check_date DESC, id DESC LIMIT 1",
            (asset_id, ct_id)
        ).fetchone()

    def _status_from_next(self, next_due: Optional[str], reminder_days: int) -> str:
        if not next_due:
            return STATUS_OK
        dd = days_until(next_due)
        if dd is None:
            return STATUS_OK
        if dd < 0:
            return STATUS_EXPIRED
        if dd <= reminder_days:
            return STATUS_SOON
        return STATUS_OK

    def add_or_update_check(self, data: Dict[str, Any], mode_next_is_final: bool = False) -> int:
        now = today_str()
        last_date = data.get("last_check_date")
        validity_months = int(data.get("validity_months") or 0)
        if mode_next_is_final:
            next_due = data.get("next_due_date")
        else:
            next_due = compute_next_due(last_date, validity_months)
        reminder = int(self.get_settings()["reminder_days"] or DEFAULT_REMINDER_DAYS)
        status = self._status_from_next(next_due, reminder)
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO checks(asset_id,check_type_id,last_check_date,next_due_date,validity_months,status,document_path,notes,created_at,updated_at)
            VALUES(:asset_id,:check_type_id,:last_check_date,:next_due_date,:validity_months,:status,:document_path,:notes,:created_at,:updated_at)
            """,
            dict(data, next_due_date=next_due, status=status, created_at=now, updated_at=now)
        )
        self.conn.commit()
        return cur.lastrowid

    def recompute_all(self):
        s = self.get_settings()
        rem = int(s["reminder_days"] or DEFAULT_REMINDER_DAYS)
        rows = self.conn.execute("SELECT id,last_check_date,validity_months,next_due_date FROM checks").fetchall()
        with self.conn:
            for r in rows:
                next_due = r["next_due_date"] or compute_next_due(r["last_check_date"], int(r["validity_months"] or 0))
                st = self._status_from_next(next_due, rem)
                self.conn.execute("UPDATE checks SET next_due_date=?, status=?, updated_at=? WHERE id=?",
                                  (next_due, st, today_str(), r["id"]))

    def iter_matrix(self, site: Optional[str], category: Optional[str], name_like: str) -> Tuple[List[sqlite3.Row], List[sqlite3.Row]]:
        q = "SELECT * FROM assets WHERE 1=1"
        params: List[Any] = []
        if site:
            q += " AND site=?"; params.append(site)
        if category:
            q += " AND category=?"; params.append(category)
        if name_like.strip():
            like = f"%{name_like.strip()}%"
            q += " AND (name LIKE ? OR plate LIKE ? OR vin LIKE ? OR responsible_name LIKE ? OR responsible_email LIKE ?)"
            params += [like, like, like, like, like]
        q += " ORDER BY site, category, name"
        assets = list(self.conn.execute(q, params))
        cts = self.list_check_types()
        return assets, cts

    def due_rows(self, horizon_days: int) -> List[sqlite3.Row]:
        max_date = (datetime.now() + timedelta(days=int(horizon_days))).strftime(DATE_FMT)
        q = (
            "SELECT c.*, a.name AS asset_name, a.plate, a.site, a.category, a.responsible_name, a.responsible_email, t.name AS check_name "
            "FROM checks c JOIN assets a ON a.id=c.asset_id JOIN check_types t ON t.id=c.check_type_id "
            "WHERE c.next_due_date IS NOT NULL AND c.next_due_date <= ? ORDER BY c.next_due_date"
        )
        return list(self.conn.execute(q, (max_date,)))

# --------------------------- Email --------------------------------

def _smtp_cfg(db: DB) -> Dict[str, Any]:
    s = db.get_settings()
    return {
        "to": (s["secretary_email"] or "").strip(),
        "cc": [e.strip() for e in (s["cc_emails"] or "").split(";") if e.strip()],
        "host": (s["smtp_host"] or "").strip(),
        "port": int(s["smtp_port"] or 0),
        "user": (s["smtp_user"] or "").strip(),
        "pwd": base64.b64decode(s["smtp_password_b64"]).decode("utf-8") if s["smtp_password_b64"] else "",
        "tls": bool(int(s["use_tls"] or 0)),
        "ssl": bool(int(s["use_ssl"] or 0)),
        "mail_resp": bool(int(s["mail_responsibles"] or 0)),
    }


def _smtp_send(cfg: Dict[str, Any], msg: EmailMessage):
    if cfg["ssl"]:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"]) as s:
            if cfg["user"] and cfg["pwd"]:
                s.login(cfg["user"], cfg["pwd"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            s.ehlo()
            if cfg["tls"]:
                s.starttls(context=ssl.create_default_context())
            if cfg["user"] and cfg["pwd"]:
                s.login(cfg["user"], cfg["pwd"])
            s.send_message(msg)


def send_secretary_summary(db: DB):
    cfg = _smtp_cfg(db)
    if not cfg["to"]:
        raise RuntimeError("Renseignez l'e‑mail de la secrétaire dans Paramètres.")
    rem = int(db.get_settings()["reminder_days"] or DEFAULT_REMINDER_DAYS)
    rows = db.due_rows(rem)

    msg = EmailMessage()
    msg["Subject"] = f"Rappels contrôle technique (≤ {rem} j) – {today_str()}"
    msg["From"] = cfg["user"] or cfg["to"]
    msg["To"] = cfg["to"]
    if cfg["cc"]:
        msg["Cc"] = ", ".join(cfg["cc"]) 

    if not rows:
        msg.set_content("Bonjour,\n\nAucun rappel à émettre aujourd'hui.\n\nCordialement.")
        _smtp_send(cfg, msg); return

    header = ["Actif","Immatriculation","Site","Catégorie","Type contrôle","Dernier contrôle","Prochaine échéance","Jours","Statut","Responsable","E‑mail"]
    lines = [";".join(header)]
    for r in rows:
        dd = days_until(r["next_due_date"]) if r["next_due_date"] else ""
        lines.append(";".join([
            r["asset_name"] or "", r["plate"] or "", r["site"] or "", r["category"] or "",
            r["check_name"], r["last_check_date"] or "", r["next_due_date"] or "",
            str(dd if dd is not None else ""), r["status"] or "",
            r["responsible_name"] or "", r["responsible_email"] or ""
        ]))
    csv_bytes = ("\n".join(lines)).encode("utf-8")

    msg.set_content("Bonjour,\n\nVeuillez trouver en PJ le récapitulatif des contrôles à échéance.\n\nCordialement.")
    msg.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=f"rappels_controle_{today_str()}.csv")
    _smtp_send(cfg, msg)


def send_responsible_emails(db: DB):
    cfg = _smtp_cfg(db)
    if not cfg["mail_resp"]:
        return
    rem = int(db.get_settings()["reminder_days"] or DEFAULT_REMINDER_DAYS)
    rows = db.due_rows(rem)
    # group by responsible email
    by_r: Dict[str, List[sqlite3.Row]] = {}
    for r in rows:
        mail = (r["responsible_email"] or "").strip()
        if not mail:
            continue
        by_r.setdefault(mail, []).append(r)
    for mail, items in by_r.items():
        msg = EmailMessage()
        msg["Subject"] = f"Rappel contrôles techniques – {today_str()}"
        msg["From"] = cfg["user"] or cfg.get("to") or mail
        msg["To"] = mail
        if cfg["to"]:
            msg["Cc"] = cfg["to"]
        lines = []
        for r in items:
            dd = days_until(r["next_due_date"]) if r["next_due_date"] else None
            jtxt = f"J-{dd}" if dd is not None and dd >= 0 else "expiré"
            lines.append(f"• {r['asset_name']} ({r['plate'] or '—'}) – {r['check_name']}: {r['next_due_date'] or '—'} ({jtxt})")
        msg.set_content(
            "Bonjour,\n\n" +
            "Les contrôles suivants sont à planifier :\n" + "\n".join(lines) + "\n\n"
            "Merci de coordonner avec la secrétaire pour la prise de RDV.\nCordialement."
        )
        _smtp_send(cfg, msg)


def send_all_reminders(db: DB):
    send_secretary_summary(db)
    send_responsible_emails(db)

# --------------------------- Import matriciel ---------------------

def read_excel_any(path: str) -> Tuple[pd.DataFrame, str]:
    ext = os.path.splitext(path.lower())[1]
    if ext == ".xlsx":
        return pd.read_excel(path, engine="openpyxl"), "openpyxl"
    if ext == ".xls":
        return pd.read_excel(path, engine="xlrd"), "xlrd"
    return pd.read_excel(path), "auto"


def parse_any_date(s: str, fmt_hint: str) -> Optional[str]:
    s = (s or "").strip()
    if not s or s.lower() in {"nan","none","nat"}:
        return None
    try:
        return datetime.strptime(s, fmt_hint).strftime(DATE_FMT)
    except Exception:
        pass
    try:
        d = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(d):
            return None
        return d.strftime(DATE_FMT)
    except Exception:
        return None

class ImportMatrixDialog(QtWidgets.QDialog):
    """Assistant d’import conçu pour la **matrice de contrôle technique**."""
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Importer – Matrice contrôle technique (Excel)")
        self.resize(980, 640)
        self.df: Optional[pd.DataFrame] = None
        self.mode_next = False  # False=cell=dernière intervention ; True=cell=prochaine échéance

        lay = QtWidgets.QVBoxLayout(self)
        pick = QtWidgets.QHBoxLayout(); self.ed_path = QtWidgets.QLineEdit(); b = QtWidgets.QPushButton("Parcourir…"); b.clicked.connect(self._browse)
        pick.addWidget(self.ed_path, 1); pick.addWidget(b)
        lay.addLayout(pick)
        self.lbl = QtWidgets.QLabel("Sélectionnez le fichier .xls/.xlsx (matrice).")
        self.lbl.setStyleSheet("color:#666"); lay.addWidget(self.lbl)

        grid = QtWidgets.QGridLayout()
        self.cb_name = QtWidgets.QComboBox(); self.cb_plate = QtWidgets.QComboBox(); self.cb_vin = QtWidgets.QComboBox()
        self.cb_site = QtWidgets.QComboBox(); self.cb_cat = QtWidgets.QComboBox()
        self.cb_resp = QtWidgets.QComboBox(); self.cb_mail = QtWidgets.QComboBox()
        for i, (lab, cb) in enumerate([
            ("Nom actif", self.cb_name), ("Immatriculation", self.cb_plate), ("VIN", self.cb_vin),
            ("Site/Service", self.cb_site), ("Catégorie", self.cb_cat),
            ("Responsable (nom)", self.cb_resp), ("Responsable (e‑mail)", self.cb_mail)
        ]):
            grid.addWidget(QtWidgets.QLabel(lab), i, 0); grid.addWidget(cb, i, 1)
        lay.addLayout(grid)

        fmtrow = QtWidgets.QHBoxLayout()
        self.ed_fmt = QtWidgets.QLineEdit("%d/%m/%Y")
        self.rb_last = QtWidgets.QRadioButton("Cellules = dernière intervention")
        self.rb_next = QtWidgets.QRadioButton("Cellules = prochaine échéance")
        self.rb_last.setChecked(True)
        self.rb_last.toggled.connect(lambda: setattr(self, 'mode_next', not self.rb_last.isChecked()))
        for w in [QtWidgets.QLabel("Format date"), self.ed_fmt, self.rb_last, self.rb_next]:
            fmtrow.addWidget(w)
        fmtrow.addStretch(1); lay.addLayout(fmtrow)

        self.tbl = QtWidgets.QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Colonne Excel", "Type de contrôle", "Validité (mois)"])
        self.tbl.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        lay.addWidget(self.tbl, 1)

        btns = QtWidgets.QHBoxLayout(); btns.addStretch(1)
        bi = QtWidgets.QPushButton("Importer"); bi.clicked.connect(self.on_import)
        bc = QtWidgets.QPushButton("Annuler"); bc.clicked.connect(self.reject)
        btns.addWidget(bi); btns.addWidget(bc); lay.addLayout(btns)

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choisir Excel", "", "Excel (*.xlsx *.xls)")
        if not path: return
        self.ed_path.setText(path)
        try:
            self.df, engine = read_excel_any(path)
            cols = [str(c) for c in self.df.columns]
            # Remplir combos
            for cb in [self.cb_name, self.cb_plate, self.cb_vin, self.cb_site, self.cb_cat, self.cb_resp, self.cb_mail]:
                cb.clear(); cb.addItem("—"); cb.addItems(cols)
            # Heuristique : trouver colonnes classiques
            hints = {
                self.cb_name: ["nom", "name", "actif", "véhicule", "vehicle"],
                self.cb_plate: ["immat", "plaque", "plate"],
                self.cb_vin: ["vin"],
                self.cb_site: ["site", "service"],
                self.cb_cat: ["cat", "categorie", "category"],
                self.cb_resp: ["responsable", "driver", "conducteur"],
                self.cb_mail: ["mail", "email", "e-mail"],
            }
            for cb, keys in hints.items():
                for k in keys:
                    for c in cols:
                        if k in c.lower():
                            cb.setCurrentText(c); break
                    if cb.currentIndex()>0: break
            # Colonnes contrôles = le reste
            fixed = {cb.currentText() for cb in [self.cb_name, self.cb_plate, self.cb_vin, self.cb_site, self.cb_cat, self.cb_resp, self.cb_mail] if cb.currentIndex()>0}
            ctl_cols = [c for c in cols if c not in fixed]
            self.tbl.setRowCount(0)
            for col in ctl_cols:
                r = self.tbl.rowCount(); self.tbl.insertRow(r)
                self.tbl.setItem(r, 0, QtWidgets.QTableWidgetItem(col))
                self.tbl.setItem(r, 1, QtWidgets.QTableWidgetItem(col))
                self.tbl.setItem(r, 2, QtWidgets.QTableWidgetItem(str(DEFAULT_VALIDITY_MONTHS)))
            self.lbl.setText(f"Colonnes chargées via {engine}. Vérifiez les types de contrôle et validités.")
        except Exception as e:
            self.lbl.setText(f"Erreur lecture Excel : {e}")
            self.df = None

    def on_import(self):
        if self.df is None:
            QtWidgets.QMessageBox.warning(self, "Import", "Sélectionnez un fichier Excel valide.")
            return
        name_col = self.cb_name.currentText() if self.cb_name.currentIndex()>0 else None
        if not name_col:
            QtWidgets.QMessageBox.warning(self, "Import", "Choisissez la colonne 'Nom actif'.")
            return
        fmt = self.ed_fmt.text().strip() or "%Y-%m-%d"
        # Construire mapping colonne -> (type contrôle, validité)
        col_map: List[Tuple[str, str, int]] = []
        for r in range(self.tbl.rowCount()):
            excel_col = self.tbl.item(r,0).text().strip()
            chk_name  = self.tbl.item(r,1).text().strip()
            try:
                valid = int(self.tbl.item(r,2).text().strip())
            except Exception:
                valid = DEFAULT_VALIDITY_MONTHS
            if chk_name:
                col_map.append((excel_col, chk_name, valid))
        # Créer types si besoin
        ct_valid = {n:v for (_, n, v) in col_map}
        name_to_id = self.db.ensure_check_types(ct_valid)
        # Parcours lignes
        added = 0
        for _, row in self.df.iterrows():
            name = str(row.get(name_col, "")).strip()
            if not name: continue
            plate = str(row.get(self.cb_plate.currentText(), "")).strip() if self.cb_plate.currentIndex()>0 else ""
            vin   = str(row.get(self.cb_vin.currentText(), "")).strip() if self.cb_vin.currentIndex()>0 else ""
            site  = str(row.get(self.cb_site.currentText(), "")).strip() if self.cb_site.currentIndex()>0 else ""
            cat   = str(row.get(self.cb_cat.currentText(),  "")).strip() if self.cb_cat.currentIndex()>0  else ""
            resp  = str(row.get(self.cb_resp.currentText(), "")).strip() if self.cb_resp.currentIndex()>0 else ""
            mail  = str(row.get(self.cb_mail.currentText(), "")).strip() if self.cb_mail.currentIndex()>0 else ""
            # upsert asset (nom + plaque)
            asset = self.db.conn.execute(
                "SELECT * FROM assets WHERE lower(name)=? AND COALESCE(lower(plate),'')=COALESCE(?, '')",
                (name.lower(), plate.lower() if plate else None)
            ).fetchone()
            if asset:
                aid = asset["id"]
            else:
                aid = self.db.add_asset({
                    "name": name, "plate": plate, "vin": vin, "category": cat, "site": site,
                    "responsible_name": resp, "responsible_email": mail, "phone": "", "notes": "(import)"
                })
            for excel_col, chk_name, vmonths in col_map:
                cell = row.get(excel_col)
                if pd.isna(cell):
                    continue
                cell_str = str(cell).strip()
                if not cell_str:
                    continue
                date_parsed = parse_any_date(cell_str, fmt)
                ct_id = name_to_id[chk_name]
                if self.mode_next:
                    self.db.add_or_update_check({
                        "asset_id": aid, "check_type_id": ct_id,
                        "last_check_date": None, "next_due_date": date_parsed, "validity_months": int(vmonths),
                        "document_path": "", "notes": "(import)"
                    }, mode_next_is_final=True)
                else:
                    if not date_parsed:
                        continue
                    self.db.add_or_update_check({
                        "asset_id": aid, "check_type_id": ct_id,
                        "last_check_date": date_parsed, "validity_months": int(vmonths),
                        "document_path": "", "notes": "(import)"
                    })
                added += 1
        self.db.recompute_all()
        QtWidgets.QMessageBox.information(self, "Import", f"Import terminé : {added} enregistrements ajoutés.")
        self.accept()

# --------------------------- Dialogs CRUD -------------------------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Paramètres e‑mail & rappels")
        self.resize(720, 480)
        s = db.get_settings()
        form = QtWidgets.QFormLayout(self)
        self.ed_secretary = QtWidgets.QLineEdit(s["secretary_email"] or "")
        self.ed_cc = QtWidgets.QLineEdit(s["cc_emails"] or "")
        self.ed_host = QtWidgets.QLineEdit(s["smtp_host"] or "")
        self.sp_port = QtWidgets.QSpinBox(); self.sp_port.setRange(1,65535); self.sp_port.setValue(int(s["smtp_port"] or 587))
        self.ed_user = QtWidgets.QLineEdit(s["smtp_user"] or "")
        self.ed_pwd  = QtWidgets.QLineEdit(); self.ed_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
        if s["smtp_password_b64"]:
            try: self.ed_pwd.setText(base64.b64decode(s["smtp_password_b64"]).decode("utf-8"))
            except Exception: pass
        self.cb_tls = QtWidgets.QCheckBox("TLS"); self.cb_tls.setChecked(bool(int(s["use_tls"] or 0)))
        self.cb_ssl = QtWidgets.QCheckBox("SSL"); self.cb_ssl.setChecked(bool(int(s["use_ssl"] or 0)))
        self.cb_mailresp = QtWidgets.QCheckBox("Envoyer un e‑mail aux responsables"); self.cb_mailresp.setChecked(bool(int(s["mail_responsibles"] or 0)))
        self.sp_rem = QtWidgets.QSpinBox(); self.sp_rem.setRange(1,365); self.sp_rem.setValue(int(s["reminder_days"] or DEFAULT_REMINDER_DAYS))
        def ex():
            if self.sender() is self.cb_tls and self.cb_tls.isChecked(): self.cb_ssl.setChecked(False)
            if self.sender() is self.cb_ssl and self.cb_ssl.isChecked(): self.cb_tls.setChecked(False)
        self.cb_tls.clicked.connect(ex); self.cb_ssl.clicked.connect(ex)
        form.addRow("Email secrétaire", self.ed_secretary)
        form.addRow("CC (séparés par ;)", self.ed_cc)
        form.addRow("SMTP host", self.ed_host)
        form.addRow("SMTP port", self.sp_port)
        form.addRow("SMTP user", self.ed_user)
        form.addRow("SMTP password", self.ed_pwd)
        row = QtWidgets.QWidget(); hl = QtWidgets.QHBoxLayout(row); hl.setContentsMargins(0,0,0,0); hl.addWidget(self.cb_tls); hl.addWidget(self.cb_ssl); hl.addStretch(1)
        form.addRow("Sécurité", row)
        form.addRow("Horizon rappel (jours)", self.sp_rem)
        form.addRow(self.cb_mailresp)
        bt = QtWidgets.QHBoxLayout(); btest = QtWidgets.QPushButton("E‑mail de test"); bsave = QtWidgets.QPushButton("Enregistrer"); bcancel = QtWidgets.QPushButton("Annuler")
        btest.clicked.connect(self.on_test); bsave.clicked.connect(self.accept); bcancel.clicked.connect(self.reject)
        bt.addWidget(btest); bt.addStretch(1); bt.addWidget(bsave); bt.addWidget(bcancel)
        form.addRow(bt)
    def data(self) -> Dict[str,Any]:
        return {
            "secretary_email": self.ed_secretary.text().strip(),
            "cc_emails": self.ed_cc.text().strip(),
            "smtp_host": self.ed_host.text().strip(),
            "smtp_port": int(self.sp_port.value()),
            "smtp_user": self.ed_user.text().strip(),
            "smtp_password_b64": base64.b64encode(self.ed_pwd.text().encode("utf-8")).decode("ascii") if self.ed_pwd.text() else "",
            "use_tls": 1 if self.cb_tls.isChecked() else 0,
            "use_ssl": 1 if self.cb_ssl.isChecked() else 0,
            "mail_responsibles": 1 if self.cb_mailresp.isChecked() else 0,
            "reminder_days": int(self.sp_rem.value()),
        }
    def on_test(self):
        self._save()
        try:
            cfg = _smtp_cfg(self.db)
            if not cfg["to"]: raise RuntimeError("Renseignez l'e‑mail de la secrétaire.")
            msg = EmailMessage(); msg["Subject"] = "[TEST] Contrôles – configuration"; msg["From"] = cfg["user"] or cfg["to"]; msg["To"] = cfg["to"]
            msg.set_content("Test OK : configuration SMTP valide.")
            _smtp_send(cfg, msg)
            QtWidgets.QMessageBox.information(self, "Test", "Email de test envoyé.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Test", f"Échec : {e}")
    def _save(self):
        self.db.update_settings(self.data())

class CheckDialog(QtWidgets.QDialog):
    def __init__(self, db: DB, asset: sqlite3.Row, ctype: sqlite3.Row, preset: Optional[sqlite3.Row] = None, parent=None):
        super().__init__(parent)
        self.db, self.asset, self.ctype, self.preset = db, asset, ctype, preset
        self.setWindowTitle(f"Contrôle – {asset['name']} / {ctype['name']}")
        self.resize(560, 380)
        form = QtWidgets.QFormLayout(self)
        self.ed_last = QtWidgets.QDateEdit(calendarPopup=True); self.ed_last.setDisplayFormat("yyyy-MM-dd")
        if preset and preset.get("last_check_date"): self.ed_last.setDate(QtCore.QDate.fromString(preset["last_check_date"], "yyyy-MM-dd"))
        else: self.ed_last.setDate(QtCore.QDate.currentDate())
        self.sp_valid = QtWidgets.QSpinBox(); self.sp_valid.setRange(0,600); self.sp_valid.setValue(int(preset.get("validity_months") if preset else (self.ctype["validity_months"] or DEFAULT_VALIDITY_MONTHS)))
        self.ed_doc = QtWidgets.QLineEdit((preset or {}).get("document_path", ""))
        self.ed_notes = QtWidgets.QPlainTextEdit((preset or {}).get("notes", ""))
        form.addRow("Dernière intervention", self.ed_last)
        form.addRow("Validité (mois)", self.sp_valid)
        form.addRow("Document (PDF)", self.ed_doc)
        form.addRow("Notes", self.ed_notes)
        btns = QtWidgets.QHBoxLayout(); bok = QtWidgets.QPushButton("Enregistrer"); bcancel = QtWidgets.QPushButton("Annuler"); bok.clicked.connect(self.accept); bcancel.clicked.connect(self.reject)
        btns.addWidget(bok); btns.addWidget(bcancel); form.addRow(btns)
    def data(self) -> Dict[str,Any]:
        return {
            "asset_id": int(self.asset["id"]),
            "check_type_id": int(self.ctype["id"]),
            "last_check_date": self.ed_last.date().toString("yyyy-MM-dd"),
            "validity_months": int(self.sp_valid.value()),
            "document_path": self.ed_doc.text().strip(),
            "notes": self.ed_notes.toPlainText().strip(),
        }

# --------------------------- UI Matrice --------------------------
class MatrixWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Contrôles techniques – Matrice")
        self.resize(1480, 860)
        self.db = DB()

        # Top bar – filtres dédiés
        top = QtWidgets.QWidget(); tl = QtWidgets.QHBoxLayout(top)
        self.cb_site = QtWidgets.QComboBox(); self.cb_site.addItem("Tous sites", "")
        for s in self.db.list_sites(): self.cb_site.addItem(s, s)
        self.cb_cat = QtWidgets.QComboBox(); self.cb_cat.addItem("Toutes catégories", "")
        for c in self.db.list_categories(): self.cb_cat.addItem(c, c)
        self.cb_status = QtWidgets.QComboBox(); self.cb_status.addItems(["Tous statuts", STATUS_OK, STATUS_SOON, STATUS_EXPIRED])
        self.cb_check = QtWidgets.QComboBox(); self.cb_check.addItem("Tous types", 0)
        for t in self.db.list_check_types(): self.cb_check.addItem(t["name"], int(t["id"]))
        self.ed_search = QtWidgets.QLineEdit(); self.ed_search.setPlaceholderText("Rechercher nom/immat/VIN/responsable…")
        self.sp_horizon = QtWidgets.QSpinBox(); self.sp_horizon.setRange(1,365); self.sp_horizon.setValue(int(self.db.get_settings()["reminder_days"] or DEFAULT_REMINDER_DAYS))
        self.cb_only_cols_due = QtWidgets.QCheckBox("Colonnes avec rappels seulement")
        b_import = QtWidgets.QPushButton("Importer Excel (matrice)…"); b_import.clicked.connect(self.on_import)
        b_settings = QtWidgets.QPushButton("Paramètres…"); b_settings.clicked.connect(self.on_settings)
        b_send = QtWidgets.QPushButton("Envoyer rappels (sec + resp)"); b_send.clicked.connect(self.on_send)
        b_refresh = QtWidgets.QPushButton("↻"); b_refresh.clicked.connect(self.reload)
        for w in [QtWidgets.QLabel("Site"), self.cb_site, QtWidgets.QLabel("Catégorie"), self.cb_cat, QtWidgets.QLabel("Statut"), self.cb_status,
                  QtWidgets.QLabel("Type"), self.cb_check, self.ed_search, QtWidgets.QLabel("≤ J"), self.sp_horizon, self.cb_only_cols_due,
                  b_import, b_settings, b_send, b_refresh]:
            tl.addWidget(w)
        self.cb_site.currentTextChanged.connect(self.reload)
        self.cb_cat.currentTextChanged.connect(self.reload)
        self.cb_status.currentTextChanged.connect(self.reload)
        self.cb_check.currentTextChanged.connect(self.reload)
        self.ed_search.textChanged.connect(self.reload)
        self.sp_horizon.valueChanged.connect(self.reload)
        self.cb_only_cols_due.toggled.connect(self.reload)

        # Chips résumé
        chips = QtWidgets.QWidget(); cl = QtWidgets.QHBoxLayout(chips); cl.setContentsMargins(0,0,0,0)
        self.ch_ok = QtWidgets.QLabel(); self._chip(self.ch_ok, STATUS_OK)
        self.ch_sn = QtWidgets.QLabel(); self._chip(self.ch_sn, STATUS_SOON)
        self.ch_ex = QtWidgets.QLabel(); self._chip(self.ch_ex, STATUS_EXPIRED)
        cl.addWidget(self.ch_ok); cl.addWidget(self.ch_sn); cl.addWidget(self.ch_ex); cl.addStretch(1)

        # Table matrice
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.on_cell_dbl)
        self.table.setAlternatingRowColors(True)

        # Aide
        helpb = QtWidgets.QGroupBox("Aide")
        hl = QtWidgets.QVBoxLayout(helpb)
        txt = QtWidgets.QLabel(
            "• Double‑cliquez une cellule pour enregistrer un contrôle.\n"
            "• Utilisez l’import Excel ‘matrice’ pour migrer l’ancien fichier.\n"
            "• ‘Envoyer rappels’ expédie un récap à la secrétaire + un e‑mail par responsable."
        ); txt.setWordWrap(True)
        hl.addWidget(txt)

        central = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(central)
        v.addWidget(top); v.addWidget(chips); v.addWidget(self.table, 1); v.addWidget(helpb)
        self.setCentralWidget(central)

        self.reload()

    def _chip(self, lbl: QtWidgets.QLabel, text: str):
        lbl.setText(f"{text}: 0")
        lbl.setStyleSheet(f"QLabel {{ background:{STATUS_COLORS.get(text,'#777')}; color:white; padding:2px 8px; border-radius:10px; }}")

    def reload(self):
        self.db.recompute_all()
        site = self.cb_site.currentData()
        category = self.cb_cat.currentData()
        name_like = self.ed_search.text()
        assets, types_all = self.db.iter_matrix(site or None, category or None, name_like)
        # Colonnes visibles
        if self.cb_only_cols_due.isChecked():
            types = []
            rem = int(self.sp_horizon.value())
            for t in types_all:
                for a in assets:
                    ch = self.db.latest_check_for(a["id"], t["id"]) or {}
                    st = ch.get("status")
                    if st in (STATUS_SOON, STATUS_EXPIRED):
                        types.append(t); break
        else:
            types = list(types_all)
        # Filtre type
        ct_filter = int(self.cb_check.currentData() or 0)
        if ct_filter:
            types = [t for t in types if int(t["id"]) == ct_filter]
        # Headers
        headers = ["Actif", "Immatriculation", "VIN", "Site", "Catégorie", "Responsable", "E‑mail"] + [t["name"] for t in types]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)
        counts = {STATUS_OK:0, STATUS_SOON:0, STATUS_EXPIRED:0}
        rem = int(self.sp_horizon.value())
        stat_filter = self.cb_status.currentText()
        for a in assets:
            row_stats: List[str] = []
            row_cells: List[Tuple[str, Optional[str], Optional[int], Optional[str]]] = []
            for t in types:
                ch = self.db.latest_check_for(a["id"], t["id"]) or {}
                next_due = ch.get("next_due_date") or compute_next_due(ch.get("last_check_date"), int(ch.get("validity_months") or t["validity_months"] or DEFAULT_VALIDITY_MONTHS))
                dd = days_until(next_due) if next_due else None
                st = STATUS_OK
                if next_due:
                    if dd is not None and dd < 0:
                        st = STATUS_EXPIRED
                    elif dd is not None and dd <= rem:
                        st = STATUS_SOON
                row_stats.append(st)
                row_cells.append((st, next_due, dd, ch.get("last_check_date")))
            # appliquer filtre de statut (conserver la ligne si au moins une cellule correspond)
            keep = True
            if stat_filter != "Tous statuts":
                keep = any(st == stat_filter for st in row_stats)
            if not keep:
                continue
            # ajouter la ligne
            r = self.table.rowCount()
            self.table.insertRow(r)
            base = [
                a["name"] or "", a["plate"] or "", a["vin"] or "",
                a["site"] or "", a["category"] or "",
                a["responsible_name"] or "", a["responsible_email"] or ""
            ]
            for c, val in enumerate(base):
                it = QtWidgets.QTableWidgetItem(val)
                self.table.setItem(r, c, it)
            for j, (st, next_due, dd, last) in enumerate(row_cells):
                c = 7 + j
                disp = (next_due or "—")
                if dd is not None:
                    disp += f"\n(J-{dd})" if dd >= 0 else "\n(expiré)"
                it = QtWidgets.QTableWidgetItem(disp)
                it.setData(QtCore.Qt.UserRole, {"asset_id": int(a["id"]), "ctype_id": int(types[j]["id"])})
                it.setTextAlignment(QtCore.Qt.AlignCenter)
                it.setBackground(QtGui.QColor(STATUS_COLORS.get(st, "#999")))
                it.setForeground(QtGui.QColor("#ffffff"))
                self.table.setItem(r, c, it)
                counts[st] += 1

        # mise à jour des chips
        self.ch_ok.setText(f"{STATUS_OK}: {counts[STATUS_OK]}")
        self.ch_sn.setText(f"{STATUS_SOON}: {counts[STATUS_SOON]}")
        self.ch_ex.setText(f"{STATUS_EXPIRED}: {counts[STATUS_EXPIRED]}")
        self.table.resizeColumnsToContents()

    # Actions
    def on_import(self):
        dlg = ImportMatrixDialog(self.db, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.reload()

    def on_settings(self):
        dlg = SettingsDialog(self.db, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.update_settings(dlg.data())
            self.reload()

    def on_send(self):
        try:
            send_all_reminders(self.db)
            QtWidgets.QMessageBox.information(self, "Rappels", "E-mails envoyés (secrétaire + responsables).")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Rappels", f"Échec : {e}")

    def on_cell_dbl(self, item: QtWidgets.QTableWidgetItem):
        col = item.column()
        # colonnes 0..6 = infos de base
        if col < 7:
            return
        payload = item.data(QtCore.Qt.UserRole) or {}
        aid = payload.get("asset_id")
        ctid = payload.get("ctype_id")
        if not aid or not ctid:
            return
        asset = self.db.get_asset(int(aid))
        ctype = self.db.get_check_type(int(ctid))
        preset = self.db.latest_check_for(int(aid), int(ctid))
        dlg = CheckDialog(self.db, asset, ctype, preset, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db.add_or_update_check(dlg.data())
            QtWidgets.QMessageBox.information(self, "Contrôle", "Enregistré.")
            self.reload()


# --------------------------- Entrée & CLI ------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Contrôles techniques – Matrice de rappels")
    parser.add_argument("--send-reminders", action="store_true",
                        help="Envoi des e-mails (secrétaire + responsables) puis sortie")
    args = parser.parse_args()

    if args.send_reminders:
        db = DB()
        db.recompute_all()
        send_all_reminders(db)
        print("Rappels envoyés.")
        return

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Contrôles techniques – Matrice")
    win = MatrixWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


            