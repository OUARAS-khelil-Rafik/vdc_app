# etalons_manager.py
# -*- coding: utf-8 -*-
"""
Gestion d'Étalons – PyQt5 + SQLite3 (single file, copy-paste ready)

Points forts
------------
• Statuts simplifiés : OK / Bientôt dû / Bloqué (couleurs).
  - Bloqué = blocage manuel OU échéance dépassée (auto-blocage).
• Traçabilité : n° de série, modèle, fabricant, certificat, historique.
• Planification : dernier étalonnage, intervalle (mois), prochain étalonnage (auto).
• Gouvernance : blocage/déblocage avec motif, journal des étalonnages.
• Filtres : catégorie, statut, recherche (nom/série/tags), export CSV.
• UI épurée (Unités/Plage/Résolution/Labo/Incertitude/Traçabilité retirés).

Fichier DB : etalons.db (auto-créé, même dossier).
"""
import csv
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QDate, QUrl
from PyQt5.QtGui import QDesktopServices, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QComboBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QSpinBox,
    QCheckBox, QDateEdit, QDialog, QInputDialog, QGroupBox
)

# --------------------------- Helpers ---------------------------------

DATE_FMT = "%Y-%m-%d"
DUE_SOON_DAYS = 30

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
    "Bloqué": "#dc3545",   # on choisit rouge pour attirer l'attention
}


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


def set_pill(label: QLabel, status: Optional[str]):
    if not status:
        label.setText("—")
        label.setStyleSheet("QLabel { background:#999; color:white; padding:4px 8px; border-radius:10px; }")
        return
    color = STATUS_COLORS.get(status, "#17a2b8")
    label.setText(status)
    label.setStyleSheet(f"QLabel {{ background:{color}; color:white; padding:4px 8px; border-radius:10px; }}")


# --------------------------- Database ---------------------------------

class DB:
    def __init__(self, path: str = "etalons.db"):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.initialize()

    def initialize(self):
        c = self.conn.cursor()
        # Étalons (instruments)
        c.execute("""
        CREATE TABLE IF NOT EXISTS standards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial TEXT,
            name TEXT,
            category TEXT,
            manufacturer TEXT,
            model TEXT,
            location TEXT,        -- site / armoire
            owner TEXT,           -- responsable
            tags TEXT,            -- CSV
            interval_months INTEGER,
            last_cal_date TEXT,   -- YYYY-MM-DD
            next_cal_date TEXT,   -- auto
            status TEXT,          -- OK, Bientôt dû, Bloqué
            blocked INTEGER,      -- 0/1 (blocage manuel)
            block_reason TEXT,
            certificate_path TEXT,
            certificate_id TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """)
        # Journal des étalonnages
        c.execute("""
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            standard_id INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
            cal_date TEXT,
            due_date TEXT,
            on_site INTEGER,       -- 0 labo / 1 sur site
            method TEXT,
            certificate_id TEXT,
            certificate_path TEXT,
            pass_fail INTEGER,     -- conservé pour l'historique mais non utilisé pour le statut global
            results_json TEXT,
            notes TEXT,
            created_at TEXT
        )
        """)
        self.conn.commit()

    # -------- Standards CRUD --------
    def add_standard(self, data: Dict[str, Any]) -> int:
        now = today_str()
        data = data.copy()
        data.setdefault("tags", "")
        data.setdefault("certificate_path", "")
        data.setdefault("certificate_id", "")
        data["created_at"] = now
        data["updated_at"] = now
        data["next_cal_date"] = compute_next_due(data.get("last_cal_date"), int(data.get("interval_months") or 0))
        data["status"] = self._compute_status_rowlike(data)
        data["blocked"] = 1 if data.get("blocked") else 0
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
        if "last_cal_date" in data or "interval_months" in data:
            row = self.get_standard(sid)
            last = data.get("last_cal_date", row["last_cal_date"])
            interval = int(data.get("interval_months", row["interval_months"] or 0))
            data["next_cal_date"] = compute_next_due(last, interval)
        row = self.get_standard(sid)
        merged = dict(row) if row else {}
        merged.update(data)
        data["status"] = self._compute_status_rowlike(merged)
        keys = ", ".join([f"{k}=:{k}" for k in data.keys()])
        data["id"] = sid
        with self.conn:
            self.conn.execute(f"UPDATE standards SET {keys} WHERE id=:id", data)

    def get_standard(self, sid: int) -> Optional[sqlite3.Row]:
        cur = self.conn.execute("SELECT * FROM standards WHERE id=?", (sid,))
        return cur.fetchone()

    def list_standards(self, category: Optional[str], status: Optional[str],
                       search: str) -> List[sqlite3.Row]:
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
        # Tri: Bloqué > Bientôt dû > OK, puis prochaine date
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
            status = "Bloqué" if block else self._compute_status_rowlike(dict(row, blocked=0))
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

    # -------- Calibrations --------
    def add_calibration(self, sid: int, data: Dict[str, Any]):
        now = today_str()
        data = data.copy()
        data["created_at"] = now
        std = self.get_standard(sid)
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
            # Mise à jour de l'étalon
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

    # -------- Status logic (seulement 3 états) --------
    def _compute_status_rowlike(self, r: Dict[str, Any]) -> str:
        # 1) Blocage manuel prioritaire
        if int(r.get("blocked") or 0) == 1:
            return "Bloqué"
        # 2) Échéance dépassée → Bloqué (auto)
        nxt = r.get("next_cal_date")
        if nxt:
            dd = days_until(nxt)
            if dd is not None and dd < 0:
                return "Bloqué"
            # 3) Bientôt dû
            if dd is not None and dd <= DUE_SOON_DAYS:
                return "Bientôt dû"
        # 4) Sinon OK
        return "OK"


