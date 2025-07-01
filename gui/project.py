import os
from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy,
    QPushButton, QFormLayout, QLineEdit, QDateEdit, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor
from models.projectmanager import ProjectManager
from models.utils import dict_from_row


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

class ProjectWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db = db
        self.user = user
        self.manager = ProjectManager(db)
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
                padding: 8px 24px; font-weight: bold; font-size: 10px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)
        self.table = ProjectTable()
        self.table.setFocusPolicy(Qt.NoFocus)
        self.btn_add = QPushButton("Ajouter Projet")
        self.btn_edit = QPushButton("Modifier Projet")
        self.btn_delete = QPushButton("Supprimer Projet")
        self.btn_test = QPushButton("Saisir Test")
        self.btn_validate = QPushButton("Valider Test")
        self.btn_pdf = QPushButton("Générer un PDF")
        self.btn_add.clicked.connect(self.add_project)
        self.btn_edit.clicked.connect(self.edit_project)
        self.btn_delete.clicked.connect(self.delete_project)
        self.btn_test.clicked.connect(self.saisir_test)
        self.btn_validate.clicked.connect(self.valider_test)
        self.btn_pdf.clicked.connect(self.generer_pdf)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_test)
        btn_layout.addWidget(self.btn_validate)
        btn_layout.addWidget(self.btn_pdf)
        btn_layout.addStretch()
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.refresh_projects()

    def refresh_projects(self):
        dict_rows = self.manager.get_projects()
        self.table.populate(dict_rows)
        for i in range(self.table.rowCount()):
            for j in range(self.table.columnCount()):
                item = self.table.item(i, j)
                if item:
                    item.setBackground(QColor(Qt.white))
                    item.setTextAlignment(Qt.AlignCenter)

    def add_project(self):
        dialog = ProjectForm(self.db, self.user)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()

    def edit_project(self):
        project_id = self.table.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à modifier.", QMessageBox.Ok)
            return
        dialog = ProjectForm(self.db, self.user, project_id)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()

    def delete_project(self):
        project_id = self.table.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à supprimer.", QMessageBox.Ok)
            return
        confirm = QMessageBox.question(
            self, "Confirmation", "Supprimer ce projet définitivement ?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                self.manager.delete_project(project_id)
                self.refresh_projects()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le projet : {e}", QMessageBox.Ok)

    def saisir_test(self):
        project_id = self.table.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Saisir un test")
        layout = QFormLayout(dialog)
        layout.addRow("Date :", QDateEdit(calendarPopup=True))
        layout.addRow("Description :", QLineEdit())
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        layout.addRow(button_box)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        if dialog.exec_() == QDialog.Accepted:
            self.manager.add_test(project_id, dialog.input_date.date(), dialog.input_description.text())
        dialog.exec_()

    def valider_test(self):
        role = self.user['role']
        if role not in ('Administrateur', 'Technicien premium'):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return
        project_id = self.table.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        QMessageBox.information(self, "Validation", "Fonctionnalité de validation à venir.", QMessageBox.Ok)

    def generer_pdf(self):
        role = self.user['role']
        if role != 'Administrateur':
            QMessageBox.warning(self, "Accès refusé", "Seul un administrateur peut générer un PDF.", QMessageBox.Ok)
            return
        project_id = self.table.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        from pdf.generator import PDFGenerator
        gen = PDFGenerator(self.db)
        save_path = os.path.join(os.getcwd(), f"static/pdf_template/rapport_projet_{project_id}.pdf")
        gen.generate_report(project_id, save_path)
        QMessageBox.information(self, "PDF généré", f"Rapport enregistré ici : {save_path}", QMessageBox.Ok)
