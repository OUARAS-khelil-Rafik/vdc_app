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
    QMainWindow, QWidget, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy, QToolBar, QAction,
    QPushButton, QSpacerItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

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
                border: none;
                font-size: 15px;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                gridline-color: #333333;
            }
            QHeaderView::section {
                background-color: #1c5ea3;
                color: #ffffff;
                font-weight: bold;
                border: none;
                padding: 6px;
                qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QToolButton {
                background: transparent;
                border: none;
                color: #1c5ea3;
                font-size: 15px;
                font-weight: bold;
                padding: 8px 18px;
                margin: 0 4px;
            }
            QToolButton:hover {
                color: #b8d5ed;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: #fff;
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
                padding: 8px 24px;
                margin: 8px 8px 0 0;
            }
            QPushButton:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
            }
        """)

        # Toolbar en haut (remplace les boutons classiques)
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("background: #e0e0e0; border: none;")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Actions (icônes facultatives, texte seulement ici)
        self.action_projects = QAction("Projets", self)
        self.action_projects.triggered.connect(self.show_dashboard)
        self.action_thresholds = QAction("Seuils", self)
        self.action_thresholds.triggered.connect(self.open_thresholds)
        self.action_input_tests = QAction("Saisie tests", self)
        self.action_input_tests.triggered.connect(self.open_form_tests)
        self.action_validate = QAction("Valider tests", self)
        self.action_validate.triggered.connect(self.open_validate_tests)
        self.action_generate_pdf = QAction("Générer PDF", self)
        self.action_generate_pdf.triggered.connect(self.generate_pdf)
        self.action_logout = QAction("Déconnexion", self)
        self.action_logout.triggered.connect(self.logout)

        # Ajout des actions selon le rôle
        role = self.user['role']
        # Ajout d'un spacer pour pousser les actions à droite
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        if role == 'Administrateur':
            toolbar.addAction(self.action_projects)
            toolbar.addAction(self.action_thresholds)
            toolbar.addAction(self.action_input_tests)
            toolbar.addAction(self.action_validate)
            toolbar.addAction(self.action_generate_pdf)
        elif role == 'Technicien premium':
            toolbar.addAction(self.action_thresholds)
            toolbar.addAction(self.action_input_tests)
            toolbar.addAction(self.action_validate)
        elif role == 'Technicien':
            toolbar.addAction(self.action_input_tests)
        toolbar.addSeparator()
        toolbar.addAction(self.action_logout)

        # Widget central
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Bandeau de bienvenue
        welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        welcome.setObjectName("welcomeLabel")
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        # Tableau des projets (affiche la colonne ID)
        self.table_projects = NoFocusTableWidget()
        self.table_projects.setColumnCount(5)
        self.table_projects.setHorizontalHeaderLabels([
            "ID", "Entreprise", "Localisation", "Type de salle", "Date de test"
        ])
        self.table_projects.setSelectionBehavior(self.table_projects.SelectRows)
        self.table_projects.setSelectionMode(self.table_projects.ExtendedSelection)
        self.table_projects.setEditTriggers(self.table_projects.NoEditTriggers)
        self.table_projects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_projects.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_projects.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table_projects.setMinimumHeight(200)
        layout.addWidget(self.table_projects, stretch=1)

        # Masquer la colonne des numéros de ligne (vertical header)
        self.table_projects.verticalHeader().setVisible(False)

        # Permettre à la table de s'ajuster dynamiquement à la fenêtre
        self.table_projects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_projects.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_projects.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # --- Ajout des boutons sous le tableau, centrés ---
        if role == 'Administrateur':
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            self.btn_ajouter = QPushButton("Ajouter Projet")
            self.btn_supprimer = QPushButton("Supprimer Projet")
            self.btn_modifier = QPushButton("Modifier Projet")
            btn_layout.addWidget(self.btn_ajouter)
            btn_layout.addWidget(self.btn_supprimer)
            btn_layout.addWidget(self.btn_modifier)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)

            self.btn_ajouter.clicked.connect(self.open_form_project)
            self.btn_supprimer.clicked.connect(self.delete_selected_project)
            self.btn_modifier.clicked.connect(self.edit_selected_project)

        # Aligner les titres du header au centre
        header = self.table_projects.horizontalHeader()
        for i in range(self.table_projects.columnCount()):
            header.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)

    def show_dashboard(self):
        """
        Affiche le dashboard (rafraîchit la liste des projets).
        """
        self.refresh_projects()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        col_count = self.table_projects.columnCount()
        for i in range(col_count):
            self.table_projects.setColumnWidth(i, self.table_projects.width() // col_count)

    def refresh_projects(self):
        """
        Recharge la liste des projets depuis la base SQLite.
        Centre les valeurs dans le tableau.
        """
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        self.table_projects.setRowCount(len(rows))
        for i, row in enumerate(rows):
            # Affiche l'ID dans la première colonne
            item_id = QTableWidgetItem(str(row['id']))
            item_id.setData(Qt.UserRole, row['id'])
            item_id.setTextAlignment(Qt.AlignCenter)
            item_id.setBackground(QColor(Qt.white))
            item_company = QTableWidgetItem(row['company_name'])
            item_company.setTextAlignment(Qt.AlignCenter)
            item_company.setBackground(QColor(Qt.white))
            item_location = QTableWidgetItem(row['location'])
            item_location.setTextAlignment(Qt.AlignCenter)
            item_location.setBackground(QColor(Qt.white))
            item_room = QTableWidgetItem(row['room_type'])
            item_room.setTextAlignment(Qt.AlignCenter)
            item_room.setBackground(QColor(Qt.white))
            item_date = QTableWidgetItem(row['test_date'])
            item_date.setTextAlignment(Qt.AlignCenter)
            item_date.setBackground(QColor(Qt.white))
            self.table_projects.setItem(i, 0, item_id)
            self.table_projects.setItem(i, 1, item_company)
            self.table_projects.setItem(i, 2, item_location)
            self.table_projects.setItem(i, 3, item_room)
            self.table_projects.setItem(i, 4, item_date)
        self.table_projects.resizeColumnsToContents()
        self.table_projects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_project_id(self):
        """
        Récupère l'ID du projet sélectionné (stocké dans Qt.UserRole de la colonne ID).
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

    def delete_selected_project(self):
        """
        Supprime le projet sélectionné après confirmation.
        """
        project_id = self.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à supprimer.", QMessageBox.Ok)
            return
        reply = QMessageBox.question(
            self, "Confirmation", "Voulez-vous vraiment supprimer ce projet ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.db.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            self.db.conn.commit()
            self.refresh_projects()

    def edit_selected_project(self):
        """
        Ouvre la fenêtre de modification du projet sélectionné.
        """
        project_id = self.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à modifier.", QMessageBox.Ok)
            return
        from gui.form_project import ProjectForm
        dialog = ProjectForm(self.db, self.user, project_id)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()
