# gui/etalons.py
# -*- coding: utf-8 -*-
"""
Gestion des Étalons – intégré à l'app VDC (PyQt5 + SQLite de models.database.Database)

Points clés
-----------
• Identité visuelle : bleu VDC (#1c5ea3 / #b8d5ed), tableaux stylés, chips de synthèse.
• Statuts : OK / Bientôt dû / Bloqué (Bloqué = blocage manuel OU échéance dépassée).
• Responsable : sélection parmi les utilisateurs « Validé » de la BDD (table users).
• CRUD : créer, éditer, supprimer ; blocage / déblocage ; journal d’étalonnage minimal.
• UX : sélection auto de la 1ère ligne, badge statut toujours visible, ouverture PDF certificat, export CSV.

Tables créées si absentes
-------------------------
standards(id, serial, name, category, manufacturer, model, location, owner_id,
          tags, interval_months, last_cal_date, next_cal_date, status,
          blocked, block_reason, certificate_path, certificate_id, notes,
          created_at, updated_at)

calibrations(id, standard_id, cal_date, due_date, on_site, method, certificate_id,
             certificate_path, pass_fail, results_json, notes, created_at)
"""

import csv
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QDate, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QComboBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QSpinBox,
    QCheckBox, QDateEdit, QDialog, QSizePolicy
)

# ---------- Thème / constantes ----------

THEME_PRIMARY = "#1c5ea3"
THEME_ACCENT  = "#b8d5ed"

DATE_FMT = "%Y-%m-%d"
DUE_SOON_DAYS = 30  # fenêtre "Bientôt dû"

CATEGORIES = [
    "Anémomètre",
    "Balomètre",
    "Température",
    "Humidité",
    "Pression diff.",
    "Pression absolue",
    "Débit (air)",
    "Particules (OPC)",
    "Thermo-hygromètre",
    "Manomètre",
    "Autre"
]

STATUS_COLORS = {
    "OK": "#28a745",
    "Bientôt dû": "#ffc107",
    "Bloqué": "#6c757d",
}

# ---------- Helpers ----------

def today_str() -> str:
    return datetime.now().strftime(DATE_FMT)

