#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/login.py
Fenêtre de connexion pour l’application VDC Engineering MVP.
Gère l’authentification des utilisateurs et leurs rôles
(Administrateur, Technicien, Technicien premium) :contentReference[oaicite:1]{index=1}.
"""

from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt
from gui.signup import SignupWindow

class LoginWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Connexion")
        self.setFixedSize(300, 180)

        # Champs utilisateur / mot de passe
        self.label_username = QLabel("Utilisateur :")
        self.input_username = QLineEdit()
        self.label_password = QLabel("Mot de passe :")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)

        # Bouton de connexion
        self.button_login = QPushButton("Se connecter")
        self.button_login.clicked.connect(self._handle_login)

        # Lien ou bouton d'inscription
        self.button_signup = QPushButton("Créer un compte")
        self.button_signup.setFlat(True)
        self.button_signup.setStyleSheet("color: blue; text-decoration: underline; background: none; border: none;")
        self.button_signup.clicked.connect(self._handle_signup)

        # Layout vertical
        layout = QVBoxLayout()
        layout.addWidget(self.label_username)
        layout.addWidget(self.input_username)
        layout.addWidget(self.label_password)
        layout.addWidget(self.input_password)
        layout.addWidget(self.button_login, alignment=Qt.AlignCenter)
        layout.addWidget(self.button_signup, alignment=Qt.AlignCenter)
        self.setLayout(layout)

    def _handle_login(self):
        username = self.input_username.text().strip()
        password = self.input_password.text()

        # Authentification via la base de données
        user = self.db.authenticate_user(username, password)
        if user:
            from gui.dashboard import DashboardWindow
            self.dashboard = DashboardWindow(self.db, user)
            self.dashboard.show()
            self.close()
        else:
            QMessageBox.warning(
                self,
                "Erreur d’authentification",
                "Nom d’utilisateur ou mot de passe incorrect.",
                QMessageBox.Ok
            )

    # la méthode _handle_signup :
    def _handle_signup(self):
        self.signup_window = SignupWindow(self.db)
        self.close()
        self.signup_window.show()
