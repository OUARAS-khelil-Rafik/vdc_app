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

class NoFocusTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)

class ProjectTable(NoFocusTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels([
            "ID", "Entreprise", "Localisation", "Type de salle", "Date de test"
        ])
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.ExtendedSelection)
        self.setEditTriggers(self.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Aligner les titres du header au centre
        header = self.horizontalHeader()
        for i in range(self.columnCount()):
            header.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)

    def populate(self, rows):
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
            # row peut être un dict ou un tuple selon sqlite3.Row
            if isinstance(row, dict):
                get = row.get
            else:
                # tuple, on suppose l'ordre: id, company_name, location, room_type, test_date
                get = lambda k: row[["id", "company_name", "location", "room_type", "test_date"].index(k)]
            item_id = QTableWidgetItem(str(get('id')))
            item_id.setData(Qt.UserRole, get('id'))
            item_id.setTextAlignment(Qt.AlignCenter)
            item_id.setBackground(QColor(Qt.white))
            item_company = QTableWidgetItem(get('company_name'))
            item_company.setTextAlignment(Qt.AlignCenter)
            item_company.setBackground(QColor(Qt.white))
            item_location = QTableWidgetItem(get('location'))
            item_location.setTextAlignment(Qt.AlignCenter)
            item_location.setBackground(QColor(Qt.white))
            item_room = QTableWidgetItem(get('room_type'))
            item_room.setTextAlignment(Qt.AlignCenter)
            item_room.setBackground(QColor(Qt.white))
            item_date = QTableWidgetItem(get('test_date'))
            item_date.setTextAlignment(Qt.AlignCenter)
            item_date.setBackground(QColor(Qt.white))
            self.setItem(i, 0, item_id)
            self.setItem(i, 1, item_company)
            self.setItem(i, 2, item_location)
            self.setItem(i, 3, item_room)
            self.setItem(i, 4, item_date)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def get_selected_project_id(self):
        sel = self.currentRow()
        if sel < 0:
            return None
        item = self.item(sel, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

class ProjectForm(QDialog):
    def __init__(self, db, user, project=None):
        """
        :param db: instance de models.database.Database
        :param user: dict {id, username, role}
        :param project: dict représentant le projet à modifier (ou None pour ajout)
        """
        super().__init__()
        self.db = db
        self.user = user
        # If project is an int (project id), fetch the project dict from the database
        if isinstance(project, int):
            cursor = self.db.conn.execute(
                "SELECT * FROM projects WHERE id=?",
                (project,)
            )
            row = cursor.fetchone()
            if row:
                columns = [col[0] for col in cursor.description]
                self.project = dict(zip(columns, row))
            else:
                self.project = None
        else:
            self.project = project
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Modifier projet" if self.project else "Nouveau projet")
        self.setModal(True)
        self.resize(400, 200)

        # Appliquer le style global
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
            }
            QLineEdit, QDateEdit {
                background: #ffffff;
                border: 1px solid #b8d5ed;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus {
                border: 2px solid #1c5ea3;
            }
            QLabel {
                color: #1c5ea3;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton {
                background-color: #b8d5ed;
                color: #1c5ea3;
                border: none;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1c5ea3;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #14406e;
            }
        """)

        # Champs du formulaire
        self.input_company  = QLineEdit()
        self.input_location = QLineEdit()
        self.input_room     = QLineEdit()
        self.input_date     = QDateEdit(calendarPopup=True)
        self.input_date.setDate(QDate.currentDate())

        # Pré-remplir si modification
        if self.project:
            self.input_company.setText(self.project.get("company_name", ""))
            self.input_location.setText(self.project.get("location", ""))
            self.input_room.setText(self.project.get("room_type", ""))
            try:
                date = QDate.fromString(self.project.get("test_date", ""), "yyyy-MM-dd")
                if date.isValid():
                    self.input_date.setDate(date)
            except Exception:
                pass

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
        """
        Valide la saisie et enregistre ou modifie le projet en base.
        """
        company  = self.input_company.text().strip()
        location = self.input_location.text().strip()
        room     = self.input_room.text().strip()
        date     = self.input_date.date().toString("yyyy-MM-dd")

        # Validation des champs obligatoires
        if not company or not date:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Le nom de l'entreprise et la date sont obligatoires.",
                QMessageBox.Ok
            )
            return

        try:
            if self.project:
                # Modification
                self.db.conn.execute(
                    """
                    UPDATE projects
                    SET company_name=?, location=?, room_type=?, test_date=?
                    WHERE id=?
                    """,
                    (company, location, room, date, self.project["id"])
                )
            else:
                # Insertion
                self.db.conn.execute(
                    """
                    INSERT INTO projects
                        (company_name, location, room_type, test_date, created_by)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (company, location, room, date, self.user['id'])
                )
            self.db.conn.commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur",
                f"Impossible de {'modifier' if self.project else 'créer'} le projet : {e}",
                QMessageBox.Ok
            )