# --------------------------- Dialogs ----------------------------------

class StandardDialog(QDialog):
    """Créer / éditer un étalon (UI épurée)."""
    def __init__(self, parent=None, preset: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.setWindowTitle("Étalon")
        self.setModal(True)
        self.resize(680, 480)
        self.preset = preset or {}

        form = QFormLayout(self)

        # Champs essentiels
        self.serial = QLineEdit(self.preset.get("serial", ""))
        self.name = QLineEdit(self.preset.get("name", ""))
        self.category = QComboBox(); self.category.addItems([""] + CATEGORIES)
        if self.preset.get("category"): self.category.setCurrentText(self.preset["category"])
        self.manufacturer = QLineEdit(self.preset.get("manufacturer", ""))
        self.model = QLineEdit(self.preset.get("model", ""))
        self.location = QLineEdit(self.preset.get("location", ""))
        self.owner = QLineEdit(self.preset.get("owner", ""))
        self.tags = QLineEdit(self.preset.get("tags", ""))

        self.interval = QSpinBox(); self.interval.setRange(0, 120); self.interval.setValue(int(self.preset.get("interval_months") or 12))
        self.interval.setToolTip("Périodicité d'étalonnage en mois (0 = pas d'échéance).")

        self.last_cal = QDateEdit(calendarPopup=True); self.last_cal.setDisplayFormat("yyyy-MM-dd")
        if self.preset.get("last_cal_date"):
            self.last_cal.setDate(QDate.fromString(self.preset["last_cal_date"], "yyyy-MM-dd"))
        else:
            self.last_cal.setDate(QDate.currentDate())

        self.certificate_id = QLineEdit(self.preset.get("certificate_id", ""))
        self.certificate_path = QLineEdit(self.preset.get("certificate_path", ""))

        btn_cert = QPushButton("Choisir certificat…")
        btn_cert.clicked.connect(self._choose_cert)

        self.blocked = QCheckBox("Bloquer dès la création"); self.blocked.setChecked(bool(self.preset.get("blocked", False)))
        self.block_reason = QLineEdit(self.preset.get("block_reason", ""))

        self.notes = QPlainTextEdit(self.preset.get("notes", ""))

        # Guide rapide
        guide = QGroupBox("Guide rapide")
        gl = QVBoxLayout(guide)
        gtxt = QLabel("Remplir au minimum : Série, Nom, Catégorie, Intervalle, Dernier étalonnage.\n"
                      "Le prochain étalonnage est calculé automatiquement. Joignez le certificat si dispo.")
        gtxt.setWordWrap(True)
        gl.addWidget(gtxt)

        # Form layout
        form.addRow(guide)
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
        btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

    def _choose_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le certificat (PDF)", "", "PDF (*.pdf);;Tous (*.*)")
        if path:
            self.certificate_path.setText(path)

    def data(self) -> Dict[str, Any]:
        last = self.last_cal.date().toString("yyyy-MM-dd")
        return {
            "serial": self.serial.text().strip(),
            "name": self.name.text().strip(),
            "category": self.category.currentText().strip(),
            "manufacturer": self.manufacturer.text().strip(),
            "model": self.model.text().strip(),
            "location": self.location.text().strip(),
            "owner": self.owner.text().strip(),
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
    """Enregistrer un étalonnage (UI simplifiée)."""
    def __init__(self, parent=None, default_date: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Nouvel étalonnage")
        self.setModal(True)
        self.resize(600, 420)

        form = QFormLayout(self)
        self.cal_date = QDateEdit(calendarPopup=True); self.cal_date.setDisplayFormat("yyyy-MM-dd")
        if default_date:
            self.cal_date.setDate(QDate.fromString(default_date, "yyyy-MM-dd"))
        else:
            self.cal_date.setDate(QDate.currentDate())
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
        gtxt = QLabel("Renseignez la date, la méthode, cochez PASS si conforme, joignez le certificat si possible.")
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
        btns.addWidget(b_ok); btns.addWidget(b_cancel)
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


# --------------------------- Main Window ------------------------------

class EtalonsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestion des Étalons")
        self.resize(1200, 720)
        self.db = DB()

        # --- Top filters & actions ---
        top = QWidget(); top_l = QHBoxLayout(top)
        self.cb_cat = QComboBox(); self.cb_cat.addItems(["Toutes"] + CATEGORIES)
        self.cb_status = QComboBox(); self.cb_status.addItems(["Tous", "OK", "Bientôt dû", "Bloqué"])
        self.search = QLineEdit(); self.search.setPlaceholderText("Recherche (nom, série, tags)…")
        b_new = QPushButton("Nouvel étalon…"); b_new.clicked.connect(self.on_new)
        b_edit = QPushButton("Éditer…"); b_edit.clicked.connect(self.on_edit)
        b_block = QPushButton("Bloquer…"); b_block.clicked.connect(self.on_block)
        b_unblock = QPushButton("Débloquer"); b_unblock.clicked.connect(self.on_unblock)
        b_cal = QPushButton("Enregistrer étalonnage…"); b_cal.clicked.connect(self.on_new_cal)
        b_open_cert = QPushButton("Ouvrir certificat"); b_open_cert.clicked.connect(self.on_open_cert)
        b_export = QPushButton("Export CSV"); b_export.clicked.connect(self.on_export)
        b_refresh = QPushButton("↻"); b_refresh.clicked.connect(self.reload)

        for w in [QLabel("Catégorie"), self.cb_cat, QLabel("Statut"), self.cb_status, self.search,
                  b_new, b_edit, b_block, b_unblock, b_cal, b_open_cert, b_export, b_refresh]:
            top_l.addWidget(w)
        self.cb_cat.currentTextChanged.connect(self.reload)
        self.cb_status.currentTextChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)

        # --- Status summary chips (3) ---
        chips = QWidget(); chips_l = QHBoxLayout(chips); chips_l.setContentsMargins(0,0,0,0)
        self.chip_ok = QLabel(); self.chip_due = QLabel(); self.chip_block = QLabel()
        for lbl, txt, col in [
            (self.chip_ok, "OK", "#28a745"),
            (self.chip_due, "Bientôt dû", "#ffc107"),
            (self.chip_block, "Bloqué", "#dc3545"),
        ]:
            lbl.setText(f"{txt}: 0")
            lbl.setStyleSheet(f"QLabel {{ background:{col}; color:white; padding:2px 8px; border-radius:10px; }}")
            chips_l.addWidget(lbl)
        chips_l.addStretch(1)

        # --- Table ---
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Statut", "Série", "Nom", "Catégorie",
            "Dernier cal.", "Prochain cal.", "Jours restants",
            "Bloqué", "Responsable", "Localisation", "ID Certificat"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        # --- Bottom details ---
        bottom = QWidget(); bot_l = QFormLayout(bottom)
        self.det_status = QLabel("—"); set_pill(self.det_status, None)
        self.det_tags = QLabel("—")
        self.det_notes = QLabel("—")
        bot_l.addRow("Statut", self.det_status)
        bot_l.addRow("Tags", self.det_tags)
        bot_l.addRow("Notes", self.det_notes)

        # --- Guide d’usage (mini) ---
        guide = QGroupBox("Comment utiliser")
        gl = QVBoxLayout(guide)
        gtxt = QLabel(
            "• Filtrez par catégorie/statut ou recherchez par nom/série/tags.\n"
            "• « Nouvel étalon… » pour créer. Double-clic sur une ligne pour éditer.\n"
            "• « Enregistrer étalonnage… » met à jour automatiquement l’échéance.\n"
            "• Statut global coloré : OK / Bientôt dû (≤30j) / Bloqué (manuel ou échéance dépassée).\n"
            "• Ouvrez le PDF du certificat via le bouton dédié."
        )
        gtxt.setWordWrap(True); gl.addWidget(gtxt)

        # --- Central layout ---
        central = QWidget(); lay = QVBoxLayout(central)
        lay.addWidget(top)
        lay.addWidget(chips)
        lay.addWidget(self.table, 1)
        lay.addWidget(guide)
        lay.addWidget(bottom)
        self.setCentralWidget(central)

        self.table.itemSelectionChanged.connect(self._on_sel_change)

        # Initial load
        self.db.recompute_status_all()
        self.reload()

    # --------- UI helpers ----------
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
            blocked,
            r["owner"] or "",
            r["location"] or "",
            r["certificate_id"] or "",
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            if c == 1 and v:
                col = STATUS_COLORS.get(v)
                if col:
                    item.setBackground(QColor(col))
                    item.setForeground(QColor("#ffffff"))
            self.table.setItem(row, c, item)

    def _fill_details(self, r: Optional[sqlite3.Row]):
        if not r:
            set_pill(self.det_status, None)
            self.det_tags.setText("—")
            self.det_notes.setText("—")
            return
        set_pill(self.det_status, r["status"])
        self.det_tags.setText(r["tags"] or "—")
        self.det_notes.setText(r["notes"] or "—")

    def _update_chips(self, rows: List[sqlite3.Row]):
        counts = {"OK":0, "Bientôt dû":0, "Bloqué":0}
        for r in rows:
            s = r["status"] or "OK"
            if s in counts: counts[s] += 1
        self.chip_ok.setText(f"OK: {counts['OK']}")
        self.chip_due.setText(f"Bientôt dû: {counts['Bientôt dû']}")
        self.chip_block.setText(f"Bloqué: {counts['Bloqué']}")

    # --------- Actions -------------
    def reload(self):
        self.table.setRowCount(0)
        rows = self.db.list_standards(
            self.cb_cat.currentText(),
            self.cb_status.currentText(),
            self.search.text()
        )
        for r in rows:
            self._load_row_into_table(r)
        self._update_chips(rows)
        self._on_sel_change()

    def on_new(self):
        dlg = StandardDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            sid = self.db.add_standard(dlg.data())
            QMessageBox.information(self, "Étalon", f"Étalon #{sid} créé.")
            self.reload()

    def on_edit(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Éditer", "Sélectionnez un étalon.")
            return
        row = self.db.get_standard(sid)
        if not row: return
        dlg = StandardDialog(self, preset=dict(row))
        if dlg.exec_() == QDialog.Accepted:
            self.db.update_standard(sid, dlg.data())
            QMessageBox.information(self, "Étalon", "Mise à jour enregistrée.")
            self.reload()

    def _on_double_click(self, *args):
        self.on_edit()

    def on_block(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Blocage", "Sélectionnez un étalon.")
            return
        reason, ok = QInputDialog.getText(self, "Blocage", "Motif du blocage :", QLineEdit.Normal, "")
        if not ok:
            return
        self.db.set_block(sid, True, reason or "")
        QMessageBox.information(self, "Blocage", "Étalon bloqué.")
        self.reload()

    def on_unblock(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Déblocage", "Sélectionnez un étalon.")
            return
        self.db.set_block(sid, False, "")
        QMessageBox.information(self, "Déblocage", "Étalon débloqué.")
        self.reload()

    def on_new_cal(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Étalonnage", "Sélectionnez un étalon.")
            return
        dlg = CalibrationDialog(self, default_date=today_str())
        if dlg.exec_() == QDialog.Accepted:
            self.db.add_calibration(sid, dlg.data())
            QMessageBox.information(self, "Étalonnage", "Journal d'étalonnage mis à jour.")
            self.reload()

    def on_open_cert(self):
        sid = self._selected_id()
        if not sid:
            QMessageBox.information(self, "Certificat", "Sélectionnez un étalon.")
            return
        row = self.db.get_standard(sid)
        path = row["certificate_path"]
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Certificat", "Aucun fichier de certificat trouvé.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", "etalons.csv", "CSV (*.csv)")
        if not path: return
        rows = self.db.list_standards(self.cb_cat.currentText(), self.cb_status.currentText(), self.search.text())
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([
                "id","status","serial","name","category","manufacturer","model",
                "location","owner","tags","interval_months","last_cal_date",
                "next_cal_date","blocked","block_reason","certificate_id","certificate_path","notes"
            ])
            for r in rows:
                w.writerow([
                    r["id"], r["status"], r["serial"], r["name"], r["category"], r["manufacturer"], r["model"],
                    r["location"], r["owner"], r["tags"], r["interval_months"], r["last_cal_date"],
                    r["next_cal_date"], r["blocked"], r["block_reason"], r["certificate_id"], r["certificate_path"],
                    (r["notes"] or "").replace("\n", " ")
                ])
        QMessageBox.information(self, "Export", f"Exporté : {path}")

    def _on_sel_change(self):
        sid = self._selected_id()
        if not sid:
            self._fill_details(None); return
        row = self.db.get_standard(sid)
        self._fill_details(row)


# --------------------------- App entry --------------------------------

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = EtalonsWindow()
    win.show()
    sys.exit(app.exec_())
    
