# gui/thresholds.py

"""
Fenêtre de gestion des seuils ISO et personnalisés pour l’application VDC Engineering MVP.
Gère l’affichage, l’ajout, la modification et la suppression des seuils selon le rôle de l’utilisateur.
Gère les seuils ISO prédéfinis selon la norme ISO 14644-1 et les seuils personnalisés.
Gère la persistance des seuils dans une base de données SQLite.
Gère les interactions utilisateur via une interface graphique PyQt5.
"""


from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy,
    QPushButton, QFormLayout, QLineEdit, QComboBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from models.thresholdmanager import ThresholdManager
import sqlite3
import os

# Predefined ISO 14644-1 thresholds (µm/m³ for particles, °C and %)
# SEUILS ISO 14644-1:2015 – Tableau 1 (concentrations maximales particules/m³)
DEFAULT_ISO_THRESHOLDS = {
    "ISO 1": {
        "Particles ≥0.1 µm": 10
    },
    "ISO 2": {
        "Particles ≥0.1 µm": 100,
        "Particles ≥0.2 µm": 24,
        "Particles ≥0.3 µm": 10
    },
    "ISO 3": {
        "Particles ≥0.1 µm": 1_000,
        "Particles ≥0.2 µm": 237,
        "Particles ≥0.3 µm": 102,
        "Particles ≥0.5 µm": 35
    },
    "ISO 4": {
        "Particles ≥0.1 µm": 10_000,
        "Particles ≥0.2 µm": 2_370,
        "Particles ≥0.3 µm": 1_020,
        "Particles ≥0.5 µm": 352,
        "Particles ≥1 µm": 83
    },
    "ISO 5": {
        "Particles ≥0.1 µm": 100_000,
        "Particles ≥0.2 µm": 23_700,
        "Particles ≥0.3 µm": 10_200,
        "Particles ≥0.5 µm": 3_520,
        "Particles ≥1 µm": 832
    },
    "ISO 6": {
        "Particles ≥0.1 µm": 1_000_000,
        "Particles ≥0.2 µm": 237_000,
        "Particles ≥0.3 µm": 102_000,
        "Particles ≥0.5 µm": 35_200,
        "Particles ≥1 µm": 8_320,
        "Particles ≥5 µm": 293
    },
    "ISO 7": {
        "Particles ≥0.5 µm": 352_000,
        "Particles ≥1 µm": 83_200,
        "Particles ≥5 µm": 2_930
    },
    "ISO 8": {
        "Particles ≥0.5 µm": 3_520_000,
        "Particles ≥1 µm": 832_000,
        "Particles ≥5 µm": 29_300
    },
    "ISO 9": {
        "Particles ≥0.5 µm": 35_200_000,
        "Particles ≥1 µm": 8_320_000,
        "Particles ≥5 µm": 293_000
    },
}


DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data/vdc.db')

def ensure_thresholds_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS thresholds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iso_name TEXT, -- ISO 1, ISO 2, etc. (NULL si seuil personnalisé)
            test_name TEXT NOT NULL,
            value REAL,
            UNIQUE(iso_name, test_name)
        )
    """)
    conn.commit()
    # Populate with defaults if empty
    c.execute("SELECT COUNT(*) FROM thresholds WHERE iso_name IS NOT NULL")
    if c.fetchone()[0] == 0:
        for iso, tests in DEFAULT_ISO_THRESHOLDS.items():
            for test, value in tests.items():
                c.execute(
                    "INSERT OR IGNORE INTO thresholds (iso_name, test_name, value) VALUES (?, ?, ?)",
                    (iso, test, value)
                )
        conn.commit()
    conn.close()

def load_iso_thresholds():
    ensure_thresholds_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT iso_name, test_name, value FROM thresholds WHERE iso_name IS NOT NULL")
    rows = c.fetchall()
    iso_thresholds = {}
    for iso, test, value in rows:
        if iso not in iso_thresholds:
            iso_thresholds[iso] = {}
        iso_thresholds[iso][test] = value
    conn.close()
    # Ensure all ISOs are present (fallback to default if missing)
    for iso, tests in DEFAULT_ISO_THRESHOLDS.items():
        if iso not in iso_thresholds:
            iso_thresholds[iso] = tests.copy()
        else:
            for test, value in tests.items():
                if test not in iso_thresholds[iso]:
                    iso_thresholds[iso][test] = value
    return iso_thresholds

def update_iso_threshold(iso_name, test_name, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO thresholds (iso_name, test_name, value)
        VALUES (?, ?, ?)
        ON CONFLICT(iso_name, test_name) DO UPDATE SET value=excluded.value
    """, (iso_name, test_name, value))
    conn.commit()
    conn.close()

