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
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from PyQt5.QtWidgets import QApplication
class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

class ProjectTable(NoFocusTableWidget):
    HEADERS = [
        "ID Projet", "Nom Entreprise", "Localisation", "Tag", "Responsables",
        "Date de Test", "Type de travail", "Statut", "Actions"
    ]
    COLUMNS = [
        "id", "company_name", "location", "room_tag", "responsables",
        "test_date", "work_type", "validation_status"
    ]

    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.user = user
        self.show_actions = True
        if self.user and self.user.get("role") in ("Technicien", "Technicien responsable"):
            self.show_actions = False

        headers = self.HEADERS if self.show_actions else self.HEADERS[:-1]
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.SingleSelection)
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
                color: #000;
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
        filtered_rows = []
        if self.user:
            role = self.user.get("role")
            user_id = self.user.get("id")
            # Superviseur = Admin
            if role in ("Administrateur", "Admin", "Superviseur"):
                filtered_rows = rows
            else:
                for row in rows:
                    responsables_ids = []
                    if "responsables_ids" in row:
                        responsables_ids = row["responsables_ids"]
                    else:
                        cursor = self.parent().db.conn.cursor()
                        cursor.execute("SELECT user_id FROM project_users WHERE project_id=?", (row["id"],))
                        responsables_ids = [r["user_id"] for r in cursor.fetchall()]
                    if user_id in responsables_ids:
                        filtered_rows.append(row)
        else:
            filtered_rows = rows

        self.setRowCount(len(filtered_rows))
        icon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icons"))
        for i, row in enumerate(filtered_rows):
            row = dict(row)
            value_responsables = row.get("responsables", "")
            contact_info = row.get("contact_info", "")
            contact_email, contact_phone = "", ""
            if contact_info:
                parts = contact_info.split("/")
                contact_email = parts[0].strip() if len(parts) > 0 else ""
                contact_phone = parts[1].strip() if len(parts) > 1 else ""
            for col, key in enumerate(self.COLUMNS):
                if key == "responsables":
                    value = value_responsables
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QColor(Qt.white))
                    if col == 0:
                        item.setData(Qt.UserRole, row.get('id'))
                    self.setItem(i, col, item)
                else:
                    value = row.get(key, "")
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QColor(Qt.white))
                    if col == 0:
                        item.setData(Qt.UserRole, row.get('id'))
                    self.setItem(i, col, item)
            # Actions column (last column)
            if self.show_actions:
                action_widget = QWidget()
                h_layout = QHBoxLayout(action_widget)
                h_layout.setContentsMargins(0, 0, 0, 0)
                h_layout.setSpacing(5)
                h_layout.addStretch()

                # Contact buttons
                btn_email = QPushButton()
                btn_email.setIcon(QIcon(os.path.join(icon_dir, "email.png")))
                btn_email.setToolTip("Envoyer Email")
                btn_email.setFixedSize(28, 28)
                btn_email.setStyleSheet("""
                    QPushButton {
                        border: none;
                        background: transparent;
                    }
                    QPushButton:focus, QPushButton:hover {
                        background: #e6f0fa;
                    }
                """)
                btn_email.clicked.connect(lambda _, email=contact_email: self.show_email_dialog(email))

                btn_phone = QPushButton()
                btn_phone.setIcon(QIcon(os.path.join(icon_dir, "appel.png")))
                btn_phone.setToolTip("Afficher Numéro Téléphone")
                btn_phone.setFixedSize(28, 28)
                btn_phone.setStyleSheet("""
                    QPushButton {
                        border: none;
                        background: transparent;
                    }
                    QPushButton:focus, QPushButton:hover {
                        background: #e6f0fa;
                    }
                """)
                btn_phone.clicked.connect(lambda _, phone=contact_phone: self.show_phone_dialog(phone))

                h_layout.addWidget(btn_email)
                h_layout.addWidget(btn_phone)

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
                h_layout.addStretch()
                action_widget.setLayout(h_layout)
                self.setCellWidget(i, len(self.COLUMNS), action_widget)
                self.setRowHeight(i, 36)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def show_phone_dialog(self, phone):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QApplication
        from PyQt5.QtGui import QClipboard
        dialog = QDialog(self)
        dialog.setWindowTitle("Téléphone")
        layout = QVBoxLayout(dialog)
        label = QLabel(f"Numéro : {phone if phone else 'Aucun numéro disponible.'}")
        layout.addWidget(label)
        if phone:
            btn_copy = QPushButton("Copier le numéro")
            btn_copy.clicked.connect(lambda: self.copy_to_clipboard(phone))
            layout.addWidget(btn_copy)
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.setLayout(layout)
        dialog.exec_()

    def show_email_dialog(self, email):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QApplication
        from PyQt5.QtGui import QClipboard
        dialog = QDialog(self)
        dialog.setWindowTitle("Email")
        layout = QVBoxLayout(dialog)
        label = QLabel(f"Adresse email : {email if email else 'Aucune adresse email disponible.'}")
        layout.addWidget(label)
        if email:
            btn_copy = QPushButton("Copier l'email")
            btn_copy.clicked.connect(lambda: self.copy_to_clipboard(email))
            layout.addWidget(btn_copy)
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.setLayout(layout)
        dialog.exec_()

    def copy_to_clipboard(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "Copié", f"Copié dans le presse-papier : {text}", QMessageBox.Ok)

    def generate_pdf(self, project_id):
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

