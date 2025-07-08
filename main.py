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
from PyQt5.QtGui import QIcon

from models.database import Database
from gui.login import LoginWindow

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "vdc.db")
ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "vdc_logo.png")

def ensure_data_dir():
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR)

def initialize_database():
    db = Database(DB_PATH)
    db.initialize()
    try:
        db.create_user("admin", "admin", "SAIDI Nacim", "Administrateur", "Validé")
    except Exception:
        pass  # Ignore if user already exists
    return db

def main():
    ensure_data_dir()
    db = initialize_database()

    app = QApplication(sys.argv)
    app.setApplicationName("VDC Engineering")
    app.setWindowIcon(QIcon(ICON_PATH))

    login_win = LoginWindow(db)
    login_win.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
