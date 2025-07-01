import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox
)

class SignupWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.setWindowTitle("Technicien - Inscription")
        self.setGeometry(100, 100, 350, 250)
        self.db = db
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        self.username_label = QLabel("Nom d'utilisateur:")
        self.username_input = QLineEdit()
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)

        self.password_label = QLabel("Mot de passe:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)

        self.confirm_label = QLabel("Confirmer le mot de passe:")
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.confirm_label)
        layout.addWidget(self.confirm_input)

        self.signup_btn = QPushButton("S'inscrire")
        self.signup_btn.clicked.connect(self.handle_signup)
        layout.addWidget(self.signup_btn)

        # Ajout du bouton "Se connecter"
        self.login_btn = QPushButton("Se connecter")
        self.login_btn.clicked.connect(self.open_login)
        layout.addWidget(self.login_btn)

        self.setLayout(layout)

    def handle_signup(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not username or not password or not confirm:
            QMessageBox.warning(self, "Erreur", "Tous les champs sont obligatoires.")
            return

        if password != confirm:
            QMessageBox.warning(self, "Erreur", "Les mots de passe ne correspondent pas.")
            return

        if len(password) < 6:
            QMessageBox.warning(self, "Erreur", "Le mot de passe doit contenir au moins 6 caractères.")
            return

        try:
            self.db.create_user(username, password, "Technicien")
            QMessageBox.information(self, "Succès", "Inscription réussie !")
            self.open_login()  # Ouvre la fenêtre de connexion après inscription
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                QMessageBox.warning(self, "Erreur", "Nom d'utilisateur déjà existant.")
            else:
                QMessageBox.warning(self, "Erreur", f"Erreur lors de l'inscription : {e}")

    def open_login(self):
        from gui.login import LoginWindow  # Import ici pour éviter l'import circulaire
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()
