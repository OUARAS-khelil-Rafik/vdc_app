import sys
import os
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QApplication
)
from PyQt5.QtCore import Qt

class SignupWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.setWindowTitle("Technicien - Inscription")
        self.setFixedSize(350, 380)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        # Center the window using QScreen
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        self.db = db
        self.login_window = None
        self.init_ui()

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

        self.username_label = QLabel("Nom d'utilisateur:")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Entrez votre nom d'utilisateur")
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)

        self.password_label = QLabel("Mot de passe:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Entrez votre mot de passe")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)

        self.confirm_label = QLabel("Confirmer le mot de passe:")
        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("Confirmez votre mot de passe")
        self.confirm_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.confirm_label)
        layout.addWidget(self.confirm_input)

        self.signup_btn = QPushButton("S'inscrire")
        self.signup_btn.clicked.connect(self.handle_signup)
        layout.addWidget(self.signup_btn)

        self.login_label = QLabel("<a href='#'>Déjà un compte ? Se connecter</a>")
        self.login_label.setAlignment(Qt.AlignCenter)
        self.login_label.setTextFormat(Qt.RichText)
        self.login_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.login_label.setOpenExternalLinks(False)
        self.login_label.linkActivated.connect(lambda _: self.open_login())
        self.login_label.setStyleSheet("""
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
        layout.addWidget(self.login_label)

        self.setLayout(layout)

    def handle_signup(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not username or not password or not confirm:
            QMessageBox.warning(self, "Erreur", "Tous les champs sont obligatoires.")
            return

        if not re.match(r"^[A-Za-z0-9_.-]{3,20}$", username):
            QMessageBox.warning(self, "Erreur", "Le nom d'utilisateur doit contenir uniquement des lettres, chiffres, points, tirets ou underscores (3-20 caractères).")
            return

        if password != confirm:
            QMessageBox.warning(self, "Erreur", "Les mots de passe ne correspondent pas.")
            return

        if len(password) < 8:
            QMessageBox.warning(self, "Erreur", "Le mot de passe doit contenir au moins 8 caractères.")
            return

        # Optionnel : vérification de complexité du mot de passe
        if not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"\d", password):
            QMessageBox.warning(self, "Erreur", "Le mot de passe doit contenir au moins une majuscule, une minuscule et un chiffre.")
            return

        try:
            self.db.create_user(username, password, "Technicien")
            QMessageBox.information(self, "Succès", "Inscription réussie !")
            self.open_login()
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                QMessageBox.warning(self, "Erreur", "Nom d'utilisateur déjà existant.")
            else:
                QMessageBox.warning(self, "Erreur", f"Erreur lors de l'inscription : {e}")

    def open_login(self):
        if self.login_window is None:
            from gui.login import LoginWindow
            self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
