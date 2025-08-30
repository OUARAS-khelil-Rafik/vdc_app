# gui/users.py

"""
Module GUI de gestion des utilisateurs pour VDC Engineering (MVP).

Fonctionnalités :
- Affichage, ajout, modification et suppression d'utilisateurs.
- Rôles autorisés : Administrateur, Technicien, Technicien responsable, Superviseur.
- Validation des comptes : « Validé » / « Non validé ».
- Contraintes : unicité du nom d'utilisateur et de l'email, rôles/validation conformes au schéma SQLite.
- Protection : les comptes Administrateur ne peuvent pas être modifiés ni supprimés via l'interface.
- Vérification simple du format d'email.

Composants :
- NoFocusTableWidget : QTableWidget sans focus.
- UserForm : boîte de dialogue de création/édition d’utilisateur.
- UsersTable : tableau des utilisateurs (colonnes : id, username, full_name, role, email, phone_number, validate_user).
- UsersWidget : conteneur principal avec actions (ajouter, modifier, supprimer).

Persistance :
- S’appuie sur models.usermanager.UserManager pour accéder à SQLite.

Remarques :
- Le mot de passe est requis à la création ; sa mise à jour n’est pas gérée ici.
- Interface basée sur PyQt5.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView, QSizePolicy, QTableWidget,
    QPushButton, QHBoxLayout, QDialog, QFormLayout, QLineEdit, QComboBox, QMessageBox, QLabel
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from models.usermanager import UserManager
import sqlite3

# Define theme colors
THEME_PRIMARY = "#1c5ea3"
THEME_ACCENT = "#b8d5ed"

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)
class UserForm(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.user = user  # (id, username, full_name, role, email, phone_number, validate_user) or None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Modifier utilisateur" if self.user else "Nouvel utilisateur")
        self.setModal(True)
        self.resize(400, 260)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QLineEdit, QDateEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus { border: 2px solid #1c5ea3; }
            QLabel { background: #f0f0f0; color: #1c5ea3; font-weight: bold; font-size: 13px; }
            QPushButton {
                background-color: #b8d5ed; color: #1c5ea3; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1c5ea3; color: #fff; }
            QPushButton:pressed { background-color: #14406e; }
            QComboBox {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QComboBox:focus { border: 2px solid #1c5ea3; }
        """)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.fullname_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.role_combo = QComboBox()
        # Nouvelles valeurs de rôle alignées sur la contrainte CHECK du schéma
        allowed_roles = ["Technicien responsable", "Technicien", "Superviseur", "Administrateur"]
        self.role_combo.addItems(allowed_roles)

        if self.user:
            # user = (id, username, full_name, role, email, phone_number, validate_user)
            self.username_edit.setText(self.user[1] or "")
            self.fullname_edit.setText(self.user[2] or "")
            if self.user[3] not in allowed_roles and self.user[3]:
                self.role_combo.addItem(self.user[3])
            self.role_combo.setCurrentText(self.user[3] or "")
            self.email_edit.setText(self.user[4] or "")
            self.phone_edit.setText(self.user[5] or "")

        for widget in [self.username_edit, self.fullname_edit, self.email_edit, self.phone_edit, self.role_combo]:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.validation_combo = QComboBox()
        self.validation_combo.addItems(["Non validé", "Validé"])
        if self.user:
            v = self.user[6]
            if v in (1, "1", "Validé", True):
                self.validation_combo.setCurrentText("Validé")
            else:
                self.validation_combo.setCurrentText("Non validé")
        else:
            self.validation_combo.setCurrentText("Non validé")

        # Désactiver la modification si Administrateur
        if self.user and (self.user[3] == "Administrateur" or self.user[3] == "admin"):
            self.validation_combo.setEnabled(False)
            self.username_edit.setEnabled(False)
            self.fullname_edit.setEnabled(False)
            self.role_combo.setEnabled(False)
            self.password_edit.setEnabled(False)
            self.email_edit.setEnabled(False)
            self.phone_edit.setEnabled(False)
        else:
            self.validation_combo.setEnabled(True)

        self.btn_save = QPushButton("Modifier" if self.user else "Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Nom d'utilisateur :", self.username_edit)
        form_layout.addRow("Mot de passe :", self.password_edit)
        form_layout.addRow("Nom complet :", self.fullname_edit)
        form_layout.addRow("Email :", self.email_edit)
        form_layout.addRow("Téléphone :", self.phone_edit)
        form_layout.addRow("Rôle :", self.role_combo)
        form_layout.addRow("Validation :", self.validation_combo)

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

        # Désactiver le bouton "Modifier" si Administrateur
        if self.user and (self.user[3] == "Administrateur" or self.user[3] == "admin"):
            self.btn_save.setEnabled(False)

    def get_data(self):
        return (
            self.username_edit.text().strip(),
            self.password_edit.text(),
            self.fullname_edit.text().strip(),
            self.role_combo.currentText(),
            self.email_edit.text().strip(),
            self.phone_edit.text().strip(),
            self.validation_combo.currentText()
        )

