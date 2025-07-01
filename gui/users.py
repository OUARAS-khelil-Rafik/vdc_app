from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem
import sqlite3

class UsersWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        label = QLabel("Utilisateurs")
        layout.addWidget(label)

        # Table to display users
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["ID", "Nom d'utilisateur"])

        # Fetch users from the database
        users = self.fetch_users_from_db()

        self.table.setRowCount(len(users))
        for row, user in enumerate(users):
            self.table.setItem(row, 0, QTableWidgetItem(str(user[0])))
            self.table.setItem(row, 1, QTableWidgetItem(user[1]))

        layout.addWidget(self.table)
        self.setLayout(layout)

    def fetch_users_from_db(self):
        conn = sqlite3.connect("data/vdc.db")
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, username FROM users")
            users = cursor.fetchall()
        except Exception as e:
            users = []
        finally:
            conn.close()
        return users