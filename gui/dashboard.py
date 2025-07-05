# gui/dashboard.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/dashboard.py

Tableau de bord principal de l’application VDC Engineering MVP.
Affiche la liste des projets et propose les fonctionnalités disponibles
selon le rôle de l’utilisateur (Administrateur, Technicien, Technicien premium).
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout,
    QHBoxLayout, QSizePolicy, QToolBar, QAction,
)
from PyQt5.QtCore import Qt
from .login import LoginWindow
from .project import ProjectWidget
from .thresholds import ThresholdsWidget
from .users import UsersWidget
from .test import TestsWidget
from PyQt5.QtGui import QIcon

class DashboardToolbar(QToolBar):
    def __init__(self, user, parent=None):
        _ = user  # Mark user as used to avoid linter warning
        super().__init__("Tableau de bord", parent)
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setStyleSheet("""
            QToolBar {
                background: transparent;
                border: 2px solid #1c5ea3;
                border-radius: 8px;
                spacing: 0px;
                padding: 4px 8px;
                margin: 8px 16px;
            }
        """)
        self.actions_dict = {
            'projects': QAction(QIcon("icons/projects.png"), "Projets", self),
            'tests': QAction(QIcon("icons/tests.png"), "Tests", self),
            'thresholds': QAction(QIcon("icons/thresholds.png"), "Seuils", self),
            'users': QAction(QIcon("icons/users.png"), "Utilisateurs", self),
            'logout': QAction(QIcon("icons/logout.png"), "Déconnexion", self)
        }
        for action in self.actions_dict.values():
            action.setIconText(action.text())
            action.setText("")

        self.spacer_left = QWidget()
        self.spacer_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.spacer_right = QWidget()
        self.spacer_right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.addWidget(self.spacer_left)
        for key in ['projects', 'tests', 'thresholds', 'users']:
            self.addAction(self.actions_dict[key])
        self.addSeparator()
        self.addAction(self.actions_dict['logout'])
        self.addWidget(self.spacer_right)

class DashboardWindow(QMainWindow):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Tableau de bord")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #e0e0e0; }
            QLabel#welcomeLabel {
                color: #1c5ea3; font-size: 22px; font-weight: bold;
                border-radius: 10px; padding: 12px; margin-bottom: 10px;
            }
            QToolButton {
                background: transparent; border: none; color: #1c5ea3;
                font-size: 15px; font-weight: bold; padding: 8px 18px; margin: 0 4px;
            }
            QToolButton:hover { color: #b8d5ed; }
        """)
        toolbar_container = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)
        self.toolbar = DashboardToolbar(self.user)
        toolbar_layout.addWidget(self.toolbar)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.setMenuWidget(toolbar_container)

        # Connect actions based on role
        self.toolbar.actions_dict['projects'].triggered.connect(self.show_projects)
        self.toolbar.actions_dict['tests'].triggered.connect(self.show_tests)
        if self.user.get('role') in ('Administrateur', 'Technicien premium'):
            self.toolbar.actions_dict['thresholds'].setVisible(True)
            self.toolbar.actions_dict['thresholds'].triggered.connect(self.show_thresholds)
        else:
            self.toolbar.actions_dict['thresholds'].setVisible(False)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)

        # Only Administrateur can see and use "Utilisateurs"
        if self.user.get('role', '').lower() == 'administrateur':
            self.toolbar.actions_dict['users'].setVisible(True)
            self.toolbar.actions_dict['users'].triggered.connect(self.show_users)
        else:
            self.toolbar.actions_dict['users'].setVisible(False)

        self.central = QWidget()
        self.central_layout = QVBoxLayout(self.central)
        self.setCentralWidget(self.central)
        self.welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        self.welcome.setObjectName("welcomeLabel")
        self.welcome.setAlignment(Qt.AlignCenter)
        self.central_layout.addWidget(self.welcome)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.central_layout.addWidget(self.content_widget)

        self.project_widget = ProjectWidget(self.db, self.user)
        self.tests_widget = TestsWidget(self.db, self.user)
        self.users_widget = UsersWidget(self.db)
        self.thresholds_widget = ThresholdsWidget(self.db, self.user)
        self.content_layout.addWidget(self.project_widget)
        self.project_widget.show()
        self.tests_widget.hide()
        self.users_widget.hide()
        self.thresholds_widget.hide()

    def show_projects(self):
        self.project_widget.refresh_projects()
        self.project_widget.show()
        self.tests_widget.hide()
        self.users_widget.hide()
        self.thresholds_widget.hide()
        if self.content_layout.indexOf(self.project_widget) == -1:
            self.content_layout.addWidget(self.project_widget)
        if self.content_layout.indexOf(self.tests_widget) != -1:
            self.content_layout.removeWidget(self.tests_widget)
        if self.content_layout.indexOf(self.users_widget) != -1:
            self.content_layout.removeWidget(self.users_widget)
        if self.content_layout.indexOf(self.thresholds_widget) != -1:
            self.content_layout.removeWidget(self.thresholds_widget)

    def show_tests(self):
        self.tests_widget.refresh_tests()
        self.project_widget.hide()
        self.tests_widget.show()
        self.users_widget.hide()
        self.thresholds_widget.hide()
        if self.content_layout.indexOf(self.tests_widget) == -1:
            self.content_layout.addWidget(self.tests_widget)
        if self.content_layout.indexOf(self.project_widget) != -1:
            self.content_layout.removeWidget(self.project_widget)
        if self.content_layout.indexOf(self.users_widget) != -1:
            self.content_layout.removeWidget(self.users_widget)
        if self.content_layout.indexOf(self.thresholds_widget) != -1:
            self.content_layout.removeWidget(self.thresholds_widget)

    def show_thresholds(self):
        self.thresholds_widget.refresh_thresholds()
        self.project_widget.hide()
        self.tests_widget.hide()
        self.users_widget.hide()
        if self.content_layout.indexOf(self.thresholds_widget) == -1:
            self.content_layout.addWidget(self.thresholds_widget)
        self.thresholds_widget.show()

    def show_users(self):
        self.users_widget.refresh_users()
        self.project_widget.hide()
        self.tests_widget.hide()
        self.users_widget.show()
        self.thresholds_widget.hide()
        if self.content_layout.indexOf(self.users_widget) == -1:
            self.content_layout.addWidget(self.users_widget)
        if self.content_layout.indexOf(self.project_widget) != -1:
            self.content_layout.removeWidget(self.project_widget)
        if self.content_layout.indexOf(self.tests_widget) != -1:
            self.content_layout.removeWidget(self.tests_widget)
        if self.content_layout.indexOf(self.thresholds_widget) != -1:
            self.content_layout.removeWidget(self.thresholds_widget)

    def logout(self):
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