def delete_iso_threshold(iso_name, test_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM thresholds WHERE iso_name=? AND test_name=?", (iso_name, test_name))
    conn.commit()
    conn.close()

# Use this global variable in the rest of the code
ISO_THRESHOLDS = load_iso_thresholds()

class IsoChoiceWidget(QWidget):
    def __init__(self, combo: QComboBox, parent=None):
        super().__init__(parent)
        self.setObjectName("IsoChoiceWidget")

        self.combo = combo
        self.combo.setObjectName("isoCombo")
        self.combo.setVisible(False)
        self.combo.setEditable(False)
        self.combo.setInsertPolicy(QComboBox.NoInsert)

        self.btn = QPushButton(self)
        self.btn.setObjectName("isoBtn")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setText(f"{self.combo.currentText()}  ▲")

        # Signals
        self.btn.clicked.connect(self.show_combo_popup)
        self.combo.currentTextChanged.connect(self.update_text)

        # Style
        self.setStyleSheet("""
            QWidget#IsoChoiceWidget {
                background: transparent;
            }
            QPushButton#isoBtn {
                background-color: #1c5ea3;
                color: #fff;
                border-radius: 8px;
                padding: 8px 32px 8px 24px;
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #1c5ea3;
                text-align: left;
            }
            QPushButton#isoBtn:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
            }
            QComboBox#isoCombo {
                background-color: #1c5ea3;
                color: #fff;
                border-radius: 8px;
                padding: 8px 32px 8px 24px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QComboBox#isoCombo::drop-down {
                border: none;
                background: transparent;
                width: 0px;
            }
            QComboBox#isoCombo QAbstractItemView {
                background: #fff;
                color: #1c5ea3;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                border-radius: 8px;
                font-size: 14px;
            }
        """)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.btn)
        layout.addWidget(self.combo)
        layout.addStretch()

        self.update_button_size()

    def update_text(self, text):
        self.btn.setText(f"{text}  ▲")
        self.update_button_size()

    def update_button_size(self):
        font_metrics = self.btn.fontMetrics()
        width = font_metrics.horizontalAdvance(self.btn.text()) + 40
        self.btn.setMinimumWidth(width)

    def show_combo_popup(self):
        self.combo.setFixedWidth(self.btn.width())
        popup = self.combo.view().window()
        pos = self.combo.mapToGlobal(self.combo.rect().bottomLeft())
        popup.move(pos)
        self.combo.showPopup()
        self.combo.setFocus()

