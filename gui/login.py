#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/login.py
Fenêtre de connexion pour l’application VDC Engineering MVP.
Gère l’authentification des utilisateurs et leurs rôles
(Administrateur, Technicien, Technicien premium).
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
        # Center the window on the screen
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

        self.label_username = QLabel("Nom d'utilisateur :")
        self.input_username = QLineEdit()
        self.input_username.setPlaceholderText("Entrez votre nom d'utilisateur")
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
        username = self.input_username.text().strip()
        password = self.input_password.text()

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

    def _handle_signup(self):
        self.signup_window = SignupWindow(self.db)
        self.signup_window.show()
        self.signup_window.raise_()
        self.close()
