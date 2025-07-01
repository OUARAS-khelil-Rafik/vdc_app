#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/form_project.py

Formulaire d’ajout de projet pour le MVP VDC Engineering.
Permet de saisir : nom entreprise, localisation, type de salle, date de test
et enregistre en base avec l’ID de l’utilisateur courant. :contentReference[oaicite:0]{index=0}
"""

from PyQt5.QtWidgets import (
    QDialog, QLineEdit, QDateEdit, QPushButton,
    QFormLayout, QVBoxLayout, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import QDate

class ProjectForm(QDialog):
    def __init__(self, db, user):
        """
        :param db: instance de models.database.Database
        :param user: dict {id, username, role}
        """
        super().__init__()
        self.db = db
        self.user = user
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Nouveau projet")
        self.setModal(True)
        self.resize(400, 200)

        # Appliquer le style global
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
            }
            QLineEdit, QDateEdit {
                background: #ffffff;
                border: 1px solid #b8d5ed;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus {
                border: 2px solid #1c5ea3;
            }
            QLabel {
                color: #1c5ea3;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton {
                background-color: #b8d5ed;
                color: #1c5ea3;
                border: none;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1c5ea3;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #14406e;
            }
        """)

        # Champs du formulaire
        self.input_company  = QLineEdit()
        self.input_location = QLineEdit()
        self.input_room     = QLineEdit()
        self.input_date     = QDateEdit(calendarPopup=True)
        self.input_date.setDate(QDate.currentDate())

        # Boutons
        self.btn_save   = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_project)
        self.btn_cancel.clicked.connect(self.reject)

        # Layouts
        form_layout = QFormLayout()
        form_layout.addRow("Entreprise :",    self.input_company)
        form_layout.addRow("Localisation :",  self.input_location)
        form_layout.addRow("Type de salle :", self.input_room)
        form_layout.addRow("Date du test :",  self.input_date)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def save_project(self):
        """
        Valide la saisie et enregistre le projet en base.
        """
        company  = self.input_company.text().strip()
        location = self.input_location.text().strip()
        room     = self.input_room.text().strip()
        date     = self.input_date.date().toString("yyyy-MM-dd")

        # Validation des champs obligatoires
        if not company or not date:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Le nom de l'entreprise et la date sont obligatoires.",
                QMessageBox.Ok
            )
            return

        try:
            # Insertion en base
            self.db.conn.execute(
                """
                INSERT INTO projects
                    (company_name, location, room_type, test_date, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company, location, room, date, self.user['id'])
            )
            self.db.conn.commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur de création",
                f"Impossible de créer le projet : {e}",
                QMessageBox.Ok
            )
