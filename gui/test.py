import os
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QMessageBox, QDialog, QPushButton, QFormLayout, QLineEdit
)

from models.testmanager import TestManager

class TestForm(QDialog):
    def __init__(self, db, project_id, user):
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.user = user
        self.manager = TestManager(db)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Saisie des tests")
        self.setModal(True)
        self.resize(450, 300)
        self.setStyleSheet("""
            QDialog { background-color: #e0e0e0; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 14px; }
            QLineEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 5px;
                padding: 4px; font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 6px;
                padding: 6px 18px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)
        row = self.db.conn.execute("SELECT room_type FROM projects WHERE id = ?", (self.project_id,)).fetchone()
        self.iso_class = row["room_type"]
        self.thresholds = self.manager.get_thresholds(self.iso_class)
        form_layout = QFormLayout()
        self.input_point = QLineEdit()
        form_layout.addRow("Point de mesure :", self.input_point)
        self.widgets = {}
        for param, max_val in self.thresholds:
            label = f"{param} (≤ {max_val})"
            widget = QLineEdit()
            widget.setPlaceholderText("Valeur numérique")
            form_layout.addRow(label, widget)
            self.widgets[param] = (widget, max_val)
        self.btn_save   = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_test)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def save_test(self):
        point_name = self.input_point.text().strip()
        if not point_name:
            QMessageBox.warning(self, "Champs manquant", "Merci de renseigner le nom du point de mesure.", QMessageBox.Ok)
            return
        measurements = []
        for param, (widget, max_val) in self.widgets.items():
            text = widget.text().strip()
            try:
                value = float(text)
            except ValueError:
                QMessageBox.warning(self, "Valeur invalide", f"La valeur pour « {param} » n’est pas un nombre valide.", QMessageBox.Ok)
                return
            measurements.append((param, value, max_val))
        compliant = self.manager.save_test(self.project_id, self.user["id"], point_name, measurements)
        status = "Conforme" if compliant else "Non conforme"
        QMessageBox.information(self, "Test enregistré", f"Le test a bien été enregistré.\nStatut de conformité : {status}", QMessageBox.Ok)
        self.accept()