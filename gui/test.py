# gui/test.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QDialog,
    QPushButton, QFormLayout, QLineEdit, QLabel, QComboBox
)
from PyQt5.QtCore import Qt
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
            QLineEdit, QComboBox {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 5px;
                padding: 4px; font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 6px;
                padding: 6px 18px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)

        # Récupère la liste des seuils pour ce projet
        self.thresholds = self.manager.get_thresholds(self.project_id)

        form_layout = QFormLayout()
        # Nom du point de mesure
        self.input_point = QLineEdit()
        form_layout.addRow("Point de mesure :", self.input_point)

        # Pour chaque test (anciennement 'parameter'), on ajoute un champ
        self.widgets = {}
        for test_name, min_val, max_val in self.thresholds:
            label_parts = []
            if min_val is not None:
                label_parts.append(f"≥ {min_val}")
            if max_val is not None:
                label_parts.append(f"≤ {max_val}")
            constraints = "  ".join(label_parts)
            label = QLabel(f"{test_name} ({constraints})")
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            widget = QLineEdit()
            widget.setPlaceholderText("Valeur numérique")
            form_layout.addRow(label, widget)
            self.widgets[test_name] = (widget, min_val, max_val)

        # Boutons
        self.btn_save   = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_test)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        # Assemblage
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def save_test(self):
        point_name = self.input_point.text().strip()
        if not point_name:
            QMessageBox.warning(self, "Champs manquant",
                                "Merci de renseigner le nom du point de mesure.",
                                QMessageBox.Ok)
            return

        measurements = []
        compliant = True

        for test_name, (widget, min_val, max_val) in self.widgets.items():
            text = widget.text().strip()
            if not text:
                QMessageBox.warning(self, "Champs manquant",
                    f"Merci de renseigner la valeur pour « {test_name} ».",
                    QMessageBox.Ok)
                return
            try:
                value = float(text)
            except ValueError:
                QMessageBox.warning(self, "Valeur invalide",
                    f"La valeur pour « {test_name} » n’est pas un nombre valide.",
                    QMessageBox.Ok)
                return

            # Vérification ISO 14644
            if (min_val is not None and value < min_val) or \
               (max_val is not None and value > max_val):
                compliant = False

            measurements.append((test_name, value, min_val, max_val))

        # Enregistrement
        self.manager.save_test(self.project_id, self.user['id'],
                               point_name, measurements)

        statut = "Conforme" if compliant else "Non conforme"
        QMessageBox.information(self, "Test enregistré",
            f"Le test a bien été enregistré.\nStatut de conformité : {statut}",
            QMessageBox.Ok)
        self.accept()
