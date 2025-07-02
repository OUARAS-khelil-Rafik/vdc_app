# gui/thresholds.py
from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy,
    QPushButton, QFormLayout, QLineEdit, QComboBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from models.thresholdmanager import ThresholdManager

class ThresholdsTable(QTableWidget):
    HEADERS = ["ID", "Projet", "Test", "Min", "Max"]
    COLUMNS = ["id", "project_id", "test_name", "min_value", "max_value"]

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
        for i, row in enumerate(rows):
            for col, key in enumerate(self.COLUMNS):
                if key == "project_id":
                    pid = row.get("project_id")
                    proj = self.db.conn.execute(
                        "SELECT company_name FROM projects WHERE id = ?",
                        (pid,)
                    ).fetchone()
                    text = proj["company_name"] if proj else str(pid)
                else:
                    text = str(row.get(key, ""))
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(Qt.white))
                if col == 0:
                    item.setData(Qt.UserRole, row.get("id"))
                self.setItem(i, col, item)
        # masquer la colonne ID
        self.hideColumn(0)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_threshold_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        return self.item(sel, 0).data(Qt.UserRole)

class ThresholdForm(QDialog):
    def __init__(self, db, threshold=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.threshold = threshold
        self.setWindowTitle("Modifier seuil" if threshold else "Nouveau seuil")
        self.setModal(True)
        self.resize(400, 200)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QComboBox, QLineEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 13px; }
            QPushButton {
                background-color: #b8d5ed; color: #1c5ea3; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1c5ea3; color: #fff; }
        """)
        # Champs du formulaire
        self.input_project = QComboBox()
        # Charger les projets existants
        for p in self.db.conn.execute("SELECT id, company_name FROM projects").fetchall():
            self.input_project.addItem(p["company_name"], p["id"])
        self.input_test = QLineEdit()
        self.input_min = QLineEdit()
        self.input_min.setPlaceholderText("Optionnel")
        self.input_max = QLineEdit()
        self.input_max.setPlaceholderText("Optionnel")

        # Pré-remplissage si modification
        if threshold:
            # seuil passé sous forme de dict avec clés id, project_id, test_name, min_value, max_value
            idx = self.input_project.findData(threshold["project_id"])
            if idx >= 0:
                self.input_project.setCurrentIndex(idx)
            self.input_test.setText(threshold.get("test_name", ""))
            if threshold.get("min_value") is not None:
                self.input_min.setText(str(threshold["min_value"]))
            if threshold.get("max_value") is not None:
                self.input_max.setText(str(threshold["max_value"]))

        form = QFormLayout()
        form.addRow("Projet :", self.input_project)
        form.addRow("Nom du test :", self.input_test)
        form.addRow("Valeur min :", self.input_min)
        form.addRow("Valeur max :", self.input_max)

        self.btn_save = QPushButton("Modifier" if threshold else "Enregistrer")
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
        # Retourne les valeurs saisies, sous forme brute
        return {
            "project_id": self.input_project.currentData(),
            "test_name": self.input_test.text().strip(),
            "min_value": self.input_min.text().strip(),
            "max_value": self.input_max.text().strip(),
        }

class ThresholdsWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self.manager = ThresholdManager(db)

        self.setStyleSheet("""
            QWidget { background-color: #e0e0e0; }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)

        self.table = ThresholdsTable(self.db)
        self.table.setFocusPolicy(Qt.NoFocus)

        self.btn_add = QPushButton("Ajouter Seuil")
        self.btn_edit = QPushButton("Modifier Seuil")
        self.btn_delete = QPushButton("Supprimer Seuil")

        self.btn_add.clicked.connect(self.add_threshold)
        self.btn_edit.clicked.connect(self.edit_threshold)
        self.btn_delete.clicked.connect(self.delete_threshold)

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

        # Seuls Administrateur et Technicien premium
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            self.btn_add.hide()
            self.btn_edit.hide()
            self.btn_delete.hide()

        self.refresh_thresholds()

    def refresh_thresholds(self):
        rows = self.manager.get_thresholds()
        self.table.populate(rows)

    def add_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        dialog = ThresholdForm(self.db)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            # validation des champs
            if not data["test_name"] or data["project_id"] is None:
                QMessageBox.warning(self, "Champs manquants", "Projet et nom du test obligatoires.", QMessageBox.Ok)
                return
            # au moins une borne doit être renseignée
            if data["min_value"] == "" and data["max_value"] == "":
                QMessageBox.warning(self, "Champs manquants", "Au moins une valeur min ou max doit être renseignée.", QMessageBox.Ok)
                return
            try:
                min_val = float(data["min_value"]) if data["min_value"] else None
                max_val = float(data["max_value"]) if data["max_value"] else None
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "Les valeurs min/max doivent être des nombres.", QMessageBox.Ok)
                return
            try:
                self.manager.add_threshold(data["project_id"], data["test_name"], min_val, max_val)
                self.refresh_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible d’ajouter le seuil : {e}", QMessageBox.Ok)

    def edit_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        tid = self.table.get_selected_threshold_id()
        if tid is None:
            QMessageBox.warning(self, "Aucun seuil", "Veuillez sélectionner un seuil à modifier.", QMessageBox.Ok)
            return

        thresh = self.manager.get_threshold(tid)
        if not thresh:
            QMessageBox.warning(self, "Erreur", "Seuil non trouvé.", QMessageBox.Ok)
            return

        dialog = ThresholdForm(self.db, thresh)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["test_name"] or data["project_id"] is None:
                QMessageBox.warning(self, "Champs manquants", "Projet et nom du test obligatoires.", QMessageBox.Ok)
                return
            if data["min_value"] == "" and data["max_value"] == "":
                QMessageBox.warning(self, "Champs manquants", "Au moins une valeur min ou max doit être renseignée.", QMessageBox.Ok)
                return
            try:
                min_val = float(data["min_value"]) if data["min_value"] else None
                max_val = float(data["max_value"]) if data["max_value"] else None
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "Les valeurs min/max doivent être des nombres.", QMessageBox.Ok)
                return
            try:
                self.manager.update_threshold(tid, data["project_id"], data["test_name"], min_val, max_val)
                self.refresh_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de modifier le seuil : {e}", QMessageBox.Ok)

    def delete_threshold(self):
        if self.user['role'] not in ("Administrateur", "Technicien premium"):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return

        tid = self.table.get_selected_threshold_id()
        if tid is None:
            QMessageBox.warning(self, "Aucun seuil", "Veuillez sélectionner un seuil à supprimer.", QMessageBox.Ok)
            return

        confirm = QMessageBox.question(
            self, "Confirmation", "Supprimer ce seuil définitivement ?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                self.manager.delete_threshold(tid)
                self.refresh_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le seuil : {e}", QMessageBox.Ok)
