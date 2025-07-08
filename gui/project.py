# gui/project.py

"""
Fenêtre de gestion des projets pour l’application VDC Engineering MVP.
Gère l'affichage, l'ajout, la modification et la suppression des projets.
Gère la génération et l'affichage des rapports PDF pour chaque projet.
Gère les interactions utilisateur via une interface graphique PyQt5.
Gère la persistance des projets dans une base de données SQLite.
Gère les seuils ISO et les utilisateurs assignés aux projets.
Gère les interactions avec le gestionnaire de projets.
Gère les interactions avec le gestionnaire de seuils ISO.
Gère les interactions avec le gestionnaire d'utilisateurs.
Gère les interactions avec le gestionnaire de tests.
Gère les interactions avec le gestionnaire de rapports PDF.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QMessageBox, QDialog, QHeaderView, QSizePolicy,
    QPushButton, QFormLayout, QLineEdit, QDateEdit, QDialogButtonBox,
    QComboBox
)
from PyQt5.QtCore import Qt, QDate, QUrl
from PyQt5.QtGui import QColor, QIcon, QDesktopServices, QIntValidator
from models.projectmanager import ProjectManager
from models.utils import dict_from_row        

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

class ProjectTable(NoFocusTableWidget):
    HEADERS = [
        "Entreprise", "Localisation", "Salle", "Surface (m²)", "Date de test",
        "Classe ISO", "Statut", "Responsable", "Actions"
    ]
    COLUMNS = [
        "company_name", "location", "room_type", "cleanroom_area", "test_date",
        "iso_class", "validation_status", "assigned_user"
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
                font-size: 13px;
                border-radius: 8px;
                color: #1c5ea3;
                font-weight: bold;
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
            row = dict_from_row(row, self.COLUMNS + ['id', 'validation_status'])
            for col, key in enumerate(self.COLUMNS):
                value = row.get(key, "")
                if key == "cleanroom_area":
                    # Affiche comme entier naturel, pas de virgule
                    try:
                        value = str(int(float(value)))
                    except Exception:
                        value = ""
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(Qt.white))
                if col == 0:
                    item.setData(Qt.UserRole, row.get('id'))
                self.setItem(i, col, item)
            # Actions column (last column)
            action_widget = QWidget()
            h_layout = QHBoxLayout(action_widget)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.setSpacing(5)
            h_layout.addStretch()  # Ajoute un stretch avant les boutons pour centrer

            icon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icons"))

            # Vérifie si le projet est validé
            is_valid = row.get("validation_status", "").lower() == "validé"

            btn_generate_pdf = QPushButton()
            btn_generate_pdf.setIcon(QIcon(
                os.path.join(icon_dir, "pdf_generate.png" if is_valid else "pdf_generate_disabled.png")
            ))
            btn_generate_pdf.setToolTip("Générer PDF" if is_valid else "Impossible de générer PDF tant que le projet n'est pas validé")
            btn_generate_pdf.setFixedSize(28, 28)
            btn_generate_pdf.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: transparent;
                }
                QPushButton:focus, QPushButton:hover {
                    background: #e6f0fa;
                }
            """)
            btn_generate_pdf.setEnabled(is_valid)
            btn_generate_pdf.clicked.connect(lambda _, pid=row['id']: self.generate_pdf(pid))

            btn_show_pdf = QPushButton()
            btn_show_pdf.setIcon(QIcon(
                os.path.join(icon_dir, "pdf_show.png" if is_valid else "pdf_show_disabled.png")
            ))
            btn_show_pdf.setToolTip("Afficher PDF" if is_valid else "Impossible d'afficher PDF tant que le projet n'est pas validé")
            btn_show_pdf.setFixedSize(28, 28)
            btn_show_pdf.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: transparent;
                }
                QPushButton:focus, QPushButton:hover {
                    background: #e6f0fa;
                }
            """)
            btn_show_pdf.setEnabled(is_valid)
            btn_show_pdf.clicked.connect(lambda _, pid=row['id']: self.show_pdf(pid))

            h_layout.addWidget(btn_generate_pdf)
            h_layout.addWidget(btn_show_pdf)
            h_layout.addStretch()  # Ajoute un stretch après les boutons pour centrer

            action_widget.setLayout(h_layout)
            # Centre le widget dans la cellule
            self.setCellWidget(i, len(self.COLUMNS), action_widget)
            self.setRowHeight(i, 36)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def generate_pdf(self, project_id):
        # Génère le PDF pour le projet sélectionné
        try:
            from pdf.generator import PDFGenerator
            gen = PDFGenerator(self.parent().db)
            import os
            save_path = os.path.join(os.getcwd(), f"static/pdf_template/rapport_projet_{project_id}.pdf")
            gen.generate_report(project_id, save_path)
            QMessageBox.information(self, "PDF généré", f"Rapport enregistré ici : {save_path}", QMessageBox.Ok)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de générer le PDF : {e}", QMessageBox.Ok)

    def show_pdf(self, project_id):
        pdf_path = os.path.join(os.getcwd(), f"static/pdf_template/rapport_projet_{project_id}.pdf")
        if not os.path.exists(pdf_path):
            QMessageBox.warning(self, "PDF manquant", f"Le PDF {pdf_path} n'existe pas.", QMessageBox.Ok)
            return
        url = QUrl.fromLocalFile(pdf_path)
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir le PDF : {pdf_path}", QMessageBox.Ok)

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

        self.input_company  = QLineEdit()
        self.input_location = QLineEdit()
        self.input_room     = QLineEdit()
        self.input_surface  = QLineEdit()
        self.input_surface.setValidator(QIntValidator(0, 1000000))
        self.input_date     = QDateEdit(calendarPopup=True)
        self.input_date.setDate(QDate.currentDate())
        self.input_iso      = QComboBox()
        self.input_iso.addItems(self.ISO_CLASSES)
        self.input_status   = QComboBox()
        self.input_status.addItems(self.VALIDATION_STATUSES)
        
        # Récupère tous les utilisateurs disponibles
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE validate_user='Validé'")
        self.user_list = cursor.fetchall()

        self.input_assigned_to = QComboBox()
        for user in self.user_list:
            self.input_assigned_to.addItem(user["full_name"], user["id"])
        
        if self.project and self.project.get("assigned_to"):
            for idx in range(self.input_assigned_to.count()):
                if self.input_assigned_to.itemData(idx) == self.project["assigned_to"]:
                    self.input_assigned_to.setCurrentIndex(idx)
                    break

        # Ajout d'un bouton pour afficher les seuils ISO sélectionnés
        self.btn_show_thresholds = QPushButton("Voir seuils ISO")
        self.btn_show_thresholds.clicked.connect(self.show_iso_thresholds_dialog)

        if self.project:
            self.input_company.setText(self.project.get("company_name", ""))
            self.input_location.setText(self.project.get("location", ""))
            self.input_room.setText(self.project.get("room_type", ""))
            self.input_surface.setText(str(self.project.get("cleanroom_area", "")))
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
            self.input_company, self.input_location, self.input_room, self.input_surface,
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
        form_layout.addRow("Salle :", self.input_room)
        form_layout.addRow("Surface (m²) :", self.input_surface)
        form_layout.addRow("Date du test :",  self.input_date)
        form_layout.addRow("Classe ISO :",    self.input_iso)
        form_layout.addRow("Statut :", self.input_status)
        form_layout.addRow("Responsable du projet :", self.input_assigned_to)
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
        surface  = self.input_surface.text().strip()
        date     = self.input_date.date().toString("yyyy-MM-dd")
        iso_class = self.input_iso.currentText()
        validation_status = self.input_status.currentText()
        assigned_to = self.input_assigned_to.currentData()

        if not company or not date or not iso_class or not validation_status or not surface:
            QMessageBox.warning(self, "Champs manquants", "Le nom de l'entreprise, la date, la classe ISO, la surface et le statut sont obligatoires.", QMessageBox.Ok)
            return
        try:
            surface_int = int(surface)
            if self.project:
                self.manager.update_project(
                    self.project["id"], company, location, room, surface_int, date, iso_class, validation_status, assigned_to
                )
            else:
                self.manager.add_project(company, location, room, surface_int, date, iso_class, validation_status, assigned_to)
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
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
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

        self.table = ProjectTable()
        self.table.setFocusPolicy(Qt.NoFocus)

        self.btn_add = QPushButton("Ajouter Projet")
        self.btn_add.setToolTip("Ajouter Projet")
        self.btn_add.setFixedHeight(36)

        self.btn_edit = QPushButton("Modifier Projet")
        self.btn_edit.setToolTip("Modifier Projet")
        self.btn_edit.setFixedHeight(36)

        self.btn_delete = QPushButton("Supprimer Projet")
        self.btn_delete.setToolTip("Supprimer Projet")
        self.btn_delete.setFixedHeight(36)

        self.btn_add.clicked.connect(self.add_project)
        self.btn_edit.clicked.connect(self.edit_project)
        self.btn_delete.clicked.connect(self.delete_project)

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
