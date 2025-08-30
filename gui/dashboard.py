# gui/dashboard.py
# -*- coding: utf-8 -*-
"""
Tableau de bord principal de l’application VDC Engineering (MVP).

Mises à jour :
- Remplace l’onglet "Seuils" par "Étalons".
- L’onglet Étalons est visible pour : Administrateur, Superviseur, Technicien responsable.
- Conserve l’identité visuelle (bleu #1c5ea3 / #b8d5ed, tables, boutons).

Fonctionnalités :
- Navigation : Projets, Tests, Étalons, Utilisateurs, Déconnexion.
- Règles d’accès selon le rôle :
    * Étalons visibles pour : Administrateur, Superviseur, Technicien responsable.
    * Utilisateurs visible uniquement pour : Administrateur.
- Affiche un message de bienvenue et rafraîchit les vues au moment de l’affichage.
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout,
    QSizePolicy, QToolBar, QAction
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from .login       import LoginWindow
from .project     import ProjectWidget
from .users       import UsersWidget
# from .test        import TestSessionWidget  # Active si ton module Tests est prêt
from .etalons     import EtalonsWidget       # <<< Nouveau widget

# ---------------------- Barre d’outils ----------------------

class DashboardToolbar(QToolBar):
    def __init__(self, user, parent=None):
        _ = user  # éviter l’avertissement linter
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

        # Icônes attendus dans le dossier "icons"
        self.actions_dict = {
            'projects': QAction(QIcon("icons/projects.png"),   "Projets",      self),
            'tests':    QAction(QIcon("icons/tests.png"),      "Tests",        self),
            'etalons':  QAction(QIcon("icons/etalons.png"),  "Étalons",      self),
            'users':    QAction(QIcon("icons/users.png"),      "Utilisateurs", self),
            'logout':   QAction(QIcon("icons/logout.png"),     "Déconnexion",  self)
        }
        # Affiche uniquement les icônes (texte dans tooltips si besoin)
        for act in self.actions_dict.values():
            act.setIconText(act.text())
            act.setText("")

        spacer_l = QWidget(); spacer_l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer_r = QWidget(); spacer_r.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.addWidget(spacer_l)
        for key in ('projects', 'tests', 'etalons', 'users'):
            self.addAction(self.actions_dict[key])
        self.addSeparator()
        self.addAction(self.actions_dict['logout'])
        self.addWidget(spacer_r)


# ---------------------- Fenêtre principale ----------------------

class DashboardWindow(QMainWindow):
    def __init__(self, db, user):
        super().__init__()
        self.db   = db
        self.user = user
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Tableau de bord")
        self.setMinimumSize(1200, 600)
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

        # Barre d'outils
        self.toolbar = DashboardToolbar(self.user)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        # Connexions de base
        self.toolbar.actions_dict['projects'].triggered.connect(self.show_projects)
        self.toolbar.actions_dict['tests'].triggered.connect(self.show_tests)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)

        # Logique des rôles
        role = (self.user.get('role') or '').strip().lower()

        # Étalons : Admin / Superviseur / Technicien responsable
        etalons_allowed = role in {'administrateur', 'superviseur', 'technicien responsable'}
        self.toolbar.actions_dict['etalons'].setVisible(etalons_allowed)
        if etalons_allowed:
            self.toolbar.actions_dict['etalons'].triggered.connect(self.show_etalons)

        # Utilisateurs : Admin uniquement
        users_allowed = role == 'administrateur'
        self.toolbar.actions_dict['users'].setVisible(users_allowed)
        if users_allowed:
            self.toolbar.actions_dict['users'].triggered.connect(self.show_users)

        # Conteneur central
        self.central = QWidget()
        self.central_layout = QVBoxLayout(self.central)
        self.setCentralWidget(self.central)

        # Message de bienvenue
        self.welcome = QLabel(f"Bonjour {self.user.get('full_name','')} ({self.user.get('role','')})")
        self.welcome.setObjectName("welcomeLabel")
        self.welcome.setAlignment(Qt.AlignCenter)
        self.central_layout.addWidget(self.welcome)

        # Zone de contenu
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.central_layout.addWidget(self.content_widget)

        # Instanciation des widgets principaux
        self.project_widget  = ProjectWidget(self.db, self.user)
        # self.tests_widget    = TestSessionWidget(self.db, self.user)  # Dé-commente si nécessaire
        self.etalons_widget  = EtalonsWidget(self.db, self.user)
        self.users_widget    = UsersWidget(self.db)

        # Ajout au layout (tous cachés sauf celui affiché)
        for w in (
            self.project_widget,
            # self.tests_widget,
            self.etalons_widget,
            self.users_widget
        ):
            self.content_layout.addWidget(w)

        # Affiche l'onglet Projets au démarrage
        self.show_projects()

    # ----------------- Vues -----------------

    def _hide_all(self):
        self.project_widget.hide()
        # if hasattr(self, 'tests_widget'): self.tests_widget.hide()
        self.etalons_widget.hide()
        self.users_widget.hide()

    def show_projects(self):
        self._hide_all()
        self.project_widget.refresh_projects()
        self.project_widget.show()

    def show_tests(self):
        self._hide_all()
        # if hasattr(self, 'tests_widget'):
        #     self.tests_widget.refresh()
        #     self.tests_widget.show()

    def show_etalons(self):
        self._hide_all()
        self.etalons_widget.reload()
        self.etalons_widget.show()

    def show_users(self):
        self._hide_all()
        self.users_widget.refresh_users()
        self.users_widget.show()

    # ----------------- Session -----------------

    def logout(self):
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
