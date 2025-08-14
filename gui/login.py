# gui/login.py

"""
Fenêtre de connexion de l’application VDC Engineering (MVP).

Fonctions :
- Authentification par nom d’utilisateur ou email + mot de passe.
- Vérification de la validation du compte avant l’accès au tableau de bord.
- Lien vers la création de compte.

Rôles pris en charge :
- Administrateur, Technicien, Technicien responsable, Superviseur.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QApplication
)
from PyQt5.QtCore import Qt
from gui.signup import SignupWindow

class LoginWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("VDC Engineering – Connexion")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setFixedSize(350, 280)
        self.init_ui()
        self.center_window()

    def center_window(self):
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)

    def init_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #e0e0e0;
            }
            QLabel {
                color: #1c5ea3;
                font-size: 14px;
                font-weight: bold;
            }
            QLineEdit {
                background: #f0f0f0;
                border: 1px solid #1c5ea3;
                border-radius: 5px;
                padding: 5px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: white;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #14467a;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        self.label_username = QLabel("Nom d'utilisateur ou Email :")
        self.input_username = QLineEdit()
        self.input_username.setPlaceholderText("Entrez votre nom d'utilisateur ou votre email")
        layout.addWidget(self.label_username)
        layout.addWidget(self.input_username)

        self.label_password = QLabel("Mot de passe :")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setPlaceholderText("Entrez votre mot de passe")
        layout.addWidget(self.label_password)
        layout.addWidget(self.input_password)

        self.button_login = QPushButton("Se connecter")
        self.button_login.clicked.connect(self._handle_login)
        layout.addWidget(self.button_login)

        self.signup_label = QLabel("<a href='#'>Créer un compte</a>")
        self.signup_label.setAlignment(Qt.AlignCenter)
        self.signup_label.setTextFormat(Qt.RichText)
        self.signup_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.signup_label.setOpenExternalLinks(False)
        self.signup_label.linkActivated.connect(lambda _: self._handle_signup())
        self.signup_label.setStyleSheet("""
            QLabel {
                color: #1c5ea3;
                font-size: 13px;
                text-decoration: underline;
                margin-top: 10px;
            }
            QLabel:hover {
                color: #14467a;
            }
        """)
        layout.addWidget(self.signup_label)

        self.setLayout(layout)

    def _handle_login(self):
        login_value = self.input_username.text().strip()
        password = self.input_password.text()
        if not login_value or not password:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Veuillez remplir tous les champs.",
                QMessageBox.Ok
            )
            return

        # Try to authenticate using username or email
        user = None
        try:
            # If DB supports a unified method that accepts username or email
            user = self.db.authenticate_user(login_value, password)
        except Exception:
            user = None

        # If not authenticated and it's likely an email, try email-specific method if available
        if user is None and "@" in login_value and hasattr(self.db, "authenticate_user_by_email"):
            try:
                user = self.db.authenticate_user_by_email(login_value, password)
            except Exception:
                user = None

        # If still not authenticated and a username-specific method exists, try it
        if user is None and hasattr(self.db, "authenticate_user_by_username"):
            try:
                user = self.db.authenticate_user_by_username(login_value, password)
            except Exception:
                user = None

        self.input_password.clear()
        if user is not None:
            from gui.dashboard import DashboardWindow
            self.dashboard = DashboardWindow(self.db, user)
            self.dashboard.show()
            self.close()
        else:
            QMessageBox.warning(
                self,
                "Erreur d’authentification",
                "Nom d'utilisateur, email, mot de passe ou validation incorrects.",
                QMessageBox.Ok
            )

    def _handle_signup(self):
        if hasattr(self, 'signup_window') and self.signup_window is not None:
            self.signup_window.raise_()
            self.signup_window.activateWindow()
        else:
            self.signup_window = SignupWindow(self.db)
            self.signup_window.show()
        self.close()
