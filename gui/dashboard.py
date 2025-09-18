# gui/dashboard.py
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout,
    QSizePolicy, QToolBar, QAction
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from .login   import LoginWindow
from .project import ProjectWidget
from .users   import UsersWidget
from .etalons import EtalonsWidget

from .hvac_workflow import HVACWorkflow   # <<<< NOUVEAU

class DashboardToolbar(QToolBar):
    def __init__(self, user, parent=None):
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
            'projects': QAction(QIcon("icons/projects.png"),   "Projets",      self),
            'tests':    QAction(QIcon("icons/tests.png"),      "Tests",        self),
            'etalons':  QAction(QIcon("icons/etalons.png"),    "Étalons",      self),
            'users':    QAction(QIcon("icons/users.png"),      "Utilisateurs", self),
            'logout':   QAction(QIcon("icons/logout.png"),     "Déconnexion",  self)
        }
        for act in self.actions_dict.values():
            act.setIconText(act.text()); act.setText("")
        spacer_l = QWidget(); spacer_l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer_r = QWidget(); spacer_r.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer_l)
        for key in ('projects', 'tests', 'etalons', 'users'):
            self.addAction(self.actions_dict[key])
        self.addSeparator()
        self.addAction(self.actions_dict['logout'])
        self.addWidget(spacer_r)

class DashboardWindow(QMainWindow):
    def __init__(self, db, user):
        super().__init__()
        self.db   = db
        self.user = user
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Tableau de bord")
        self.setMinimumSize(1300, 700)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #e0e0e0; }
            QLabel#welcomeLabel {
                color: #1c5ea3; font-size: 22px; font-weight: bold;
                border-radius: 5px;
            }
            QToolButton {
                background: transparent; border: none; color: #1c5ea3;
                font-size: 15px; font-weight: bold; padding: 8px 18px; margin: 0 4px;
            }
            QToolButton:hover { color: #b8d5ed; }
        """)

        self.toolbar = DashboardToolbar(self.user)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.toolbar.actions_dict['projects'].triggered.connect(self.show_projects)
        self.toolbar.actions_dict['tests'].triggered.connect(self.show_tests)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)

        role = (self.user.get('role') or '').strip().lower()
        etalons_allowed = role in {'administrateur', 'superviseur', 'technicien responsable'}
        self.toolbar.actions_dict['etalons'].setVisible(etalons_allowed)
        if etalons_allowed:
            self.toolbar.actions_dict['etalons'].triggered.connect(self.show_etalons)

        users_allowed = role == 'administrateur'
        self.toolbar.actions_dict['users'].setVisible(users_allowed)
        if users_allowed:
            self.toolbar.actions_dict['users'].triggered.connect(self.show_users)

        self.central = QWidget()
        self.central_layout = QVBoxLayout(self.central)
        self.setCentralWidget(self.central)

        self.welcome = QLabel(f"Bienvenue {self.user.get('full_name','')} ({self.user.get('role','')})")
        self.welcome.setObjectName("welcomeLabel")
        self.welcome.setAlignment(Qt.AlignCenter)
        self.central_layout.addWidget(self.welcome)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.central_layout.addWidget(self.content_widget)

        # Widgets principaux
        self.project_widget  = ProjectWidget(self.db, self.user)
        self.hvac_widget     = HVACWorkflow(self.db, get_project_id=lambda: self.project_widget.table.get_selected_project_id())
        self.etalons_widget  = EtalonsWidget(self.db, self.user)
        self.users_widget    = UsersWidget(self.db)

        for w in (self.project_widget, self.hvac_widget, self.etalons_widget, self.users_widget):
            self.content_layout.addWidget(w)

        self.show_projects()

    # -------- Vues --------
    def _hide_all(self):
        self.project_widget.hide()
        self.hvac_widget.hide()
        self.etalons_widget.hide()
        self.users_widget.hide()

    def show_projects(self):
        self._hide_all()
        self.project_widget.refresh_projects()
        self.project_widget.show()

    def show_tests(self):
        self._hide_all()
        # met à jour le contexte projet + pastille globale
        self.hvac_widget.rebuild_for_current_project()
        self.hvac_widget.show()

    def show_etalons(self):
        self._hide_all()
        self.etalons_widget.reload()
        self.etalons_widget.show()

    def show_users(self):
        self._hide_all()
        self.users_widget.refresh_users()
        self.users_widget.show()

    # -------- Session --------
    def logout(self):
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
