# hvac_qp_app.py
# -*- coding: utf-8 -*-
"""
HVAC QP Test Bench – PyQt5 + SQLite3 (single file, copy‑paste ready)

What you get
------------
• A complete PyQt5 desktop app to run 8 HVAC QP tests, one by one, with a left tree (arborescence)
  and smart forms for each test. Each test computes outputs & conformity against default or
  project‑specific thresholds, and saves results to SQLite.
• Projects (company/location/tag/responsables/etc.) are managed in the DB and selectable in the top bar.
• Thresholds can be edited (global defaults or per‑project overrides).
• All calculations follow the algorithms described in your presentation.

Implemented tests
-----------------
1) Débit & Taux de renouvellement d’air (ACPH)
   Modes: gaine_pitot, gaine_anemo, bouche_balomètre, bouche_anemo
2) Cascade de pressions (ΔP)
3) Vitesses sous filtres / uniformité
4) Intégrité filtres HEPA (leak test)
5) Comptage particulaire en air (classification)
6) Recovery time (100:1)
7) Visualisation de flux (fumée)
8) Température & Humidité

Notes
-----
• DB file: hvac_qp.db in the current folder (auto‑created).
• The UI favors clarity over fancy widgets to keep it portable. You can skin via Qt stylesheets.
• Pseudocode references from your slides are embedded in each page class docstring.
"""
import json
import math
import sqlite3
import statistics as stats
from datetime import datetime
from typing import List, Dict, Any, Optional

import sys
from PyQt5.QtWidgets import QTabWidget

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QComboBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox, QHeaderView,
    QFileDialog
)

# --------------------------- Helpers ---------------------------------
# ---- NEW HELPERS (ajouter dans la section Helpers) -------------------

def air_density_from_TP(T_C: float, P_mbar: float = 1013.25) -> float:
    """
    Densité de l'air (kg/m³) calculée à partir de T (°C) et P (mbar).
    Formule gaz parfaits : rho = P / (R * T_K), avec P en Pa, R=287.05 J/kg/K.
    """
    T_K = T_C + 273.15
    P_Pa = P_mbar * 100.0
    R = 287.05
    return P_Pa / (R * T_K)


def table_non_empty_floats(tbl: QTableWidget, cols_from: int = 0) -> List[float]:
    """Parcourt un QTableWidget et renvoie toutes les valeurs numériques non vides (float)."""
    vals: List[float] = []
    for r in range(tbl.rowCount()):
        for c in range(cols_from, tbl.columnCount()):
            it = tbl.item(r, c)
            if not it:
                continue
            raw = (it.text() or "").strip()
            if not raw:
                continue
            try:
                vals.append(float(raw.replace(",", ".")))
            except:
                pass
    return vals


def parse_floats(text: str) -> List[float]:
    """Parse a comma/space/semicolon/newline separated list of numbers into floats."""
    if not text.strip():
        return []
    parts = [p.strip() for p in text.replace("\n", ",").replace(";", ",").split(",")]
    out = []
    for p in parts:
        if not p:
            continue
        try:
            out.append(float(p))
        except ValueError:
            # Allow European decimal comma
            try:
                out.append(float(p.replace(" ", "").replace(",", ".")))
            except ValueError:
                pass
    return out


def set_status_pill(label: QLabel, ok: Optional[bool]):
    """Green/Red/Gray pill indicator on a QLabel based on ok flag."""
    if ok is None:
        label.setText("—")
        label.setStyleSheet("QLabel { background:#999; color:white; padding:4px 8px; border-radius:10px; }")
    elif ok:
        label.setText("Conforme")
        label.setStyleSheet("QLabel { background:#28a745; color:white; padding:4px 8px; border-radius:10px; }")
    else:
        label.setText("Non conforme")
        label.setStyleSheet("QLabel { background:#dc3545; color:white; padding:4px 8px; border-radius:10px; }")


# --------------------------- Database ---------------------------------

