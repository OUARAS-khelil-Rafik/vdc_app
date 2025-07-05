from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
    QMessageBox, QDialog, QHeaderView, QSizePolicy, QPushButton, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class TestsTable(QTableWidget):
    HEADERS = ["ID", "Nom du test"]
    COLUMNS = ["id", "name"]

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
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
        self.setStyleSheet("")

    def populate(self, rows):
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for col, key in enumerate(self.COLUMNS):
                text = str(row.get(key, ""))
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(Qt.white))
                if col == 0:
                    item.setData(Qt.UserRole, row.get("id"))
                self.setItem(i, col, item)
        self.hideColumn(0)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_test_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        return self.item(sel, 0).data(Qt.UserRole)

class TestForm(QDialog):
    def __init__(self, db, test=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.test = test
        self.setWindowTitle("Modifier test" if test else "Nouveau test")
        self.setModal(True)
        self.resize(300, 120)
        self.setStyleSheet("")
        self.input_name = QLineEdit()
        if test:
            self.input_name.setText(test.get("name", ""))
        form = QFormLayout()
        form.addRow("Nom du test :", self.input_name)
        self.btn_save = QPushButton("Edit" if test else "Save")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(form)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def get_data(self):
        return {"name": self.input_name.text().strip()}

class TestsWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self.setStyleSheet("")
        self.table = TestsTable(self.db)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.btn_add = QPushButton("Add Test")
        self.btn_edit = QPushButton("Edit Test")
        self.btn_delete = QPushButton("Delete Test")
        self.btn_add.clicked.connect(self.add_test)
        self.btn_edit.clicked.connect(self.edit_test)
        self.btn_delete.clicked.connect(self.delete_test)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        if self.user['role'] not in ("Administrator", "Premium Technician"):
            self.btn_add.hide()
            self.btn_edit.hide()
            self.btn_delete.hide()
        self.refresh_tests()

    def refresh_tests(self):
        rows = self.db.conn.execute("PRAGMA table_info(tests)").fetchall()
        column_names = [col[1] for col in rows]
        display_name = "name" if "name" in column_names else column_names[1] if len(column_names) > 1 else ""
        rows = self.db.conn.execute(f"SELECT id, {display_name} FROM tests").fetchall()
        # Convert to dict for compatibility with populate
        dict_rows = []
        for row in rows:
            dict_rows.append({"id": row[0], "name": row[1]})
        self.table.populate(dict_rows)

    def add_test(self):
        dialog = TestForm(self.db)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Missing Fields", "Test name is required.", QMessageBox.Ok)
                return
            try:
                self.db.conn.execute("INSERT INTO tests (name) VALUES (?)", (data["name"],))
                self.db.conn.commit()
                self.refresh_tests()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Unable to add test: {e}", QMessageBox.Ok)
    
    def edit_test(self):
        tid = self.table.get_selected_test_id()
        if tid is None:
            QMessageBox.warning(self, "No Test Selected", "Please select a test to edit.", QMessageBox.Ok)
            return
        test = self.db.conn.execute("SELECT * FROM tests WHERE id = ?", (tid,)).fetchone()
        if not test:
            QMessageBox.warning(self, "Error", "Test not found.", QMessageBox.Ok)
            return
        # Convert sqlite3.Row to dict if needed
        test_dict = dict(test)
        dialog = TestForm(self.db, test_dict)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Missing Fields", "Test name is required.", QMessageBox.Ok)
                return
            try:
                self.db.conn.execute("UPDATE tests SET name = ? WHERE id = ?", (data["name"], tid))
                self.db.conn.commit()
                self.refresh_tests()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Unable to edit test: {e}", QMessageBox.Ok)

    def delete_test(self):
        tid = self.table.get_selected_test_id()
        if tid is None:
            QMessageBox.warning(self, "No Test Selected", "Please select a test to delete.", QMessageBox.Ok)
            return
        confirm = QMessageBox.question(
            self, "Confirmation", "Delete this test permanently?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                self.db.conn.execute("DELETE FROM tests WHERE id = ?", (tid,))
                self.db.conn.commit()
                self.refresh_tests()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Unable to delete test: {e}", QMessageBox.Ok)
