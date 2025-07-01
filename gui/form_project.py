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
    QFormLayout, QVBoxLayout, QHBoxLayout, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import QDate

class ProjectForm(QDialog):
    def __init__(self, db, user, project=None):
        """
        :param db: instance de models.database.Database
        :param user: dict {id, username, role}
        :param project: dict représentant le projet à modifier (ou None pour ajout)
        """
        super().__init__()
        self.db = db
        self.user = user
        # If project is an int (project id), fetch the project dict from the database
        if isinstance(project, int):
            cursor = self.db.conn.execute(
                "SELECT * FROM projects WHERE id=?",
                (project,)
            )
            row = cursor.fetchone()
            if row:
                # Convert row to dict (assuming row is a sqlite3.Row or tuple)
                columns = [col[0] for col in cursor.description]
                self.project = dict(zip(columns, row))
            else:
                self.project = None
        else:
            self.project = project
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Modifier projet" if self.project else "Nouveau projet")
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

        # Pré-remplir si modification
        if self.project:
            self.input_company.setText(self.project.get("company_name", ""))
            self.input_location.setText(self.project.get("location", ""))
            self.input_room.setText(self.project.get("room_type", ""))
            try:
                date = QDate.fromString(self.project.get("test_date", ""), "yyyy-MM-dd")
                if date.isValid():
                    self.input_date.setDate(date)
            except Exception:
                pass

        # Ajuster la taille des champs pour qu'ils s'étendent avec la fenêtre
        for widget in [self.input_company, self.input_location, self.input_room, self.input_date]:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Boutons
        self.btn_save   = QPushButton("Modifier" if self.project else "Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_project)
        self.btn_cancel.clicked.connect(self.reject)

        # Layouts
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 0)
        self.setLayout(main_layout)

    def save_project(self):
        """
        Valide la saisie et enregistre ou modifie le projet en base.
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
            if self.project:
                # Modification
                self.db.conn.execute(
                    """
                    UPDATE projects
                    SET company_name=?, location=?, room_type=?, test_date=?
                    WHERE id=?
                    """,
                    (company, location, room, date, self.project["id"])
                )
            else:
                # Insertion
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
                "Erreur",
                f"Impossible de {'modifier' if self.project else 'créer'} le projet : {e}",
                QMessageBox.Ok
            )
