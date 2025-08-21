# gui/dashboard.py

"""
Tableau de bord principal de l’application VDC Engineering (MVP).

Fonctionnalités :
- Navigation : Projets, Tests, Seuils, Utilisateurs, Déconnexion.
- Intègre les widgets : ProjectWidget, TestSessionWidget, ThresholdsWidget, UsersWidget.
- Règles d’accès selon le rôle :
    * Seuils visibles pour : Administrateur, Superviseur, Technicien responsable.
    * Utilisateurs visible uniquement pour : Administrateur.
- Rôles supportés : Administrateur, Technicien, Technicien responsable, Superviseur.
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
from .thresholds  import ThresholdsWidget
from .users       import UsersWidget
from .test        import TestSessionWidget

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
        self.actions_dict = {
            'projects':   QAction(QIcon("icons/projects.png"),   "Projets",      self),
            'tests':      QAction(QIcon("icons/tests.png"),      "Tests",        self),
            'thresholds': QAction(QIcon("icons/thresholds.png"), "Seuils",       self),
            'users':      QAction(QIcon("icons/users.png"),      "Utilisateurs", self),
            'logout':     QAction(QIcon("icons/logout.png"),     "Déconnexion",   self)
        }
        for act in self.actions_dict.values():
            act.setIconText(act.text())
            act.setText("")

        spacer_l = QWidget()
        spacer_l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer_r = QWidget()
        spacer_r.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.addWidget(spacer_l)
        for key in ('projects','tests','thresholds','users'):
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

        # Connecte les actions de base
        self.toolbar.actions_dict['projects'].triggered.connect(self.show_projects)
        self.toolbar.actions_dict['tests'].triggered.connect(self.show_tests)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)

        # Logique des rôles
        role = (self.user.get('role') or '').strip().lower()
        # Seuils: Administrateur, Superviseur, Technicien responsable
        thresholds_allowed = role in {'administrateur', 'superviseur', 'technicien responsable'}
        self.toolbar.actions_dict['thresholds'].setVisible(thresholds_allowed)
        if thresholds_allowed:
            self.toolbar.actions_dict['thresholds'].triggered.connect(self.show_thresholds)

        # Utilisateurs: seulement Administrateur
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

        # Instanciation des widgets
        self.project_widget    = ProjectWidget(self.db, self.user)
        #self.tests_widget      = TestSessionWidget(self.db, self.user)
        #self.thresholds_widget = ThresholdsWidget(self.db, self.user)
        self.users_widget      = UsersWidget(self.db)

        # Ajout au layout
        for w in (self.project_widget,
                  # self.tests_widget,
                  #self.thresholds_widget,
                  self.users_widget):
            self.content_layout.addWidget(w)

        # Affiche l'onglet Projets au démarrage
        self.show_projects()

    def show_projects(self):
        self.project_widget.refresh_projects()
        self.project_widget.show()
        #self.tests_widget.hide()
        #self.thresholds_widget.hide()
        self.users_widget.hide()

    def show_tests(self):
        self.project_widget.hide()
        #self.thresholds_widget.hide()
        self.users_widget.hide()
        #self.tests_widget.refresh()
        #self.tests_widget.show()

    def show_thresholds(self):
        #self.thresholds_widget.refresh_thresholds()
        self.project_widget.hide()
        #self.tests_widget.hide()
        #self.thresholds_widget.show()
        self.users_widget.hide()

    def show_users(self):
        self.users_widget.refresh_users()
        self.project_widget.hide()
        #self.tests_widget.hide()
        #self.thresholds_widget.hide()
        self.users_widget.show()

    def logout(self):
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