class TestForm(QDialog):
    def __init__(self, db, project_id, user):
        """
        :param db: instance de models.database.Database
        :param project_id: ID du projet sélectionné
        :param user: dict {id, username, role}
        """
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.user = user
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Saisie des tests")
        self.setModal(True)
        self.resize(450, 300)

        # Style général
        self.setStyleSheet("""
            QDialog {
                background-color: #e0e0e0;
            }
            QLabel {
                color: #1c5ea3;
                font-weight: bold;
                font-size: 14px;
            }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #b8d5ed;
                border-radius: 5px;
                padding: 4px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: #ffffff;
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
            }
        """)

        # 1. Récupérer la classe ISO (room_type) du projet
        row = self.db.conn.execute(
            "SELECT room_type FROM projects WHERE id = ?",
            (self.project_id,)
        ).fetchone()
        self.iso_class = row["room_type"]

        # 2. Charger les seuils pour cette classe
        rows = self.db.conn.execute(
            "SELECT parameter, max_value FROM thresholds WHERE iso_class = ?",
            (self.iso_class,)
        ).fetchall()
        self.thresholds = [(r["parameter"], r["max_value"]) for r in rows]

        # 3. Construire le formulaire dynamique
        form_layout = QFormLayout()
        # Nom du point de mesure
        self.input_point = QLineEdit()
        form_layout.addRow("Point de mesure :", self.input_point)

        # Champs pour chaque paramètre (avec indication du seuil max)
        self.widgets = {}
        for param, max_val in self.thresholds:
            label = f"{param} (≤ {max_val})"
            widget = QLineEdit()
            widget.setPlaceholderText("Valeur numérique")
            form_layout.addRow(label, widget)
            self.widgets[param] = widget

        # Boutons Enregistrer / Annuler
        self.btn_save   = QPushButton("Enregistrer")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_save.clicked.connect(self.save_test)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        # Assemblage final
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def save_test(self):
        # 4. Validation du nom du point
        point_name = self.input_point.text().strip()
        if not point_name:
            QMessageBox.warning(
                self, "Champs manquant",
                "Merci de renseigner le nom du point de mesure.",
                QMessageBox.Ok
            )
            return

        # 5. Insertion du test
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        cursor = self.db.conn.execute(
            "INSERT INTO tests (project_id, technician_id, measurement_date) "
            "VALUES (?, ?, ?)",
            (self.project_id, self.user["id"], timestamp)
        )
        test_id = cursor.lastrowid

        # 6. Lecture des valeurs et insertion des mesures
        compliant = True
        for param, max_val in self.thresholds:
            text = self.widgets[param].text().strip()
            try:
                value = float(text)
            except ValueError:
                QMessageBox.warning(
                    self, "Valeur invalide",
                    f"La valeur pour « {param} » n’est pas un nombre valide.",
                    QMessageBox.Ok
                )
                # Nettoyage partiel en cas d’erreur
                self.db.conn.execute("DELETE FROM tests WHERE id = ?", (test_id,))
                self.db.conn.commit()
                return

            # Enregistrer la mesure
            self.db.conn.execute(
                "INSERT INTO measurements (test_id, point_name, parameter, value) "
                "VALUES (?, ?, ?, ?)",
                (test_id, point_name, param, value)
            )

            # Vérifier la conformité
            if value > max_val:
                compliant = False

        # 7. Validation finale de la transaction
        self.db.conn.commit()

        # 8. Affichage du résultat
        status = "Conforme" if compliant else "Non conforme"
        QMessageBox.information(
            self, "Test enregistré",
            f"Le test a bien été enregistré.\nStatut de conformité : {status}",
            QMessageBox.Ok
        )
        self.accept()

class ThresholdsDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("Seuils de conformité")
        self.resize(600, 400)
        self._apply_styles()
        self._init_ui()
        self.refresh_thresholds()

    def _apply_styles(self):
        # Couleurs : bleu clair #b8d5ed, bleu foncé #1c5ea3, blanc, fond gris
        self.setStyleSheet("""
            QDialog {
                background-color: #e0e0e0;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #b8d5ed;
                gridline-color: #1c5ea3;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                border: 1px solid #1c5ea3;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #1c5ea3;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #b8d5ed;
                padding: 4px;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #1c5ea3;
                padding: 3px;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: #ffffff;
                border-radius: 5px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
            }
            QMessageBox {
                background-color: #ffffff;
            }
        """)

    def _init_ui(self):
        # Formulaire d’ajout
        self.input_iso    = QLineEdit()
        self.input_param  = QLineEdit()
        self.input_max    = QLineEdit()
        btn_add = QPushButton("Ajouter")
        btn_add.clicked.connect(self.add_threshold)

        form = QFormLayout()
        form.addRow("Classe ISO :", self.input_iso)
        form.addRow("Paramètre  :", self.input_param)
        form.addRow("Valeur Max :", self.input_max)

        # Table des seuils existants
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Classe ISO", "Paramètre", "Valeur max"])
        self.table.setEditTriggers(self.table.NoEditTriggers)
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.hideColumn(0)  # masque la colonne ID

        # Bouton suppression
        btn_del = QPushButton("Supprimer sélection")
        btn_del.clicked.connect(self.delete_threshold)

        # Layout global
        hl = QHBoxLayout()
        hl.addLayout(form)
        hl.addWidget(btn_add, alignment=Qt.AlignBottom)

        vl = QVBoxLayout()
        vl.addLayout(hl)
        vl.addWidget(self.table)
        vl.addWidget(btn_del, alignment=Qt.AlignRight)
        self.setLayout(vl)

    def refresh_thresholds(self):
        rows = self.db.conn.execute(
            "SELECT id, iso_class, parameter, max_value FROM thresholds"
        ).fetchall()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(i, 1, QTableWidgetItem(r["iso_class"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["parameter"]))
            self.table.setItem(i, 3, QTableWidgetItem(str(r["max_value"])))
        self.table.resizeColumnsToContents()

    def add_threshold(self):
        iso   = self.input_iso.text().strip()
        param = self.input_param.text().strip()
        maxv  = self.input_max.text().strip()
        if not (iso and param and maxv):
            QMessageBox.warning(self, "Champs manquants",
                                "Tous les champs doivent être remplis.", QMessageBox.Ok)
            return
        try:
            mv = float(maxv)
        except ValueError:
            QMessageBox.warning(self, "Valeur incorrecte",
                                "La valeur max doit être un nombre.", QMessageBox.Ok)
            return

        try:
            self.db.conn.execute(
                "INSERT INTO thresholds (iso_class, parameter, max_value) VALUES (?, ?, ?)",
                (iso, param, mv)
            )
            self.db.conn.commit()
            self.input_iso.clear()
            self.input_param.clear()
            self.input_max.clear()
            self.refresh_thresholds()
        except Exception as e:
            QMessageBox.critical(self, "Erreur",
                                 f"Impossible d’ajouter le seuil : {e}", QMessageBox.Ok)

    def delete_threshold(self):
        sel = self.table.currentRow()
        if sel < 0:
            QMessageBox.warning(self, "Aucune sélection",
                                "Veuillez sélectionner un seuil à supprimer.", QMessageBox.Ok)
            return
        tid = int(self.table.item(sel, 0).text())
        confirm = QMessageBox.question(
            self, "Confirmation",
            "Supprimer ce seuil définitivement ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                self.db.conn.execute("DELETE FROM thresholds WHERE id = ?", (tid,))
                self.db.conn.commit()
                self.refresh_thresholds()
            except Exception as e:
                QMessageBox.critical(self, "Erreur",
                                     f"Impossible de supprimer le seuil : {e}", QMessageBox.Ok)

class DashboardToolbar(QToolBar):
    def __init__(self, user, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setStyleSheet("background: #e0e0e0; border: none;")
        self.actions_dict = {}
        self._setup_actions(user)

    def _setup_actions(self, user):
        self.actions_dict['projects'] = QAction("Projets", self)
        self.actions_dict['thresholds'] = QAction("Seuils", self)
        self.actions_dict['input_tests'] = QAction("Saisie tests", self)
        self.actions_dict['validate'] = QAction("Valider tests", self)
        self.actions_dict['generate_pdf'] = QAction("Générer PDF", self)
        self.actions_dict['logout'] = QAction("Déconnexion", self)

        role = user['role']
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)
        if role == 'Administrateur':
            self.addAction(self.actions_dict['projects'])
            self.addAction(self.actions_dict['thresholds'])
            self.addAction(self.actions_dict['input_tests'])
            self.addAction(self.actions_dict['validate'])
            self.addAction(self.actions_dict['generate_pdf'])
        elif role == 'Technicien premium':
            self.addAction(self.actions_dict['thresholds'])
            self.addAction(self.actions_dict['input_tests'])
            self.addAction(self.actions_dict['validate'])
        elif role == 'Technicien':
            self.addAction(self.actions_dict['input_tests'])
        self.addSeparator()
        self.addAction(self.actions_dict['logout'])

class DashboardWindow(QMainWindow):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user  # dict avec keys: id, username, role
        self._init_ui()
        self.refresh_projects()

    def _init_ui(self):
        self.setWindowTitle("VDC Engineering – Tableau de bord")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #e0e0e0;
            }
            QWidget {
                background-color: #e0e0e0;
            }
            QLabel#welcomeLabel {
                color: #1c5ea3;
                font-size: 22px;
                font-weight: bold;
                border-radius: 10px;
                padding: 12px;
                margin-bottom: 10px;
            }
            QTableWidget {
                border: none;
                font-size: 15px;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                gridline-color: #333333;
            }
            QHeaderView::section {
                background-color: #1c5ea3;
                color: #ffffff;
                font-weight: bold;
                border: none;
                padding: 6px;
                qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QToolButton {
                background: transparent;
                border: none;
                color: #1c5ea3;
                font-size: 15px;
                font-weight: bold;
                padding: 8px 18px;
                margin: 0 4px;
            }
            QToolButton:hover {
                color: #b8d5ed;
            }
            QPushButton {
                background-color: #1c5ea3;
                color: #fff;
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
                padding: 8px 24px;
                margin: 8px 8px 0 0;
            }
            QPushButton:hover {
                background-color: #b8d5ed;
                color: #1c5ea3;
            }
        """)

        # Toolbar
        self.toolbar = DashboardToolbar(self.user)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.toolbar.actions_dict['projects'].triggered.connect(self.show_dashboard)
        self.toolbar.actions_dict['thresholds'].triggered.connect(self.open_thresholds)
        self.toolbar.actions_dict['input_tests'].triggered.connect(self.open_form_tests)
        self.toolbar.actions_dict['validate'].triggered.connect(self.open_validate_tests)
        self.toolbar.actions_dict['generate_pdf'].triggered.connect(self.generate_pdf)
        self.toolbar.actions_dict['logout'].triggered.connect(self.logout)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Welcome label
        welcome = QLabel(f"Bienvenue {self.user['username']} ({self.user['role']})")
        welcome.setObjectName("welcomeLabel")
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        # Project table
        self.table_projects = ProjectTable()
        layout.addWidget(self.table_projects, stretch=1)

        # Buttons for admin
        if self.user['role'] == 'Administrateur':
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            self.btn_ajouter = QPushButton("Ajouter Projet")
            self.btn_supprimer = QPushButton("Supprimer Projet")
            self.btn_modifier = QPushButton("Modifier Projet")
            btn_layout.addWidget(self.btn_ajouter)
            btn_layout.addWidget(self.btn_supprimer)
            btn_layout.addWidget(self.btn_modifier)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
            self.btn_ajouter.clicked.connect(self.add_project)
            self.btn_supprimer.clicked.connect(self.delete_selected_project)
            self.btn_modifier.clicked.connect(self.edit_selected_project)

    def show_dashboard(self):
        self.refresh_projects()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        col_count = self.table_projects.columnCount()
        for i in range(col_count):
            self.table_projects.setColumnWidth(i, self.table_projects.width() // col_count)

    def refresh_projects(self):
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        # Correction : transformer les tuples en dicts pour la table
        columns = ["id", "company_name", "location", "room_type", "test_date"]
        dict_rows = []
        for row in rows:
            if isinstance(row, dict):
                dict_rows.append(row)
            else:
                dict_rows.append(dict(zip(columns, row)))
        self.table_projects.populate(dict_rows)

    def add_project(self):
        dialog = ProjectForm(self.db, self.user)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()

    def open_thresholds(self):
        dlg = ThresholdsDialog(self.db)
        dlg.exec_()

    def open_form_tests(self):
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        dialog = TestForm(self.db, project_id, self.user)
        dialog.exec_()

    def open_validate_tests(self):
        role = self.user['role']
        if role not in ('Administrateur', 'Technicien premium'):
            QMessageBox.warning(self, "Accès refusé", "Vous n'avez pas accès à cette fonctionnalité.", QMessageBox.Ok)
            return
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet.", QMessageBox.Ok)
            return
        QMessageBox.information(
            self, "Validation", "Fonctionnalité de validation à venir.", QMessageBox.Ok
        )

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
        QMessageBox.information(
            self, "PDF généré", f"Rapport enregistré ici : {save_path}", QMessageBox.Ok
        )

    def logout(self):
        from gui.login import LoginWindow
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
        self.close()

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
            self.db.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            self.db.conn.commit()
            self.refresh_projects()

    def edit_selected_project(self):
        project_id = self.table_projects.get_selected_project_id()
        if project_id is None:
            QMessageBox.warning(self, "Aucun projet", "Veuillez sélectionner un projet à modifier.", QMessageBox.Ok)
            return
        # Correction : utiliser ProjectForm de ce fichier, pas de gui.form_project
        dialog = ProjectForm(self.db, self.user, project_id)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh_projects()