class DB:
    def __init__(self, path: str = "hvac_qp.db"):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self):
        c = self.conn.cursor()
        # Projects & users
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT,
                name TEXT,
                location TEXT,
                tag TEXT,
                work_type TEXT,
                test_date TEXT,
                contact TEXT,
                responsables TEXT, -- comma-separated names for simplicity
                notes TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS default_thresholds (
                test_type TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY(test_type, key)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS project_thresholds (
                project_id INTEGER,
                test_type TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY(project_id, test_type, key)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                test_type TEXT,
                status TEXT,            -- e.g. "done"
                conformity INTEGER,     -- 1/0/NULL
                params_json TEXT,
                results_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.conn.commit()
        self.ensure_defaults()

    def ensure_defaults(self):
        """Insert sensible default thresholds if not present."""
        defaults = {
    
            "ACPH": {
                "rule": "ACPH_ge",          # ACPH_ge | ACPH_tolpct | Q_ge | Q_tolpct
                "target": "30",             # h-1 (si rule=ACPH_*) ou m3/h (si rule=Q_*)
                "tol_pct": "5",             # % si rule *_tolpct
                "pitot_K": "1.00"           # coeff Pitot par défaut (si utilisé)
            },
            "DeltaP": {
                "default_target_Pa": "15",  # valeur proposée à l'ajout d'une interface
                "default_tol_mode": "none", # none | plusminus_pct | plusminus_pa
                "default_tol_value": "0"    # valeur de tol selon mode
            },
            # ... le reste inchangé ...

            "Uniformity": {"seuil_uniformite": "20"},
            "HEPA_Leak": {"seuil_fuite_pct": "0.01", "signal_amont_min": "1.0"},
            "Particle_Class": {"debit_OPC_Lmin": "28.3"},
            "Recovery_Time": {"t_max_cible_min": "20"},
            "Temp_RH": {"Tmin": "20", "Tmax": "24", "RHmin": "40", "RHmax": "60"},
            "Smoke_Visual": {}
        }
        c = self.conn.cursor()
        for ttype, pairs in defaults.items():
            for k, v in pairs.items():
                c.execute("SELECT 1 FROM default_thresholds WHERE test_type=? AND key=?", (ttype, k))
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO default_thresholds(test_type, key, value) VALUES (?,?,?)",
                        (ttype, k, str(v))
                    )
        self.conn.commit()

    # ---------- Thresholds ----------
    def get_threshold(self, project_id: Optional[int], test_type: str, key: str, fallback: Optional[str] = None) -> Optional[str]:
        c = self.conn.cursor()
        if project_id is not None:
            c.execute(
                "SELECT value FROM project_thresholds WHERE project_id=? AND test_type=? AND key=?",
                (project_id, test_type, key)
            )
            row = c.fetchone()
            if row:
                return row[0]
        c.execute(
            "SELECT value FROM default_thresholds WHERE test_type=? AND key=?",
            (test_type, key)
        )
        row = c.fetchone()
        return row[0] if row else fallback

    def set_threshold(self, project_id: Optional[int], test_type: str, key: str, value: str):
        c = self.conn.cursor()
        if project_id is None:
            c.execute(
                "REPLACE INTO default_thresholds(test_type, key, value) VALUES (?,?,?)",
                (test_type, key, value)
            )
        else:
            c.execute(
                "REPLACE INTO project_thresholds(project_id, test_type, key, value) VALUES (?,?,?,?)",
                (project_id, test_type, key, value)
            )
        self.conn.commit()

    # ---------- Projects ----------
    def add_project(self, data: Dict[str, Any]) -> int:
        c = self.conn.cursor()
        c.execute(
            """
            INSERT INTO projects(company, name, location, tag, work_type, test_date, contact, responsables, notes)
            VALUES(:company, :name, :location, :tag, :work_type, :test_date, :contact, :responsables, :notes)
            """,
            data
        )
        self.conn.commit()
        return c.lastrowid

    def list_projects(self) -> List[sqlite3.Row]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM projects ORDER BY id DESC")
        return c.fetchall()

    # ---------- Tests ----------
    def save_test(self, project_id: int, test_type: str, conformity: Optional[bool], params: Dict[str, Any], results: Dict[str, Any]):
        now = datetime.utcnow().isoformat()
        c = self.conn.cursor()
        c.execute(
            """
            INSERT INTO tests(project_id, test_type, status, conformity, params_json, results_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                project_id, test_type, "done",
                None if conformity is None else (1 if conformity else 0),
                json.dumps(params, ensure_ascii=False),
                json.dumps(results, ensure_ascii=False),
                now, now
            )
        )
        self.conn.commit()


# --------------------------- Threshold editor -------------------------

class ThresholdEditor(QWidget):
    """Simple editor to view/set thresholds for a given test type (global or for current project)."""
    def __init__(self, db: DB, project_id: Optional[int], test_type: str, keys: List[str]):
        super().__init__()
        self.db = db
        self.project_id = project_id
        self.test_type = test_type
        self.keys = keys
        self.edits: Dict[str, QLineEdit] = {}
        lay = QFormLayout(self)
        for k in keys:
            e = QLineEdit(self)
            e.setText(self.db.get_threshold(project_id, test_type, k, "" ) or "")
            self.edits[k] = e
            lay.addRow(QLabel(k), e)
        btns = QHBoxLayout()
        b_save = QPushButton("Save thresholds")
        b_save.clicked.connect(self.on_save)
        btns.addWidget(b_save)
        lay.addRow(btns)

    def on_save(self):
        for k, e in self.edits.items():
            self.db.set_threshold(self.project_id, self.test_type, k, e.text().strip())
        QMessageBox.information(self, "OK", "Thresholds saved.")


# --------------------------- Test Pages -------------------------------
# Nécessaire si pas déjà importé plus haut :
# from PyQt5.QtWidgets import QTabWidget

class ACPHPage(QWidget):
    """
    Débit & ACPH — 4 modes + évaluation en direct
      • Pitot (débit direct m³/h)      -> liste simple des Q
      • Balomètre (m³/h)               -> liste des diffuseurs (attention Jet rotorique = alerte)
      • Balayage anémomètre (m³/h)     -> **1 valeur moyenne par diffuseur** (onglets)
      • Point par point (m³/h)         -> **onglets indépendants** (chaque onglet = une grille, ex. 6p6, 3p3, ...)

    Conformité (toujours):
      OK si Q_total ∈ [Q_requis*(1−tol%), Q_requis*(1+tol%)]  (tolérance %; 0% = strict)
    """

    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self._initialized = False

        # collections dynamiques
        self._scan_qspins: List[QDoubleSpinBox] = []  # 1 par diffuseur (balayage anémo)
        self._pp_tabs: List[dict] = []                # [{tbl, combo, spin, subtotal}, ...]

        # ---------- Paramètres pièce (pour ACPH – info)
        self.A = QDoubleSpinBox(); self.A.setRange(0, 1e6); self.A.setDecimals(3); self.A.setValue(50.0)
        self.H = QDoubleSpinBox(); self.H.setRange(0, 100); self.H.setDecimals(3); self.H.setValue(2.70)

        # ---------- Seuils (toujours Q requis + tol%)
        self.Q_req = QDoubleSpinBox(); self.Q_req.setRange(0, 1e8); self.Q_req.setDecimals(1); self.Q_req.setValue(1000.0)
        self.tol_pct = QDoubleSpinBox(); self.tol_pct.setRange(0, 100); self.tol_pct.setDecimals(1); self.tol_pct.setValue(0.0)

        # ---------- Méthode
        self.method = QComboBox()
        self.method.addItems([
            "Pitot (débit direct m³/h)",
            "Balomètre (m³/h)",
            "Balayage anémomètre (m³/h)",
            "Point par point (m³/h)"
        ])
        self.method.currentIndexChanged.connect(self._on_method_change)

        # ---------- Stack des modes
        self.stack = QStackedWidget()

        # ==== PITOT ====
        self.pitot_points = QSpinBox(); self.pitot_points.setRange(1, 500); self.pitot_points.setValue(3)
        self.pitot_points.valueChanged.connect(self._build_pitot_table)
        btn_pitot_gen = QPushButton("Générer points"); btn_pitot_gen.clicked.connect(self._build_pitot_table)
        self.tbl_pitot = QTableWidget(0, 2); self.tbl_pitot.setHorizontalHeaderLabels(["Point", "Q (m³/h)"])
        self.tbl_pitot.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_pitot.itemChanged.connect(self._recalc_live)
        pitot_box = QWidget(); pl = QVBoxLayout(pitot_box)
        form_p = QFormLayout(); form_p.addRow("Nombre de points", self.pitot_points); form_p.addRow(btn_pitot_gen)
        pl.addLayout(form_p); pl.addWidget(self.tbl_pitot)
        self.stack.addWidget(pitot_box)

        # ==== BALOMÈTRE ====
        self.balo_n = QSpinBox(); self.balo_n.setRange(1, 200); self.balo_n.setValue(2)
        self.balo_n.valueChanged.connect(self._build_balo_table)
        self.balo_type = QComboBox(); self.balo_type.addItems(["Autre (non rotorique)", "Jet rotorique (rotorique)"])
        self.balo_type.currentIndexChanged.connect(self._on_balo_type)
        btn_balo_gen = QPushButton("Générer diffuseurs"); btn_balo_gen.clicked.connect(self._build_balo_table)
        self.tbl_balo = QTableWidget(0, 2); self.tbl_balo.setHorizontalHeaderLabels(["Diffuseur", "Q (m³/h)"])
        self.tbl_balo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_balo.itemChanged.connect(self._recalc_live)
        balo_box = QWidget(); bl = QVBoxLayout(balo_box)
        form_b = QFormLayout(); form_b.addRow("Nombre de diffuseurs", self.balo_n); form_b.addRow("Type de diffuseur", self.balo_type); form_b.addRow(btn_balo_gen)
        bl.addLayout(form_b); bl.addWidget(self.tbl_balo)
        self.stack.addWidget(balo_box)

        # ==== BALAYAGE ANÉMO (onglets par diffuseur, **1 valeur moyenne** par onglet) ====
        self.scan_n = QSpinBox(); self.scan_n.setRange(1, 200); self.scan_n.setValue(2)
        self.scan_type = QComboBox(); self.scan_type.addItems(["Autre (non rotorique)", "Jet rotorique (rotorique)"])
        self.scan_type.currentIndexChanged.connect(self._on_scan_type)
        # champs info (non utilisés dans les calculs)
        self.scan_Kp = QDoubleSpinBox(); self.scan_Kp.setRange(0.1, 5.0); self.scan_Kp.setDecimals(3); self.scan_Kp.setValue(1.00)
        self.scan_S = QDoubleSpinBox(); self.scan_S.setRange(0, 10); self.scan_S.setDecimals(4)
        self.lbl_formula = QLabel("Info: en balayage anémométrique on saisit la **valeur moyenne Q (m³/h)** par diffuseur")
        btn_scan_gen = QPushButton("Générer les onglets"); btn_scan_gen.clicked.connect(self._build_scan_tabs)
        self.scan_block = QLabel("")
        self.scan_tabs = QTabWidget()
        self.scan_n.valueChanged.connect(self._build_scan_tabs)
        scan_box = QWidget(); sl = QVBoxLayout(scan_box)
        form_s = QFormLayout()
        form_s.addRow("Nombre de diffuseurs (onglets)", self.scan_n)
        form_s.addRow("Type de diffuseur", self.scan_type)
        form_s.addRow("Coeff. perforation Kp (info)", self.scan_Kp)
        form_s.addRow("Surface S (m², info)", self.scan_S)
        sl.addLayout(form_s); sl.addWidget(self.lbl_formula)
        sl.addWidget(btn_scan_gen); sl.addWidget(self.scan_block)
        sl.addWidget(self.scan_tabs)
        self.stack.addWidget(scan_box)

        # ==== POINT PAR POINT (onglets indépendants, ex. 6p6 / 3p3, etc.) ====
        self.pp_default_map = {"3p3": 2, "6p6": 5, "6p9": 8, "6p12": 11, "9p12": 18, "12p12": 25}
        self.pp_n = QSpinBox(); self.pp_n.setRange(1, 200); self.pp_n.setValue(2)
        self.pp_n.valueChanged.connect(self._build_pp_tabs)
        self.pp_Kp = QDoubleSpinBox(); self.pp_Kp.setRange(0.1, 5.0); self.pp_Kp.setDecimals(3); self.pp_Kp.setValue(1.00)
        self.pp_S = QDoubleSpinBox(); self.pp_S.setRange(0, 10); self.pp_S.setDecimals(4)
        self.lbl_pp_formula = QLabel("Info: Point par point — saisie **directe** des Q (m³/h) pour chaque grille; libellés en 6p6, 3p3, ...")
        btn_pp_gen = QPushButton("Générer les onglets"); btn_pp_gen.clicked.connect(self._build_pp_tabs)
        self.pp_tabs = QTabWidget()
        pp_box = QWidget(); ppl = QVBoxLayout(pp_box)
        form_pp_top = QFormLayout()
        form_pp_top.addRow("Nombre de grilles (onglets)", self.pp_n)
        form_pp_top.addRow("Coeff. perforation Kp (info)", self.pp_Kp)
        form_pp_top.addRow("Surface S (m², info)", self.pp_S)
        ppl.addLayout(form_pp_top); ppl.addWidget(self.lbl_pp_formula); ppl.addWidget(btn_pp_gen); ppl.addWidget(self.pp_tabs)
        self.stack.addWidget(pp_box)

        # ---------- Bandeau Guide (titre + explications dynamiques)
        self.help_title = QLabel(); self.help_title.setStyleSheet("font-weight:600; font-size:14px;")
        self.help_text = QLabel(); self.help_text.setWordWrap(True); self.help_text.setStyleSheet("color:#555;")
        guide_box = QGroupBox("Guide rapide — Débit & ACPH")
        gb_l = QVBoxLayout(guide_box); gb_l.addWidget(self.help_title); gb_l.addWidget(self.help_text)

        # ---------- Sorties (communes)
        self.out_Q = QLabel("—"); self.out_ACPH = QLabel("—"); self.out_window = QLabel("—")
        self.status = QLabel(); set_status_pill(self.status, None)

        # ---------- Boutons (on garde “Calculer”, mais tout est live)
        btn_calc = QPushButton("Calculer"); btn_calc.clicked.connect(self.recalc)
        btn_save = QPushButton("Enregistrer"); btn_save.clicked.connect(self.on_save)
        btn_th = QPushButton("Seuils…"); btn_th.clicked.connect(self.edit_thresholds)

        # ---------- Layout principal
        root = QVBoxLayout(self)
        head = QFormLayout()
        head.addRow("Débit requis Q (m³/h)", self.Q_req)
        head.addRow("Tolérance ± (%)", self.tol_pct)
        head.addRow("Surface A (m²)", self.A)
        head.addRow("Hauteur H (m)", self.H)
        root.addLayout(head)

        root.addWidget(QLabel("— Mode de mesure —"))
        root.addWidget(self.method)
        root.addWidget(guide_box)
        root.addWidget(self.stack)

        outs = QFormLayout()
        outs.addRow("Q total mesuré (m³/h)", self.out_Q)
        outs.addRow("Fenêtre cible (m³/h)", self.out_window)
        outs.addRow("ACPH (h⁻¹) (info)", self.out_ACPH)
        outs.addRow("Conformité", self.status)
        root.addLayout(outs)

        btns = QHBoxLayout(); btns.addWidget(btn_calc); btns.addWidget(btn_save); btns.addStretch(1); btns.addWidget(btn_th)
        root.addLayout(btns)

        # Init
        self._refresh_thresholds()
        self._build_pitot_table()
        self._build_balo_table()
        self._build_scan_tabs()
        self._build_pp_tabs()

        # Démarrage: pas d’alerte → se mettre sur Balomètre
        self.method.blockSignals(True)
        self.method.setCurrentIndex(1)  # 0=Pitot, 1=Balomètre
        self.method.blockSignals(False)
        self._on_method_change(1)
        self._initialized = True

        # Live recalc sur seuils / géométrie pièce
        self.Q_req.valueChanged.connect(self._recalc_live)
        self.tol_pct.valueChanged.connect(self._recalc_live)
        self.A.valueChanged.connect(self._recalc_live)
        self.H.valueChanged.connect(self._recalc_live)

    # ---------- Thresholds
    def _refresh_thresholds(self):
        pid = self.get_project_id()
        try: self.Q_req.setValue(float(self.db.get_threshold(pid, "ACPH", "Q_requis", "1000") or 1000))
        except: pass
        try: self.tol_pct.setValue(float(self.db.get_threshold(pid, "ACPH", "tol_pct", "0") or 0))
        except: pass

    def edit_thresholds(self):
        w = ThresholdEditor(self.db, self.get_project_id(), "ACPH", ["Q_requis", "tol_pct"])
        w.setWindowModality(Qt.ApplicationModality.ApplicationModal); w.setWindowTitle("Seuils – Débit requis & Tolérance")
        w.show(); self._th_win = w

    # ---------- Small utils
    def _fill_rows(self, table: QTableWidget, n: int, label: str):
        table.blockSignals(True)
        table.setRowCount(0)
        for i in range(n):
            r = table.rowCount(); table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(f"{label} {i+1}"))
            table.setItem(r, 1, QTableWidgetItem(""))
        table.blockSignals(False)

    def _sum_col(self, table: QTableWidget, col: int = 1) -> (float, int):
        total = 0.0; used = 0
        for r in range(table.rowCount()):
            it = table.item(r, col)
            if not it: continue
            raw = (it.text() or "").strip().lower().replace(",", ".")
            raw = raw.replace("m3/h", "").replace("m³/h", "").strip()
            if not raw: continue
            try:
                v = float(raw)
                total += v; used += 1
            except: pass
        return total, used

    # ---------- Build tables / tabs
    def _build_pitot_table(self):
        self._fill_rows(self.tbl_pitot, self.pitot_points.value(), "Point")
        self.recalc()

    def _build_balo_table(self):
        self._fill_rows(self.tbl_balo, self.balo_n.value(), "Diffuseur")
        self.recalc()

    # ---- Balayage Anémo: un Q moyen par onglet ----
    def _build_scan_tabs(self):
        if self._is_scan_jet_rotorique():
            self.scan_tabs.blockSignals(True)
            self.scan_tabs.clear(); self._scan_qspins.clear()
            self.scan_tabs.blockSignals(False)
            self.scan_block.setStyleSheet("color:#b00020; font-weight:bold;")
            self.scan_block.setText("⛔ interdit sur diffuseur rotorique. Choisissez un autre type ou un autre mode.")
            self.scan_tabs.setEnabled(False)
            self.recalc(); return
        else:
            self.scan_block.setText(""); self.scan_tabs.setEnabled(True)

        self._scan_qspins.clear()
        self.scan_tabs.blockSignals(True)
        self.scan_tabs.clear()
        for i in range(self.scan_n.value()):
            tab = QWidget(); lay = QFormLayout(tab)
            sp = QDoubleSpinBox(); sp.setRange(0, 1e9); sp.setDecimals(1); sp.valueChanged.connect(self._recalc_live)
            lay.addRow("Q moyen (m³/h)", sp)
            self._scan_qspins.append(sp)
            self.scan_tabs.addTab(tab, f"Diffuseur {i+1} — 0.0 m³/h")
        self.scan_tabs.blockSignals(False)
        self.recalc()

    def _is_scan_jet_rotorique(self) -> bool:
        return self.scan_type.currentIndex() == 1

    def _on_scan_type(self):
        self._build_scan_tabs(); self._update_help()

    # ---- Point par point: onglets indépendants ----
    def _build_pp_tabs(self):
        self._pp_tabs.clear()
        self.pp_tabs.blockSignals(True)
        self.pp_tabs.clear()
        for i in range(self.pp_n.value()):
            tab = QWidget(); v = QVBoxLayout(tab)

            row = QWidget(); hl = QHBoxLayout(row)
            combo = QComboBox(); combo.addItems(list(self.pp_default_map.keys()))
            spin = QSpinBox(); spin.setRange(1, 500); spin.setValue(self.pp_default_map[combo.currentText()])
            btn = QPushButton("Générer points")
            hl.addWidget(QLabel("Preset")); hl.addWidget(combo)
            hl.addWidget(QLabel("Nb points")); hl.addWidget(spin)
            hl.addStretch(1); hl.addWidget(btn)
            v.addWidget(row)

            tbl = QTableWidget(0, 2); tbl.setHorizontalHeaderLabels(["Point", "Q (m³/h)"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tbl.itemChanged.connect(self._recalc_live)
            v.addWidget(tbl)

            # wiring
            def _regen(_=None, t=tbl, s=spin):
                self._fill_rows(t, s.value(), "Point"); self.recalc()
            btn.clicked.connect(_regen)
            spin.valueChanged.connect(_regen)
            def _preset_changed(_=None, c=combo, s=spin):
                s.setValue(self.pp_default_map.get(c.currentText(), s.value()))
            combo.currentTextChanged.connect(_preset_changed)

            # init
            self._fill_rows(tbl, spin.value(), "Point")

            self._pp_tabs.append({"tbl": tbl, "combo": combo, "spin": spin, "subtotal": 0.0})
            self.pp_tabs.addTab(tab, f"Grille {i+1} — 0.0 m³/h")

        self.pp_tabs.blockSignals(False)
        self.recalc()

    # ---------- Aide/Guide dynamique
    def _update_help(self):
        m = self.method.currentText()
        if "Pitot" in m:
            self.help_title.setText("Mode Pitot — comment saisir correctement")
            self.help_text.setText(
                "• Placez la sonde sur une <b>portion rectiligne</b> de gaine, loin des perturbations (≈ <b>≥7D amont</b>, <b>≥3D aval</b>).<br>"
                "• Saisissez les <b>débits m³/h</b> lus au manomètre (un point par ligne).<br>"
                "• La <b>conformité</b> est évaluée sur la somme vs <b>Q requis ± tol%</b>."
            )
        elif "Balomètre" in m:
            rotor = (self.balo_type.currentIndex() == 1)
            self.help_title.setText("Mode Balomètre — bonnes pratiques")
            self.help_text.setText(
                ("• Sélectionnez le <b>nombre de diffuseurs</b> puis le <b>type</b>.<br>"
                 "• Renseignez le <b>débit m³/h</b> pour chaque diffuseur.<br>") +
                ("• <b>Jet rotorique :</b> vérifiez l’adaptateur, l’étanchéité et le centrage du cône.<br>" if rotor else "") +
                "• La <b>conformité</b> est évaluée sur la somme vs <b>Q requis ± tol%</b>."
            )
        elif "Balayage" in m:
            if self._is_scan_jet_rotorique():
                self.help_title.setText("Mode Balayage — jet rotorique : interdit")
                self.help_text.setText(
                    "• Le balayage anémométrique est <b>interdit</b> sur un diffuseur à <b>jet rotorique</b>.<br>"
                    "• Choisissez un autre type ou changez de mode de mesure."
                )
            else:
                self.help_title.setText("Mode Balayage — un onglet = 1 valeur moyenne")
                self.help_text.setText(
                    "• Choisissez le <b>nombre de diffuseurs</b> (onglets).<br>"
                    "• Saisissez la <b>valeur moyenne Q (m³/h)</b> par diffuseur (pas de points multiples).<br>"
                    "• La <b>conformité</b> est évaluée sur la somme vs <b>Q requis ± tol%</b>."
                )
        else:  # Point par point
            self.help_title.setText("Mode Point par point — grilles indépendantes")
            self.help_text.setText(
                "• Définissez le <b>nombre de grilles</b> (onglets).<br>"
                "• Chaque onglet possède son <b>preset</b> (ex. 6p6, 3p3…) et son <b>nombre de points</b> propre.<br>"
                "• Saisissez les Q (m³/h) par point. Le total additionne toutes les grilles.<br>"
                "• La <b>conformité</b> est évaluée sur la somme vs <b>Q requis ± tol%</b>."
            )

    # ---------- Events
    def _on_method_change(self, idx: int):
        self.stack.setCurrentIndex(idx)
        m = self.method.currentText()
        if self._initialized and "Pitot" in m:
            QMessageBox.information(
                self, "Bonnes pratiques – Pitot",
                "Sélectionnez votre point de mesure sur une <b>portion rectiligne</b> avec au moins <b>≥7D amont</b> et <b>≥3D aval</b>."
            )
        self._update_help(); self.recalc()

    def _on_balo_type(self):
        if self.balo_type.currentIndex() == 1:
            QMessageBox.information(
                self, "Avertissement – Jet rotorique",
                "Diffuseur à jet rotorique : vérifiez l’adaptateur, l’étanchéité et le centrage du cône."
            )
        self._update_help(); self.recalc()

    def _recalc_live(self, *args, **kwargs):
        self.recalc()

    # ---------- Calcul commun (LIVE)
    def recalc(self):
        m = self.method.currentText()
        Q_total = 0.0; used = 0

        if "Pitot" in m:
            Q_total, used = self._sum_col(self.tbl_pitot)

        elif "Balomètre" in m:
            Q_total, used = self._sum_col(self.tbl_balo)

        elif "Balayage" in m:
            if self._is_scan_jet_rotorique():
                self.out_Q.setText("—"); self.out_window.setText("—"); self.out_ACPH.setText("—")
                set_status_pill(self.status, None); return
            for i, sp in enumerate(self._scan_qspins):
                q = sp.value(); Q_total += q
                self.scan_tabs.setTabText(i, f"Diffuseur {i+1} — {q:.1f} m³/h")

        else:  # Point par point: sommer toutes les grilles
            for i, d in enumerate(self._pp_tabs):
                subtotal, u = self._sum_col(d["tbl"]) ; Q_total += subtotal ; used += u
                self.pp_tabs.setTabText(i, f"Grille {i+1} — {subtotal:.1f} m³/h")

        Q_req = self.Q_req.value(); tol = self.tol_pct.value()
        lo = Q_req * (1 - tol/100.0); hi = Q_req * (1 + tol/100.0)
        V = self.A.value() * self.H.value()
        ACPH = (Q_total / V) if V > 0 else 0.0

        self.out_Q.setText(f"{Q_total:.1f}")
        self.out_window.setText(f"[{lo:.1f} ; {hi:.1f}]")
        self.out_ACPH.setText("—" if V <= 0 else f"{ACPH:.2f}")

        ok = None
        if Q_total > 0 or used > 0:
            ok = (Q_total >= lo) and (Q_total <= hi)
        set_status_pill(self.status, ok)

        # enrichir résultat sauvegardé
        scan_vals = [sp.value() for sp in self._scan_qspins] if ("Balayage" in m and not self._is_scan_jet_rotorique()) else []
        pp_tabs_meta = [
            {
                "preset": d["combo"].currentText(),
                "n_points": d["spin"].value(),
                "subtotal_m3h": float(self.pp_tabs.tabText(i).split(" — ")[-1].split(" ")[0]) if self.pp_tabs.count()>i else None
            } for i, d in enumerate(self._pp_tabs)
        ] if "Point par point" in m else []

        self._last_result = {
            "method": m,
            "Q_total_m3h": Q_total,
            "Q_required_m3h": Q_req,
            "tol_pct": tol, "lo": lo, "hi": hi, "ok": ok,
            "room": {"A_m2": self.A.value(), "H_m": self.H.value(), "V_m3": V},
            "balo_type": self.balo_type.currentText() if "Balomètre" in m else "",
            "scan_type": self.scan_type.currentText() if "Balayage" in m else "",
            "scan_info": {"Kp": self.scan_Kp.value(), "S_m2": self.scan_S.value(), "Q_moyens_m3h": scan_vals},
            "pp_info": {"Kp": self.pp_Kp.value(), "S_m2": self.pp_S.value(), "grilles": pp_tabs_meta},
        }

    # ---------- Save
    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Saisissez des valeurs d’abord."); return
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet."); return
        self.db.save_test(pid, "ACPH", self._last_result.get("ok"), {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class DeltaPPage(QWidget):
    """
    Cascade de pressions (ΔP) — version simplifiée, LIVE

    • Colonnes : Local | ΔP (Pa) | Cible (Pa) | Tolérance (%) | OK?
    • Une seule lecture ΔP par local (pas de moyenne).
    • Conformité : OK si ΔP ∈ [Cible*(1−tol%), Cible*(1+tol%)]. (tolérance 0% = strict)
    • Évaluation en direct : la colonne OK? et le statut global se mettent à jour à chaque saisie.
    """

    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id

        # Champs "défaut" (préremplissage des lignes)
        self.default_target = QDoubleSpinBox(); self.default_target.setRange(-500, 500); self.default_target.setDecimals(1)
        self.default_tolpct = QDoubleSpinBox(); self.default_tolpct.setRange(0, 100); self.default_tolpct.setDecimals(1)
        self._refresh_thresholds()

        # Tooltips pour clarifier l'usage
        self.default_target.setToolTip(
            "Cible ΔP (Pa) utilisée pour préremplir la colonne «Cible (Pa)» des nouvelles lignes\n"
            "ou des cases vides quand vous cliquez sur «Appliquer défauts…».")
        self.default_tolpct.setToolTip(
            "Tolérance (%) utilisée pour préremplir la colonne «Tolérance (%)» des nouvelles lignes\n"
            "ou des cases vides quand vous cliquez sur «Appliquer défauts…». (0% = strict)")

        # Guide utilisateur
        guide = QGroupBox("Guide rapide — Cascade ΔP")
        g = QVBoxLayout(guide)
        title = QLabel("Comment saisir et interpréter")
        title.setStyleSheet("font-weight:600;")
        txt = QLabel(
            "• Ajoutez un <b>Local</b> par ligne et saisissez <b>ΔP (Pa)</b> mesuré.<br>"
            "• Les colonnes <b>Cible</b> et <b>Tolérance</b> peuvent être remplies par défaut avec les champs du haut.<br>"
            "• Bouton <b>Appliquer défauts…</b> : ne remplit <u>que</u> les cases vides (vous pouvez personnaliser par local).<br>"
            "• Conformité par local : <i>ΔP</i> doit être dans la fenêtre <i>[Cible ± Tolérance%]</i>.<br>"
            "• L’évaluation est <b>automatique</b> : la colonne <b>OK?</b> et l’indicateur global se mettent à jour à chaque saisie.<br>"
            "• Utilisez <b>Supprimer sélection</b> pour retirer un local."
        )
        txt.setWordWrap(True)
        g.addWidget(title); g.addWidget(txt)

        # Tableau
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Local", "ΔP (Pa)", "Cible (Pa)", "Tolérance (%)", "OK?"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Évaluation live à chaque modif
        self.table.itemChanged.connect(self._recalc_live)

        # Boutons
        b_add = QPushButton("+ Local"); b_add.clicked.connect(self.add_row)
        b_del = QPushButton("Supprimer sélection"); b_del.clicked.connect(self.delete_selected)
        b_fill = QPushButton("Appliquer défauts aux lignes vides"); b_fill.clicked.connect(self.apply_defaults_to_rows)
        b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.on_save)
        b_th = QPushButton("Seuils…"); b_th.clicked.connect(self.edit_thresholds)

        # Statut global
        self.status = QLabel(); set_status_pill(self.status, None)

        # Layout
        lay = QVBoxLayout(self)
        f = QFormLayout()
        f.addRow("Cible par défaut (Pa)", self.default_target)
        f.addRow("Tolérance par défaut (%)", self.default_tolpct)
        lay.addLayout(f)
        lay.addWidget(guide)
        lay.addWidget(self.table)

        btns = QHBoxLayout()
        btns.addWidget(b_add); btns.addWidget(b_del); btns.addWidget(b_fill)
        btns.addStretch(1); btns.addWidget(b_save); btns.addWidget(b_th)
        lay.addLayout(btns)
        lay.addWidget(self.status)

        # Réactivité des champs défauts (remplit les vides + recalc)
        self.default_target.valueChanged.connect(self._on_defaults_changed)
        self.default_tolpct.valueChanged.connect(self._on_defaults_changed)

        # Deux exemples de lignes pour démarrer
        self.add_row("Local A")
        self.add_row("Local B")
        self.recalc()  # premier calcul

    # -------- seuils par défaut (stockés en DB)
    def _refresh_thresholds(self):
        pid = self.get_project_id()
        try:
            self.default_target.setValue(float(self.db.get_threshold(pid, "DeltaP", "deltaP_cible", "15") or 15))
        except:
            pass
        try:
            self.default_tolpct.setValue(float(self.db.get_threshold(pid, "DeltaP", "tol_pct_default", "10") or 10))
        except:
            pass

    def edit_thresholds(self):
        # Permet d’éditer les 2 clés utilisées : deltaP_cible (Pa) et tol_pct_default (%)
        w = ThresholdEditor(self.db, self.get_project_id(), "DeltaP", ["deltaP_cible", "tol_pct_default"])
        w.setWindowModality(Qt.ApplicationModal)
        w.setWindowTitle("Seuils – ΔP (défauts)")
        w.show()
        self._th_win = w

    # -------- gestion du tableau
    def add_row(self, local_name: Optional[str] = None):
        r = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(local_name or f"Local {r+1}"))
        self.table.setItem(r, 1, QTableWidgetItem(""))  # ΔP mesuré (Pa)
        self.table.setItem(r, 2, QTableWidgetItem(f"{self.default_target.value():.1f}"))
        self.table.setItem(r, 3, QTableWidgetItem(f"{self.default_tolpct.value():.1f}"))
        self.table.setItem(r, 4, QTableWidgetItem("—"))
        self.table.blockSignals(False)
        self.recalc()

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self.table.blockSignals(True)
        for r in rows:
            self.table.removeRow(r)
        self.table.blockSignals(False)
        self.recalc()

    def apply_defaults_to_rows(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            # Cible
            it = self.table.item(r, 2)
            if not it or not (it.text() or "").strip():
                self.table.setItem(r, 2, QTableWidgetItem(f"{self.default_target.value():.1f}"))
            # Tolérance
            it2 = self.table.item(r, 3)
            if not it2 or not (it2.text() or "").strip():
                self.table.setItem(r, 3, QTableWidgetItem(f"{self.default_tolpct.value():.1f}"))
        self.table.blockSignals(False)
        self.recalc()

    def _on_defaults_changed(self):
        # Remplit seulement les cases vides + recalc live
        self.apply_defaults_to_rows()

    # -------- utilitaires
    def _cell_float(self, r: int, c: int) -> Optional[float]:
        it = self.table.item(r, c)
        if not it:
            return None
        raw = (it.text() or "").strip().lower().replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except:
            return None

    def _set_ok_cell(self, r: int, text: str, tooltip: str = ""):
        self.table.blockSignals(True)
        item = QTableWidgetItem(text)
        if tooltip:
            item.setToolTip(tooltip)
        self.table.setItem(r, 4, item)
        self.table.blockSignals(False)

    # -------- calcul (LIVE)
    def _recalc_live(self, *args, **kwargs):
        self.recalc()

    def recalc(self):
        results = []
        has_false = False
        has_none = False

        for r in range(self.table.rowCount()):
            local = (self.table.item(r, 0).text() if self.table.item(r, 0) else f"Local {r+1}").strip()
            dp = self._cell_float(r, 1)
            target = self._cell_float(r, 2)
            tol = self._cell_float(r, 3)

            if dp is None or target is None or tol is None:
                self._set_ok_cell(r, "—", "Saisir ΔP, Cible et Tolérance pour évaluer.")
                has_none = True
                results.append({"local": local, "deltaP_Pa": dp, "target_Pa": target, "tol_pct": tol, "ok": None})
                continue

            lo = target * (1 - tol/100.0)
            hi = target * (1 + tol/100.0)
            ok = (dp >= lo) and (dp <= hi)

            tip = f"Plage acceptable : [{lo:.1f} ; {hi:.1f}] Pa"
            self._set_ok_cell(r, "OK" if ok else "NON", tip)
            results.append({"local": local, "deltaP_Pa": dp, "target_Pa": target, "tol_pct": tol, "ok": ok})
            if ok is False:
                has_false = True

        if self.table.rowCount() == 0:
            ok_global = None
        elif has_false:
            ok_global = False
        elif has_none:
            ok_global = None
        else:
            ok_global = True

        set_status_pill(self.status, ok_global)
        self._last_result = {"locals": results, "conforme": ok_global}

    # -------- enregistrement
    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Saisissez au moins une ligne complète.")
            return
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return
        self.db.save_test(pid, "DeltaP", self._last_result.get("conforme"), {"note": "cascade_simple_live"}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")



class UniformityPage(QWidget):
    """Vitesses sous filtres – Uniformité
PSEUDOCODE:
Given v_ms[] → v̄, v_min, v_max, uniformité = ((v_max−v_min)/v̄)*100
conforme if uniformité ≤ seuil_uniformite
"""
    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db; self.get_project_id = get_project_id
        self.v_ms = QPlainTextEdit(); self.v_ms.setPlaceholderText("v (m/s) list…")
        self.seuil = QDoubleSpinBox(); self.seuil.setRange(0, 1000); self.seuil.setDecimals(1)
        self.out_vbar = QLabel("—"); self.out_vmin = QLabel("—"); self.out_vmax = QLabel("—"); self.out_uni = QLabel("—")
        self.status = QLabel(); set_status_pill(self.status, None)

        lay = QVBoxLayout(self)
        f = QFormLayout(); f.addRow("v (m/s) – liste", self.v_ms); f.addRow("Seuil uniformité (%)", self.seuil)
        lay.addLayout(f)
        out = QFormLayout(); out.addRow("v̄ (m/s)", self.out_vbar); out.addRow("v_min", self.out_vmin); out.addRow("v_max", self.out_vmax); out.addRow("Uniformité (%)", self.out_uni)
        lay.addLayout(out)
        btns = QHBoxLayout(); b_calc = QPushButton("Calculer"); b_calc.clicked.connect(self.on_calc); b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.on_save); b_th = QPushButton("Seuils…"); b_th.clicked.connect(self.edit_thresholds)
        btns.addWidget(b_calc); btns.addWidget(b_save); btns.addStretch(1); btns.addWidget(b_th)
        lay.addLayout(btns); lay.addWidget(self.status)
        self._refresh_thresholds()

    def _refresh_thresholds(self):
        pid = self.get_project_id()
        v = self.db.get_threshold(pid, "Uniformity", "seuil_uniformite", "20")
        try: self.seuil.setValue(float(v))
        except: pass

    def edit_thresholds(self):
        w = ThresholdEditor(self.db, self.get_project_id(), "Uniformity", ["seuil_uniformite"])
        w.setWindowModality(Qt.ApplicationModal); w.setWindowTitle("Seuils – Uniformité")
        w.show(); self._th_win = w

    def on_calc(self):
        v = parse_floats(self.v_ms.toPlainText())
        if not v:
            QMessageBox.warning(self, "Entrées", "Liste de vitesses vide.")
            return
        vbar = stats.mean(v); vmin = min(v); vmax = max(v)
        uni = ((vmax - vmin) / vbar * 100.0) if vbar > 0 else float("inf")
        ok = uni <= self.seuil.value()
        self.out_vbar.setText(f"{vbar:.3f}"); self.out_vmin.setText(f"{vmin:.3f}"); self.out_vmax.setText(f"{vmax:.3f}"); self.out_uni.setText(f"{uni:.1f}")
        set_status_pill(self.status, ok)
        self._last_result = {"vbar": vbar, "vmin": vmin, "vmax": vmax, "uniformite_pct": uni, "seuil": self.seuil.value(), "conforme": ok}

    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Calculez d’abord.")
            return
        pid = self.get_project_id()
        pid = sel
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return
        self.db.save_test(pid, "Uniformity", self._last_result.get("conforme"), {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class HEPALeakPage(QWidget):
    """Intégrité filtres HEPA (leak test) – version simplifiée & live

    LOGIQUE
    -------
    • Sélectionner le type de filtre : 
        - H10  → seuil = 5.00 %
        - H13/H14/U15/U16/U17 → seuil = 0.01 %
    • Entrer directement, pour chaque diffuseur, la fuite mesurée en % (valeur max relevée).
    • Conformité par diffuseur : fuite_mesurée ≤ seuil(type).
    • Conformité globale : OK si tous les diffuseurs saisis sont OK (None si aucune valeur saisie).

    NOTES
    -----
    • “Signal amont (réf)” est conservé pour la traçabilité, il n’entre pas dans le calcul puisque
      la saisie se fait déjà en pourcentage.
    """

    THRESHOLDS = {
        "H10": 5.00,
        "H13": 0.01,
        "H14": 0.01,
        "U15": 0.01,
        "U16": 0.01,
        "U17": 0.01,
    }

    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self._updating = False  # garde-fou contre les boucles itemChanged

        # --- Guide / Aide ---
        guide = QGroupBox("Comment utiliser – HEPA Leak (simplifié)")
        gl = QVBoxLayout(guide)
        lbl = QLabel(
            "1) Choisir le type de filtre (le seuil s'applique automatiquement : H10=5 %, autres=0,01 %).\n"
            "2) Indiquer le nombre de diffuseurs puis saisir la fuite mesurée (%) par diffuseur.\n"
            "3) Les colonnes « Seuil » et « OK? » se mettent à jour automatiquement (sans bouton Calculer).\n"
            "4) « Signal amont (réf) » est stocké pour la traçabilité ; il n'entre pas dans le calcul."
        )
        lbl.setWordWrap(True)
        gl.addWidget(lbl)

        # --- Entrées hautes ---
        self.filter_type = QComboBox()
        self.filter_type.addItems(["H10", "H13", "H14", "U15", "U16", "U17"])

        self.signal_up = QDoubleSpinBox()
        self.signal_up.setRange(0, 1e12)
        self.signal_up.setDecimals(3)
        self.signal_up.setValue(100.0)
        self.signal_up.setToolTip("Traçabilité uniquement (non utilisé pour les calculs ici).")

        self.n_diff = QSpinBox()
        self.n_diff.setRange(1, 500)
        self.n_diff.setValue(2)
        self.n_diff.setToolTip("Crée ou ajuste automatiquement le nombre de lignes Diffuseur.")

        top_form = QFormLayout()
        top_form.addRow("Type de filtre", self.filter_type)
        top_form.addRow("Signal amont (réf)", self.signal_up)
        top_form.addRow("Nombre de diffuseurs", self.n_diff)

        # --- Tableau des mesures ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Diffuseur", "Fuite mesurée (%)", "Seuil (%)", "OK?"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # --- Boutons d'édition lignes ---
        b_add = QPushButton("+ Diffuseur")
        b_add.clicked.connect(self.add_row)
        b_del = QPushButton("Supprimer sélection")
        b_del.clicked.connect(self.delete_selected)

        # --- Statut global & résumé ---
        self.status = QLabel()
        set_status_pill(self.status, None)
        self.lbl_worst = QLabel("Pire fuite : — %")

        # --- Actions bas ---
        b_save = QPushButton("Enregistrer")
        b_save.clicked.connect(self.on_save)

        # --- Layout principal ---
        root = QVBoxLayout(self)
        root.addWidget(guide)
        row_top = QWidget(); row_top.setLayout(top_form)
        root.addWidget(row_top)
        root.addWidget(self.table)

        row_btns = QHBoxLayout()
        row_btns.addWidget(b_add)
        row_btns.addWidget(b_del)
        row_btns.addStretch(1)
        row_btns.addWidget(self.lbl_worst)
        row_btns.addWidget(self.status)
        row_btns.addWidget(b_save)
        root.addLayout(row_btns)

        # Connexions pour évaluation LIVE
        self.filter_type.currentTextChanged.connect(self.rebuild_thresholds_and_eval)
        self.n_diff.valueChanged.connect(self.sync_rows_to_count)
        self.table.itemChanged.connect(self._on_item_changed)

        # Initialisation : 2 lignes
        self.sync_rows_to_count()

    # ------------------ Helpers UI & table ------------------

    def _current_threshold(self) -> float:
        return self.THRESHOLDS.get(self.filter_type.currentText(), 0.01)

    def add_row(self, name: Optional[str] = None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._updating = True
        try:
            self.table.setItem(r, 0, QTableWidgetItem(name or f"Diffuseur {r+1}"))
            self.table.setItem(r, 1, QTableWidgetItem(""))  # Fuite mesurée (%)
            self.table.setItem(r, 2, QTableWidgetItem(f"{self._current_threshold():.4f}"))  # Seuil (%)
            self.table.setItem(r, 3, QTableWidgetItem("—"))  # OK?
        finally:
            self._updating = False
        self.evaluate_live()

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self.table.removeRow(r)
        # Renommer les diffuseurs restants proprement
        self._updating = True
        try:
            for i in range(self.table.rowCount()):
                it0 = self.table.item(i, 0)
                if not it0 or not (it0.text() or "").strip():
                    self.table.setItem(i, 0, QTableWidgetItem(f"Diffuseur {i+1}"))
        finally:
            self._updating = False
        self.evaluate_live()

    def sync_rows_to_count(self):
        """Ajuste le nombre de lignes au QSpinBox (ajoute ou coupe)."""
        target = self.n_diff.value()
        cur = self.table.rowCount()
        if target > cur:
            for _ in range(target - cur):
                self.add_row()
        elif target < cur:
            self._updating = True
            try:
                for _ in range(cur - target):
                    self.table.removeRow(self.table.rowCount() - 1)
            finally:
                self._updating = False
            self.evaluate_live()
        else:
            # même nombre → juste mettre à jour le seuil affiché
            self.rebuild_thresholds_and_eval()

    def _cell_float(self, r: int, c: int) -> Optional[float]:
        it = self.table.item(r, c)
        if not it:
            return None
        raw = (it.text() or "").strip()
        if not raw:
            return None
        try:
            return float(raw.replace(",", "."))
        except Exception:
            return None

    # ------------------ LIVE evaluate ------------------

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating:
            return
        # On ne réagit qu'aux changements de la colonne "Fuite mesurée (%)"
        if item.column() == 1:
            self.evaluate_live()

    def rebuild_thresholds_and_eval(self):
        """Quand on change le type de filtre → met à jour la colonne Seuil et recalcule."""
        thr = self._current_threshold()
        self._updating = True
        try:
            for r in range(self.table.rowCount()):
                self.table.setItem(r, 2, QTableWidgetItem(f"{thr:.4f}"))
        finally:
            self._updating = False
        self.evaluate_live()

    def evaluate_live(self):
        """Met à jour OK? ligne par ligne + statut global + pire fuite, en direct."""
        thr = self._current_threshold()
        oks: List[bool] = []
        worst = None

        self._updating = True
        try:
            for r in range(self.table.rowCount()):
                meas = self._cell_float(r, 1)  # %
                # Met à jour la colonne seuil au cas où (sécurité)
                self.table.setItem(r, 2, QTableWidgetItem(f"{thr:.4f}"))
                if meas is None:
                    self.table.setItem(r, 3, QTableWidgetItem("—"))
                    continue
                ok = (meas <= thr)
                oks.append(ok)
                self.table.setItem(r, 3, QTableWidgetItem("OK" if ok else "NON"))
                worst = meas if (worst is None or (meas is not None and meas > worst)) else worst
        finally:
            self._updating = False

        # Statut global : None si aucune valeur saisie
        ok_global = (all(oks) if oks else None)
        set_status_pill(self.status, ok_global)
        self.lbl_worst.setText("Pire fuite : " + ("— %" if worst is None else f"{worst:.4f} %"))

        # Prépare _last_result pour un enregistrement immédiat si besoin
        positions = []
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text() if self.table.item(r, 0) else f"Diffuseur {r+1}"
            meas = self._cell_float(r, 1)
            positions.append({
                "diffuseur": name,
                "fuite_pct": meas,
                "seuil_pct": thr,
                "ok": (None if meas is None else meas <= thr)
            })
        self._last_result = {
            "filter_type": self.filter_type.currentText(),
            "seuil_pct": thr,
            "signal_amont_ref": self.signal_up.value(),
            "positions": positions,
            "worst_pct": (None if worst is None else float(worst)),
            "conforme": ok_global
        }

    # ------------------ Save ------------------

    def on_save(self):
        # s'il n'y a aucune valeur saisie → prévenir
        has_value = any(self._cell_float(r, 1) is not None for r in range(self.table.rowCount()))
        if not has_value:
            QMessageBox.information(self, "Info", "Saisissez au moins une fuite (%) avant d'enregistrer.")
            return

        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez d’abord un projet.")
            return

        self.evaluate_live()  # assure _last_result à jour
        self.db.save_test(pid, "HEPA_Leak", self._last_result.get("conforme"), {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class ParticleClassPage(QWidget):
    """Comptage particulaire en air (classification)
PSEUDOCODE (simplified):
1) N_pos = provided else ceil(sqrt(A_m2))  [fallback]
2) C_min = min(limites)
   Vs_L = (20 / C_min) * 1000 ; t_sec = ceil(Vs_L / débit_Lmin * 60)
