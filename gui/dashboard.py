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
    QPushButton
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

class ProjectTable(NoFocusTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels([
            "ID", "Entreprise", "Localisation", "Type de salle", "Date de test"
        ])
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.ExtendedSelection)
        self.setEditTriggers(self.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Aligner les titres du header au centre
        header = self.horizontalHeader()
        for i in range(self.columnCount()):
            header.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)

    def populate(self, rows):
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
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
            self.setItem(i, 0, item_id)
            self.setItem(i, 1, item_company)
            self.setItem(i, 2, item_location)
            self.setItem(i, 3, item_room)
            self.setItem(i, 4, item_date)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_project_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

class DashboardToolbar(QToolBar):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setStyleSheet("background: #e0e0e0; border: none;")
        self.actions_dict = {}
        self._setup_actions(user)

    def _setup_actions(self, user):
        self.actions_dict['projects'] = QAction("Projets", self)
        self.actions_dict['thresholds'] = QAction("Seuils", self)
        self.actions_dict['input_tests'] = QAction("Saisie tests", self)
        self.actions_dict['validate'] = QAction("Valider tests", self)
        self.actions_dict['generate_pdf'] = QAction("Générer PDF", self)
        self.actions_dict['logout'] = QAction("Déconnexion", self)

        role = user['role']
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)
        if role == 'Administrateur':
            self.addAction(self.actions_dict['projects'])
            self.addAction(self.actions_dict['thresholds'])
            self.addAction(self.actions_dict['input_tests'])
            self.addAction(self.actions_dict['validate'])
            self.addAction(self.actions_dict['generate_pdf'])
        elif role == 'Technicien premium':
            self.addAction(self.actions_dict['thresholds'])
            self.addAction(self.actions_dict['input_tests'])
            self.addAction(self.actions_dict['validate'])
        elif role == 'Technicien':
            self.addAction(self.actions_dict['input_tests'])
        self.addSeparator()
        self.addAction(self.actions_dict['logout'])

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

        # Toolbar
        self.toolbar = DashboardToolbar(self.user)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.toolbar.actions_dict['projects'].triggered.connect(self.show_dashboard)
        self.toolbar.actions_dict['thresholds'].triggered.connect(self.open_thresholds)
        self.toolbar.actions_dict['input_tests'].triggered.connect(self.open_form_tests)
        self.toolbar.actions_dict['validate'].triggered.connect(self.open_validate_tests)
        self.toolbar.actions_dict['generate_pdf'].triggered.connect(self.generate_pdf)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Welcome label
        welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        welcome.setObjectName("welcomeLabel")
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        # Project table
        self.table_projects = ProjectTable()
        layout.addWidget(self.table_projects, stretch=1)

        # Buttons for admin
        if self.user['role'] == 'Administrateur':
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
            self.btn_ajouter.clicked.connect(self.add_project)
            self.btn_supprimer.clicked.connect(self.delete_selected_project)
            self.btn_modifier.clicked.connect(self.edit_selected_project)

    def show_dashboard(self):
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
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        self.table_projects.populate(rows)

    def add_project(self):
        from gui.form_project import ProjectForm
        dialog = ProjectForm(self.db, self.user)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()

    def open_thresholds(self):
        from gui.thresholds import ThresholdsDialog
        dlg = ThresholdsDialog(self.db)
        dlg.exec_()

    def open_form_tests(self):
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        from gui.form_tests import TestForm
        dialog = TestForm(self.db, project_id, self.user)
        dialog.exec_()

    def open_validate_tests(self):
        role = self.user['role']
        if role not in ('Administrateur', 'Technicien premium'):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        QMessageBox.information(
            self, "Validation", "Fonctionnalité de validation à venir.", QMessageBox.Ok
        )

    def generate_pdf(self):
        role = self.user['role']
        if role != 'Administrateur':
            QMessageBox.warning(self, "Accès refusé", "Seul un administrateur peut générer un PDF.", QMessageBox.Ok)
            return
        project_id = self.table_projects.get_selected_project_id()
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
        from gui.login import LoginWindow
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()

    def delete_selected_project(self):
        project_id = self.table_projects.get_selected_project_id()
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
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à modifier.", QMessageBox.Ok)
            return
        from gui.form_project import ProjectForm
        dialog = ProjectForm(self.db, self.user, project_id)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()
