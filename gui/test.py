# gui/test.py

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt
from datetime import datetime

from models.projectmanager import ProjectManager
from models.testmanager    import TestManager

class TestSessionWidget(QWidget):
    def __init__(self, db, user, parent=None):
        super().__init__(parent)
        self.db   = db
        self.user = user
        self.pm   = ProjectManager(db)
        self.tm   = TestManager(db)
        self.current_test_id = None

        # Sélecteur de projet
        self.lbl_proj = QLabel("Projets assignés :")
        self.combo    = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_project_changed)

        # Info points requis
        self.lbl_points = QLabel("Points requis : –")

        # Tableau de saisie
        self.table = QTableWidget()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Boutons
        self.btn_save   = QPushButton("Enregistrer mesures")
        self.btn_modify = QPushButton("Modifier mesures")
        self.btn_save.clicked.connect(self._save_measurements)
        self.btn_modify.clicked.connect(self._enable_editing)

        # Layout
        v = QVBoxLayout(self)
        v.addWidget(self.lbl_proj)
        v.addWidget(self.combo)
        v.addWidget(self.lbl_points)
        v.addWidget(self.table)
        h = QHBoxLayout()
        h.addWidget(self.btn_save)
        h.addWidget(self.btn_modify)
        v.addLayout(h)

        self.btn_modify.hide()

        # Initialisation
        self.refresh()

    def refresh(self):
        """
        Recharge la liste des projets et reconstruit le tableau
        (appelé à l'ouverture de l'onglet pour préserver les valeurs).
        """
        self.current_test_id = None
        self.btn_modify.hide()
        self.btn_save.show()

        # 1) Charge projets
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

        # 2) Reconstruit le tableau pour le projet sélectionné (index courant)
        self._on_project_changed(self.combo.currentIndex())

    def _on_project_changed(self, idx):
        # même logique qu'avant
        self.current_test_id = None
        self.btn_modify.hide()
        self.btn_save.show()

        if idx < 0 or idx >= len(self.projects):
            return

        project_id = self.combo.itemData(idx)
        proj       = self.projects[idx]
        area       = proj["cleanroom_area"]
        iso_class  = proj["iso_class"]

        needed = self.tm.get_required_points(project_id)
        self.lbl_points.setText(f"Surface = {area} m² • {needed} points requis")

        # Paramètres ISO
        rows = self.db.conn.execute(
            "SELECT test_name FROM thresholds WHERE iso_name = ?", (iso_class,)
        ).fetchall()
        params = [r["test_name"] for r in rows]

        # Préparation du tableau
        headers = ["Point"] + params
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(needed)

        # Charger session existante si présente
        session = self.tm.get_latest_test(project_id, self.user["id"])
        if session:
            self.current_test_id = session["id"]
            measurements = self.tm.get_measurements(self.current_test_id)
            mmap = {(m["point_name"], m["parameter"]): m for m in measurements}
            for r in range(needed):
                pt = f"Point {r+1}"
                item = QTableWidgetItem(pt)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 0, item)
                for c, param in enumerate(params, start=1):
                    m = mmap.get((pt, param))
                    le = QLineEdit(str(m["value"]) if m else "")
                    le.setProperty("measurement_id", m["id"] if m else None)
                    le.setReadOnly(True)
                    self.table.setCellWidget(r, c, le)
            if session["is_validated"] == 0:
                self.btn_modify.show()
            else:
                self.btn_save.hide()
        else:
            # pas de session => vide
            for r in range(needed):
                item = QTableWidgetItem(f"Point {r+1}")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 0, item)
                for c in range(1, len(headers)):
                    le = QLineEdit()
                    le.setPlaceholderText("Valeur")
                    self.table.setCellWidget(r, c, le)

    def _enable_editing(self):
        self.btn_modify.hide()
        self.btn_save.show()
        for r in range(self.table.rowCount()):
            for c in range(1, self.table.columnCount()):
                w = self.table.cellWidget(r, c)
                w.setReadOnly(False)

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
                    QMessageBox.warning(
                        self, "Champs manquants",
                        f"Mesure manquante pour {pt} → {param}", QMessageBox.Ok)
                    return
                try:
                    val = float(txt)
                except ValueError:
                    QMessageBox.warning(
                        self, "Valeur incorrecte",
                        f"Valeur non numérique pour {pt} → {param}", QMessageBox.Ok)
                    return
                measurements.append((pt, param, val))

        session_name = f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        payload = [(param, val, None, None) for _, param, val in measurements]
        self.tm.save_test(project_id, tech_id, session_name, payload)

        QMessageBox.information(self, "Succès", "Mesures enregistrées !", QMessageBox.Ok)
        self.btn_save.hide()
        self.btn_modify.show()
        # ne pas vider : on reste sur les valeurs enregistrées
