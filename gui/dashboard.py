#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/dashboard.py

Tableau de bord principal de l’application VDC Engineering MVP.
Affiche la liste des projets et propose les fonctionnalités disponibles
selon le rôle de l’utilisateur (Administrateur, Technicien, Technicien premium).
"""

import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog
)
from PyQt5.QtCore import Qt

class DashboardWindow(QMainWindow):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user  # dict avec keys: id, username, role
        self._init_ui()
        self.refresh_projects()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Tableau de bord")
        self.setMinimumSize(800, 600)

        # Widget central
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Bandeau de bienvenue
        welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        # Tableau des projets
        self.table_projects = QTableWidget()
        self.table_projects.setColumnCount(5)
        self.table_projects.setHorizontalHeaderLabels([
            "ID", "Entreprise", "Localisation", "Type de salle", "Date de test"
        ])
        self.table_projects.setSelectionBehavior(self.table_projects.SelectRows)
        self.table_projects.setEditTriggers(self.table_projects.NoEditTriggers)
        layout.addWidget(self.table_projects)

        # Barre de boutons d’actions
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        # Nouveau projet (Admin uniquement)
        self.btn_new_project = QPushButton("Nouveau projet")
        self.btn_new_project.clicked.connect(self.open_form_project)
        btn_layout.addWidget(self.btn_new_project)

        # Seuils de conformité (Admin + Technicien premium)
        self.btn_thresholds = QPushButton("Seuils")
        self.btn_thresholds.clicked.connect(self.open_thresholds)
        btn_layout.addWidget(self.btn_thresholds)

        # Saisie des tests (tous profils)
        self.btn_input_tests = QPushButton("Saisie tests")
        self.btn_input_tests.clicked.connect(self.open_form_tests)
        btn_layout.addWidget(self.btn_input_tests)

        # Validation des tests (Admin + Technicien premium)
        self.btn_validate = QPushButton("Valider tests")
        self.btn_validate.clicked.connect(self.open_validate_tests)
        btn_layout.addWidget(self.btn_validate)

        # Génération de rapport PDF (Admin uniquement)
        self.btn_generate_pdf = QPushButton("Générer PDF")
        self.btn_generate_pdf.clicked.connect(self.generate_pdf)
        btn_layout.addWidget(self.btn_generate_pdf)

        # Déconnexion (tous profils)
        self.btn_logout = QPushButton("Déconnexion")
        self.btn_logout.clicked.connect(self.logout)
        btn_layout.addWidget(self.btn_logout)

        # Ajuster la visibilité des boutons selon le rôle
        role = self.user['role']
        if role == 'Technicien':
            self.btn_new_project.hide()
            self.btn_thresholds.hide()
            self.btn_validate.hide()
            self.btn_generate_pdf.hide()
        elif role == 'Technicien premium':
            self.btn_new_project.hide()
            self.btn_generate_pdf.hide()
        # Administrateur : tout visible

    def refresh_projects(self):
        """
        Recharge la liste des projets depuis la base SQLite.
        """
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        self.table_projects.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.table_projects.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.table_projects.setItem(i, 1, QTableWidgetItem(row['company_name']))
            self.table_projects.setItem(i, 2, QTableWidgetItem(row['location']))
            self.table_projects.setItem(i, 3, QTableWidgetItem(row['room_type']))
            self.table_projects.setItem(i, 4, QTableWidgetItem(row['test_date']))
        self.table_projects.resizeColumnsToContents()

    def open_form_project(self):
        """
        Ouvre la fenêtre de création de projet (form_project.py),
        en passant l’utilisateur courant.
        """
        from gui.form_project import ProjectForm
        dialog = ProjectForm(self.db, self.user)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()

    def open_thresholds(self):
        """
        Ouvre le dialog de gestion des seuils de conformité.
        """
        from gui.thresholds import ThresholdsDialog
        dlg = ThresholdsDialog(self.db)
        dlg.exec_()

    def open_form_tests(self):
        """
        Ouvre la fenêtre de saisie des tests pour le projet sélectionné.
        """
        sel = self.table_projects.currentRow()
        if sel < 0:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        project_id = int(self.table_projects.item(sel, 0).text())
        from gui.form_tests import TestForm
        dialog = TestForm(self.db, project_id, self.user)
        dialog.exec_()

    def open_validate_tests(self):
        """
        Placeholder pour la validation des tests (à implémenter).
        """
        QMessageBox.information(
            self, "Validation", "Fonctionnalité de validation à venir.", QMessageBox.Ok
        )

    def generate_pdf(self):
        """
        Génère le PDF du projet sélectionné via pdf/generator.py.
        """
        sel = self.table_projects.currentRow()
        if sel < 0:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        project_id = int(self.table_projects.item(sel, 0).text())
        from pdf.generator import PDFGenerator
        gen = PDFGenerator(self.db)
        save_path = os.path.join(os.getcwd(), f"rapport_projet_{project_id}.pdf")
        gen.generate_report(project_id, save_path)
        QMessageBox.information(
            self, "PDF généré", f"Rapport enregistré ici : {save_path}", QMessageBox.Ok
        )

    def logout(self):
        """
        Déconnecte l’utilisateur et retourne à l’écran de login.
        """
        from gui.login import LoginWindow
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
