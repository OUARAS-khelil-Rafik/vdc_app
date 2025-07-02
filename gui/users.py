from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidgetItem, QHeaderView, QSizePolicy, QTableWidget,
    QPushButton, QHBoxLayout, QDialog, QFormLayout, QLineEdit, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
import sqlite3

class UserManager:
    DB_PATH = "data/vdc.db"

    @staticmethod
    def fetch_users():
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, username, role FROM users")
            users = cursor.fetchall()
        except Exception:
            users = []
        finally:
            conn.close()
        return users

    @staticmethod
    def username_exists(username, exclude_id=None):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            if exclude_id:
                cursor.execute("SELECT 1 FROM users WHERE username=? AND id!=?", (username, exclude_id))
            else:
                cursor.execute("SELECT 1 FROM users WHERE username=?", (username,))
            exists = cursor.fetchone() is not None
        finally:
            conn.close()
        return exists

    @staticmethod
    def add_user(username, role):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, role) VALUES (?, ?)", (username, role))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def update_user(user_id, username, role):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE users SET username=?, role=? WHERE id=?", (username, role, user_id))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def delete_user(user_id):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE id=? AND role!='admin'", (user_id,))
            conn.commit()
        finally:
            conn.close()

class UserForm(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.setWindowTitle("Utilisateur")
        self.user = user
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        self.username_edit = QLineEdit(self)
        self.role_combo = QComboBox(self)
        self.role_combo.addItems(["Technicien premium", "Technicien"])
        # Si modification, afficher le rôle existant même si c'est admin
        if self.user:
            self.username_edit.setText(self.user[1])
            if self.user[2] not in ["Technicien premium", "Technicien"]:
                self.role_combo.addItem(self.user[2])
            self.role_combo.setCurrentText(self.user[2])

        layout.addRow("Nom d'utilisateur:", self.username_edit)
        layout.addRow("Rôle:", self.role_combo)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Enregistrer")
        self.save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.save_btn)
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)

    def get_data(self):
        return self.username_edit.text().strip(), self.role_combo.currentText()

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

class UsersTable(NoFocusTableWidget):
    HEADERS = ["ID", "Nom d'utilisateur", "Role"]
    COLUMNS = ["id", "username", "role"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.ExtendedSelection)
        self.setEditTriggers(self.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #fff; 
                alternate-background-color: #b8d5ed;
                gridline-color: #1c5ea3; 
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; 
                border: 2px solid #1c5ea3; 
                font-size: 15px;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QTableWidget::item {
                border-bottom: 1px solid #b8d5ed;
                border-right: 1px solid #b8d5ed;
            }
        """)

    def populate(self, rows):
        self.setRowCount(len(rows))
        for i, user in enumerate(rows):
            for col, key in enumerate(self.COLUMNS):
                item = QTableWidgetItem(str(user[col]))
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(Qt.white))
                if col == 0:
                    item.setData(Qt.UserRole, user[0])
                self.setItem(i, col, item)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_user_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        return item.data(Qt.UserRole) if item else None

class UsersWidget(QWidget):
    def __init__(self, parent=None):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.head_label = QLabel("Utilisateurs")
        self.head_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #1c5ea3;")
        layout.addWidget(self.head_label)

        self.table = UsersTable()
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Ajouter")
        self.add_btn.clicked.connect(self.add_user)
        btn_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Modifier")
        self.edit_btn.clicked.connect(self.edit_user)
        btn_layout.addWidget(self.edit_btn)

        self.del_btn = QPushButton("Supprimer")
        self.del_btn.clicked.connect(self.delete_user)
        btn_layout.addWidget(self.del_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.refresh_users()

    def refresh_users(self):
        users = UserManager.fetch_users()
        self.table.populate(users)

    def add_user(self):
        form = UserForm(self)
        if form.exec_() == QDialog.Accepted:
            username, role = form.get_data()
            if not username or not role:
                QMessageBox.warning(self, "Erreur", "Veuillez remplir tous les champs.")
                return
            if UserManager.username_exists(username):
                QMessageBox.warning(self, "Erreur", "Ce nom d'utilisateur existe déjà.")
                return
            UserManager.add_user(username, role)
            self.refresh_users()

    def edit_user(self):
        user_id = self.table.get_selected_user_id()
        if user_id is None:
            return
        row = self.table.currentRow()
        username = self.table.item(row, 1).text()
        role = self.table.item(row, 2).text()
        if role == "admin":
            QMessageBox.warning(self, "Erreur", "Impossible de modifier un admin.")
            return
        form = UserForm(self, user=(user_id, username, role))
        if form.exec_() == QDialog.Accepted:
            new_username, new_role = form.get_data()
            if not new_username or not new_role:
                QMessageBox.warning(self, "Erreur", "Veuillez remplir tous les champs.")
                return
            if UserManager.username_exists(new_username, exclude_id=user_id):
                QMessageBox.warning(self, "Erreur", "Ce nom d'utilisateur existe déjà.")
                return
            UserManager.update_user(user_id, new_username, new_role)
            self.refresh_users()

    def delete_user(self):
        user_id = self.table.get_selected_user_id()
        if user_id is None:
            return
        row = self.table.currentRow()
        role = self.table.item(row, 2).text()
        if role == "admin":
            QMessageBox.warning(self, "Erreur", "Impossible de supprimer un admin.")
            return
        reply = QMessageBox.question(self, "Confirmation", "Supprimer cet utilisateur ?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            UserManager.delete_user(user_id)
            self.refresh_users()