3) For each position p and size m: conc = (comptes_pm / Vs_L) * 1000 ≤ limite[m] ? OK
Global OK if all positions OK for all sizes.
"""
    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db; self.get_project_id = get_project_id
        self.A = QDoubleSpinBox(); self.A.setRange(0, 1e6); self.A.setDecimals(2)
        self.sizes = QLineEdit(); self.sizes.setPlaceholderText("Tailles (µm), ex: 0.5, 5.0")
        self.limites = QPlainTextEdit(); self.limites.setPlaceholderText("Limites taille→part/m³, ex: 0.5=352000; 5.0=2900")
        self.debit = QDoubleSpinBox(); self.debit.setRange(0.1, 1000); self.debit.setDecimals(1)
        self.Npos = QSpinBox(); self.Npos.setRange(0, 999); self.Npos.setValue(0)
        self.out_Vs = QLabel("—"); self.out_t = QLabel("—")
        self.table = QTableWidget(0, 0)  # dynamic grid counts
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.status = QLabel(); set_status_pill(self.status, None)

        lay = QVBoxLayout(self)
        f = QFormLayout()
        f.addRow("Surface A (m²)", self.A)
        f.addRow("Tailles (µm)", self.sizes)
        f.addRow("Limites (taille=limite; …)", self.limites)
        f.addRow("Débit OPC (L/min)", self.debit)
        f.addRow("N positions (0 = auto)", self.Npos)
        lay.addLayout(f)
        out = QFormLayout(); out.addRow("Vs (L)", self.out_Vs); out.addRow("Durée par pos (s)", self.out_t)
        lay.addLayout(out)

        btns = QHBoxLayout()
        b_build = QPushButton("Construire la grille")
        b_build.clicked.connect(self.build_grid)
        b_calc = QPushButton("Évaluer")
        b_calc.clicked.connect(self.on_calc)
        b_save = QPushButton("Enregistrer")
        b_save.clicked.connect(self.on_save)
        btns.addWidget(b_build); btns.addStretch(1); btns.addWidget(b_calc); btns.addWidget(b_save)
        lay.addLayout(btns)
        lay.addWidget(self.table)
        lay.addWidget(self.status)
        self._refresh_thresholds()

    def _refresh_thresholds(self):
        pid = self.get_project_id()
        deb = self.db.get_threshold(pid, "Particle_Class", "debit_OPC_Lmin", "28.3")
        try: self.debit.setValue(float(deb))
        except: pass

    def _parse_limits(self) -> Dict[float, float]:
        d: Dict[float, float] = {}
        text = self.limites.toPlainText().strip()
        if not text:
            return d
        # Accept lines or ; separated "size=limit"
        text = text.replace("\n", ";")
        for part in text.split(";"):
            if not part.strip():
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    size = float(k.strip().replace(",", "."))
                    lim = float(v.strip().replace(",", "."))
                    d[size] = lim
                except ValueError:
                    pass
        return d

    def build_grid(self):
        sizes = [float(s.strip().replace(",", ".")) for s in self.sizes.text().split(",") if s.strip()]
        limits = self._parse_limits()
        if not sizes or not limits:
            QMessageBox.warning(self, "Entrées", "Renseignez tailles et limites.")
            return
        if any(s not in limits for s in sizes):
            QMessageBox.warning(self, "Entrées", "Chaque taille doit avoir une limite.")
            return
        A = self.A.value()
        Npos = self.Npos.value() or math.ceil(math.sqrt(A)) if A > 0 else 1
        Cmin = min(limits[s] for s in sizes)
        Vs_L = (20.0 / Cmin) * 1000.0
        t_sec = math.ceil((Vs_L / self.debit.value()) * 60.0)
        self.out_Vs.setText(f"{Vs_L:.1f}"); self.out_t.setText(str(int(t_sec)))
        # Build table: rows = positions, columns = counts per size
        self.table.clear()
        headers = [f"Pos"] + [f"Counts @ {s} µm" for s in sizes]
        self.table.setColumnCount(1 + len(sizes))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(Npos)
        for r in range(Npos):
            self.table.setItem(r, 0, QTableWidgetItem(str(r+1)))
            for j in range(len(sizes)):
                self.table.setItem(r, 1+j, QTableWidgetItem(""))
        # Cache for calc
        self._grid_meta = {"sizes": sizes, "limits": limits, "Vs_L": Vs_L, "t_sec": t_sec}

    def on_calc(self):
        if not hasattr(self, "_grid_meta"):
            QMessageBox.information(self, "Info", "Construisez la grille d’abord.")
            return
        sizes = self._grid_meta["sizes"]; limits = self._grid_meta["limits"]; Vs_L = self._grid_meta["Vs_L"]
        Npos = self.table.rowCount()
        ok_all = True
        pos_results = []
        for r in range(Npos):
            pos_ok = True
            size_results = []
            for j, s in enumerate(sizes):
                txt = self.table.item(r, 1+j).text() if self.table.item(r, 1+j) else "0"
                try: counts = float(txt.replace(",", "."))
                except: counts = 0.0
                conc = (counts / Vs_L) * 1000.0  # part/m³
                ok = conc <= limits[s]
                if not ok:
                    pos_ok = False
                    ok_all = False
                size_results.append({"size_um": s, "counts": counts, "conc_part_m3": conc, "limit": limits[s], "ok": ok})
            pos_results.append({"position": r+1, "ok": pos_ok, "sizes": size_results})
        set_status_pill(self.status, ok_all)
        self._last_result = {
            "Vs_L": self._grid_meta["Vs_L"],
            "t_sec": self._grid_meta["t_sec"],
            "positions": pos_results,
            "conforme": ok_all
        }

    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Évaluez d’abord.")
            return
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return
        params = {
            "A_m2": self.A.value(),
            "sizes": self._grid_meta.get("sizes", []) if hasattr(self, "_grid_meta") else [],
            "limits": self._grid_meta.get("limits", {}) if hasattr(self, "_grid_meta") else {},
            "debit_Lmin": self.debit.value(),
        }
        self.db.save_test(pid, "Particle_Class", self._last_result.get("conforme"), params, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class RecoveryPage(QWidget):
    """Recovery time (100:1)
