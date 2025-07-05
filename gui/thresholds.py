# gui/thresholds.py
from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy,
    QPushButton, QFormLayout, QLineEdit, QComboBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from models.thresholdmanager import ThresholdManager

# Seuils ISO 14644-1 prédéfinis (µm/m³ pour particules, °C et %)
ISO_THRESHOLDS = {
    "ISO 1": {"Particules >0.5 µm": 10,      "Particules >5 µm": 0,     "Température": 22, "Humidité relative": 50},
    "ISO 2": {"Particules >0.5 µm": 100,     "Particules >5 µm": 0,     "Température": 22, "Humidité relative": 50},
    "ISO 3": {"Particules >0.5 µm": 1000,    "Particules >5 µm": 0,     "Température": 22, "Humidité relative": 50},
    "ISO 4": {"Particules >0.5 µm": 10000,   "Particules >5 µm": 0,     "Température": 22, "Humidité relative": 50},
    "ISO 5": {"Particules >0.5 µm": 100000,  "Particules >5 µm": 0,     "Température": 22, "Humidité relative": 50},
    "ISO 6": {"Particules >0.5 µm": 1000000, "Particules >5 µm": 0,     "Température": 22, "Humidité relative": 50},
    "ISO 7": {"Particules >0.5 µm": 352000,  "Particules >5 µm": 2900,  "Température": 22, "Humidité relative": 50},
    "ISO 8": {"Particules >0.5 µm": 832000,  "Particules >5 µm": 29300, "Température": 22, "Humidité relative": 50},
    "ISO 9": {"Particules >0.5 µm": 8320000, "Particules >5 µm": 293000,"Température": 22, "Humidité relative": 50},
}

from PyQt5.QtWidgets import QWidget, QPushButton, QComboBox, QHBoxLayout
from PyQt5.QtCore import Qt

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

        # Signaux
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
        
        # Force the popup to open below the button
        popup = self.combo.view().window()
        pos = self.combo.mapToGlobal(self.combo.rect().bottomLeft())
        popup.move(pos)  # Move popup below combo
        self.combo.showPopup()
        self.combo.setFocus()



class ThresholdsTable(QTableWidget):
    # Change headers: "Test" (au lieu de "Seuil"), et "Seuil" (au lieu de "Min"/"Max")
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
            self.setItem(row, 0, QTableWidgetItem(seuil))  # "Test"
            self.setItem(row, 1, QTableWidgetItem(str(valeur)))  # "Seuil"

    def populate_custom(self, rows):
        self.setRowCount(0)
        for row in rows:
            idx = self.rowCount()
            self.insertRow(idx)
            self.setItem(idx, 0, QTableWidgetItem(row.get("test_name", "")))
            min_val = row.get("min_value")
            max_val = row.get("max_value")
            if min_val is not None and max_val is not None:
                seuil_str = f"{min_val} - {max_val}"
            elif min_val is not None:
                seuil_str = f">= {min_val}"
            elif max_val is not None:
                seuil_str = f"<= {max_val}"
            else:
                seuil_str = ""
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
        self.iso_combo.setVisible(False)  # Hidden, used by IsoChoiceWidget

        self.iso_choice = IsoChoiceWidget(self.iso_combo)
        # self.iso_combo.currentTextChanged.connect(self.iso_choice.update_text) # Already connected in IsoChoiceWidget

        self.btn_add = QPushButton("Ajouter Seuil")
        self.btn_edit = QPushButton("Modifier Seuil")
        self.btn_delete = QPushButton("Supprimer Seuil")

        self.btn_add.clicked.connect(self.add_threshold)
        self.btn_edit.clicked.connect(self.edit_threshold)
        self.btn_delete.clicked.connect(self.delete_threshold)

        # Place iso_choice above, buttons below
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

        # Seuls Administrateur et Technicien premium
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

        dialog = ThresholdForm(self.db)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["test_name"]:
                QMessageBox.warning(self, "Champs manquants", "Nom du test obligatoire.", QMessageBox.Ok)
                return
            if data["min_value"] == "" and data["max_value"] == "":
                QMessageBox.warning(self, "Champs manquants", "Au moins une valeur min ou max doit être renseignée.", QMessageBox.Ok)
                return
            try:
                min_val = float(data["min_value"]) if data["min_value"] else None
                max_val = float(data["max_value"]) if data["max_value"] else None
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "Les valeurs min/max doivent être des nombres.", QMessageBox.Ok)
                return
            try:
                self.manager.add_threshold(None, data["test_name"], min_val, max_val)
                self.show_custom_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible d’ajouter le seuil : {e}", QMessageBox.Ok)

    def edit_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        if self.showing_iso:
            QMessageBox.warning(self, "Non modifiable", "Les seuils ISO par défaut ne peuvent pas être modifiés.", QMessageBox.Ok)
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
            if data["min_value"] == "" and data["max_value"] == "":
                QMessageBox.warning(self, "Champs manquants", "Au moins une valeur min ou max doit être renseignée.", QMessageBox.Ok)
                return
            try:
                min_val = float(data["min_value"]) if data["min_value"] else None
                max_val = float(data["max_value"]) if data["max_value"] else None
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "Les valeurs min/max doivent être des nombres.", QMessageBox.Ok)
                return
            try:
                self.manager.update_threshold(thresh["id"], None, data["test_name"], min_val, max_val)
                self.show_custom_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de modifier le seuil : {e}", QMessageBox.Ok)

    def delete_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        if self.showing_iso:
            QMessageBox.warning(self, "Non modifiable", "Les seuils ISO par défaut ne peuvent pas être supprimés.", QMessageBox.Ok)
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
        self.resize(400, 200)
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
        self.input_min = QLineEdit()
        self.input_min.setPlaceholderText("Optionnel")
        self.input_max = QLineEdit()
        self.input_max.setPlaceholderText("Optionnel")

        if threshold:
            self.input_test.setText(threshold.get("test_name", ""))
            if threshold.get("min_value") is not None:
                self.input_min.setText(str(threshold["min_value"]))
            if threshold.get("max_value") is not None:
                self.input_max.setText(str(threshold["max_value"]))

        form = QFormLayout()
        form.addRow("Nom du test :", self.input_test)
        form.addRow("Valeur min :", self.input_min)
        form.addRow("Valeur max :", self.input_max)

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
            "min_value": self.input_min.text().strip(),
            "max_value": self.input_max.text().strip(),
        }
