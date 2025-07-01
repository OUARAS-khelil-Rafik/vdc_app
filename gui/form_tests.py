#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/form_tests.py

Formulaire de saisie des tests pour l’application VDC Engineering MVP.
– Pour chaque projet, charge les seuils (particules, température…)
  correspondant à la classe ISO (stored in room_type).  
– Permet de saisir les valeurs mesurées par point de mesure.  
– Évalue automatiquement la conformité (Conforme / Non conforme).  
"""

from PyQt5.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton,
    QFormLayout, QVBoxLayout, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import QDateTime

class TestForm(QDialog):
    def __init__(self, db, project_id, user):
        """
        :param db: instance de models.database.Database
        :param project_id: ID du projet sélectionné
        :param user: dict {id, username, role}
        """
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.user = user
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Saisie des tests")
        self.setModal(True)
        self.resize(450, 300)

        # Style général
        self.setStyleSheet("""
            QDialog {
                background-color: #e0e0e0;
            }
            QLabel {
                color: #1c5ea3;
                font-weight: bold;
                font-size: 14px;
            }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #b8d5ed;
                border-radius: 5px;
                padding: 4px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: #ffffff;
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
            }
        """)

        # 1. Récupérer la classe ISO (room_type) du projet
        row = self.db.conn.execute(
            "SELECT room_type FROM projects WHERE id = ?",
            (self.project_id,)
        ).fetchone()
        self.iso_class = row["room_type"]

        # 2. Charger les seuils pour cette classe
        rows = self.db.conn.execute(
            "SELECT parameter, max_value FROM thresholds WHERE iso_class = ?",
            (self.iso_class,)
        ).fetchall()
        self.thresholds = [(r["parameter"], r["max_value"]) for r in rows]

        # 3. Construire le formulaire dynamique
        form_layout = QFormLayout()
        # Nom du point de mesure
        self.input_point = QLineEdit()
        form_layout.addRow("Point de mesure :", self.input_point)

        # Champs pour chaque paramètre (avec indication du seuil max)
        self.widgets = {}
        for param, max_val in self.thresholds:
            label = f"{param} (≤ {max_val})"
            widget = QLineEdit()
            widget.setPlaceholderText("Valeur numérique")
            form_layout.addRow(label, widget)
            self.widgets[param] = widget

        # Boutons Enregistrer / Annuler
        self.btn_save   = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_test)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        # Assemblage final
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def save_test(self):
        # 4. Validation du nom du point
        point_name = self.input_point.text().strip()
        if not point_name:
            QMessageBox.warning(
                self, "Champs manquant",
                "Merci de renseigner le nom du point de mesure.",
                QMessageBox.Ok
            )
            return

        # 5. Insertion du test
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        cursor = self.db.conn.execute(
            "INSERT INTO tests (project_id, technician_id, measurement_date) "
            "VALUES (?, ?, ?)",
            (self.project_id, self.user["id"], timestamp)
        )
        test_id = cursor.lastrowid

        # 6. Lecture des valeurs et insertion des mesures
        compliant = True
        for param, max_val in self.thresholds:
            text = self.widgets[param].text().strip()
            try:
                value = float(text)
            except ValueError:
                QMessageBox.warning(
                    self, "Valeur invalide",
                    f"La valeur pour « {param} » n’est pas un nombre valide.",
                    QMessageBox.Ok
                )
                # Nettoyage partiel en cas d’erreur
                self.db.conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
                self.db.conn.commit()
                return

            # Enregistrer la mesure
            self.db.conn.execute(
                "INSERT INTO measurements (test_id, point_name, parameter, value) "
                "VALUES (?, ?, ?, ?)",
                (test_id, point_name, param, value)
            )

            # Vérifier la conformité
            if value > max_val:
                compliant = False

        # 7. Validation finale de la transaction
        self.db.conn.commit()

        # 8. Affichage du résultat
        status = "Conforme" if compliant else "Non conforme"
        QMessageBox.information(
            self, "Test enregistré",
            f"Le test a bien été enregistré.\nStatut de conformité : {status}",
            QMessageBox.Ok
        )
        self.accept()
