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
    QCheckBox, QDateEdit, QDialog, QSizePolicy,
    QListWidget, QListWidgetItem
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

# ---------- Repository (utilise db.conn de l'app) ----------

# Repository adapté : ne crée plus les tables, utilise StandardManager du modèle


class StandardsRepository:
    def __init__(self, app_db, user_id: int = None):
        # app_db est Database() qui a .conn
        self.manager = StandardManager(db_path=app_db.db_path)
        self.conn = self.manager.conn
        self.conn.row_factory = sqlite3.Row
        self.user_id = user_id

    # --- Status logic ---
    def _compute_status(self, row_like: Dict[str, Any]) -> str:
        if int(row_like.get("blocked") or 0) == 1:
            return "Bloqué"
        nxt = row_like.get("next_cal_date")
        if not nxt:
            return "OK"
        dd = days_until(nxt)
        if dd is None:
            return "OK"
        if dd < 0:
            return "Bloqué"
        if dd <= DUE_SOON_DAYS:
            return "Bientôt dû"
        return "OK"

    def list_users_validated(self) -> List[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT id, full_name, role FROM users WHERE validate_user='Validé' ORDER BY full_name ASC"
        ).fetchall())

    def get_owner_names(self, owner_ids: Optional[str]) -> str:
        if not owner_ids:
            return ""
        # owner_ids can be int or CSV string
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

    def add_standard(self, data: Dict[str, Any]) -> int:
        now = today_str()
        data = data.copy()
        data.setdefault("tags", "")
        data.setdefault("certificate_path", "")
        data.setdefault("certificate_id", "")
        data["created_at"] = now
        data["updated_at"] = now
        data["next_cal_date"] = compute_next_due(data.get("last_cal_date"), int(data.get("interval_months") or 0))
        data["status"] = self._compute_status(data)
        data["blocked"] = 1 if data.get("blocked") else 0
        # Accept owner_id as list for multiple responsible
        owner_ids = data.get("owner_id")
        if isinstance(owner_ids, list):
            data["owner_id"] = ",".join(str(i) for i in owner_ids)
        with self.conn:
            self.manager.add_standard(data)
            row = self.conn.execute("SELECT id FROM standards WHERE serial=?", (data["serial"],)).fetchone()
            return row["id"] if row else None

    def update_standard(self, sid: int, data: Dict[str, Any]):
        now = today_str()
        row = self.get_standard(sid)
        merged = dict(row) if row else {}
        merged.update(data)
        if "last_cal_date" in data or "interval_months" in data:
            last = merged.get("last_cal_date")
            interval = int(merged.get("interval_months") or 0)
            merged["next_cal_date"] = compute_next_due(last, interval)
            data["next_cal_date"] = merged["next_cal_date"]
        merged["blocked"] = 1 if merged.get("blocked") else 0
        new_status = self._compute_status(merged)
        data["status"] = new_status
        data["updated_at"] = now
        # Accept owner_id as list for multiple responsible
        owner_ids = data.get("owner_id")
        if isinstance(owner_ids, list):
            data["owner_id"] = ",".join(str(i) for i in owner_ids)
        keys = ", ".join([f"{k}=:{k}" for k in data.keys()])
        with self.conn:
            self.conn.execute(f"UPDATE standards SET {keys} WHERE id=:id", dict(data, id=sid))

    def delete_standard(self, sid: int):
        self.manager.delete_standard(sid)

    def get_standard(self, sid: int) -> Optional[sqlite3.Row]:
        return self.manager.get_standard(sid)

    def list_standards(self, category: str, status: str, search: str) -> List[Dict[str, Any]]:
        q = """
        SELECT s.*,
            s.owner_id AS owner_ids
        FROM standards s
        WHERE 1=1
        """
        params: List[Any] = []
        if category and category.lower() not in ["toutes"]:
            q += " AND s.category=?"; params.append(category)
        if status and status.lower() not in ["tous"]:
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

        rows = self.conn.execute(q, params).fetchall()
        updated: List[Dict[str, Any]] = []
        for r in rows:
            row_dict = dict(r)
            row_dict["status"] = self._compute_status(row_dict)
            # Add all responsible names
            row_dict["owner_names"] = self.get_owner_names(row_dict.get("owner_id"))
            # For CSV export compatibility
            row_dict["owner_name"] = row_dict["owner_names"]
            updated.append(row_dict)
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

    def recompute_status_all(self):
        rows = self.conn.execute("SELECT * FROM standards").fetchall()
        with self.conn:
            for r in rows:
                new_s = self._compute_status(dict(r))
                if new_s != r["status"]:
                    self.conn.execute("UPDATE standards SET status=?, updated_at=? WHERE id=?",
                                      (new_s, today_str(), r["id"]))

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
    def __init__(self, db, user, repo: Optional[StandardsRepository] = None, preset: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.db = db
        self.user = user
        self.repo = repo
        self.preset = preset or {}
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Modifier étalon" if self.preset else "Nouvel étalon")
        self.setModal(True)
        self.resize(500, 420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #f0f0f0; }}
            QLineEdit, QDateEdit, QComboBox {{
                background: #fff; border: 1px solid {THEME_ACCENT}; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }}
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus {{ border: 2px solid {THEME_PRIMARY}; }}
            QLabel {{ color: {THEME_PRIMARY}; font-weight: bold; font-size: 13px; background: transparent; }}
            QPushButton {{
                background-color: {THEME_ACCENT}; color: {THEME_PRIMARY}; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME_PRIMARY}; color: #fff; }}
            QPushButton:pressed {{ background-color: #14406e; }}
        """)

        self.input_serial = QLineEdit(self.preset.get("serial", ""))
        self.input_name = QLineEdit(self.preset.get("name", ""))
        self.input_category = QComboBox()
        self.input_category.addItems(CATEGORIES)
        if self.preset.get("category"):
            idx = self.input_category.findText(self.preset["category"])
            if idx >= 0:
                self.input_category.setCurrentIndex(idx)
        self.input_manufacturer = QLineEdit(self.preset.get("manufacturer", ""))
        self.input_model = QLineEdit(self.preset.get("model", ""))
        self.input_location = QLineEdit(self.preset.get("location", ""))

        # Responsable depuis BDD (multi-sélection)
        self.input_owner = QListWidget()
        self.input_owner.setSelectionMode(QListWidget.MultiSelection)
        self._users_map: List[Tuple[int, str]] = []
        if self.repo:
            users = self.repo.list_users_validated()
            for u in users:
                item = QListWidgetItem(f"{u['full_name']} ({u['role']})")
                item.setData(Qt.UserRole, int(u["id"]))
                self.input_owner.addItem(item)
                self._users_map.append((int(u["id"]), u["full_name"]))
        # Sélectionne les responsables si preset
        if self.preset.get("owner_id"):
            owner_ids = []
            if isinstance(self.preset["owner_id"], int):
                owner_ids = [self.preset["owner_id"]]
            elif isinstance(self.preset["owner_id"], str):
                owner_ids = [int(x) for x in self.preset["owner_id"].split(",") if x.strip().isdigit()]
            for i in range(self.input_owner.count()):
                item = self.input_owner.item(i)
                if item.data(Qt.UserRole) in owner_ids:
                    item.setSelected(True)

        self.input_tags = QLineEdit(self.preset.get("tags", ""))
        self.input_interval = QSpinBox()
        self.input_interval.setRange(0, 120)
        self.input_interval.setValue(int(self.preset.get("interval_months") or 12))
        self.input_last_cal = QDateEdit(calendarPopup=True)
        self.input_last_cal.setDisplayFormat("yyyy-MM-dd")
        if self.preset.get("last_cal_date"):
            self.input_last_cal.setDate(QDate.fromString(self.preset["last_cal_date"], "yyyy-MM-dd"))
        else:
            self.input_last_cal.setDate(QDate.currentDate())
        self.input_certificate_id = QLineEdit(self.preset.get("certificate_id", ""))
        self.input_certificate_path = QLineEdit(self.preset.get("certificate_path", ""))
        btn_cert = QPushButton("Choisir certificat…")
        btn_cert.clicked.connect(self._choose_cert)

        # Blocage : affichage conditionnel
        self.input_block_reason = QLineEdit(self.preset.get("block_reason", ""))
        self.input_block_reason.setVisible(False)
        self.block_reason_label = QLabel("Motif de blocage :")
        self.block_reason_label.setVisible(False)

        # Affiche le motif de blocage uniquement si modification ET bloqué
        if self.preset and int(self.preset.get("blocked", 0)) == 1:
            self.input_block_reason.setVisible(True)
            self.block_reason_label.setVisible(True)
            self.input_block_reason.setText(self.preset.get("block_reason", ""))

        self.input_notes = QPlainTextEdit(self.preset.get("notes", ""))

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("N° de série :", self.input_serial)
        form_layout.addRow("Nom / Désignation :", self.input_name)
        form_layout.addRow("Catégorie :", self.input_category)
        form_layout.addRow("Fabricant :", self.input_manufacturer)
        form_layout.addRow("Modèle :", self.input_model)
        form_layout.addRow("Localisation :", self.input_location)
        form_layout.addRow("Responsable(s) :", self.input_owner)
        form_layout.addRow("Tags (CSV) :", self.input_tags)
        form_layout.addRow("Intervalle (mois) :", self.input_interval)
        form_layout.addRow("Dernier étalonnage :", self.input_last_cal)
        form_layout.addRow("ID Certificat :", self.input_certificate_id)
        row_w = QWidget()
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.addWidget(self.input_certificate_path)
        row_l.addWidget(btn_cert)
        form_layout.addRow("Fichier certificat :", row_w)
        # Blocage : affichage conditionnel
        form_layout.addRow(self.block_reason_label, self.input_block_reason)
        form_layout.addRow("Notes :", self.input_notes)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Modifier" if self.preset else "Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_standard)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 0)
        self.setLayout(main_layout)

    def _choose_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir le certificat (PDF)", "", "PDF (*.pdf);;Tous (*.*)")
        if path:
            self.input_certificate_path.setText(path)

    def save_standard(self):
        serial = self.input_serial.text().strip()
        name = self.input_name.text().strip()
        category = self.input_category.currentText().strip()
        manufacturer = self.input_manufacturer.text().strip()
        model = self.input_model.text().strip()
        location = self.input_location.text().strip()
        tags = self.input_tags.text().strip()
        interval_months = int(self.input_interval.value())
        last_cal_date = self.input_last_cal.date().toString("yyyy-MM-dd")
        certificate_id = self.input_certificate_id.text().strip()
        certificate_path = self.input_certificate_path.text().strip()
        blocked = False  # Toujours False car le checkbox est supprimé
        block_reason = ""
        # Si modification et bloqué, on prend le motif
        if self.preset and int(self.preset.get("blocked", 0)) == 1:
            block_reason = self.input_block_reason.text().strip()
        notes = self.input_notes.toPlainText().strip()
        owner_ids = [item.data(Qt.UserRole) for item in self.input_owner.selectedItems()]
        if not serial or not name or not category or not interval_months or not last_cal_date or not owner_ids:
            QMessageBox.warning(self, "Champs manquants", "Tous les champs sont obligatoires, y compris au moins un responsable.", QMessageBox.Ok)
            return

        # Vérification existence dans la base (par numéro de série)
        if self.repo:
            # Si création (pas preset), on vérifie si le serial existe déjà
            if not self.preset:
                existing = self.repo.conn.execute("SELECT id FROM standards WHERE serial=?", (serial,)).fetchone()
                if existing:
                    QMessageBox.warning(self, "Déjà existe", "Un étalon avec ce numéro de série existe déjà.", QMessageBox.Ok)
                    return
            # Si édition, on vérifie si le serial existe pour un autre id
            else:
                existing = self.repo.conn.execute("SELECT id FROM standards WHERE serial=? AND id<>?", (serial, self.preset["id"])).fetchone()
                if existing:
                    QMessageBox.warning(self, "Déjà existe", "Un autre étalon avec ce numéro de série existe déjà.", QMessageBox.Ok)
                    return

        data = {
            "serial": serial,
            "name": name,
            "category": category,
            "manufacturer": manufacturer,
            "model": model,
            "location": location,
            "owner_id": owner_ids,  # <-- Pass all selected ids as a list
            "tags": tags,
            "interval_months": interval_months,
            "last_cal_date": last_cal_date,
            "blocked": blocked,
            "block_reason": block_reason,
            "certificate_path": certificate_path,
            "certificate_id": certificate_id,
            "notes": notes,
        }
        try:
            if self.preset:
                self.repo.update_standard(self.preset["id"], data)
            else:
                self.repo.add_standard(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de {'modifier' if self.preset else 'créer'} l'étalon : {e}", QMessageBox.Ok)

    def data(self) -> Dict[str, Any]:
        serial = self.input_serial.text().strip()
        name = self.input_name.text().strip()
        category = self.input_category.currentText().strip()
        manufacturer = self.input_manufacturer.text().strip()
        model = self.input_model.text().strip()
        location = self.input_location.text().strip()
        tags = self.input_tags.text().strip()
        interval_months = int(self.input_interval.value())
        last_cal_date = self.input_last_cal.date().toString("yyyy-MM-dd")
        certificate_id = self.input_certificate_id.text().strip()
        certificate_path = self.input_certificate_path.text().strip()
        blocked = False  # Toujours False car le checkbox est supprimé
        block_reason = ""
        if self.preset and int(self.preset.get("blocked", 0)) == 1:
            block_reason = self.input_block_reason.text().strip()
        notes = self.input_notes.toPlainText().strip()
        owner_ids = [item.data(Qt.UserRole) for item in self.input_owner.selectedItems()]
        return {
            "serial": serial,
            "name": name,
            "category": category,
            "manufacturer": manufacturer,
            "model": model,
            "location": location,
            "owner_id": owner_ids,  # <-- Pass all selected ids as a list
            "tags": tags,
            "interval_months": interval_months,
            "last_cal_date": last_cal_date,
            "blocked": blocked,
            "block_reason": block_reason,
            "certificate_path": certificate_path,
            "certificate_id": certificate_id,
            "notes": notes,
        }
class CalibrationDialog(QDialog):
    """Journal d'étalonnage (minimal)."""
    def __init__(self, parent=None, default_date: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Nouvel étalonnage")
        self.setModal(True)
        self.resize(500, 320)
        self.setStyleSheet(f"""
            QDialog {{ background-color: #f0f0f0; }}
            QLineEdit, QDateEdit {{
                background: #fff; border: 1px solid {THEME_ACCENT}; border-radius: 4px; padding: 4px 8px; font-size: 14px;
            }}
            QLineEdit:focus, QDateEdit:focus {{ border: 2px solid {THEME_PRIMARY}; }}
            QLabel {{ color: {THEME_PRIMARY}; font-weight: bold; font-size: 13px; background: transparent; }}
            QPushButton {{
                background-color: {THEME_ACCENT}; color: {THEME_PRIMARY}; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME_PRIMARY}; color: #fff; }}
            QPushButton:pressed {{ background-color: #14406e; }}
        """)

        self.input_cal_date = QDateEdit(calendarPopup=True)
        self.input_cal_date.setDisplayFormat("yyyy-MM-dd")
        self.input_cal_date.setDate(QDate.fromString(default_date, "yyyy-MM-dd") if default_date else QDate.currentDate())
        self.input_on_site = QCheckBox("Étalonnage sur site")
        self.input_method = QLineEdit()
        self.input_certificate_id = QLineEdit()
        self.input_certificate_path = QLineEdit()
        btn_cert = QPushButton("Joindre certificat…")
        btn_cert.clicked.connect(self._choose_cert)
        self.input_pass_ok = QCheckBox("Conforme (PASS)")
        self.input_results = QPlainTextEdit()
        self.input_notes = QPlainTextEdit()

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Date d'étalonnage :", self.input_cal_date)
        form_layout.addRow(self.input_on_site)
        form_layout.addRow("Méthode :", self.input_method)
        form_layout.addRow("ID Certificat :", self.input_certificate_id)
        row_w = QWidget()
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.addWidget(self.input_certificate_path)
        row_l.addWidget(btn_cert)
        form_layout.addRow("Fichier certificat :", row_w)
        form_layout.addRow(self.input_pass_ok)
        form_layout.addRow("Résultats (JSON / texte) :", self.input_results)
        form_layout.addRow("Notes :", self.input_notes)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 0)
        self.setLayout(main_layout)

    def _choose_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Joindre le certificat (PDF)", "", "PDF (*.pdf);;Tous (*.*)")
        if path:
            self.input_certificate_path.setText(path)

    def data(self) -> Dict[str, Any]:
        return {
            "cal_date": self.input_cal_date.date().toString("yyyy-MM-dd"),
            "on_site": 1 if self.input_on_site.isChecked() else 0,
            "method": self.input_method.text().strip(),
            "certificate_id": self.input_certificate_id.text().strip(),
            "certificate_path": self.input_certificate_path.text().strip(),
            "pass_fail": 1 if self.input_pass_ok.isChecked() else 0,
            "results_json": self.input_results.toPlainText().strip(),
            "notes": self.input_notes.toPlainText().strip(),
        }


# ---------- Widget principal ----------

class StandardsTable(QTableWidget):
    HEADERS = [
        "Série", "Nom", "Catégorie",
        "Dernier étalonnage", "Prochain étalonnage", "Jours restants",
        "Responsable(s)", "Localisation", "Tag", "Statut", "Actions"
    ]
    COLUMNS = [
        "serial", "name", "category",
        "last_cal_date", "next_cal_date", "days_remaining",
        "owner_names", "location", "tags", "status"
    ]

    # Default column widths (pixels) for a nice initial layout
    DEFAULT_COLUMN_WIDTHS = [120, 120, 120, 110, 120, 80, 140, 120, 120, 80, 80]
    DEFAULT_ROW_HEIGHT = 36

    def __init__(self, parent=None, user=None):
        super().__init__(0, len(self.HEADERS), parent)
        self.user = user
        self.show_actions = True
        if self.user and self.user.get("role") in ("Technicien", "Technicien responsable"):
            self.show_actions = False
        headers = self.HEADERS if self.show_actions else self.HEADERS[:-1]
        headers_wrapped = [h.replace(" ", "\n") if len(h) > 12 else h for h in headers]
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers_wrapped)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.SingleSelection)
        self.setEditTriggers(self.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.setWordWrap(True)
        # Custom scroll bar style
        self.setStyleSheet("""
            QTableWidget {
                background-color: #fff;
                gridline-color: #1c5ea3;
                border: 2px solid #1c5ea3; 
                font-size: 13px;
                border-radius: 8px;
                color: #000;
                font-weight: bold;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #e0e0e0;
                border-radius: 6px;
                width: 12px;
                margin: 2px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #b8d5ed;
                border-radius: 6px;
                min-height: 30px;
                min-width: 30px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
                border: none;
            }
        """)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)
        self._restore_default_sizes()

    def _restore_default_sizes(self):
        # Set default column widths and row heights
        for col, width in enumerate(self.DEFAULT_COLUMN_WIDTHS[:self.columnCount()]):
            self.setColumnWidth(col, width)
        for row in range(self.rowCount()):
            self.setRowHeight(row, self.DEFAULT_ROW_HEIGHT)

    def populate(self, rows):
        self.setRowCount(len(rows))
        icon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icons"))
        for i, r in enumerate(rows):
            r = dict(r)
            days = days_until(r.get("next_cal_date"))
            owner_ids = r.get("owner_id")
            owner_names = ""
            if owner_ids:
                if isinstance(owner_ids, int):
                    ids = [owner_ids]
                elif isinstance(owner_ids, str):
                    ids = [int(x) for x in owner_ids.split(",") if x.strip().isdigit()]
                else:
                    ids = []
                names = []
                if ids:
                    db_conn = self.parent().repo.conn
                    q = f"SELECT full_name FROM users WHERE id IN ({','.join(['?']*len(ids))})"
                    res = db_conn.execute(q, ids).fetchall()
                    names = [row["full_name"] for row in res]
                owner_names = ", ".join(names)
            r["owner_names"] = owner_names

            for col, key in enumerate(self.COLUMNS):
                if key == "days_remaining":
                    value = "" if days is None else str(days)
                else:
                    value = r.get(key, "")
                if isinstance(value, str) and len(value) > 30:
                    value = self._wrap_text(value, 30)
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(item.flags() | Qt.TextWordWrap)
                if key == "status":
                    value = r.get(key, "")
                    if value == "OK":
                        item.setData(Qt.BackgroundRole, QColor("#4CAF50"))
                        item.setData(Qt.TextColorRole, QColor("#ffffff"))
                    elif value == "Bientôt dû":
                        item.setData(Qt.BackgroundRole, QColor("#FFC107"))
                        item.setData(Qt.TextColorRole, QColor("#000000"))
                    elif value == "Bloqué":
                        item.setData(Qt.BackgroundRole, QColor("#F44336"))
                        item.setData(Qt.TextColorRole, QColor("#ffffff"))
                if col == 0:
                    item.setData(Qt.UserRole, r.get('id'))
                self.setItem(i, col, item)
            if self.show_actions:
                action_widget = QWidget()
                h_layout = QHBoxLayout(action_widget)
                h_layout.setContentsMargins(0, 0, 0, 0)
                h_layout.setSpacing(5)
                h_layout.addStretch()
                btn_block = QPushButton()
                btn_block.setIcon(QIcon(os.path.join(icon_dir, "bloquer.png")))
                btn_block.setToolTip("Bloquer l'étalon")
                btn_block.setFixedSize(28, 28)
                btn_block.setStyleSheet("""
                    QPushButton {
                        border: none;
                        background: transparent;
                    }
                    QPushButton:focus, QPushButton:hover {
                        background: #e6f0fa;
                    }
                """)
                btn_block.setEnabled(int(r.get("blocked", 0)) == 0)
                btn_block.clicked.connect(lambda _, sid=r["id"]: self.parent().on_block_row(sid))
                btn_unblock = QPushButton()
                btn_unblock.setIcon(QIcon(os.path.join(icon_dir, "debloquer.png")))
                btn_unblock.setToolTip("Débloquer l'étalon")
                btn_unblock.setFixedSize(28, 28)
                btn_unblock.setStyleSheet("""
                    QPushButton {
                        border: none;
                        background: transparent;
                    }
                    QPushButton:focus, QPushButton:hover {
                        background: #e6f0fa;
                    }
                """)
                btn_unblock.setEnabled(int(r.get("blocked", 0)) == 1)
                btn_unblock.clicked.connect(lambda _, sid=r["id"]: self.parent().on_unblock_row(sid))
                btn_cert = QPushButton()
                btn_cert.setIcon(QIcon(os.path.join(icon_dir, "certificat.png")))
                btn_cert.setToolTip("Ouvrir certificat PDF")
                btn_cert.setFixedSize(28, 28)
                btn_cert.setStyleSheet("""
                    QPushButton {
                        border: none;
                        background: transparent;
                    }
                    QPushButton:focus, QPushButton:hover {
                        background: #e6f0fa;
                    }
                """)
                cert_path = r.get("certificate_path", "")
                btn_cert.setEnabled(bool(cert_path and os.path.exists(cert_path)))
                btn_cert.clicked.connect(lambda _, path=cert_path: QDesktopServices.openUrl(QUrl.fromLocalFile(path)) if path and os.path.exists(path) else None)
                h_layout.addWidget(btn_block)
                h_layout.addWidget(btn_unblock)
                h_layout.addWidget(btn_cert)
                h_layout.addStretch()
                action_widget.setLayout(h_layout)
                self.setCellWidget(i, len(self.COLUMNS), action_widget)
                self.setRowHeight(i, self.DEFAULT_ROW_HEIGHT)
        self._restore_default_sizes()

    def _wrap_text(self, text, width):
        return "\n".join(textwrap.wrap(text, width=width))

    def get_selected_standard_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        return item.data(Qt.UserRole) if item else None

    def hideEvent(self, event):
        # Restore default sizes when the widget is hidden (e.g., page change or close)
        self._restore_default_sizes()
        super().hideEvent(event)

    def showEvent(self, event):
        # Restore default sizes when the widget is shown
        self._restore_default_sizes()
        super().showEvent(event)
class EtalonsWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self.repo = StandardsRepository(self.db, user_id=user.get("id") if user else None)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME_PRIMARY}; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 14px; border: none;
            }}
            QPushButton:hover {{ background-color: {THEME_ACCENT}; color: {THEME_PRIMARY}; }}
            QTableWidget {{
                background-color: #fff; 
                gridline-color: {THEME_PRIMARY};
                selection-color: {THEME_PRIMARY};
                border: 2px solid {THEME_PRIMARY}; 
                font-size: 13px;
                font-weight: bold;
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

        # Filtres
        self.filter_cat_label = QLabel("Catégorie :")
        self.filter_cat_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #1c5ea3; background: transparent;")
        self.filter_cat_combo = QComboBox()
        self.filter_cat_combo.addItems(["Toutes"] + CATEGORIES)
        self.filter_cat_combo.setToolTip("Filtrer par catégorie")
        self.filter_cat_combo.setFixedHeight(28)
        self.filter_cat_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.filter_status_label = QLabel("Statut :")
        self.filter_status_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #1c5ea3; background: transparent;")
        self.filter_status_combo = QComboBox()
        self.filter_status_combo.addItems(["Tous", "OK", "Bientôt dû", "Bloqué"])
        self.filter_status_combo.setToolTip("Filtrer par statut")
        self.filter_status_combo.setFixedHeight(28)
        self.filter_status_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.filter_status_combo.setStyleSheet("""
            QComboBox {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QComboBox:focus { border: 2px solid #1c5ea3; }
        """)

        self.filter_search_label = QLabel("Recherche :")
        self.filter_search_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #1c5ea3; background: transparent;")
        self.filter_search_text = QLineEdit()
        self.filter_search_text.setPlaceholderText("Nom, série, tags…")
        self.filter_search_text.setToolTip("Recherche")
        self.filter_search_text.setFixedHeight(28)
        self.filter_search_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.filter_cat_combo.currentTextChanged.connect(self.reload)
        self.filter_status_combo.currentTextChanged.connect(self.reload)
        self.filter_search_text.textChanged.connect(self.reload)

        # Bouton d'aide (icon à droite des filtres)
        icon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icons"))
        self.btn_help = QPushButton()
        self.btn_help.setIcon(QIcon(os.path.join(icon_dir, "aide.png")))
        self.btn_help.setToolTip("Afficher le guide d'utilisation")
        self.btn_help.setFixedSize(36, 36)
        self.btn_help.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
            }
            QPushButton:focus, QPushButton:hover {
                background: #e6f0fa;
            }
        """)
        self.btn_help.clicked.connect(self.show_guide)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        filter_layout.addWidget(self.filter_cat_label)
        filter_layout.addWidget(self.filter_cat_combo)
        filter_layout.addWidget(self.filter_status_label)
        filter_layout.addWidget(self.filter_status_combo)
        filter_layout.addWidget(self.filter_search_label)
        filter_layout.addWidget(self.filter_search_text)
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_help)  # Ajout du bouton aide à droite

        # Table setup
        self.table = StandardsTable(self, user=self.user)
        self.table.setFocusPolicy(Qt.NoFocus)

        self.btn_add = QPushButton("Ajouter Étalon")
        self.btn_add.setToolTip("Ajouter un étalon")
        self.btn_add.setFixedHeight(36)

        self.btn_edit = QPushButton("Modifier Étalon")
        self.btn_edit.setToolTip("Modifier l'étalon sélectionné")
        self.btn_edit.setFixedHeight(36)

        self.btn_delete = QPushButton("Supprimer Étalon")
        self.btn_delete.setToolTip("Supprimer l'étalon sélectionné")
        self.btn_delete.setFixedHeight(36)

        self.btn_cal = QPushButton("Enregistrer Étalonnage")
        self.btn_cal.setToolTip("Ajouter un étalonnage")
        self.btn_cal.setFixedHeight(36)

        self.btn_export = QPushButton("Exporter en CSV")
        self.btn_export.setToolTip("Exporter la liste en CSV")
        self.btn_export.setFixedHeight(36)

        self.btn_add.clicked.connect(self.on_new)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_cal.clicked.connect(self.on_new_cal)
        self.btn_export.clicked.connect(self.on_export)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        if self.user.get("role") not in ("Technicien", "Technicien responsable"):
            btn_layout.addWidget(self.btn_add)
            btn_layout.addWidget(self.btn_edit)
            btn_layout.addWidget(self.btn_delete)
            btn_layout.addWidget(self.btn_cal)
            btn_layout.addWidget(self.btn_export)
        btn_layout.addStretch()

        lay = QVBoxLayout(self)
        lay.addLayout(filter_layout)
        lay.addWidget(self.table, 1)
        lay.addLayout(btn_layout)

        self.table.itemDoubleClicked.connect(lambda *_: self.on_edit())

        self.repo.recompute_status_all()
        self.reload()

    def show_guide(self):
        msg = (
            "• Filtrez par catégorie/statut ou recherchez par nom/série/tags.\n"
            "• « Nouvel étalon… » pour créer. Double-clic pour éditer.\n"
            "• « Enregistrer étalonnage… » met à jour automatiquement l’échéance.\n"
            "• Statut : OK / Bientôt dû (≤30j) / Bloqué (manuel ou échéance dépassée)."
        )
        QMessageBox.information(self, "Guide d'utilisation", msg)

    def reload(self):
        self.table.setRowCount(0)
        rows = self.repo.list_standards(
            self.filter_cat_combo.currentText(),
            self.filter_status_combo.currentText(),
            self.filter_search_text.text()
        )
        self.table.populate(rows)
        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def on_new(self):
        dlg = StandardDialog(self.db, self.user, repo=self.repo)
        if dlg.exec_() == QDialog.Accepted:
            try:
                sid = self.repo.add_standard(dlg.data())
                QMessageBox.information(self, "Étalon", f"Étalon #{sid} créé.")
                self.reload()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Création impossible : {e}")

    def on_edit(self):
        sid = self.table.get_selected_standard_id()
        if not sid:
            QMessageBox.information(self, "Éditer", "Sélectionnez un étalon.")
            return
        row = self.repo.get_standard(sid)
        if not row: return
        dlg = StandardDialog(self.db, self.user, repo=self.repo, preset=dict(row))
        if dlg.exec_() == QDialog.Accepted:
            try:
                self.repo.update_standard(sid, dlg.data())
                QMessageBox.information(self, "Étalon", "Mise à jour enregistrée.")
                self.reload()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Mise à jour impossible : {e}")

    def on_delete(self):
        sid = self.table.get_selected_standard_id()
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

    def on_new_cal(self):
        sid = self.table.get_selected_standard_id()
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

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", "etalons.csv", "CSV (*.csv)")
        if not path: return
        rows = self.repo.list_standards(self.filter_cat_combo.currentText(), self.filter_status_combo.currentText(), self.filter_search_text.text())
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

    def on_export_row(self, sid):
        row = self.repo.get_standard(sid)
        if not row:
            QMessageBox.warning(self, "Export", "Impossible d'exporter cet étalon.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter cet étalon en CSV", f"etalons_{sid}.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([
                "id","status","serial","name","category","manufacturer","model",
                "location","owner_id","owner_name","tags","interval_months","last_cal_date",
                "next_cal_date","blocked","block_reason","certificate_id","certificate_path","notes"
            ])
            w.writerow([
                row["id"], row["status"], row["serial"], row["name"], row["category"], row["manufacturer"], row["model"],
                row["location"], row["owner_id"], (row["owner_name"] or ""),
                row["tags"], row["interval_months"], row["last_cal_date"],
                row["next_cal_date"], row["blocked"], row["block_reason"], row["certificate_id"], row["certificate_path"],
                (row["notes"] or "").replace("\n", " ")
            ])
        QMessageBox.information(self, "Export", f"Exporté : {path}")

    def on_block_row(self, sid):
        row = self.repo.get_standard(sid)
        if not row or int(row["blocked"] or 0) == 1:
            return
        reason, ok = QInputDialog_getText(self, "Blocage", "Motif du blocage :", "")
        if not ok:
            return
        self.repo.set_block(sid, True, reason or "")
        QMessageBox.information(self, "Blocage", "Étalon bloqué.")
        self.reload()

    def on_unblock_row(self, sid):
        row = self.repo.get_standard(sid)
        if not row or int(row["blocked"] or 0) == 0:
            return
        self.repo.set_block(sid, False, "")
        QMessageBox.information(self, "Déblocage", "État mis à jour.")
        self.reload()

# ----------- Petit helper (éviter import global QInputDialog) ----------
from PyQt5.QtWidgets import QInputDialog
from models.standardmanager import StandardManager
import textwrap
def QInputDialog_getText(parent, title, label, text=""):
    return QInputDialog.getText(parent, title, label, QLineEdit.Normal, text)