class ProjectForm(QDialog):
    WORK_TYPES = ["HVAC", "Thermal Mapping", "Instrumentation"]
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
        self.resize(500, 400)
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

        self.input_company = QLineEdit()
        self.input_location = QLineEdit()
        self.input_room_tag = QLineEdit()
        self.input_test_date = QDateEdit(calendarPopup=True)
        self.input_test_date.setDate(QDate.currentDate())
        self.input_contact_email = QLineEdit()
        self.input_contact_email.setPlaceholderText("Email")
        self.input_contact_phone = QLineEdit()
        self.input_contact_phone.setPlaceholderText("Numéro de téléphone")
        self.input_work_type = QComboBox()
        self.input_work_type.addItems(self.WORK_TYPES)
        self.input_status = QComboBox()
        self.input_status.addItems(self.VALIDATION_STATUSES)

        # Récupère tous les utilisateurs validés
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT id, full_name, role FROM users WHERE validate_user='Validé'")
        self.user_list = cursor.fetchall()

        # Ajout d'une QListWidget pour multi-sélection des responsables
        self.input_responsables = QListWidget()
        self.input_responsables.setSelectionMode(QListWidget.MultiSelection)
        for user in self.user_list:
            item = QListWidgetItem(f"{user['full_name']} ({user['role']})")
            item.setData(Qt.UserRole, user["id"])
            self.input_responsables.addItem(item)
        self.input_responsables.setToolTip("Sélectionnez un ou plusieurs responsables")

        # Pré-remplissage si modification
        if self.project:
            self.input_company.setText(self.project.get("company_name", ""))
            self.input_location.setText(self.project.get("location", ""))
            self.input_room_tag.setText(self.project.get("room_tag", ""))
            date = QDate.fromString(self.project.get("test_date", ""), "yyyy-MM-dd")
            if date.isValid():
                self.input_test_date.setDate(date)
            contact_info = self.project.get("contact_info", "")
            if contact_info:
                parts = contact_info.split("/")
                self.input_contact_email.setText(parts[0].strip() if len(parts) > 0 else "")
                self.input_contact_phone.setText(parts[1].strip() if len(parts) > 1 else "")
            work_type = self.project.get("work_type", self.WORK_TYPES[0])
            idx_work = self.input_work_type.findText(work_type)
            if idx_work >= 0:
                self.input_work_type.setCurrentIndex(idx_work)
            status = self.project.get("validation_status", self.VALIDATION_STATUSES[0])
            idx_status = self.input_status.findText(status)
            if idx_status >= 0:
                self.input_status.setCurrentIndex(idx_status)
            # Sélection des responsables
            cursor.execute("SELECT user_id FROM project_users WHERE project_id=?", (self.project["id"],))
            responsables_ids = set(row["user_id"] for row in cursor.fetchall())
            for i in range(self.input_responsables.count()):
                item = self.input_responsables.item(i)
                if item.data(Qt.UserRole) in responsables_ids:
                    item.setSelected(True)

        self.btn_save = QPushButton("Modifier" if self.project else "Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_project)
        self.btn_cancel.clicked.connect(self.reject)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Entreprise :", self.input_company)
        form_layout.addRow("Localisation :", self.input_location)
        form_layout.addRow("Tag :", self.input_room_tag)
        form_layout.addRow("Responsables :", self.input_responsables)
        form_layout.addRow("Date de Test :", self.input_test_date)
        form_layout.addRow("Contact Email :", self.input_contact_email)
        form_layout.addRow("Contact Téléphone :", self.input_contact_phone)
        form_layout.addRow("Type de travail :", self.input_work_type)
        # Affiche le champ statut seulement en modification
        if self.project:
            form_layout.addRow("Statut :", self.input_status)

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
        company = self.input_company.text().strip()
        location = self.input_location.text().strip()
        room_tag = self.input_room_tag.text().strip()
        test_date = self.input_test_date.date().toString("yyyy-MM-dd")
        contact_email = self.input_contact_email.text().strip()
        contact_phone = self.input_contact_phone.text().strip()
        contact_info = f"{contact_email} / {contact_phone}"
        work_type = self.input_work_type.currentText()
        # Pour l'ajout, le statut est toujours "En attente"
        if self.project:
            validation_status = self.input_status.currentText()
        else:
            validation_status = "En attente"

        # Récupérer les IDs des responsables sélectionnés
        responsables_ids = []
        for item in self.input_responsables.selectedItems():
            responsables_ids.append(item.data(Qt.UserRole))

        if not company or not test_date or not contact_email or not contact_phone or not work_type or not validation_status or not responsables_ids:
            QMessageBox.warning(self, "Champs manquants", "Tous les champs sont obligatoires, y compris au moins un responsable.", QMessageBox.Ok)
            return
        try:
            if self.project:
                self.manager.update_project(
                    self.project["id"], company, location, room_tag, test_date,
                    contact_info, work_type, validation_status, responsables_ids
                )
            else:
                self.manager.add_project(
                    company, location, room_tag, test_date,
                    contact_info, work_type, validation_status, responsables_ids
                )
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
            QLineEdit, QDateEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus { border: 2px solid #1c5ea3; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 13px; }
        """)

        # Filtres
        self.filter_company_label = QLabel("Filtrer par entreprise :")
        self.filter_company_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #1c5ea3; background: transparent;")
        self.filter_company_text = QLineEdit()
        self.filter_company_text.setPlaceholderText("Nom de l'entreprise")
        self.filter_company_text.setToolTip("Filtrer par entreprise")
        self.filter_company_text.setFixedHeight(28)
        self.filter_company_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.filter_start_date_label = QLabel("Date de début :")
        self.filter_start_date_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #1c5ea3; background: transparent;")
        self.filter_start_date = QDateEdit(calendarPopup=True)
        self.filter_start_date.setDisplayFormat("yyyy-MM-dd")
        self.filter_start_date.setDate(QDate(2024, 1, 1))
        self.filter_start_date.setToolTip("Date de début")
        self.filter_start_date.setFixedHeight(28)
        self.filter_start_date.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.filter_end_date_label = QLabel("Date de fin :")
        self.filter_end_date_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #1c5ea3; background: transparent;")
        self.filter_end_date = QDateEdit(calendarPopup=True)
        self.filter_end_date.setDisplayFormat("yyyy-MM-dd")
        self.filter_end_date.setDate(QDate.currentDate())
        self.filter_end_date.setToolTip("Date de fin")
        self.filter_end_date.setFixedHeight(28)
        self.filter_end_date.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.filter_company_text.textChanged.connect(self.refresh_projects)
        self.filter_start_date.dateChanged.connect(self.refresh_projects)
        self.filter_end_date.dateChanged.connect(self.refresh_projects)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        filter_layout.addWidget(self.filter_company_label)
        filter_layout.addWidget(self.filter_company_text)
        filter_layout.addWidget(self.filter_start_date_label)
        filter_layout.addWidget(self.filter_start_date)
        filter_layout.addWidget(self.filter_end_date_label)
        filter_layout.addWidget(self.filter_end_date)
        filter_layout.addStretch()

        # Table setup
        self.table = ProjectTable(user=self.user)
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
        # Hide buttons for Technicien and Technicien responsable
        if self.user.get("role") not in ("Technicien", "Technicien responsable"):
            btn_layout.addWidget(self.btn_add)
            btn_layout.addWidget(self.btn_edit)
            btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.refresh_projects()

    def refresh_projects(self):
        start_date = self.filter_start_date.date().toString("yyyy-MM-dd")
        end_date = self.filter_end_date.date().toString("yyyy-MM-dd")
        company_name_filter = self.filter_company_text.text().strip().lower()

        all_projects = self.manager.get_projects(
            start_date=start_date,
            end_date=end_date
        )

        if company_name_filter:
            all_projects = [
                p for p in all_projects
                if p.get("company_name", "").lower().startswith(company_name_filter)
            ]

        filtered_projects = []
        if self.user:
            role = self.user.get("role")
            user_id = self.user.get("id")
            if role in ("Administrateur", "Admin", "Superviseur"):
                filtered_projects = all_projects
            else:
                for row in all_projects:
                    cursor = self.db.conn.cursor()
                    cursor.execute("SELECT 1 FROM project_users WHERE project_id=? AND user_id=?", (row["id"], user_id))
                    if cursor.fetchone():
                        filtered_projects.append(row)
        else:
            filtered_projects = all_projects

        # Add responsables and contact info for actions
        for project in filtered_projects:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT u.full_name FROM users u
                JOIN project_users pu ON pu.user_id = u.id
                WHERE pu.project_id=?
            """, (project["id"],))
            responsables = [row["full_name"] for row in cursor.fetchall()]
            project["responsables"] = ", ".join(responsables)
            # Contact info for actions
            contact_info = project.get("contact_info", "")
            contact_email, contact_phone = "", ""
            if contact_info:
                parts = contact_info.split("/")
                contact_email = parts[0].strip() if len(parts) > 0 else ""
                contact_phone = parts[1].strip() if len(parts) > 1 else ""
            project["contact_email"] = contact_email
            project["contact_phone"] = contact_phone

        self.table.populate(filtered_projects)
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
