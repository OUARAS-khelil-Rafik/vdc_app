#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
main.py
Point d’entrée de l’application VDC Engineering MVP.
Crée l’application Qt, initialise la base de données et affiche la fenêtre de login.
"""

import sys
import os
from PyQt5.QtWidgets import QApplication

# Assurez-vous que le répertoire `data/` existe
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "vdc.db")

from models.database import Database
from gui.login import LoginWindow

def main():
    # Création du dossier data s'il n'existe pas
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR)

    # Initialisation de la base SQLite
    db = Database(DB_PATH)
    db.initialize()  # Crée les tables si nécessaire

    # Initialisation de l'application Qt
    app = QApplication(sys.argv)
    app.setApplicationName("VDC Engineering")

    # Affichage de la fenêtre de connexion
    login_win = LoginWindow(db)
    login_win.show()

    # Lancement de la boucle événementielle
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