PSEUDOCODE:
Find first t where C(t) ≤ C_cible ; t_recovery_min = t/60. If t_max provided: conforme = t_recovery_min ≤ t_max
"""
    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db; self.get_project_id = get_project_id
        self.Ccible = QDoubleSpinBox(); self.Ccible.setRange(0, 1e12); self.Ccible.setDecimals(1)
        self.tmax = QDoubleSpinBox(); self.tmax.setRange(0, 1000); self.tmax.setDecimals(0)
        self.series = QPlainTextEdit(); self.series.setPlaceholderText("t_sec, C\n120, 4000\n180, 3000\n…")
        self.out_t = QLabel("—")
        self.status = QLabel(); set_status_pill(self.status, None)

        lay = QVBoxLayout(self)
        f = QFormLayout(); f.addRow("Cible C (part/m³)", self.Ccible); f.addRow("Seuil t_max (min)", self.tmax); f.addRow("Série t,C", self.series)
        lay.addLayout(f)
        out = QFormLayout(); out.addRow("t_recovery (min)", self.out_t)
        lay.addLayout(out)
        btns = QHBoxLayout(); b_calc = QPushButton("Calculer"); b_calc.clicked.connect(self.on_calc); b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.on_save)
        btns.addWidget(b_calc); btns.addWidget(b_save)
        lay.addLayout(btns); lay.addWidget(self.status)
        self._refresh_thresholds()

    def _refresh_thresholds(self):
        pid = self.get_project_id()
        tmax = self.db.get_threshold(pid, "Recovery_Time", "t_max_cible_min", "20")
        try: self.tmax.setValue(float(tmax))
        except: pass

    def on_calc(self):
        Cc = self.Ccible.value()
        pairs = []
        for line in self.series.toPlainText().splitlines():
            if "," in line:
                t, c = line.split(",", 1)
            elif "\t" in line:
                t, c = line.split("\t", 1)
            else:
                parts = line.split()
                if len(parts) != 2:
                    continue
                t, c = parts
            try:
                t = float(t.strip()); c = float(c.strip())
            except:
                continue
            pairs.append((t, c))
        pairs.sort(key=lambda x: x[0])
        t_hit = None
        for t, c in pairs:
            if c <= Cc:
                t_hit = t; break
        trec_min = (t_hit / 60.0) if t_hit is not None else None
        self.out_t.setText("—" if trec_min is None else f"{trec_min:.1f}")
        ok = None
        if trec_min is not None:
            ok = trec_min <= self.tmax.value()
        set_status_pill(self.status, ok)
        self._last_result = {"t_recovery_min": trec_min, "C_cible": Cc, "t_max": self.tmax.value(), "conforme": ok}

    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Calculez d’abord.")
            return
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return
        self.db.save_test(pid, "Recovery_Time", self._last_result.get("conforme"), {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class SmokePage(QWidget):
    """
    Visualisation de flux (fumée) – version simple & élégante (pilotée par le technicien)

    LOGIQUE
    -------
    • Le technicien saisit 1 ligne par scène/prise :
        - ID du film (référence vidéo/photo),
        - Zone/Scénario (ex: SAS, Porte ouverte, Poste A…),
        - Coche les observations : Effet piston / Pas de stagnation / Reflux observé / Extraction & pulsion OK,
        - Choisit la Conformité : — / Conforme / Non conforme,
        - Le "Descriptif" est généré automatiquement à partir des cases (modifiable via "Commentaire" si besoin).
    • La pastille globale se met à jour en LIVE :
        - Verte si toutes les lignes saisies sont "Conforme",
        - Rouge si au moins une ligne est "Non conforme",
        - Tiret (—) s’il n’y a pas encore de choix de conformité.

    CONSEIL
    -------
    - "Effet piston" = flux dirigé vers l’extraction lors des ouvertures (pas de reflux).
    - "Pas de stagnation" = pas de zones mortes visibles.
    - "Reflux observé" = retour de fumée vers zones propres (si coché, vérifier la conformité).
    - "Extraction & pulsion OK" = captation et soufflage visuellement efficaces.
    """

    def __init__(self, db: DB, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self._updating = False  # évite les boucles itemChanged

        # --- Guide / Aide ---
        guide = QGroupBox("Comment utiliser – Visualisation de flux (fumée)")
        gl = QVBoxLayout(guide)
        lbl = QLabel(
            "1) Ajoutez une ligne par scène/prise et renseignez l'ID du film et la zone.\n"
            "2) Cochez les observations pertinentes (effet piston, stagnation, reflux, extraction/pulsion).\n"
            "3) Sélectionnez la conformité (Conforme / Non conforme). Le descriptif auto s’actualise.\n"
            "4) La pastille globale s’actualise en direct. Cliquez « Enregistrer » pour sauvegarder."
        )
        lbl.setWordWrap(True)
        gl.addWidget(lbl)

        # --- Tableau ---
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID Film", "Zone/Scénario",
            "Effet piston", "Pas de stagnation", "Reflux observé", "Extraction & pulsion OK",
            "Conformité", "Descriptif (auto)", "Commentaire"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        # --- Boutons de gestion lignes ---
        b_add = QPushButton("+ Ligne"); b_add.clicked.connect(self.add_row)
        b_del = QPushButton("Supprimer sélection"); b_del.clicked.connect(self.delete_selected)

        # --- Statut global & actions ---
        self.status = QLabel(); set_status_pill(self.status, None)
        b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.on_save)

        # --- Layout principal ---
        lay = QVBoxLayout(self)
        lay.addWidget(guide)
        lay.addWidget(self.table)

        row_buttons = QHBoxLayout()
        row_buttons.addWidget(b_add); row_buttons.addWidget(b_del)
        row_buttons.addStretch(1)
        row_buttons.addWidget(self.status); row_buttons.addWidget(b_save)
        lay.addLayout(row_buttons)

        # LIVE updates
        self.table.itemChanged.connect(self._on_item_changed)

        # Quelques exemples de départ
        self.add_row("F-001", "Porte fermée")
        self.add_row("F-002", "Porte ouverte")

    # ---------- Helpers UI ----------
    def _make_checkbox_item(self, checked: bool = False) -> QTableWidgetItem:
        it = QTableWidgetItem()
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        it.setText("")  # pas de texte, juste la case
        return it

    def _combo_conformite(self) -> QComboBox:
        cb = QComboBox()
        cb.addItems(["—", "Conforme", "Non conforme"])
        cb.currentTextChanged.connect(self.evaluate_live)
        return cb

    def add_row(self, film_id: Optional[str] = None, zone: Optional[str] = None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._updating = True
        try:
            # ID Film
            self.table.setItem(r, 0, QTableWidgetItem(film_id or f"F-{r+1:03d}"))
            # Zone / Scénario
            self.table.setItem(r, 1, QTableWidgetItem(zone or ""))

            # Cases à cocher
            self.table.setItem(r, 2, self._make_checkbox_item(checked=True))   # Effet piston (par défaut True)
            self.table.setItem(r, 3, self._make_checkbox_item(checked=True))   # Pas de stagnation (True)
            self.table.setItem(r, 4, self._make_checkbox_item(checked=False))  # Reflux observé (False)
            self.table.setItem(r, 5, self._make_checkbox_item(checked=True))   # Extraction & pulsion OK (True)

            # Conformité (combobox)
            cb = self._combo_conformite()
            self.table.setCellWidget(r, 6, cb)

            # Descriptif auto (read-only)
            desc = QTableWidgetItem("—")
            desc.setFlags(desc.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 7, desc)

            # Commentaire libre
            self.table.setItem(r, 8, QTableWidgetItem(""))

            # Première génération du descriptif
            self._update_row_descriptif(r)
        finally:
            self._updating = False

        self.evaluate_live()

    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self.evaluate_live()

    def _is_checked(self, r: int, c: int) -> Optional[bool]:
        it = self.table.item(r, c)
        if not it:
            return None
        return it.checkState() == Qt.Checked

    def _conformite_text(self, r: int) -> str:
        w = self.table.cellWidget(r, 6)
        if isinstance(w, QComboBox):
            return w.currentText()
        return "—"

    def _update_row_descriptif(self, r: int):
        eff_piston = self._is_checked(r, 2)
        no_stag    = self._is_checked(r, 3)
        reflux     = self._is_checked(r, 4)
        ep_ok      = self._is_checked(r, 5)

        phrases = []
        if eff_piston is True:
            phrases.append("Effet piston observé")
        elif eff_piston is False:
            phrases.append("Effet piston non démontré")

        if no_stag is True:
            phrases.append("Pas de stagnation")
        elif no_stag is False:
            phrases.append("Stagnations visibles")

        if reflux is True:
            phrases.append("Reflux observé")
        elif reflux is False:
            phrases.append("Pas de reflux")

        if ep_ok is True:
            phrases.append("Extraction & pulsion fonctionnelles")
        elif ep_ok is False:
            phrases.append("Anomalie extraction/pulsion")

        text = " ; ".join(phrases) if phrases else "—"
        self._updating = True
        try:
            self.table.setItem(r, 7, QTableWidgetItem(text))
        finally:
            self._updating = False

    # ---------- LIVE evaluation ----------
    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating:
            return
        # Toute modif d'une case (2..5) ou d'un champ texte (0,1,8) regénère le descriptif & statut global
        if item.column() in (2, 3, 4, 5):
            self._update_row_descriptif(item.row())
        self.evaluate_live()

    def evaluate_live(self):
        """Met à jour la pastille globale en fonction des choix de conformité."""
        oks = []
        for r in range(self.table.rowCount()):
            conf = self._conformite_text(r)
            if conf == "Conforme":
                oks.append(True)
            elif conf == "Non conforme":
                oks.append(False)
            # "—" = pas de vote, on ignore

        ok_global = (None if not oks else all(oks))
        set_status_pill(self.status, ok_global)

    # ---------- Save ----------
    def on_save(self):
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez d’abord un projet.")
            return

        # Construire le payload
        rows = []
        for r in range(self.table.rowCount()):
            row = {
                "film_id": self.table.item(r, 0).text() if self.table.item(r, 0) else "",
                "zone": self.table.item(r, 1).text() if self.table.item(r, 1) else "",
                "effet_piston": self._is_checked(r, 2),
                "pas_de_stagnation": self._is_checked(r, 3),
                "reflux_observe": self._is_checked(r, 4),
                "extraction_pulsion_ok": self._is_checked(r, 5),
                "conformite": self._conformite_text(r),
                "descriptif_auto": self.table.item(r, 7).text() if self.table.item(r, 7) else "",
                "commentaire": self.table.item(r, 8).text() if self.table.item(r, 8) else "",
            }
            rows.append(row)

        # Déterminer la conformité globale (mêmes règles que le live)
        oks = [r["conformite"] == "Conforme" for r in rows if r["conformite"] in ("Conforme", "Non conforme")]
        ok_global = (None if not oks else all(oks))

        result = {
            "scenes": rows,
            "conforme": ok_global
        }

        self.db.save_test(pid, "Smoke_Visual", ok_global, {}, result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")

class TempRHPage(QWidget):
    """
    Température & Humidité — saisie simple, évaluation en direct

    Utilisation (guide rapide) :
    1) Vérifiez/ajustez les seuils projet : Tmin/Tmax (°C), RHmin/RHmax (%).
    2) Ajoutez des points (Poste A, Poste B, …).
    3) Pour chaque point, cliquez « ➕ Lecture », entrez T et RH. Répétez autant que nécessaire.
    4) La conformité est calculée automatiquement : OK si 0 % des lectures hors limites (T et RH).
       Le statut global passe au vert uniquement si tous les points saisis sont OK.
    """

    COLS = ["Point", "Lectures", "T_min", "T_max", "T_moy", "RH_min", "RH_max", "RH_moy", "%T hors", "%RH hors", "OK?", "Actions"]

    def __init__(self, db, get_project_id):
        super().__init__()
        self.db = db; self.get_project_id = get_project_id

        # --- Seuils (avec tips)
        self.Tmin = QDoubleSpinBox(); self.Tmin.setRange(-100, 200); self.Tmin.setDecimals(1)
        self.Tmax = QDoubleSpinBox(); self.Tmax.setRange(-100, 200); self.Tmax.setDecimals(1)
        self.RHmin = QDoubleSpinBox(); self.RHmin.setRange(0, 100);  self.RHmin.setDecimals(1)
        self.RHmax = QDoubleSpinBox(); self.RHmax.setRange(0, 100);  self.RHmax.setDecimals(1)
        self._refresh_thresholds()

        self.Tmin.setToolTip("Température minimale acceptée (°C)")
        self.Tmax.setToolTip("Température maximale acceptée (°C)")
        self.RHmin.setToolTip("Humidité relative minimale acceptée (%)")
        self.RHmax.setToolTip("Humidité relative maximale acceptée (%)")

        # Guide
        guide = QGroupBox("Comment utiliser (30s)")
        gtxt = QLabel(
            "• Définissez les limites projet (T et RH).\n"
            "• Ajoutez vos points. Cliquez « ➕ Lecture » pour saisir une mesure T/RH.\n"
            "• Les min/max/moyennes et % hors plage se calculent en direct.\n"
            "• Le statut global devient vert si tout est conforme."
        )
        gtxt.setWordWrap(True)
        gl = QVBoxLayout(guide); gl.addWidget(gtxt)

        # --- Barre seuils + actions
        top = QFormLayout()
        top.addRow("Tmin (°C)", self.Tmin)
        top.addRow("Tmax (°C)", self.Tmax)
        top.addRow("RHmin (%)", self.RHmin)
        top.addRow("RHmax (%)", self.RHmax)

        # Boutons
        b_add_point = QPushButton("+ Point"); b_add_point.clicked.connect(self.add_point)
        b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.on_save)
        b_th = QPushButton("Seuils…"); b_th.clicked.connect(self.edit_thresholds)

        actions = QHBoxLayout()
        actions.addWidget(b_add_point)
        actions.addStretch(1)
        actions.addWidget(b_save)
        actions.addWidget(b_th)

        # --- Tableau
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        # style cohérent avec ton app (bleu)
        self.table.setStyleSheet("""
            QTableWidget { background:#fff; border:2px solid #1c5ea3; border-radius:8px; }
            QHeaderView::section { background:#1c5ea3; color:#fff; font-weight:bold; border:none; padding:6px; }
        """)

        # Permettre renommer le point en double-clic
        self.table.itemChanged.connect(self._on_item_changed)

        # Statut global
        self.status = QLabel(); set_status_pill(self.status, None)

        # --- Layout principal
        root = QVBoxLayout(self)
        root.addWidget(guide)
        root.addLayout(top)
        root.addLayout(actions)
        root.addWidget(self.table)
        root.addWidget(self.status)

        # Données
        self.points: List[Dict[str, Any]] = []  # [{name, T:[], RH:[]}, ...]
        # seed 3 points
        self.add_point("Poste A")
        self.add_point("Poste B")
        self.add_point("Poste C")

        # Recalcul live si seuils changent
        for w in (self.Tmin, self.Tmax, self.RHmin, self.RHmax):
            w.valueChanged.connect(self.recompute_all)

    # ------------------- Thresholds -------------------
    def _refresh_thresholds(self):
        pid = self.get_project_id()
        def _get(k, dflt):
            try:
                return float(self.db.get_threshold(pid, "Temp_RH", k, str(dflt)))
            except Exception:
                return dflt
        self.Tmin.setValue(_get("Tmin", 20))
        self.Tmax.setValue(_get("Tmax", 24))
        self.RHmin.setValue(_get("RHmin", 40))
        self.RHmax.setValue(_get("RHmax", 60))

    def edit_thresholds(self):
        w = ThresholdEditor(self.db, self.get_project_id(), "Temp_RH", ["Tmin", "Tmax", "RHmin", "RHmax"])
        w.setWindowModality(Qt.ApplicationModal)
        w.setWindowTitle("Seuils – Temp & RH")
        w.show(); self._th_win = w

    # ------------------- Points & lectures -------------------
    def add_point(self, name: Optional[str] = None):
        self.points.append({"name": name or f"Point {len(self.points)+1}", "T": [], "RH": []})
        self._insert_row(len(self.points)-1)

    def _insert_row(self, idx: int):
        self.table.insertRow(idx)
        for c in range(len(self.COLS)-1):  # dernière col = actions
            self.table.setItem(idx, c, QTableWidgetItem("—"))

        # Nom editable
        self.table.item(idx, 0).setText(self.points[idx]["name"])
        self.table.item(idx, 0).setFlags(self.table.item(idx, 0).flags() | Qt.ItemIsEditable)

        # Actions (➕ lecture / ✎ voir / 🗑 point)
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(0,0,0,0)
        b_add = QPushButton("➕ Lecture"); b_add.setToolTip("Ajouter une lecture T/RH")
        b_edit = QPushButton("✎ Lectures"); b_edit.setToolTip("Voir / supprimer des lectures")
        b_del = QPushButton("🗑"); b_del.setToolTip("Supprimer le point")
        for b in (b_add, b_edit, b_del):
            b.setFixedHeight(26)
        lay.addWidget(b_add); lay.addWidget(b_edit); lay.addWidget(b_del); lay.addStretch(1)
        self.table.setCellWidget(idx, self.COLS.index("Actions"), w)

        # Connects
        b_add.clicked.connect(lambda _, r=idx: self._add_reading(r))
        b_edit.clicked.connect(lambda _, r=idx: self._edit_readings(r))
        b_del.clicked.connect(lambda _, r=idx: self._delete_point(r))

        # calc initial
        self._update_row(idx)
        self.recompute_all()

    def _safe_mean(self, arr: List[float]) -> Optional[float]:
        return (sum(arr)/len(arr)) if arr else None

    def _pct_out(self, arr: List[float], lo: float, hi: float) -> Optional[float]:
        if not arr: return None
        n_out = sum(1 for v in arr if (v < lo or v > hi))
        return 100.0 * n_out / len(arr)

    def _update_row(self, idx: int):
        p = self.points[idx]
        Tmin, Tmax = self.Tmin.value(), self.Tmax.value()
        RHmin, RHmax = self.RHmin.value(), self.RHmax.value()

        n = min(len(p["T"]), len(p["RH"]))  # nombre de paires
        # T stats
        T_min = min(p["T"]) if p["T"] else None
        T_max = max(p["T"]) if p["T"] else None
        T_moy = self._safe_mean(p["T"])
        # RH stats
        RH_min = min(p["RH"]) if p["RH"] else None
        RH_max = max(p["RH"]) if p["RH"] else None
        RH_moy = self._safe_mean(p["RH"])

        pctT = self._pct_out(p["T"], Tmin, Tmax)
        pctRH = self._pct_out(p["RH"], RHmin, RHmax)

        ok_p = (pctT in (None, 0.0)) and (pctRH in (None, 0.0))
        ok_txt = "—" if n == 0 else ("OK" if ok_p else "NON")

        def _fmt(x, nd=2, dash="—"):
            return (f"{x:.{nd}f}" if x is not None else dash)

        vals = [
            p["name"],
            str(n),
            _fmt(T_min), _fmt(T_max), _fmt(T_moy),
            _fmt(RH_min), _fmt(RH_max), _fmt(RH_moy, nd=1),
            ("—" if pctT is None else f"{pctT:.1f}"),
            ("—" if pctRH is None else f"{pctRH:.1f}"),
            ok_txt
        ]
        for c, v in enumerate(vals):
            self.table.item(idx, c).setText(v)

        # colorer la cellule OK?
        ok_col = self.COLS.index("OK?")
        it_ok = self.table.item(idx, ok_col)
        if n == 0:
            it_ok.setBackground(Qt.transparent)
        else:
            it_ok.setBackground("#28a745" if ok_p else "#dc3545")
            it_ok.setForeground(Qt.white)

    def _add_reading(self, row: int):
        # dernieres valeurs pour auto-remplir
        p = self.points[row]
        lastT = p["T"][-1] if p["T"] else None
        lastRH = p["RH"][-1] if p["RH"] else None
        dlg = ReadingDialog(self, lastT, lastRH)
        if dlg.exec_() == QDialog.Accepted:
            T, RH = dlg.values()
            p["T"].append(T); p["RH"].append(RH)
            self._update_row(row)
            self.recompute_all()

    def _edit_readings(self, row: int):
        p = self.points[row]
        dlg = EditReadingsDialog(p["name"], p["T"], p["RH"], self)
        dlg.exec_()
        # Après modifications, recalcul
        self._update_row(row)
        self.recompute_all()

    def _delete_point(self, row: int):
        ok = QMessageBox.question(self, "Supprimer", f"Supprimer le point « {self.points[row]['name']} » ?",
                                  QMessageBox.Yes | QMessageBox.No)
        if ok != QMessageBox.Yes: return
        del self.points[row]
        self.table.removeRow(row)
        # rebrancher les boutons (les lambdas capturaient l'index)
        self._rebind_action_cells()
        self.recompute_all()

    def _rebind_action_cells(self):
        for r in range(self.table.rowCount()):
            cell = self.table.cellWidget(r, self.COLS.index("Actions"))
            if not cell: continue
            btns = cell.findChildren(QPushButton)
            if len(btns) < 3: continue
            b_add, b_edit, b_del = btns[:3]
            try:
                b_add.clicked.disconnect()
                b_edit.clicked.disconnect()
                b_del.clicked.disconnect()
            except Exception:
                pass
            b_add.clicked.connect(lambda _, rr=r: self._add_reading(rr))
            b_edit.clicked.connect(lambda _, rr=r: self._edit_readings(rr))
            b_del.clicked.connect(lambda _, rr=r: self._delete_point(rr))
            # Renommer la cellule "Point" si nécessaire (garde editable)
            self.table.item(r, 0).setText(self.points[r]["name"])

    def _on_item_changed(self, item: QTableWidgetItem):
        # Si c'est le nom du point (col 0), répercute dans self.points
        if item.column() == 0:
            r = item.row()
            if 0 <= r < len(self.points):
                self.points[r]["name"] = (item.text() or "").strip() or f"Point {r+1}"

    # ------------------- Calcul global & sauvegarde -------------------
    def recompute_all(self):
        # Recalcule toutes les lignes (cas seuils modifiés)
        for r in range(self.table.rowCount()):
            self._update_row(r)

        # Statut global
        any_data = False
        all_ok = True
        for p in self.points:
            n = min(len(p["T"]), len(p["RH"]))
            if n == 0:
                continue
            any_data = True
            Tmin, Tmax = self.Tmin.value(), self.Tmax.value()
            RHmin, RHmax = self.RHmin.value(), self.RHmax.value()
            pctT = self._pct_out(p["T"], Tmin, Tmax)
            pctRH = self._pct_out(p["RH"], RHmin, RHmax)
            ok_p = (pctT in (None, 0.0)) and (pctRH in (None, 0.0))
            if not ok_p:
                all_ok = False
        set_status_pill(self.status, (all_ok if any_data else None))
        # Buffer résultat pour sauvegarde
        results = []
        for r, p in enumerate(self.points, start=1):
            # reprendre les chiffres visibles
            row = {
                "id": p["name"],
                "T": p["T"],
                "RH": p["RH"]
            }
            results.append(row)
        self._last_result = {
            "seuils": {
                "Tmin": self.Tmin.value(), "Tmax": self.Tmax.value(),
                "RHmin": self.RHmin.value(), "RHmax": self.RHmax.value()
            },
            "points": results,
            "conforme": (all_ok if any_data else None)
        }

    def on_save(self):
        if not hasattr(self, "_last_result"):
            self.recompute_all()
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return
        self.db.save_test(pid, "Temp_RH", self._last_result.get("conforme"), {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


# --------------------------- Main Window ------------------------------

from PyQt5.QtWidgets import QDialog

class ProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau projet")
        self.setModal(True)
        form = QFormLayout(self)
        self.company = QLineEdit(); self.name = QLineEdit()
        self.location = QLineEdit(); self.tag = QLineEdit()
        self.work_type = QComboBox(); self.work_type.addItems(["HVAC", "Thermal Mapping", "Instrumentation"])
        self.test_date = QLineEdit(datetime.now().strftime("%Y-%m-%d"))
        self.contact = QLineEdit(); self.responsables = QLineEdit()
        self.notes = QPlainTextEdit()
        form.addRow("Entreprise", self.company)
        form.addRow("Nom projet", self.name)
        form.addRow("Localisation", self.location)
        form.addRow("Tag", self.tag)
        form.addRow("Type de travail", self.work_type)
        form.addRow("Date de test (YYYY-MM-DD)", self.test_date)
        form.addRow("Contact", self.contact)
        form.addRow("Responsables (séparés par ,)", self.responsables)
        form.addRow("Notes", self.notes)
        btns = QHBoxLayout()
        b_ok = QPushButton("Créer"); b_ok.clicked.connect(self.accept)
        b_cancel = QPushButton("Annuler"); b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_ok); btns.addWidget(b_cancel)
        form.addRow(btns)

    def data(self) -> Dict[str, Any]:
        return {
            "company": self.company.text().strip(),
            "name": self.name.text().strip(),
            "location": self.location.text().strip(),
            "tag": self.tag.text().strip(),
            "work_type": self.work_type.currentText(),
            "test_date": self.test_date.text().strip(),
            "contact": self.contact.text().strip(),
            "responsables": self.responsables.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HVAC QP Test Bench")
        self.resize(1200, 720)
        self.db = DB()

        # Top bar: project selector
        top = QWidget(); top_l = QHBoxLayout(top)
        self.cb_projects = QComboBox()
        b_new = QPushButton("Nouveau projet…"); b_new.clicked.connect(self.on_new_project)
        b_refresh = QPushButton("↻"); b_refresh.clicked.connect(self.reload_projects)
        top_l.addWidget(QLabel("Projet:")); top_l.addWidget(self.cb_projects, 1)
        top_l.addWidget(b_new); top_l.addWidget(b_refresh)

        # Left tree
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        root = QTreeWidgetItem(["HVAC QP – Tests"])
        self.tree.addTopLevelItem(root)
        tests = [
            ("ACPH", "1) Débit & ACPH"),
            ("DeltaP", "2) Cascade de pressions (ΔP)"),
            ("Uniformity", "3) Vitesses sous filtres / uniformité"),
            ("HEPA_Leak", "4) Intégrité filtres HEPA"),
            ("Particle_Class", "5) Comptage particulaire en air"),
            ("Recovery_Time", "6) Recovery time (100:1)"),
            ("Smoke_Visual", "7) Visualisation de flux (fumée)"),
            ("Temp_RH", "8) Température & Humidité"),
        ]
        self.key_by_item = {}
        for key, label in tests:
            it = QTreeWidgetItem([label]); root.addChild(it); self.key_by_item[id(it)] = key
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self.on_tree_change)

        # Stacked pages
        def get_pid():
            data = self.cb_projects.currentData()
            return int(data) if data is not None else None

        self.pages: Dict[str, QWidget] = {
            "ACPH": ACPHPage(self.db, get_pid),
            "DeltaP": DeltaPPage(self.db, get_pid),
            "Uniformity": UniformityPage(self.db, get_pid),
            "HEPA_Leak": HEPALeakPage(self.db, get_pid),
            "Particle_Class": ParticleClassPage(self.db, get_pid),
            "Recovery_Time": RecoveryPage(self.db, get_pid),
            "Smoke_Visual": SmokePage(self.db, get_pid),
            "Temp_RH": TempRHPage(self.db, get_pid),
        }
        self.stack = QStackedWidget()
        self.key_to_index: Dict[str, int] = {}
        for i, (k, _) in enumerate(tests):
            self.stack.addWidget(self.pages[k]); self.key_to_index[k] = i

        # Central layout
        central = QWidget(); central_l = QVBoxLayout(central)
        central_l.addWidget(top)
        body = QHBoxLayout(); body.addWidget(self.tree, 2); body.addWidget(self.stack, 7)
        central_l.addLayout(body)
        self.setCentralWidget(central)

        self.reload_projects()
        # Select first test by default
        self.tree.setCurrentItem(root.child(0))

    # ---- Projects ----
    def reload_projects(self):
        self.cb_projects.clear()
        rows = self.db.list_projects()
        self.cb_projects.addItem("— Aucun projet —", None)
        for r in rows:
            label = f"{r['id']} • {r['company'] or ''} {r['name'] or ''} [{r['location'] or ''}]".strip()
            self.cb_projects.addItem(label, r["id"])

    def on_new_project(self):
        dlg = ProjectDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            pid = self.db.add_project(dlg.data())
            self.reload_projects()
            # Select the newly created project
            for i in range(self.cb_projects.count()):
                if self.cb_projects.itemData(i) == pid:
                    self.cb_projects.setCurrentIndex(i); break
            QMessageBox.information(self, "Projet", f"Projet #{pid} créé.")

    # ---- Navigation ----
    def on_tree_change(self, cur: QTreeWidgetItem, prev: QTreeWidgetItem):
        if not cur: return
        key = self.key_by_item.get(id(cur))
        if not key: return
        idx = self.key_to_index.get(key, 0)
        self.stack.setCurrentIndex(idx)





# --------------------------- App entry --------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