class UsersTable(NoFocusTableWidget):
    HEADERS = ["ID", "Nom d'utilisateur", "Nom complet", "Rôle", "Email", "Téléphone", "Validation"]
    # Order must match fetch_users tuple: (id, username, full_name, role, email, phone_number, validate_user)
    COLUMNS = ["id", "username", "full_name", "role", "email", "phone_number", "validate_user"]

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
                gridline-color: #1c5ea3; 
                selection-color: #1c5ea3; 
                border: 2px solid #1c5ea3; 
                font-size: 13px;
                font-weight: bold;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
        """)

    def populate(self, rows):
        self.setRowCount(len(rows))
        for i, user in enumerate(rows):
            for col, _ in enumerate(self.COLUMNS):
                val = user[col] if col < len(user) else ""
                # Normalize validation display if stored as 0/1
                if col == 6:
                    if val in (1, "1", True):
                        val = "Validé"
                    elif val in (0, "0", False):
                        val = "Non validé"
                item = QTableWidgetItem("" if val is None else str(val))
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
        self.table = UsersTable()
        layout.addWidget(self.table)

        btn_style = """
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.add_btn = QPushButton("Ajouter Utilisateur")
        self.add_btn.setStyleSheet(btn_style)
        self.add_btn.clicked.connect(self.add_user)
        btn_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Modifier Utilisateur")
        self.edit_btn.setStyleSheet(btn_style)
        self.edit_btn.clicked.connect(self.edit_user)
        btn_layout.addWidget(self.edit_btn)

        self.del_btn = QPushButton("Supprimer Utilisateur")
        self.del_btn.setStyleSheet(btn_style)
        self.del_btn.clicked.connect(self.delete_user)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.refresh_users()

    def refresh_users(self):
        users = UserManager.fetch_users()
        self.table.populate(users)

    def _is_valid_email(self, email: str) -> bool:
        return bool(email) and ("@" in email and "." in email.split("@")[-1])

    def add_user(self):
        form = UserForm(self)
        if form.exec_() == QDialog.Accepted:
            username, password, full_name, role, email, phone, validation = form.get_data()
            # Champs obligatoires selon le schéma (NOT NULL + contraintes)
            if not username or not password or not full_name or not role or not email or not phone:
                QMessageBox.warning(self, "Erreur", "Veuillez remplir le nom d'utilisateur, le mot de passe, le nom complet, le rôle, l'email et le téléphone.")
                return
            if not self._is_valid_email(email):
                QMessageBox.warning(self, "Erreur", "L'email n'est pas valide.")
                return
            # Rôles autorisés
            if role not in {"Administrateur", "Technicien", "Superviseur", "Technicien responsable"}:
                QMessageBox.warning(self, "Erreur", "Rôle invalide.")
                return
            if UserManager.username_exists(username):
                QMessageBox.warning(self, "Erreur", "Ce nom d'utilisateur existe déjà.")
                return
            validate_user = "Validé" if validation == "Validé" else "Non validé"
            try:
                UserManager.add_user(username, password, full_name, role, email, phone, validate_user)
            except sqlite3.IntegrityError as e:
                msg = str(e)
                if "users.username" in msg:
                    QMessageBox.warning(self, "Erreur", "Ce nom d'utilisateur existe déjà.")
                elif "users.email" in msg:
                    QMessageBox.warning(self, "Erreur", "Cet email existe déjà.")
                elif "CHECK" in msg:
                    QMessageBox.warning(self, "Erreur", "Les données ne respectent pas les contraintes (rôle/validation/email).")
                else:
                    QMessageBox.warning(self, "Erreur", "Impossible d'ajouter l'utilisateur.")
                return
            self.refresh_users()

    def edit_user(self):
        user_id = self.table.get_selected_user_id()
        if user_id is None:
            return
        row = self.table.currentRow()
        username = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        full_name = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
        role = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
        email = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
        phone = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
        validation = self.table.item(row, 6).text() if self.table.item(row, 6) else "Non validé"

        if role == "admin" or role == "Administrateur":
            QMessageBox.warning(self, "Erreur", "Impossible de modifier un administrateur.")
            return

        form = UserForm(self, user=(user_id, username, full_name, role, email, phone, validation))
        if form.exec_() == QDialog.Accepted:
            new_username, new_password, new_full_name, new_role, new_email, new_phone, new_validation = form.get_data()
            # Mot de passe facultatif ici (non géré par UserManager.update_user), mais les autres champs sont requis
            if not new_role or not new_full_name or not new_username or not new_email or not new_phone:
                QMessageBox.warning(self, "Erreur", "Veuillez remplir le nom d'utilisateur, le nom complet, le rôle, l'email et le téléphone.")
                return
            if not self._is_valid_email(new_email):
                QMessageBox.warning(self, "Erreur", "L'email n'est pas valide.")
                return
            if new_role not in {"Administrateur", "Technicien", "Superviseur", "Technicien responsable"}:
                QMessageBox.warning(self, "Erreur", "Rôle invalide.")
                return
            if UserManager.username_exists(new_username, exclude_id=user_id):
                QMessageBox.warning(self, "Erreur", "Ce nom d'utilisateur existe déjà.")
                return
            validate_user = "Validé" if new_validation == "Validé" else "Non validé"
            try:
                UserManager.update_user(user_id, new_username, new_full_name, new_role, new_email, new_phone, validate_user)
            except sqlite3.IntegrityError as e:
                msg = str(e)
                if "users.username" in msg:
                    QMessageBox.warning(self, "Erreur", "Ce nom d'utilisateur existe déjà.")
                elif "users.email" in msg:
                    QMessageBox.warning(self, "Erreur", "Cet email existe déjà.")
                elif "CHECK" in msg:
                    QMessageBox.warning(self, "Erreur", "Les données ne respectent pas les contraintes (rôle/validation/email).")
                else:
                    QMessageBox.warning(self, "Erreur", "Impossible de modifier l'utilisateur.")
                return
            # Note: la mise à jour du mot de passe n'est pas gérée ici (méthode non prévue par UserManager)
            self.refresh_users()

    def delete_user(self):
        user_id = self.table.get_selected_user_id()
        if user_id is None:
            return
        row = self.table.currentRow()
        role = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
        if role == "admin" or role == "Administrateur":
            QMessageBox.warning(self, "Erreur", "Impossible de supprimer un administrateur.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Supprimer utilisateur")
        dialog.setModal(True)
        dialog.resize(250, 100)
        dialog.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QLabel { background: #f0f0f0; color: #1c5ea3; font-weight: bold; font-size: 15px; }
            QPushButton {
                background-color: #b8d5ed; color: #1c5ea3; border: none; border-radius: 4px;
                padding: 6px 18px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1c5ea3; color: #fff; }
            QPushButton:pressed { background-color: #14406e; }
        """)
        layout = QVBoxLayout(dialog)
        label = QLabel("Supprimer cet utilisateur ?")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_yes = QPushButton("Supprimer")
        btn_no = QPushButton("Annuler")
        btn_layout.addWidget(btn_yes)
        btn_layout.addWidget(btn_no)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        btn_yes.clicked.connect(dialog.accept)
        btn_no.clicked.connect(dialog.reject)

        if dialog.exec_() == QDialog.Accepted:
            try:
                UserManager.delete_user(user_id)
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Erreur", "Impossible de supprimer l'utilisateur.")
                return
            self.refresh_users()
