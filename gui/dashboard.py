#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/dashboard.py

Tableau de bord principal de l’application VDC Engineering MVP.
Affiche la liste des projets et propose les fonctionnalités disponibles
selon le rôle de l’utilisateur (Administrateur, Technicien, Technicien premium).
"""

import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy, QToolBar, QAction,
    QPushButton, QFormLayout, QLineEdit, QDateEdit
)
from PyQt5.QtCore import Qt, QDate, QDateTime
from PyQt5.QtGui import QColor

def dict_from_row(row, columns):
    if isinstance(row, dict):
        return row
    return dict(zip(columns, row))

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

class ProjectTable(NoFocusTableWidget):
    HEADERS = ["ID", "Entreprise", "Localisation", "Type de salle", "Date de test"]
    COLUMNS = ["id", "company_name", "location", "room_type", "test_date"]

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

    def get_selected_project_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        return item.data(Qt.UserRole) if item else None

class ProjectManager:
    def __init__(self, db):
        self.db = db

    def get_projects(self):
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        columns = ["id", "company_name", "location", "room_type", "test_date"]
        return [dict_from_row(row, columns) for row in rows]

    def add_project(self, company, location, room, date, user_id):
        self.db.conn.execute(
            "INSERT INTO projects (company_name, location, room_type, test_date, created_by) VALUES (?, ?, ?, ?, ?)",
            (company, location, room, date, user_id)
        )
        self.db.conn.commit()

    def update_project(self, project_id, company, location, room, date):
        self.db.conn.execute(
            "UPDATE projects SET company_name=?, location=?, room_type=?, test_date=? WHERE id=?",
            (company, location, room, date, project_id)
        )
        self.db.conn.commit()

    def delete_project(self, project_id):
        self.db.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.db.conn.commit()

    def get_project(self, project_id):
        cursor = self.db.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,))
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None

class ProjectForm(QDialog):
    def __init__(self, db, user, project=None):
        super().__init__()
        self.db = db
        self.user = user
        self.manager = ProjectManager(db)
        self.project = None
        if isinstance(project, int):
            self.project = self.manager.get_project(project)
        elif project:
            self.project = project
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Modifier projet" if self.project else "Nouveau projet")
        self.setModal(True)
        self.resize(400, 200)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QLineEdit, QDateEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus { border: 2px solid #1c5ea3; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 13px; }
            QPushButton {
                background-color: #b8d5ed; color: #1c5ea3; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1c5ea3; color: #fff; }
            QPushButton:pressed { background-color: #14406e; }
        """)
        self.input_company  = QLineEdit()
        self.input_location = QLineEdit()
        self.input_room     = QLineEdit()
        self.input_date     = QDateEdit(calendarPopup=True)
        self.input_date.setDate(QDate.currentDate())
        if self.project:
            self.input_company.setText(self.project.get("company_name", ""))
            self.input_location.setText(self.project.get("location", ""))
            self.input_room.setText(self.project.get("room_type", ""))
            date = QDate.fromString(self.project.get("test_date", ""), "yyyy-MM-dd")
            if date.isValid():
                self.input_date.setDate(date)
        for widget in [self.input_company, self.input_location, self.input_room, self.input_date]:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_save   = QPushButton("Modifier" if self.project else "Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_project)
        self.btn_cancel.clicked.connect(self.reject)
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Entreprise :",    self.input_company)
        form_layout.addRow("Localisation :",  self.input_location)
        form_layout.addRow("Type de salle :", self.input_room)
        form_layout.addRow("Date du test :",  self.input_date)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 0)
        self.setLayout(main_layout)

    def save_project(self):
        company  = self.input_company.text().strip()
        location = self.input_location.text().strip()
        room     = self.input_room.text().strip()
        date     = self.input_date.date().toString("yyyy-MM-dd")
        if not company or not date:
            QMessageBox.warning(self, "Champs manquants", "Le nom de l'entreprise et la date sont obligatoires.", QMessageBox.Ok)
            return
        try:
            if self.project:
                self.manager.update_project(self.project["id"], company, location, room, date)
            else:
                self.manager.add_project(company, location, room, date, self.user['id'])
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de {'modifier' if self.project else 'créer'} le projet : {e}", QMessageBox.Ok)

class TestManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, iso_class):
        rows = self.db.conn.execute("SELECT parameter, max_value FROM thresholds WHERE iso_class = ?", (iso_class,)).fetchall()
        return [(r["parameter"], r["max_value"]) for r in rows]

    def save_test(self, project_id, user_id, point_name, measurements):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        cursor = self.db.conn.execute(
            "INSERT INTO tests (project_id, technician_id, measurement_date) VALUES (?, ?, ?)",
            (project_id, user_id, timestamp)
        )
        test_id = cursor.lastrowid
        compliant = True
        for param, value, max_val in measurements:
            self.db.conn.execute(
                "INSERT INTO measurements (test_id, point_name, parameter, value) VALUES (?, ?, ?, ?)",
                (test_id, point_name, param, value)
            )
            if value > max_val:
                compliant = False
        self.db.conn.commit()
        return compliant

class TestForm(QDialog):
    def __init__(self, db, project_id, user):
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.user = user
        self.manager = TestManager(db)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Saisie des tests")
        self.setModal(True)
        self.resize(450, 300)
        self.setStyleSheet("""
            QDialog { background-color: #e0e0e0; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 14px; }
            QLineEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 5px;
                padding: 4px; font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 6px;
                padding: 6px 18px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)
        row = self.db.conn.execute("SELECT room_type FROM projects WHERE id = ?", (self.project_id,)).fetchone()
        self.iso_class = row["room_type"]
        self.thresholds = self.manager.get_thresholds(self.iso_class)
        form_layout = QFormLayout()
        self.input_point = QLineEdit()
        form_layout.addRow("Point de mesure :", self.input_point)
        self.widgets = {}
        for param, max_val in self.thresholds:
            label = f"{param} (≤ {max_val})"
            widget = QLineEdit()
            widget.setPlaceholderText("Valeur numérique")
            form_layout.addRow(label, widget)
            self.widgets[param] = (widget, max_val)
        self.btn_save   = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_test)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def save_test(self):
        point_name = self.input_point.text().strip()
        if not point_name:
            QMessageBox.warning(self, "Champs manquant", "Merci de renseigner le nom du point de mesure.", QMessageBox.Ok)
            return
        measurements = []
        for param, (widget, max_val) in self.widgets.items():
            text = widget.text().strip()
            try:
                value = float(text)
            except ValueError:
                QMessageBox.warning(self, "Valeur invalide", f"La valeur pour « {param} » n’est pas un nombre valide.", QMessageBox.Ok)
                return
            measurements.append((param, value, max_val))
        compliant = self.manager.save_test(self.project_id, self.user["id"], point_name, measurements)
        status = "Conforme" if compliant else "Non conforme"
        QMessageBox.information(self, "Test enregistré", f"Le test a bien été enregistré.\nStatut de conformité : {status}", QMessageBox.Ok)
        self.accept()

class ThresholdManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self):
        rows = self.db.conn.execute("SELECT id, iso_class, parameter, max_value FROM thresholds").fetchall()
        columns = ["id", "iso_class", "parameter", "max_value"]
        return [dict_from_row(row, columns) for row in rows]

    def add_threshold(self, iso_class, parameter, max_value):
        self.db.conn.execute(
            "INSERT INTO thresholds (iso_class, parameter, max_value) VALUES (?, ?, ?)",
            (iso_class, parameter, max_value)
        )
        self.db.conn.commit()

    def update_threshold(self, threshold_id, iso_class, parameter, max_value):
        self.db.conn.execute(
            "UPDATE thresholds SET iso_class=?, parameter=?, max_value=? WHERE id=?",
            (iso_class, parameter, max_value, threshold_id)
        )
        self.db.conn.commit()

    def delete_threshold(self, threshold_id):
        self.db.conn.execute("DELETE FROM thresholds WHERE id = ?", (threshold_id,))
        self.db.conn.commit()

    def get_threshold(self, threshold_id):
        row = self.db.conn.execute(
            "SELECT id, iso_class, parameter, max_value FROM thresholds WHERE id = ?",
            (threshold_id,)
        ).fetchone()
        columns = ["id", "iso_class", "parameter", "max_value"]
        return dict_from_row(row, columns) if row else None

class ThresholdsTable(QTableWidget):
    HEADERS = ["ID", "Classe ISO", "Paramètre", "Valeur max"]
    COLUMNS = ["id", "iso_class", "parameter", "max_value"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setEditTriggers(self.NoEditTriggers)
        self.setSelectionBehavior(self.SelectRows)
        self.setAlternatingRowColors(True)
        self.hideColumn(0)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.verticalHeader().setVisible(False)

    def populate(self, rows):
        self.setRowCount(len(rows))
        for i, r in enumerate(rows):
            r = dict_from_row(r, self.COLUMNS)
            for col, key in enumerate(self.COLUMNS):
                self.setItem(i, col, QTableWidgetItem(str(r[key])))
        self.resizeColumnsToContents()

    def get_selected_threshold_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        return int(item.text()) if item else None

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
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le seuil : {e}", QMessageBox.Ok)

class DashboardToolbar(QToolBar):
    def __init__(self, user, parent=None):
        super().__init__("Tableau de bord", parent)
        self.setMovable(False)
        self.setStyleSheet("""
            QToolBar {
                background: transparent;
                border: none;
                spacing: 0px;
                padding: 0px;
            }
        """)
        self.actions_dict = {
            'projects': QAction("Projets", self),
            'thresholds': QAction("Seuils", self),
            'logout': QAction("Déconnexion", self)
        }
        self.spacer_left = QWidget()
        self.spacer_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.spacer_right = QWidget()
        self.spacer_right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(self.spacer_left)
        self.addAction(self.actions_dict['projects'])
        self.addAction(self.actions_dict['thresholds'])
        self.addSeparator()
        self.addAction(self.actions_dict['logout'])
        self.addWidget(self.spacer_right)

class DashboardWindow(QMainWindow):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user
        self.project_manager = ProjectManager(db)
        self._init_ui()
        self.refresh_projects()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Tableau de bord")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #e0e0e0; }
            QLabel#welcomeLabel {
                color: #1c5ea3; font-size: 22px; font-weight: bold;
                border-radius: 10px; padding: 12px; margin-bottom: 10px;
            }
            QTableWidget {
                border: none; font-size: 15px; selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; gridline-color: #333;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QToolButton {
                background: transparent; border: none; color: #1c5ea3;
                font-size: 15px; font-weight: bold; padding: 8px 18px; margin: 0 4px;
            }
            QToolButton:hover { color: #b8d5ed; }
            QPushButton {
                background-color: #1c5ea3; color: #fff; font-size: 10px; font-weight: bold;
                border-radius: 8px; padding: 8px 24px; margin: 8px 8px 0 0;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)
        toolbar_container = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)
        self.toolbar = DashboardToolbar(self.user)
        toolbar_layout.addWidget(self.toolbar)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.setMenuWidget(toolbar_container)

        self.toolbar.actions_dict['projects'].triggered.connect(self.show_dashboard)
        self.toolbar.actions_dict['thresholds'].triggered.connect(self.show_thresholds)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)
        self.central = QWidget()
        self.central_layout = QVBoxLayout(self.central)
        self.setCentralWidget(self.central)
        self.welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        self.welcome.setObjectName("welcomeLabel")
        self.welcome.setAlignment(Qt.AlignCenter)
        self.central_layout.addWidget(self.welcome)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.central_layout.addWidget(self.content_widget)
        self.project_table_widget = QWidget()
        self.project_table_layout = QVBoxLayout(self.project_table_widget)
        self.table_projects = ProjectTable()
        self.project_table_layout.addWidget(self.table_projects, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ajouter = QPushButton("Ajouter Projet")
        self.btn_supprimer = QPushButton("Supprimer Projet")
        self.btn_modifier = QPushButton("Modifier Projet")
        self.btn_saisir_test = QPushButton("Saisir Test")
        self.btn_valider_test = QPushButton("Valider Test")
        self.btn_generer_pdf = QPushButton("Générer un PDF")
        btn_layout.addWidget(self.btn_ajouter)
        btn_layout.addWidget(self.btn_supprimer)
        btn_layout.addWidget(self.btn_modifier)
        btn_layout.addWidget(self.btn_saisir_test)
        btn_layout.addWidget(self.btn_valider_test)
        btn_layout.addWidget(self.btn_generer_pdf)
        btn_layout.addStretch()
        self.project_table_layout.addLayout(btn_layout)
        self.btn_ajouter.clicked.connect(self.add_project)
        self.btn_supprimer.clicked.connect(self.delete_selected_project)
        self.btn_modifier.clicked.connect(self.edit_selected_project)
        self.btn_saisir_test.clicked.connect(self.tests)
        self.btn_valider_test.clicked.connect(self.validate_tests)
        self.btn_generer_pdf.clicked.connect(self.generate_pdf)

        self.thresholds_widget = ThresholdsWidget(self.db)
        self.content_layout.addWidget(self.project_table_widget)
        self.project_table_widget.show()
        self.thresholds_widget.hide()

    def show_dashboard(self):
        self.refresh_projects()
        self.project_table_widget.show()
        self.thresholds_widget.hide()
        if self.content_layout.indexOf(self.project_table_widget) == -1:
            self.content_layout.addWidget(self.project_table_widget)
        if self.content_layout.indexOf(self.thresholds_widget) != -1:
            self.content_layout.removeWidget(self.thresholds_widget)

    def show_thresholds(self):
        self.thresholds_widget.refresh_thresholds()
        self.project_table_widget.hide()
        if self.content_layout.indexOf(self.thresholds_widget) == -1:
            self.content_layout.addWidget(self.thresholds_widget)
        self.thresholds_widget.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        col_count = self.table_projects.columnCount()
        if col_count:
            width = self.table_projects.width() // col_count
            for i in range(col_count):
                self.table_projects.setColumnWidth(i, width)

    def refresh_projects(self):
        dict_rows = self.project_manager.get_projects()
        self.table_projects.populate(dict_rows)

    def add_project(self):
        dialog = ProjectForm(self.db, self.user)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()
    
    def delete_selected_project(self):
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à supprimer.", QMessageBox.Ok)
            return
        reply = QMessageBox.question(
            self, "Confirmation", "Voulez-vous vraiment supprimer ce projet ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.project_manager.delete_project(project_id)
            self.refresh_projects()

    def edit_selected_project(self):
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à modifier.", QMessageBox.Ok)
            return
        dialog = ProjectForm(self.db, self.user, project_id)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()

    def tests(self):
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        dialog = TestForm(self.db, project_id, self.user)
        dialog.exec_()

    def validate_tests(self):
        role = self.user['role']
        if role not in ('Administrateur', 'Technicien premium'):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        QMessageBox.information(self, "Validation", "Fonctionnalité de validation à venir.", QMessageBox.Ok)

    def generate_pdf(self):
        role = self.user['role']
        if role != 'Administrateur':
            QMessageBox.warning(self, "Accès refusé", "Seul un administrateur peut générer un PDF.", QMessageBox.Ok)
            return
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        from pdf.generator import PDFGenerator
        gen = PDFGenerator(self.db)
        save_path = os.path.join(os.getcwd(), f"static/pdf_template/rapport_projet_{project_id}.pdf")
        gen.generate_report(project_id, save_path)
        QMessageBox.information(self, "PDF généré", f"Rapport enregistré ici : {save_path}", QMessageBox.Ok)

    def logout(self):
        from gui.login import LoginWindow
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()