class ThresholdsTable(QTableWidget):
    HEADERS = ["Test", "Seuil"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.SingleSelection)
        self.setEditTriggers(self.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #fff; 
                alternate-background-color: #b8d5ed;
                gridline-color: #1c5ea3; 
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; 
                border: 2px solid #1c5ea3; 
                font-size: 15px;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QTableWidget::item {
                border-bottom: 1px solid #b8d5ed;
                border-right: 1px solid #b8d5ed;
            }
        """)

    def populate_iso(self, iso_name):
        self.setRowCount(0)
        if iso_name not in ISO_THRESHOLDS:
            return
        iso_data = ISO_THRESHOLDS[iso_name]
        for seuil, valeur in iso_data.items():
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, 0, QTableWidgetItem(seuil))
            self.setItem(row, 1, QTableWidgetItem(str(valeur)))

    def populate_custom(self, rows):
        self.setRowCount(0)
        for row in rows:
            idx = self.rowCount()
            self.insertRow(idx)
            self.setItem(idx, 0, QTableWidgetItem(row.get("test_name", "")))
            value = row.get("value")
            seuil_str = str(value) if value is not None else ""
            self.setItem(idx, 1, QTableWidgetItem(seuil_str))

    def get_selected_test_name(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        return item.text() if item else None

class ThresholdsWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self.manager = ThresholdManager(db)
        self.selected_iso = "ISO 1"
        self.showing_iso = True

        self.setStyleSheet("""
            QWidget { background-color: #e0e0e0; }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
            QComboBox#isoCombo {
                background-color: #1c5ea3;
                color: #fff;
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: bold;
                font-size: 14px;
                border: none;
                min-width: 180px;
            }
            QComboBox#isoCombo::drop-down {
                border: none;
                background: transparent;
            }
            QComboBox#isoCombo QAbstractItemView {
                background: #fff;
                color: #1c5ea3;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                border-radius: 8px;
                font-size: 14px;
            }
        """)

        self.table = ThresholdsTable()
        self.table.setFocusPolicy(Qt.NoFocus)

        self.iso_combo = QComboBox()
        self.iso_combo.setObjectName("isoCombo")
        self.iso_combo.addItems(list(ISO_THRESHOLDS.keys()))
        self.iso_combo.setCurrentText(self.selected_iso)
        self.iso_combo.currentTextChanged.connect(self.on_iso_changed)
        self.iso_combo.setVisible(False)

        self.iso_choice = IsoChoiceWidget(self.iso_combo)

        self.btn_add = QPushButton("Ajouter Seuil")
        self.btn_edit = QPushButton("Modifier Seuil")
        self.btn_delete = QPushButton("Supprimer Seuil")

        self.btn_add.clicked.connect(self.add_threshold)
        self.btn_edit.clicked.connect(self.edit_threshold)
        self.btn_delete.clicked.connect(self.delete_threshold)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.iso_choice)
        top_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            self.btn_add.hide()
            self.btn_edit.hide()
            self.btn_delete.hide()

        self.show_iso_thresholds()

    def on_iso_changed(self, iso_name):
        self.selected_iso = iso_name
        self.showing_iso = True
        self.show_iso_thresholds()

    def show_iso_thresholds(self):
        self.showing_iso = True
        self.table.populate_iso(self.selected_iso)

    def show_custom_thresholds(self):
        self.showing_iso = False
        rows = self.manager.get_thresholds()
        self.table.populate_custom(rows)

    def add_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        if self.showing_iso:
            if self.user['role'] != "Administrateur":
                QMessageBox.warning(self, "Non autorisé", "Seul l'administrateur peut ajouter un seuil ISO.", QMessageBox.Ok)
                return
            dialog = ThresholdForm(self.db)
            if dialog.exec_() == QDialog.Accepted:
                data = dialog.get_data()
                if not data["test_name"]:
                    QMessageBox.warning(self, "Champs manquants", "Nom du test obligatoire.", QMessageBox.Ok)
                    return
                if data["value"] == "":
                    QMessageBox.warning(self, "Champs manquants", "La valeur du seuil doit être renseignée.", QMessageBox.Ok)
                    return
                try:
                    value = float(data["value"])
                except ValueError:
                    QMessageBox.warning(self, "Valeur incorrecte", "La valeur du seuil doit être un nombre.", QMessageBox.Ok)
                    return
                if data["test_name"] in ISO_THRESHOLDS[self.selected_iso]:
                    QMessageBox.warning(self, "Doublon", "Ce test existe déjà pour cet ISO.", QMessageBox.Ok)
                    return
                ISO_THRESHOLDS[self.selected_iso][data["test_name"]] = value
                update_iso_threshold(self.selected_iso, data["test_name"], value)  # CHANGEMENT: écrire dans la base
                self.show_iso_thresholds()
            return

        dialog = ThresholdForm(self.db)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["test_name"]:
                QMessageBox.warning(self, "Champs manquants", "Nom du test obligatoire.", QMessageBox.Ok)
                return
            if data["value"] == "":
                QMessageBox.warning(self, "Champs manquants", "La valeur du seuil doit être renseignée.", QMessageBox.Ok)
                return
            try:
                value = float(data["value"])
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "La valeur du seuil doit être un nombre.", QMessageBox.Ok)
                return
            try:
                self.manager.add_threshold(1, data["test_name"], value, None)
                self.show_custom_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible d’ajouter le seuil : {e}", QMessageBox.Ok)

    def edit_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        if self.showing_iso:
            if self.user['role'] != "Administrateur":
                QMessageBox.warning(self, "Non modifiable", "Les seuils ISO par défaut ne peuvent pas être modifiés.", QMessageBox.Ok)
                return

            iso_data = ISO_THRESHOLDS[self.selected_iso]
            test_names = list(iso_data.keys())
            sel_row = self.table.currentRow()
            if sel_row < 0 or sel_row >= len(test_names):
                QMessageBox.warning(self, "Aucun seuil", "Veuillez sélectionner un seuil ISO à modifier.", QMessageBox.Ok)
                return
            test_name = test_names[sel_row]
            valeur = iso_data[test_name]
            dialog = ThresholdForm(self.db, {"test_name": test_name, "value": valeur})
            if dialog.exec_() == QDialog.Accepted:
                data = dialog.get_data()
                if not data["test_name"]:
                    QMessageBox.warning(self, "Champs manquants", "Nom du test obligatoire.", QMessageBox.Ok)
                    return
                try:
                    new_val = float(data["value"]) if data["value"] else valeur
                except ValueError:
                    QMessageBox.warning(self, "Valeur incorrecte", "La valeur doit être un nombre.", QMessageBox.Ok)
                    return
                ISO_THRESHOLDS[self.selected_iso][test_name] = new_val
                update_iso_threshold(self.selected_iso, test_name, new_val)  # CHANGEMENT: mise à jour base
                self.show_iso_thresholds()
            return

        test_name = self.table.get_selected_test_name()
        if not test_name:
            QMessageBox.warning(self, "Aucun seuil", "Veuillez sélectionner un seuil à modifier.", QMessageBox.Ok)
            return

        rows = self.manager.get_thresholds()
        thresh = next((r for r in rows if r.get("test_name") == test_name), None)
        if not thresh:
            QMessageBox.warning(self, "Erreur", "Seuil non trouvé.", QMessageBox.Ok)
            return

        dialog = ThresholdForm(self.db, thresh)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["test_name"]:
                QMessageBox.warning(self, "Champs manquants", "Nom du test obligatoire.", QMessageBox.Ok)
                return
            if data["value"] == "":
                QMessageBox.warning(self, "Champs manquants", "La valeur du seuil doit être renseignée.", QMessageBox.Ok)
                return
            try:
                value = float(data["value"])
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "La valeur du seuil doit être un nombre.", QMessageBox.Ok)
                return
            try:
                self.manager.update_threshold(thresh["id"], None, data["test_name"], value, None)
                self.show_custom_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de modifier le seuil : {e}", QMessageBox.Ok)

    def delete_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        if self.showing_iso:
            if self.user['role'] != "Administrateur":
                QMessageBox.warning(self, "Non modifiable", "Les seuils ISO par défaut ne peuvent pas être supprimés.", QMessageBox.Ok)
                return

            iso_data = ISO_THRESHOLDS[self.selected_iso]
            test_names = list(iso_data.keys())
            sel_row = self.table.currentRow()
            if sel_row < 0 or sel_row >= len(test_names):
                QMessageBox.warning(self, "Aucun seuil", "Veuillez sélectionner un seuil ISO à supprimer.", QMessageBox.Ok)
                return
            test_name = test_names[sel_row]
            confirm = QMessageBox.question(
                self, "Confirmation", f"Supprimer le seuil ISO '{test_name}' de {self.selected_iso} ?", QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                del ISO_THRESHOLDS[self.selected_iso][test_name]
                delete_iso_threshold(self.selected_iso, test_name)  # CHANGEMENT: suppression en base
                self.show_iso_thresholds()
            return

        test_name = self.table.get_selected_test_name()
        if not test_name:
            QMessageBox.warning(self, "Aucun seuil", "Veuillez sélectionner un seuil à supprimer.", QMessageBox.Ok)
            return

        rows = self.manager.get_thresholds()
        thresh = next((r for r in rows if r.get("test_name") == test_name), None)
        if not thresh:
            QMessageBox.warning(self, "Erreur", "Seuil non trouvé.", QMessageBox.Ok)
            return

        confirm = QMessageBox.question(
            self, "Confirmation", "Supprimer ce seuil définitivement ?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                self.manager.delete_threshold(thresh["id"])
                self.show_custom_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le seuil : {e}", QMessageBox.Ok)
    def refresh_thresholds(self):
        if self.showing_iso:
            self.show_iso_thresholds()
        else:
            self.show_custom_thresholds()

class ThresholdForm(QDialog):
    def __init__(self, db, threshold=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.threshold = threshold
        self.setWindowTitle("Modifier seuil" if threshold else "Nouveau seuil")
        self.setModal(True)
        self.resize(400, 150)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QComboBox, QLineEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 13px; }
            QPushButton {
                background-color: #b8d5ed; color: #1c5ea3; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1c5ea3; color: #fff; }
        """)
        self.input_test = QLineEdit()
        self.input_value = QLineEdit()
        self.input_value.setPlaceholderText("Obligatoire")

        if threshold:
            self.input_test.setText(threshold.get("test_name", ""))
            value = threshold.get("value")
            if value is not None:
                self.input_value.setText(str(value))

        form = QFormLayout()
        form.addRow("Nom du test :", self.input_test)
        form.addRow("Valeur de seuil :", self.input_value)

        self.btn_save = QPushButton("Modifier" if threshold else "Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def get_data(self):
        return {
            "test_name": self.input_test.text().strip(),
            "value": self.input_value.text().strip(),
        }
