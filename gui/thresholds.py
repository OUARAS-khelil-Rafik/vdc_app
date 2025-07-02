from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy,
    QPushButton, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from models.thresholdmanager import ThresholdManager
from models.utils import dict_from_row

class ThresholdsTable(QTableWidget):
    HEADERS = ["ID", "Classe ISO", "Paramètre", "Valeur max"]
    COLUMNS = ["id", "iso_class", "parameter", "max_value"]

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
        for i, row in enumerate(rows):
            row = dict_from_row(row, self.COLUMNS)
            for col, key in enumerate(self.COLUMNS):
                item = QTableWidgetItem(str(row[key]))
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(Qt.white))
                if col == 0:
                    item.setData(Qt.UserRole, row['id'])
                self.setItem(i, col, item)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hideColumn(self.COLUMNS.index("id"))

    def get_selected_threshold_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        return item.data(Qt.UserRole) if item else None

class ThresholdForm(QDialog):
    def __init__(self, db, threshold=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.threshold = threshold
        self.setWindowTitle("Modifier seuil" if threshold else "Nouveau seuil")
        self.setModal(True)
        self.resize(350, 180)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QLineEdit {
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
        self.input_iso = QLineEdit()
        self.input_param = QLineEdit()
        self.input_max = QLineEdit()
        if threshold:
            self.input_iso.setText(str(threshold.get("iso_class", "")))
            self.input_param.setText(str(threshold.get("parameter", "")))
            self.input_max.setText(str(threshold.get("max_value", "")))
        form = QFormLayout()
        form.addRow("Classe ISO :", self.input_iso)
        form.addRow("Paramètre  :", self.input_param)
        form.addRow("Valeur Max :", self.input_max)
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
        return {
            "iso_class": self.input_iso.text().strip(),
            "parameter": self.input_param.text().strip(),
            "max_value": self.input_max.text().strip()
        }

class ThresholdsWidget(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.manager = ThresholdManager(db)
        self.setStyleSheet("""
            QWidget { background-color: #e0e0e0; }
            QTableWidget {
                background-color: #fff; alternate-background-color: #fff;
                gridline-color: #1c5ea3; selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; border: 2px solid #1c5ea3; font-size: 15px;
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
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)
        self.table = ThresholdsTable()
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
        self.refresh_thresholds()

    def refresh_thresholds(self):
        dict_rows = self.manager.get_thresholds()
        self.table.populate(dict_rows)
        for i in range(self.table.rowCount()):
            for j in range(self.table.columnCount()):
                item = self.table.item(i, j)
                if item:
                    item.setBackground(QColor(Qt.white))
                    item.setTextAlignment(Qt.AlignCenter)

    def add_threshold(self):
        dialog = ThresholdForm(self.db)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not (data["iso_class"] and data["parameter"] and data["max_value"]):
                QMessageBox.warning(self, "Champs manquants", "Tous les champs doivent être remplis.", QMessageBox.Ok)
                return
            try:
                mv = float(data["max_value"])
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "La valeur max doit être un nombre.", QMessageBox.Ok)
                return
            try:
                self.manager.add_threshold(data["iso_class"], data["parameter"], mv)
                self.refresh_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible d’ajouter le seuil : {e}", QMessageBox.Ok)

    def edit_threshold(self):
        threshold_id = self.table.get_selected_threshold_id()
        if threshold_id is None:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner un seuil à modifier.", QMessageBox.Ok)
            return
        threshold = self.manager.get_threshold(threshold_id)
        if not threshold:
            QMessageBox.warning(self, "Erreur", "Seuil non trouvé.", QMessageBox.Ok)
            return
        dialog = ThresholdForm(self.db, threshold)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not (data["iso_class"] and data["parameter"] and data["max_value"]):
                QMessageBox.warning(self, "Champs manquants", "Tous les champs doivent être remplis.", QMessageBox.Ok)
                return
            try:
                mv = float(data["max_value"])
            except ValueError:
                QMessageBox.warning(self, "Valeur incorrecte", "La valeur max doit être un nombre.", QMessageBox.Ok)
                return
            try:
                self.manager.update_threshold(threshold_id, data["iso_class"], data["parameter"], mv)
                self.refresh_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de modifier le seuil : {e}", QMessageBox.Ok)

    def delete_threshold(self):
        threshold_id = self.table.get_selected_threshold_id()
        if threshold_id is None:
            QMessageBox.warning(self, "Aucune sélection", "Veuillez sélectionner un seuil à supprimer.", QMessageBox.Ok)
            return
        confirm = QMessageBox.question(
            self, "Confirmation", "Supprimer ce seuil définitivement ?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                self.manager.delete_threshold(threshold_id)
                self.refresh_thresholds()
                self.table.clearSelection()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le seuil : {e}", QMessageBox.Ok)