def add_months(d: datetime, months: int) -> datetime:
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    # jours par mois
    days_in_month = [31,
                     29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    day = min(d.day, days_in_month)
    return datetime(y, m, day)

def compute_next_due(last_date: Optional[str], interval_months: int) -> Optional[str]:
    if not last_date or interval_months <= 0:
        return None
    try:
        d = datetime.strptime(last_date, DATE_FMT)
        nxt = add_months(d, interval_months)
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

def set_chip(label: QLabel, text: str, color: str):
    label.setText(text)
    label.setStyleSheet(
        f"QLabel {{ background:{color}; color:white; padding:2px 8px; border-radius:10px; }}"
    )

def set_status_pill(label: QLabel, status: Optional[str]):
    if not status:
        label.setText("—")
        label.setStyleSheet("QLabel { background:#999; color:white; padding:4px 8px; border-radius:10px; }")
        return
    color = STATUS_COLORS.get(status, "#17a2b8")
    label.setText(status)
    label.setStyleSheet(f"QLabel {{ background:{color}; color:white; padding:4px 8px; border-radius:10px; }}")


# ---------- Repository (utilise db.conn de l'app) ----------

class EtalonsRepository:
    def __init__(self, app_db):
        self.conn = app_db.conn  # <== models.database.Database().conn
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        with self.conn:
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS standards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial TEXT,
                name TEXT,
                category TEXT,
                manufacturer TEXT,
                model TEXT,
                location TEXT,
                owner_id INTEGER,        -- FK users.id (peut être NULL)
                tags TEXT,
                interval_months INTEGER,
                last_cal_date TEXT,      -- YYYY-MM-DD
                next_cal_date TEXT,      -- calculé
                status TEXT,             -- OK / Bientôt dû / Bloqué
                blocked INTEGER DEFAULT 0, -- blocage manuel 0/1
                block_reason TEXT,
                certificate_path TEXT,
                certificate_id TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            )""")
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS calibrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_id INTEGER NOT NULL,
                cal_date TEXT,
                due_date TEXT,
                on_site INTEGER,
                method TEXT,
                certificate_id TEXT,
                certificate_path TEXT,
                pass_fail INTEGER,      -- 1 OK / 0 fail
                results_json TEXT,
                notes TEXT,
                created_at TEXT,
                FOREIGN KEY(standard_id) REFERENCES standards(id) ON DELETE CASCADE
            )""")

    # --- Status logic ---
    def _compute_status(self, row_like: Dict[str, Any]) -> str:
        # Bloqué manuel prioritaire
        if int(row_like.get("blocked") or 0) == 1:
            return "Bloqué"
        nxt = row_like.get("next_cal_date")
        if not nxt:
            return "OK"
        dd = days_until(nxt)
        if dd is None:
            return "OK"
        if dd < 0:          # échéance dépassée => Bloqué auto
            return "Bloqué"
        if dd <= DUE_SOON_DAYS:
            return "Bientôt dû"
        return "OK"

    def list_users_validated(self) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT id, full_name, role FROM users WHERE validate_user='Validé' ORDER BY full_name ASC"
        ).fetchall())

    def get_owner_name(self, owner_id: Optional[int]) -> str:
        if not owner_id:
            return ""
        r = self.conn.execute("SELECT full_name FROM users WHERE id=?", (owner_id,)).fetchone()
        return r["full_name"] if r else ""

    def add_standard(self, data: Dict[str, Any]) -> int:
        now = today_str()
        data = data.copy()
        data.setdefault("tags", "")
        data.setdefault("certificate_path", "")
        data.setdefault("certificate_id", "")
        data["created_at"] = now
        data["updated_at"] = now
        # calcul next_cal_date
        data["next_cal_date"] = compute_next_due(data.get("last_cal_date"), int(data.get("interval_months") or 0))
        data["status"] = self._compute_status(data)
        data["blocked"] = 1 if data.get("blocked") else 0
        with self.conn:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO standards(serial, name, category, manufacturer, model,
                                      location, owner_id, tags, interval_months,
                                      last_cal_date, next_cal_date, status,
                                      blocked, block_reason, certificate_path, certificate_id,
                                      notes, created_at, updated_at)
                VALUES(:serial, :name, :category, :manufacturer, :model,
                       :location, :owner_id, :tags, :interval_months,
                       :last_cal_date, :next_cal_date, :status,
                       :blocked, :block_reason, :certificate_path, :certificate_id,
                       :notes, :created_at, :updated_at)
            """, data)
            return cur.lastrowid

    def update_standard(self, sid: int, data: Dict[str, Any]):
        now = today_str()
        row = self.get_standard(sid)
        merged = dict(row) if row else {}
        merged.update(data)
        # recalcul next_cal_date si last_cal/interval changent
        if "last_cal_date" in data or "interval_months" in data:
            last = merged.get("last_cal_date")
            interval = int(merged.get("interval_months") or 0)
            merged["next_cal_date"] = compute_next_due(last, interval)
            data["next_cal_date"] = merged["next_cal_date"]
        # status
        merged["blocked"] = 1 if merged.get("blocked") else 0
        new_status = self._compute_status(merged)
        data["status"] = new_status
        data["updated_at"] = now
        keys = ", ".join([f"{k}=:{k}" for k in data.keys()])
        with self.conn:
            self.conn.execute(f"UPDATE standards SET {keys} WHERE id=:id", dict(data, id=sid))

    def delete_standard(self, sid: int):
        with self.conn:
            self.conn.execute("DELETE FROM standards WHERE id=?", (sid,))

    def get_standard(self, sid: int) -> Optional[sqlite3.Row]:
        r = self.conn.execute("SELECT * FROM standards WHERE id=?", (sid,)).fetchone()
        return r

    def list_standards(self, category: str, status: str, search: str) -> List[sqlite3.Row]:
        q = """
        SELECT s.*,
               u.full_name AS owner_name
          FROM standards s
          LEFT JOIN users u ON u.id = s.owner_id
         WHERE 1=1
        """
        params: List[Any] = []
        if category and category != "Toutes":
            q += " AND s.category=?"; params.append(category)
        if status and status != "Tous":
            q += " AND s.status=?"; params.append(status)
        if search.strip():
            like = f"%{search.strip()}%"
            q += " AND (s.serial LIKE ? OR s.name LIKE ? OR s.tags LIKE ?)"
            params += [like, like, like]
        q += """
        ORDER BY
          CASE s.status
            WHEN 'Bloqué' THEN 3
            WHEN 'Bientôt dû' THEN 2
            WHEN 'OK' THEN 1
            ELSE 0
          END DESC,
          CASE WHEN s.next_cal_date IS NULL OR s.next_cal_date='' THEN 1 ELSE 0 END,
          s.next_cal_date ASC,
          s.id DESC
        """
        rows = list(self.conn.execute(q, params))
        # recalcul statuts à l'affichage (prise en compte échéances)
        updated: List[sqlite3.Row] = []
        with self.conn:
            for r in rows:
                computed = self._compute_status(dict(r))
                if computed != r["status"]:
                    self.conn.execute("UPDATE standards SET status=? WHERE id=?", (computed, r["id"]))
                    r = self.conn.execute("SELECT s.*, u.full_name AS owner_name FROM standards s LEFT JOIN users u ON u.id=s.owner_id WHERE s.id=?", (r["id"],)).fetchone()
                updated.append(r)
        return updated

    def set_block(self, sid: int, block: bool, reason: str = ""):
        row = self.get_standard(sid)
        if not row:
            return
        with self.conn:
            self.conn.execute(
                "UPDATE standards SET blocked=?, block_reason=?, updated_at=? WHERE id=?",
                (1 if block else 0, reason if block else "", today_str(), sid)
            )
            # statue recalculé automatiquement dans list_standards / update_standard

    def recompute_status_all(self):
        rows = self.conn.execute("SELECT * FROM standards").fetchall()
        with self.conn:
            for r in rows:
                new_s = self._compute_status(dict(r))
                if new_s != r["status"]:
                    self.conn.execute("UPDATE standards SET status=?, updated_at=? WHERE id=?",
                                      (new_s, today_str(), r["id"]))

    # --- Calibrations (optionnel mais utile) ---
    def add_calibration(self, sid: int, data: Dict[str, Any]):
        now = today_str()
        data = data.copy()
        data["created_at"] = now
        std = self.get_standard(sid)
        interval = int(std["interval_months"] or 0)
        due = compute_next_due(data.get("cal_date"), interval)
        data["due_date"] = due
        with self.conn:
            self.conn.execute("""
                INSERT INTO calibrations(standard_id, cal_date, due_date, on_site, method,
                                         certificate_id, certificate_path, pass_fail,
                                         results_json, notes, created_at)
                VALUES(:standard_id, :cal_date, :due_date, :on_site, :method,
                       :certificate_id, :certificate_path, :pass_fail,
                       :results_json, :notes, :created_at)
            """, dict(data, standard_id=sid))
            # mise à jour étalon : dates + certificat + statut
            upd = {
                "last_cal_date": data.get("cal_date"),
                "next_cal_date": due,
                "certificate_id": data.get("certificate_id") or std["certificate_id"],
                "certificate_path": data.get("certificate_path") or std["certificate_path"],
            }
            merged = dict(std); merged.update(upd, blocked=std["blocked"])
            status = self._compute_status(merged)
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


# ---------- Dialogs ----------

class StandardDialog(QDialog):
    """Créer / éditer un étalon (sélection responsable depuis users validés)."""
    def __init__(self, parent=None, repo: Optional[EtalonsRepository] = None, preset: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.repo = repo
        self.preset = preset or {}
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Étalon")
        self.setModal(True)
        self.resize(700, 520)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #f0f0f0; }}
            QLineEdit, QDateEdit, QComboBox {{
                background: #fff; border: 1px solid {THEME_ACCENT}; border-radius: 4px; padding: 4px 8px; font-size: 14px;
            }}
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus {{ border: 2px solid {THEME_PRIMARY}; }}
            QLabel {{ color: {THEME_PRIMARY}; font-weight: bold; font-size: 13px; }}
            QPushButton {{
                background-color: {THEME_PRIMARY}; color: #fff; border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME_ACCENT}; color: {THEME_PRIMARY}; }}
        """)

        form = QFormLayout(self)

        guide = QGroupBox("Guide rapide")
        gl = QVBoxLayout(guide)
        gtxt = QLabel("Renseigner : Série, Nom, Catégorie, Intervalle (mois), Dernier étalonnage, Responsable.\n"
                      "Le prochain étalonnage est calculé automatiquement. Le statut passe à Bloqué si l’échéance est dépassée.")
        gtxt.setWordWrap(True)
        gl.addWidget(gtxt)
        form.addRow(guide)

        self.serial = QLineEdit(self.preset.get("serial", ""))
        self.name = QLineEdit(self.preset.get("name", ""))
        self.category = QComboBox(); self.category.addItems([""] + CATEGORIES)
        if self.preset.get("category"): self.category.setCurrentText(self.preset["category"])
        self.manufacturer = QLineEdit(self.preset.get("manufacturer", ""))
        self.model = QLineEdit(self.preset.get("model", ""))
        self.location = QLineEdit(self.preset.get("location", ""))

        # Responsable depuis BDD
        self.owner = QComboBox()
        self._users_map: List[Tuple[int, str]] = []
        if self.repo:
            users = self.repo.list_users_validated()
            self.owner.addItem("", 0)
            for u in users:
                self.owner.addItem(f"{u['full_name']} ({u['role']})", int(u["id"]))
                self._users_map.append((int(u["id"]), u["full_name"]))
        if self.preset.get("owner_id"):
            idx = self.owner.findData(int(self.preset["owner_id"]))
            if idx >= 0: self.owner.setCurrentIndex(idx)

        self.tags = QLineEdit(self.preset.get("tags", ""))

        self.interval = QSpinBox(); self.interval.setRange(0, 120); self.interval.setValue(int(self.preset.get("interval_months") or 12))
        self.interval.setToolTip("Périodicité d'étalonnage en mois (0 = pas d’échéance).")

        self.last_cal = QDateEdit(calendarPopup=True); self.last_cal.setDisplayFormat("yyyy-MM-dd")
        if self.preset.get("last_cal_date"):
            self.last_cal.setDate(QDate.fromString(self.preset["last_cal_date"], "yyyy-MM-dd"))
        else:
            self.last_cal.setDate(QDate.currentDate())

        self.certificate_id = QLineEdit(self.preset.get("certificate_id", ""))
        self.certificate_path = QLineEdit(self.preset.get("certificate_path", ""))
        btn_cert = QPushButton("Choisir certificat…")
        btn_cert.clicked.connect(self._choose_cert)

        self.blocked = QCheckBox("Bloquer dès la création")
        self.blocked.setChecked(bool(self.preset.get("blocked", False)))
        self.block_reason = QLineEdit(self.preset.get("block_reason", ""))

        self.notes = QPlainTextEdit(self.preset.get("notes", ""))

        form.addRow("N° de série", self.serial)
        form.addRow("Nom / Désignation", self.name)
        form.addRow("Catégorie", self.category)
        form.addRow("Fabricant", self.manufacturer)
        form.addRow("Modèle", self.model)
        form.addRow("Localisation", self.location)
        form.addRow("Responsable", self.owner)
        form.addRow("Tags (CSV)", self.tags)
        form.addRow("Intervalle (mois)", self.interval)
        form.addRow("Dernier étalonnage", self.last_cal)
        form.addRow("ID Certificat", self.certificate_id)
        row_w = QWidget(); row_l = QHBoxLayout(row_w); row_l.setContentsMargins(0,0,0,0)
        row_l.addWidget(self.certificate_path); row_l.addWidget(btn_cert)
        form.addRow("Fichier certificat", row_w)
        form.addRow(self.blocked)
        form.addRow("Motif de blocage", self.block_reason)
        form.addRow("Notes", self.notes)

        btns = QHBoxLayout()
        b_ok = QPushButton("Enregistrer"); b_ok.clicked.connect(self.accept)
        b_cancel = QPushButton("Annuler"); b_cancel.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

    def _choose_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le certificat (PDF)", "", "PDF (*.pdf);;Tous (*.*)")
        if path:
            self.certificate_path.setText(path)

    def data(self) -> Dict[str, Any]:
        last = self.last_cal.date().toString("yyyy-MM-dd")
        owner_id = self.owner.currentData() or None
        return {
            "serial": self.serial.text().strip(),
            "name": self.name.text().strip(),
            "category": self.category.currentText().strip(),
            "manufacturer": self.manufacturer.text().strip(),
            "model": self.model.text().strip(),
            "location": self.location.text().strip(),
            "owner_id": int(owner_id) if owner_id else None,
            "tags": self.tags.text().strip(),
            "interval_months": int(self.interval.value()),
            "last_cal_date": last,
            "blocked": self.blocked.isChecked(),
            "block_reason": self.block_reason.text().strip(),
            "certificate_path": self.certificate_path.text().strip(),
            "certificate_id": self.certificate_id.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class CalibrationDialog(QDialog):
    """Journal d'étalonnage (minimal)."""
    def __init__(self, parent=None, default_date: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Nouvel étalonnage")
        self.setModal(True)
        self.resize(600, 420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #f0f0f0; }}
            QLineEdit, QDateEdit {{
                background: #fff; border: 1px solid {THEME_ACCENT}; border-radius: 4px; padding: 4px 8px; font-size: 14px;
            }}
            QLineEdit:focus, QDateEdit:focus {{ border: 2px solid {THEME_PRIMARY}; }}
            QLabel {{ color: {THEME_PRIMARY}; font-weight: bold; font-size: 13px; }}
            QPushButton {{
                background-color: {THEME_PRIMARY}; color: #fff; border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME_ACCENT}; color: {THEME_PRIMARY}; }}
        """)

        form = QFormLayout(self)
        self.cal_date = QDateEdit(calendarPopup=True); self.cal_date.setDisplayFormat("yyyy-MM-dd")
        self.cal_date.setDate(QDate.fromString(default_date, "yyyy-MM-dd") if default_date else QDate.currentDate())
        self.on_site = QCheckBox("Étalonnage sur site")
        self.method = QLineEdit()
        self.certificate_id = QLineEdit()
        self.certificate_path = QLineEdit()
        self.pass_ok = QCheckBox("Conforme (PASS)")
        self.results = QPlainTextEdit()
        self.notes = QPlainTextEdit()

        btn_cert = QPushButton("Joindre certificat…")
        btn_cert.clicked.connect(self._choose_cert)

        guide = QGroupBox("Guide rapide")
        gl = QVBoxLayout(guide)
        gtxt = QLabel("Renseignez la date et la méthode ; cochez PASS si conforme. Joignez le certificat si possible.")
        gtxt.setWordWrap(True); gl.addWidget(gtxt)

        form.addRow(guide)
        form.addRow("Date d'étalonnage", self.cal_date)
        form.addRow(self.on_site)
        form.addRow("Méthode", self.method)
        form.addRow("ID Certificat", self.certificate_id)
        row_w = QWidget(); row_l = QHBoxLayout(row_w); row_l.setContentsMargins(0,0,0,0)
        row_l.addWidget(self.certificate_path); row_l.addWidget(btn_cert)
        form.addRow("Fichier certificat", row_w)
        form.addRow(self.pass_ok)
        form.addRow("Résultats (JSON / texte)", self.results)
        form.addRow("Notes", self.notes)

        btns = QHBoxLayout()
        b_ok = QPushButton("Enregistrer"); b_ok.clicked.connect(self.accept)
        b_cancel = QPushButton("Annuler"); b_cancel.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

    def _choose_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le certificat (PDF)", "", "PDF (*.pdf);;Tous (*.*)")
        if path:
            self.certificate_path.setText(path)

    def data(self) -> Dict[str, Any]:
        return {
            "cal_date": self.cal_date.date().toString("yyyy-MM-dd"),
            "on_site": 1 if self.on_site.isChecked() else 0,
            "method": self.method.text().strip(),
            "certificate_id": self.certificate_id.text().strip(),
            "certificate_path": self.certificate_path.text().strip(),
            "pass_fail": 1 if self.pass_ok.isChecked() else 0,
            "results_json": self.results.toPlainText().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


# ---------- Widget principal ----------

class EtalonsWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self.repo = EtalonsRepository(self.db)
        self._init_ui()
        self.repo.recompute_status_all()
        self.reload()

    def _init_ui(self):
        self.setStyleSheet(f"""
            QWidget {{ background-color: #e0e0e0; }}
            QPushButton {{
                background-color: {THEME_PRIMARY}; color: #fff; border-radius: 8px;
                padding: 8px 16px; font-weight: bold; font-size: 14px; border: none;
            }}
            QPushButton:hover {{ background-color: {THEME_ACCENT}; color: {THEME_PRIMARY}; }}
            QTableWidget {{
                background-color: #fff;
                alternate-background-color: {THEME_ACCENT};
                gridline-color: {THEME_PRIMARY};
                selection-background-color: {THEME_ACCENT};
                selection-color: {THEME_PRIMARY};
                border: 2px solid {THEME_PRIMARY};
                font-size: 14px;
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background-color: {THEME_PRIMARY}; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }}
            QLineEdit, QComboBox {{
                background: #fff; border: 1px solid {THEME_ACCENT}; border-radius: 4px; padding: 4px 8px; font-size: 14px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border: 2px solid {THEME_PRIMARY}; }}
            QLabel {{ color: {THEME_PRIMARY}; font-weight: bold; font-size: 13px; }}
        """)

        # Top filters
        top = QWidget(); top_l = QHBoxLayout(top)
        self.cb_cat = QComboBox(); self.cb_cat.addItems(["Toutes"] + CATEGORIES)
        self.cb_status = QComboBox(); self.cb_status.addItems(["Tous", "OK", "Bientôt dû", "Bloqué"])
        self.search = QLineEdit(); self.search.setPlaceholderText("Recherche (nom, série, tags)…")
        b_new = QPushButton("Nouvel étalon…"); b_new.clicked.connect(self.on_new)
        b_edit = QPushButton("Éditer…"); b_edit.clicked.connect(self.on_edit)
        b_delete = QPushButton("Supprimer"); b_delete.clicked.connect(self.on_delete)
        b_block = QPushButton("Bloquer…"); b_block.clicked.connect(self.on_block)
        b_unblock = QPushButton("Débloquer"); b_unblock.clicked.connect(self.on_unblock)
        b_cal = QPushButton("Enregistrer étalonnage…"); b_cal.clicked.connect(self.on_new_cal)
        b_open_cert = QPushButton("Ouvrir certificat"); b_open_cert.clicked.connect(self.on_open_cert)
        b_export = QPushButton("Export CSV"); b_export.clicked.connect(self.on_export)
        b_refresh = QPushButton("↻"); b_refresh.clicked.connect(self.reload); b_refresh.setFixedWidth(36)

        for w in [QLabel("Catégorie"), self.cb_cat, QLabel("Statut"), self.cb_status, self.search,
                  b_new, b_edit, b_delete, b_block, b_unblock, b_cal, b_open_cert, b_export, b_refresh]:
            top_l.addWidget(w)
        self.cb_cat.currentTextChanged.connect(self.reload)
        self.cb_status.currentTextChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)

        # Status chips
        chips = QWidget(); chips_l = QHBoxLayout(chips); chips_l.setContentsMargins(0,0,0,0)
        self.chip_ok = QLabel(); self.chip_due = QLabel(); self.chip_block = QLabel()
        set_chip(self.chip_ok, "OK: 0", STATUS_COLORS["OK"])
        set_chip(self.chip_due, "Bientôt dû: 0", STATUS_COLORS["Bientôt dû"])
        set_chip(self.chip_block, "Bloqué: 0", STATUS_COLORS["Bloqué"])
        chips_l.addWidget(self.chip_ok); chips_l.addWidget(self.chip_due); chips_l.addWidget(self.chip_block); chips_l.addStretch(1)

        # Table
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Statut", "Série", "Nom", "Catégorie",
            "Dernier cal.", "Prochain cal.", "Jours restants",
            "Responsable", "Localisation", "ID Certificat", "Bloqué?"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_sel_change)

        # Bottom details
        bottom = QWidget(); bot_l = QFormLayout(bottom)
        self.det_status = QLabel("—"); set_status_pill(self.det_status, None)
        self.det_tags = QLabel("—")
        self.det_notes = QLabel("—")
        bot_l.addRow("Statut", self.det_status)
        bot_l.addRow("Tags", self.det_tags)
        bot_l.addRow("Notes", self.det_notes)

        # Guide
        guide = QGroupBox("Comment utiliser")
        gl = QVBoxLayout(guide)
        gtxt = QLabel(
            "• Filtrez par catégorie/statut ou recherchez par nom/série/tags.\n"
            "• « Nouvel étalon… » pour créer. Double-clic pour éditer.\n"
            "• « Enregistrer étalonnage… » met à jour automatiquement l’échéance.\n"
            "• Statut : OK / Bientôt dû (≤30j) / Bloqué (manuel ou échéance dépassée)."
        )
        gtxt.setWordWrap(True); gl.addWidget(gtxt)

        # Layout central
        lay = QVBoxLayout(self)
        lay.addWidget(top)
        lay.addWidget(chips)
        lay.addWidget(self.table, 1)
        lay.addWidget(guide)
        lay.addWidget(bottom)

        # Double click -> edit
        self.table.itemDoubleClicked.connect(lambda *_: self.on_edit())

    # --------- helpers ----------
    def _selected_id(self) -> Optional[int]:
        sel = self.table.selectedItems()
        if not sel: return None
        row = sel[0].row()
        try:
            return int(self.table.item(row, 0).text())
        except Exception:
            return None

    def _load_row_into_table(self, r: sqlite3.Row):
        row = self.table.rowCount()
        self.table.insertRow(row)
        nxt = r["next_cal_date"]
        days = days_until(nxt)
        owner_name = r["owner_name"] or ""
        blocked = "Oui" if int(r["blocked"] or 0) == 1 else "Non"
        vals = [
            str(r["id"]),
            r["status"] or "",
            r["serial"] or "",
            r["name"] or "",
            r["category"] or "",
            r["last_cal_date"] or "",
            nxt or "",
            ("" if days is None else str(days)),
            owner_name,
            r["location"] or "",
            r["certificate_id"] or "",
            blocked,
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            item.setTextAlignment(Qt.AlignCenter)
            if c == 1 and v:
                # Colorie cellule statut (texte blanc sur fond)
                col = STATUS_COLORS.get(v)
                if col:
                    item.setBackground(QColor(col))
                    item.setForeground(QColor("#ffffff"))
            self.table.setItem(row, c, item)

    def _fill_details(self, r: Optional[sqlite3.Row]):
        if not r:
            set_status_pill(self.det_status, None)
            self.det_tags.setText("—"); self.det_notes.setText("—")
            return
        set_status_pill(self.det_status, r["status"])
        self.det_tags.setText(r["tags"] or "—")
        self.det_notes.setText(r["notes"] or "—")

    def _update_chips(self, rows: List[sqlite3.Row]):
        counts = {"OK":0, "Bientôt dû":0, "Bloqué":0}
        for r in rows:
            s = r["status"] or "OK"
            if s in counts: counts[s] += 1
        set_chip(self.chip_ok, f"OK: {counts['OK']}", STATUS_COLORS["OK"])
        set_chip(self.chip_due, f"Bientôt dû: {counts['Bientôt dû']}", STATUS_COLORS["Bientôt dû"])
        set_chip(self.chip_block, f"Bloqué: {counts['Bloqué']}", STATUS_COLORS["Bloqué"])

    # --------- actions ----------
    def reload(self):
        self.table.setRowCount(0)
        rows = self.repo.list_standards(
            self.cb_cat.currentText(),
            self.cb_status.currentText(),
            self.search.text()
        )
        for r in rows:
            self._load_row_into_table(r)
        self._update_chips(rows)

        # Sélection auto 1ère ligne pour afficher le statut immédiatement
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        self._on_sel_change()

    def on_new(self):
        dlg = StandardDialog(self, repo=self.repo)
        if dlg.exec_() == QDialog.Accepted:
            try:
                sid = self.repo.add_standard(dlg.data())
                QMessageBox.information(self, "Étalon", f"Étalon #{sid} créé.")
                self.reload()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Création impossible : {e}")

    def on_edit(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Éditer", "Sélectionnez un étalon.")
            return
        row = self.repo.get_standard(sid)
        if not row: return
        dlg = StandardDialog(self, repo=self.repo, preset=dict(row))
        if dlg.exec_() == QDialog.Accepted:
            try:
                self.repo.update_standard(sid, dlg.data())
                QMessageBox.information(self, "Étalon", "Mise à jour enregistrée.")
                self.reload()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Mise à jour impossible : {e}")

    def on_delete(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Supprimer", "Sélectionnez un étalon.")
            return
        if QMessageBox.question(self, "Confirmation", "Supprimer cet étalon définitivement ?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.repo.delete_standard(sid)
            QMessageBox.information(self, "Suppression", "Étalon supprimé.")
            self.reload()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Suppression impossible : {e}")

    def on_block(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Blocage", "Sélectionnez un étalon.")
            return
        reason, ok = QInputDialog_getText(self, "Blocage", "Motif du blocage :", "")
        if not ok:
            return
        self.repo.set_block(sid, True, reason or "")
        QMessageBox.information(self, "Blocage", "Étalon bloqué.")
        self.reload()

    def on_unblock(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Déblocage", "Sélectionnez un étalon.")
            return
        self.repo.set_block(sid, False, "")
        QMessageBox.information(self, "Déblocage", "État mis à jour.")
        self.reload()

    def on_new_cal(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Étalonnage", "Sélectionnez un étalon.")
            return
        dlg = CalibrationDialog(self, default_date=today_str())
        if dlg.exec_() == QDialog.Accepted:
            try:
                self.repo.add_calibration(sid, dlg.data())
                QMessageBox.information(self, "Étalonnage", "Journal mis à jour.")
                self.reload()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer : {e}")

    def on_open_cert(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Certificat", "Sélectionnez un étalon.")
            return
        row = self.repo.get_standard(sid)
        path = row["certificate_path"]
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Certificat", "Aucun fichier de certificat trouvé.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", "etalons.csv", "CSV (*.csv)")
        if not path: return
        rows = self.repo.list_standards(self.cb_cat.currentText(), self.cb_status.currentText(), self.search.text())
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([
                "id","status","serial","name","category","manufacturer","model",
                "location","owner_id","owner_name","tags","interval_months","last_cal_date",
                "next_cal_date","blocked","block_reason","certificate_id","certificate_path","notes"
            ])
            for r in rows:
                w.writerow([
                    r["id"], r["status"], r["serial"], r["name"], r["category"], r["manufacturer"], r["model"],
                    r["location"], r["owner_id"], (r["owner_name"] or ""),
                    r["tags"], r["interval_months"], r["last_cal_date"],
                    r["next_cal_date"], r["blocked"], r["block_reason"], r["certificate_id"], r["certificate_path"],
                    (r["notes"] or "").replace("\n", " ")
                ])
        QMessageBox.information(self, "Export", f"Exporté : {path}")

    def _on_sel_change(self):
        """MAJ des détails quand la sélection change (corrige l'erreur d'attribut manquant)."""
        sid = self._selected_id()
        if sid is None:
            self._fill_details(None); return
        row = self.repo.get_standard(sid)
        self._fill_details(row)


# ----------- Petit helper (éviter import global QInputDialog) ----------
from PyQt5.QtWidgets import QInputDialog
def QInputDialog_getText(parent, title, label, text=""):
    return QInputDialog.getText(parent, title, label, QLineEdit.Normal, text)
