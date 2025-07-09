from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QMessageBox, QHeaderView, QSizePolicy,
    QDialog, QFormLayout, QDateEdit
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor
from datetime import datetime

from models.projectmanager import ProjectManager
from models.testmanager    import TestManager

class AddEquipmentDialog(QDialog):
    def __init__(self, parent, tm: TestManager, test_id: int):
        super().__init__(parent)
        self.tm = tm
        self.test_id = test_id
        self.setWindowTitle("Ajouter un équipement")
        self.setModal(True)
        self.resize(320, 180)
        self.setStyleSheet("""
            QDialog { background-color: #f0f0f0; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 14px; }
            QLineEdit, QDateEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 5px;
                padding: 4px; font-size: 13px;
            }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 6px;
                padding: 6px 18px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
        """)

        form = QFormLayout()
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Nom de l'équipement")
        self.input_date = QDateEdit(calendarPopup=True)
        self.input_date.setDate(QDate.currentDate())
        self.input_date.setDisplayFormat("yyyy-MM-dd")
        self.input_periodicity = QLineEdit()
        self.input_periodicity.setPlaceholderText("Mensuelle, Trimestrielle, etc.")

        form.addRow("Équipement :", self.input_name)
        form.addRow("Dernier étalonnage :", self.input_date)
        form.addRow("Périodicité     :", self.input_periodicity)

        btn_save   = QPushButton("Enregistrer")
        btn_cancel = QPushButton("Annuler")
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addLayout(btn_layout)

    def _save(self):
        name = self.input_name.text().strip()
        date_str = self.input_date.date().toString("yyyy-MM-dd")
        periodicity = self.input_periodicity.text().strip()
        if not name or not periodicity:
            QMessageBox.warning(self, "Champs manquants",
                                "Veuillez renseigner tous les champs.",
                                QMessageBox.Ok)
            return
        self.tm.add_equipment(self.test_id, name, date_str, periodicity)
        self.accept()


class TestSessionWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db   = db
        self.user = user
        self.pm   = ProjectManager(db)
        self.tm   = TestManager(db)
        self.current_test_id = None

        self.setStyleSheet("""
            QWidget { background-color: #e0e0e0; }
            QPushButton {
                background-color: #1c5ea3; color: #fff; border-radius: 8px;
                padding: 8px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b8d5ed; color: #1c5ea3; }
            QComboBox#projectCombo {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px; min-width: 180px;
                color: #1c5ea3; font-weight: bold;
            }
            QComboBox#projectCombo:focus {
                border: 2px solid #1c5ea3;
            }
            QComboBox#projectCombo QAbstractItemView {
                background: #fff; color: #1c5ea3;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; border-radius: 8px;
                font-size: 14px;
            }
            QTableWidget {
                background-color: #fff; alternate-background-color: #b8d5ed;
                gridline-color: #1c5ea3; selection-background-color: #b8d5ed;
                selection-color: #1c5ea3; border: 2px solid #1c5ea3;
                font-size: 15px; border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px;
                qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QLineEdit, QDateEdit {
                background: #fff; border: 1px solid #b8d5ed; border-radius: 4px;
                padding: 4px 8px; font-size: 14px;
            }
            QLineEdit:focus, QDateEdit:focus { border: 2px solid #1c5ea3; }
            QLabel { color: #1c5ea3; font-weight: bold; font-size: 13px; }
        """)

        # Sélection de projet
        self.lbl_choose = QLabel("Choisissez le projet :")
        self.lbl_choose.setStyleSheet("font-weight: bold; font-size: 20px; color: #1c5ea3;")

        self.combo = QComboBox(self)
        self.combo.setObjectName("projectCombo")
        self.combo.setFixedHeight(28)
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo.currentIndexChanged.connect(self._on_project_changed)

        self.lbl_points = QLabel("Points requis : –")
        self.lbl_points.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.table = TestSessionTable()
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.btn_save          = QPushButton("Enregistrer les mesures")
        self.btn_modify        = QPushButton("Modifier les mesures")
        self.btn_add_equipment = QPushButton("Ajouter équipement")
        for btn in (self.btn_save, self.btn_modify, self.btn_add_equipment):
            btn.setFixedHeight(36)
        self.btn_save.clicked.connect(self._save_measurements)
        self.btn_modify.clicked.connect(self._enable_editing)
        self.btn_add_equipment.clicked.connect(self._open_add_equipment)

        # Layout principal
        v = QVBoxLayout(self)
        h_combo = QHBoxLayout()
        h_combo.addWidget(self.lbl_choose)
        h_combo.addWidget(self.combo)
        h_combo.addStretch()
        h_combo.addWidget(self.lbl_points)
        v.addLayout(h_combo)
        v.addWidget(self.table, stretch=1)

        # Boutons
        h_buttons = QHBoxLayout()
        h_buttons.addStretch()
        h_buttons.addWidget(self.btn_add_equipment)
        h_buttons.addWidget(self.btn_save)
        h_buttons.addWidget(self.btn_modify)
        h_buttons.addStretch()
        v.addLayout(h_buttons)

        self.btn_save.hide()
        self.btn_modify.show()
        self.btn_add_equipment.hide()
        self.refresh()

    def refresh(self):
        self.current_test_id = None
        self.btn_save.hide()
        self.btn_modify.show()
        self.btn_add_equipment.hide()

        all_p = self.pm.get_projects()
        if self.user['role'] == 'Administrateur':
            self.projects = all_p
        else:
            self.projects = [p for p in all_p if p.get("assigned_to") == self.user["id"]]

        self.combo.blockSignals(True)
        self.combo.clear()
        for p in self.projects:
            label = f"{p['company_name']} – {p['room_type']} ({p['cleanroom_area']} m²)"
            self.combo.addItem(label, p["id"])
        self.combo.blockSignals(False)
        self._on_project_changed(self.combo.currentIndex())

    def _on_project_changed(self, idx):
        self.current_test_id = None
        self.btn_save.hide()
        self.btn_modify.show()
        self.btn_add_equipment.hide()

        if idx < 0 or idx >= len(self.projects):
            return

        proj       = self.projects[idx]
        project_id = proj["id"]
        area       = proj["cleanroom_area"]
        iso_class  = proj["iso_class"]

        # Affichage/masquage des actions
        if proj.get("validation_status") == "Validé":
            self.btn_modify.hide()
            self.btn_add_equipment.hide()
        else:
            self.btn_modify.show()
            self.btn_add_equipment.show()

        needed = self.tm.get_required_points(project_id)
        self.lbl_points.setText(f"Surface = {area} m² • {needed} points requis")

        rows   = self.db.conn.execute(
            "SELECT test_name FROM thresholds WHERE iso_name = ?", (iso_class,)
        ).fetchall()
        params = [r["test_name"] for r in rows]

        headers = ["Point"] + params
        self.table.setup_table(headers, needed)

        session = self.tm.get_latest_test(project_id, self.user["id"])
        if session:
            self.current_test_id = session["id"]
            measurements = self.tm.get_measurements(self.current_test_id)
            self.table.load_measurements(needed, params, measurements)
        else:
            self.table.init_empty(needed, len(headers))

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.updateGeometry()

    def _enable_editing(self):
        self.btn_modify.hide()
        self.btn_save.show()
        self.table.set_editable(True)

    def _save_measurements(self):
        idx = self.combo.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "Erreur", "Aucun projet sélectionné.", QMessageBox.Ok)
            return
        project_id = self.combo.itemData(idx)
        tech_id    = self.user["id"]

        headers = [self.table.horizontalHeaderItem(c).text()
                   for c in range(self.table.columnCount())]
        measurements = []
        for r in range(self.table.rowCount()):
            pt = self.table.item(r, 0).text()
            for c, param in enumerate(headers[1:], start=1):
                le = self.table.cellWidget(r, c)
                txt = le.text().strip()
                if not txt:
                    QMessageBox.warning(self, "Champs manquants",
                                        f"Mesure manquante pour {pt} → {param}",
                                        QMessageBox.Ok)
                    return
                try:
                    val = float(txt)
                except ValueError:
                    QMessageBox.warning(self, "Valeur incorrecte",
                                        f"Valeur non numérique pour {pt} → {param}",
                                        QMessageBox.Ok)
                    return
                measurements.append((pt, param, val, le.property("measurement_id")))

        session_name = f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        if self.current_test_id:
            for pt, param, val, m_id in measurements:
                if m_id:
                    self.tm.update_measurement(m_id, val)
                else:
                    self.tm.add_measurement(self.current_test_id, pt, param, val)
        else:
            payload = [(param, val, None, None) for _, param, val, _ in measurements]
            self.tm.save_test(project_id, tech_id, session_name, payload)

        QMessageBox.information(self, "Succès", "Mesures enregistrées !", QMessageBox.Ok)
        self.btn_save.hide()
        self.btn_modify.show()
        self._on_project_changed(self.combo.currentIndex())

    def _open_add_equipment(self):
        if not self.current_test_id:
            QMessageBox.warning(self, "Erreur",
                                "Aucune session de test disponible.\n"
                                "Enregistrez d'abord les mesures.",
                                QMessageBox.Ok)
            return
        dlg = AddEquipmentDialog(self, self.tm, self.current_test_id)
        if dlg.exec_() == QDialog.Accepted:
            QMessageBox.information(self, "Succès",
                                    "Équipement enregistré avec succès.",
                                    QMessageBox.Ok)


class TestSessionTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setStyleSheet(self._get_stylesheet())

    def _get_stylesheet(self):
        return """
            TestSessionTable {
                background-color: #fff;
                alternate-background-color: #fff;
                gridline-color: #1c5ea3;
                border: 2px solid #1c5ea3;
                selection-background-color: #b8d5ed;
                selection-color: #1c5ea3;
                font-size: 13px;
                font-weight: bold;
                border-radius: 8px;
                color: #000;
            }
            QHeaderView::section {
                background-color: #1c5ea3; color: #fff; font-weight: bold;
                border: none; padding: 6px; qproperty-alignment: 'AlignCenter | AlignVCenter';
            }
            QTableWidget::item {
                border: none;
                background: #fff;
            }
            QLineEdit {
                background-color: #b8d5ed;
                color: #1c5ea3;
                font-size: 13px;
                font-weight: bold;
                qproperty-alignment: 'AlignCenter | AlignVCenter';
                border: none;
            }
            QLineEdit:read-only {
                background-color: #fff;
                color: #000;
                border: none;
            }
        """

    def setup_table(self, headers, needed):
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(needed)

    def load_measurements(self, needed, params, measurements):
        mmap = {(m["point_name"], m["parameter"]): m for m in measurements}
        for r in range(needed):
            pt = f"Point {r+1}"
            item = QTableWidgetItem(pt)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QColor(Qt.white))
            self.setItem(r, 0, item)
            for c, param in enumerate(params, start=1):
                m = mmap.get((pt, param))
                le = QLineEdit(str(m["value"]) if m else "0")
                le.setProperty("measurement_id", m["id"] if m else None)
                le.setReadOnly(True)
                le.setAlignment(Qt.AlignCenter)
                self.setCellWidget(r, c, le)

    def init_empty(self, needed, ncols):
        for r in range(needed):
            item = QTableWidgetItem(f"Point {r+1}")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QColor(Qt.white))
            self.setItem(r, 0, item)
            for c in range(1, ncols):
                le = QLineEdit("0")
                le.setReadOnly(True)
                le.setAlignment(Qt.AlignCenter)
                self.setCellWidget(r, c, le)

    def set_editable(self, editable):
        for r in range(self.rowCount()):
            for c in range(1, self.columnCount()):
                w = self.cellWidget(r, c)
                w.setReadOnly(not editable)
