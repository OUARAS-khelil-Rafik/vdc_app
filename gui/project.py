# gui/project.py
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
    HEADERS = [
        "ID", "Entreprise", "Localisation", "Type de salle", "Date de test",
        "Classe ISO", "Statut validation"
    ]
    COLUMNS = [
        "id", "company_name", "location", "room_type", "test_date",
        "iso_class", "validation_status"
    ]

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
                item = QTableWidgetItem(str(row.get(key, "")))
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

# --- Ajout d'une méthode utilitaire pour récupérer les seuils ISO ---
def get_iso_thresholds(iso_class):
    """
    Récupère les seuils pour une classe ISO donnée.
    Importé dynamiquement depuis gui/thresholds.py pour éviter les imports circulaires.
    """
    try:
        from gui.thresholds import ISO_THRESHOLDS
        return ISO_THRESHOLDS.get(iso_class, {})
    except ImportError:
        return {}

class ProjectForm(QDialog):
    ISO_CLASSES = [f"ISO {i}" for i in range(1, 10)]
    VALIDATION_STATUSES = ["En attente", "Validé"]

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
        self.resize(400, 300)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QLineEdit, QDateEdit, QComboBox {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus { border: 2px solid #1c5ea3; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 13px; }
            QPushButton {
                background-color: #b8d5ed; color: #1c5ea3; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1c5ea3; color: #fff; }
            QPushButton:pressed { background-color: #14406e; }
        """)
        from PyQt5.QtWidgets import QComboBox

        self.input_company  = QLineEdit()
        self.input_location = QLineEdit()
        self.input_room     = QLineEdit()
        self.input_date     = QDateEdit(calendarPopup=True)
        self.input_date.setDate(QDate.currentDate())
        self.input_iso      = QComboBox()
        self.input_iso.addItems(self.ISO_CLASSES)
        self.input_status   = QComboBox()
        self.input_status.addItems(self.VALIDATION_STATUSES)

        # Ajout d'un bouton pour afficher les seuils ISO sélectionnés
        self.btn_show_thresholds = QPushButton("Voir seuils ISO")
        self.btn_show_thresholds.clicked.connect(self.show_iso_thresholds_dialog)

        if self.project:
            self.input_company.setText(self.project.get("company_name", ""))
            self.input_location.setText(self.project.get("location", ""))
            self.input_room.setText(self.project.get("room_type", ""))
            date = QDate.fromString(self.project.get("test_date", ""), "yyyy-MM-dd")
            if date.isValid():
                self.input_date.setDate(date)
            iso_class = self.project.get("iso_class", "ISO 5")
            idx_iso = self.input_iso.findText(iso_class)
            if idx_iso >= 0:
                self.input_iso.setCurrentIndex(idx_iso)
            status = self.project.get("validation_status", "En attente")
            idx_status = self.input_status.findText(status)
            if idx_status >= 0:
                self.input_status.setCurrentIndex(idx_status)
        for widget in [
            self.input_company, self.input_location, self.input_room,
            self.input_date, self.input_iso, self.input_status
        ]:
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
        form_layout.addRow("Classe ISO :",    self.input_iso)
        form_layout.addRow("Statut validation :", self.input_status)
        form_layout.addRow("", self.btn_show_thresholds)
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

    def show_iso_thresholds_dialog(self):
        iso_class = self.input_iso.currentText()
        thresholds = get_iso_thresholds(iso_class)
        if not thresholds:
            QMessageBox.information(self, "Seuils ISO", f"Aucun seuil trouvé pour {iso_class}.", QMessageBox.Ok)
            return
        msg = f"Seuils pour {iso_class} :\n\n"
        for test, value in thresholds.items():
            msg += f"- {test} : {value}\n"
        QMessageBox.information(self, f"Seuils {iso_class}", msg, QMessageBox.Ok)

    def save_project(self):
        company  = self.input_company.text().strip()
        location = self.input_location.text().strip()
        room     = self.input_room.text().strip()
        date     = self.input_date.date().toString("yyyy-MM-dd")
        iso_class = self.input_iso.currentText()
        validation_status = self.input_status.currentText()

        if not company or not date or not iso_class or not validation_status:
            QMessageBox.warning(self, "Champs manquants", "Le nom de l'entreprise, la date, la classe ISO et le statut sont obligatoires.", QMessageBox.Ok)
            return
        try:
            if self.project:
                self.manager.update_project(
                    self.project["id"], company, location, room, date, iso_class, validation_status
                )
            else:
                self.manager.add_project(company, location, room, date, iso_class, validation_status)
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
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; border: 2px solid #1c5ea3; font-size: 15px;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px;
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
        self.btn_pdf = QPushButton("Générer un PDF")
        self.btn_add.clicked.connect(self.add_project)
        self.btn_edit.clicked.connect(self.edit_project)
        self.btn_delete.clicked.connect(self.delete_project)
        self.btn_pdf.clicked.connect(self.generer_pdf)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
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
        dialog = ProjectForm(self.db, self.user, project=project_id)
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
