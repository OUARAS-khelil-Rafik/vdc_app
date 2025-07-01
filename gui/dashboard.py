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
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy
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

        # Appliquer le style général
        self.setStyleSheet("""
            QMainWindow {
                background-color: #e0e0e0;
            }
            QWidget {
                background-color: #e0e0e0;
            }
            QLabel#welcomeLabel {
                color: #1c5ea3;
                font-size: 22px;
                font-weight: bold;
                border-radius: 10px;
                padding: 12px;
                margin-bottom: 10px;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #b8d5ed;
                font-size: 15px;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                gridline-color: #b8d5ed;
            }
            QHeaderView::section {
                background-color: #1c5ea3;
                color: #ffffff;
                font-weight: bold;
                border: none;
                padding: 6px;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: #ffffff;
                border-radius: 7px;
                padding: 8px 18px;
                font-size: 15px;
                font-weight: bold;
                margin: 0 4px;
            }
            QPushButton:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
                border: 1px solid #1c5ea3;
            }
        """)

        # Widget central
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Bandeau de bienvenue
        welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        welcome.setObjectName("welcomeLabel")
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        # Tableau des projets (sans colonne ID)
        self.table_projects = QTableWidget()
        self.table_projects.setColumnCount(4)
        self.table_projects.setHorizontalHeaderLabels([
            "Entreprise", "Localisation", "Type de salle", "Date de test"
        ])
        self.table_projects.setSelectionBehavior(self.table_projects.SelectRows)
        self.table_projects.setEditTriggers(self.table_projects.NoEditTriggers)
        self.table_projects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_projects.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_projects.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table_projects.setMinimumHeight(200)
        layout.addWidget(self.table_projects, stretch=1)

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
        # Par défaut, tout est visible (Admin)
        if role == 'Technicien':
            self.btn_new_project.hide()
            self.btn_thresholds.hide()
            self.btn_validate.hide()
            self.btn_generate_pdf.hide()
        elif role == 'Technicien premium':
            self.btn_new_project.hide()
            self.btn_generate_pdf.hide()
        # Administrateur : tout visible

        # Permettre à la table de s'ajuster dynamiquement à la fenêtre
        self.table_projects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_projects.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_projects.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.table_projects.setColumnWidth(0, self.table_projects.width() // 4)
        self.table_projects.setColumnWidth(1, self.table_projects.width() // 4)
        self.table_projects.setColumnWidth(2, self.table_projects.width() // 4)
        self.table_projects.setColumnWidth(3, self.table_projects.width() // 4)

    def refresh_projects(self):
        """
        Recharge la liste des projets depuis la base SQLite.
        """
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        self.table_projects.setRowCount(len(rows))
        for i, row in enumerate(rows):
            # On n'affiche pas l'ID, mais on le stocke dans l'objet QTableWidgetItem (data Qt.UserRole)
            item_company = QTableWidgetItem(row['company_name'])
            item_company.setData(Qt.UserRole, row['id'])
            self.table_projects.setItem(i, 0, item_company)
            self.table_projects.setItem(i, 1, QTableWidgetItem(row['location']))
            self.table_projects.setItem(i, 2, QTableWidgetItem(row['room_type']))
            self.table_projects.setItem(i, 3, QTableWidgetItem(row['test_date']))
        self.table_projects.resizeColumnsToContents()
        self.table_projects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_project_id(self):
        """
        Récupère l'ID du projet sélectionné (stocké dans Qt.UserRole de la première colonne).
        """
        sel = self.table_projects.currentRow()
        if sel < 0:
            return None
        item = self.table_projects.item(sel, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

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
        project_id = self.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        from gui.form_tests import TestForm
        dialog = TestForm(self.db, project_id, self.user)
        dialog.exec_()

    def open_validate_tests(self):
        """
        Ouvre la fenêtre de validation des tests pour le projet sélectionné.
        (Admin et Technicien premium uniquement)
        """
        role = self.user['role']
        if role not in ('Administrateur', 'Technicien premium'):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return
        project_id = self.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        # À remplacer par la vraie fenêtre de validation
        QMessageBox.information(
            self, "Validation", "Fonctionnalité de validation à venir.", QMessageBox.Ok
        )

    def generate_pdf(self):
        """
        Génère le PDF du projet sélectionné via pdf/generator.py.
        (Admin uniquement)
        """
        role = self.user['role']
        if role != 'Administrateur':
            QMessageBox.warning(self, "Accès refusé", "Seul un administrateur peut générer un PDF.", QMessageBox.Ok)
            return
        project_id = self.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
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
