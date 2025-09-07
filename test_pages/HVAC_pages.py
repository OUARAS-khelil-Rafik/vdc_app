from typing import List, Dict, Any, Optional, Tuple
import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QWidget, QLabel, QFormLayout, QHBoxLayout, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QGroupBox, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QHeaderView, QScrollArea, QLineEdit, QPlainTextEdit,
    QStackedWidget, QTabWidget, QCheckBox, QFileDialog
)

from models.testmanager    import TestManager

def set_status_pill(label, ok: Optional[bool]):
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


# --------------------------- Threshold editor -------------------------
class ThresholdEditor(QWidget):
    """
    Simple editor to view/set thresholds for a given test type (global or for current project).
    """
    def __init__(self, app_db, project_id: Optional[int], test_type: str, keys: List[str]):
        super().__init__()
        self.db = app_db
        self.manager = TestManager(app_db)
        self.project_id = project_id
        self.test_type = test_type
        self.keys = keys
        self.edits: Dict[str, QLineEdit] = {}
        lay = QFormLayout(self)
        for k in keys:
            e = QLineEdit(self)
            e.setText(self.manager.get_threshold(project_id, test_type, k, "" ) or "")
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
        QMessageBox.information(self, "OK", "Seuils enregistrés.")


# --------------------------- Test Pages -------------------------------
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

    def __init__(self, app_db, get_project_id):
        super().__init__()
        self.db = app_db
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

        # ---------- (Tout est live)
        btn_save = QPushButton("Enregistrer"); btn_save.clicked.connect(self.on_save)
        btn_th = QPushButton("Seuils"); btn_th.clicked.connect(self.edit_thresholds)

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

        btns = QHBoxLayout(); btns.addWidget(btn_save); btns.addStretch(1); btns.addWidget(btn_th)
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
        w.setWindowModality(Qt.ApplicationModal); w.setWindowTitle("Seuils – Débit requis & Tolérance")
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

    def _sum_col(self, table: QTableWidget, col: int = 1) -> Tuple[float, int]:
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
            QMessageBox.information(self, "Info", "Saisissez des valeurs d’abord.")
            return
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return
        ok_global = self._last_result.get("ok")
        # Correction logique : conformité globale = False si violation, True si tout conforme, None sinon
        if ok_global is False:
            conforme = False
        elif ok_global is True:
            conforme = True
        else:
            conforme = None
        TestManager(self.db).save_test(pid, "ACPH", conforme, {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class DeltaPPage(QWidget):
    """
    Cascade de pressions (ΔP) — version simplifiée, LIVE

    • Colonnes : Local | ΔP (Pa) | Cible (Pa) | Tolérance (%) | OK?
    • Une seule lecture ΔP par local (pas de moyenne).
    • Conformité : OK si ΔP ∈ [Cible*(1−tol%), Cible*(1+tol%)]. (tolérance 0% = strict)
    • Évaluation en direct : la colonne OK? et le statut global se mettent à jour à chaque saisie.
    """

    def __init__(self, appDB, get_project_id):
        super().__init__()
        self.db = appDB
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

        # Correction logique conformité globale :
        # - False si au moins un local non conforme
        # - True si tous les locaux sont conformes (et au moins un local saisi)
        # - None sinon (pas de saisie ou incomplet)
        results = self._last_result.get("locals", [])
        if not results:
            ok_global = None
        elif any(r.get("ok") is False for r in results):
            ok_global = False
        elif all(r.get("ok") is True for r in results):
            ok_global = True
        else:
            ok_global = None

        self._last_result["conforme"] = ok_global
        TestManager(self.db).save_test(pid, "DeltaP", ok_global, {"note": "cascade_simple_live"}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")

class SmokeDynamicPage(QWidget):
    """
    Visualisation de fumée **dynamique** – Protocoles écrits + N/A justifié (intuitif & strict)

    Points clés :
      • **Protocoles écrits** : on peut en **ajouter** (Nom + descriptif). Le tableau principal est **verrouillé** tant
        que **tous** les protocoles ajoutés ne sont pas **cochés “Présent”**.
      • **Observations tri‑état** : Oui / Non / N/A pour chaque critère (Effet piston, Pas de stagnation,
        Fuite non observée, Extraction & pulsion OK).
      • Si on met **N/A** sur un critère, la **remarque** associée (colonne dédiée) devient **obligatoire**.
      • Colonne **Type d’opération** (texte) par scène.
      • Conformité d’une ligne **autorisée** uniquement si :
          – protocoles tous présents ;
          – aucun critère en **Non** ;
          – toutes les **remarques N/A** sont **remplies**.
      • Pastille globale LIVE : rouge si ≥1 “Non conforme”, verte si toutes “Conforme”, neutre sinon
        (ou si protocoles non tous présents).
    """

    TEST_KEY = "Smoke_Visual_Dynamic"
    PROTO_COLS = ["Nom du protocole", "Descriptif", "Présent"]

    # ---------------- Construction ----------------
    def __init__(self, db, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self._updating = False

        # -------- Guide --------
        guide = QGroupBox("Comment utiliser – Visualisation de fumée (dynamique)")
        gl = QVBoxLayout(guide)
        lbl = QLabel(
            "1) Ajoutez vos **protocoles écrits** (Nom + descriptif), puis cochez ‘Présent’."
            "2) Ajoutez une ligne par scène : ID, zone, **type d’opération**."
            "3) Sélectionnez Oui/Non/N/A pour chaque observation. Si **N/A**, remplissez la **remarque** juste à côté."
            "4) Choisissez la conformité de la ligne. Les règles sont vérifiées automatiquement."
            "5) La pastille globale se met à jour en direct."
        )
        lbl.setWordWrap(True)
        gl.addWidget(lbl)

        # -------- Protocoles écrits (ajout libre) --------
        proto_box = QGroupBox("Protocoles écrits")
        pl = QVBoxLayout(proto_box)

        self.tbl_proto = QTableWidget(0, 3)
        self.tbl_proto.setHorizontalHeaderLabels(self.PROTO_COLS)
        self.tbl_proto.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_proto.itemChanged.connect(self._on_protocols_changed)

        btnp_add = QPushButton("+ Protocole")
        btnp_add.clicked.connect(self._add_protocol)
        btnp_del = QPushButton("Supprimer sélection")
        btnp_del.clicked.connect(self._del_protocol)
        rowp = QHBoxLayout()
        rowp.addWidget(btnp_add)
        rowp.addWidget(btnp_del)
        rowp.addStretch(1)

        # État protocole (hint de verrouillage/déverrouillage)
        self.proto_state = QLabel("")
        self.proto_state.setWordWrap(True)

        pl.addWidget(self.tbl_proto)
        pl.addLayout(rowp)
        pl.addWidget(self.proto_state)

        # -------- Tableau scènes --------
        # Colonnes :
        # 0 ID, 1 Zone, 2 Type op, 3 EP, 4 Rem EP, 5 PS, 6 Rem PS, 7 Fuite, 8 Rem Fuite,
        # 9 EPuls, 10 Rem EPuls, 11 Conformité, 12 Descriptif (auto), 13 Commentaire général
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels([
            "ID Film", "Zone/Scénario", "Type d'opération",
            "Effet piston", "Remarque EP",
            "Pas de stagnation", "Remarque PS",
            "Fuite non observée", "Remarque Fuite",
            "Extraction & pulsion OK", "Remarque EPuls",
            "Conformité", "Descriptif (auto)", "Commentaire"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)  # textes/remarks/commentaire

        # -------- Boutons scènes --------
        self.btn_add = QPushButton("+ Ligne")
        self.btn_add.clicked.connect(self.add_row)
        self.btn_del = QPushButton("Supprimer sélection")
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_save = QPushButton("Enregistrer")
        self.btn_save.clicked.connect(self.on_save)

        # -------- Statut global --------
        self.status = QLabel()
        set_status_pill(self.status, None)

        # -------- Layout principal --------
        root = QVBoxLayout(self)
        root.addWidget(guide)
        root.addWidget(proto_box)
        root.addWidget(self.table)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(self.btn_add)
        row_buttons.addWidget(self.btn_del)
        row_buttons.addStretch(1)
        row_buttons.addWidget(self.status)
        row_buttons.addWidget(self.btn_save)
        root.addLayout(row_buttons)

        # État initial : verrouiller les scènes tant que protocoles non validés
        self._apply_protocol_lock()

    # ---------------- Protocoles ----------------
    def _add_protocol(self, name: Optional[str] = None, desc: Optional[str] = None, present: bool = False) -> None:
        r = self.tbl_proto.rowCount()
        self.tbl_proto.insertRow(r)
        self._updating = True
        try:
            self.tbl_proto.setItem(r, 0, QTableWidgetItem(name or ""))
            self.tbl_proto.setItem(r, 1, QTableWidgetItem(desc or ""))
            chk = QTableWidgetItem("")
            chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if present else Qt.Unchecked)
            self.tbl_proto.setItem(r, 2, chk)
        finally:
            self._updating = False
        self._apply_protocol_lock()

    def _del_protocol(self) -> None:
        rows = sorted({i.row() for i in self.tbl_proto.selectedIndexes()}, reverse=True)
        for r in rows:
            self.tbl_proto.removeRow(r)
        self._apply_protocol_lock()

    def _protocols_ok(self) -> bool:
        """Déverrouille si **au moins 1 protocole** et **toutes** les cases ‘Présent’ sont cochées.
        (On ne bloque **pas** sur le remplissage Nom/Descriptif pour éviter un faux-verrouillage.)"""
        n = self.tbl_proto.rowCount()
        if n == 0:
            return False
        for r in range(n):
            item = self.tbl_proto.item(r, 2)
            if (item is None) or (item.checkState() != Qt.Checked):
                return False
        return True

    def _apply_protocol_lock(self) -> None:
        locked = not self._protocols_ok()
        for w in (self.table, self.btn_add, self.btn_del, self.btn_save):
            w.setEnabled(not locked)
        # Message d'état
        if locked:
            self.proto_state.setText("🔒 Tableau verrouillé — cochez ‘Présent’ pour chaque protocole (au moins 1).")
            self.proto_state.setStyleSheet("color:#b00020;")
        else:
            self.proto_state.setText("🔓 Tableau déverrouillé — protocoles présents.")
            self.proto_state.setStyleSheet("color:#2e7d32;")
        set_status_pill(self.status, None if locked else None)

    def _on_protocols_changed(self, *_):
        if self._updating:
            return
        self._apply_protocol_lock()
        self.evaluate_live()

    # ---------------- Helpers scènes ----------------
    def _obs_combo(self) -> QComboBox:
        cb = QComboBox()
        cb.addItems(["Oui", "Non", "N/A"])  # tri-état
        cb.currentTextChanged.connect(self._on_obs_changed)
        return cb

    def _combo_conformite(self) -> QComboBox:
        cb = QComboBox()
        cb.addItems(["—", "Conforme", "Non conforme"])
        cb.currentTextChanged.connect(self._on_conformite_changed)
        return cb

    def _row_of_widget(self, w) -> Optional[int]:
        for r in range(self.table.rowCount()):
            for c in (3, 5, 7, 9, 11):  # obs & conformité colonnes combo
                if self.table.cellWidget(r, c) is w:
                    return r
        return None

    def add_row(self, film_id: Optional[str] = None, zone: Optional[str] = None) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._updating = True
        try:
            # ID, Zone, Type op
            self.table.setItem(r, 0, QTableWidgetItem(film_id or f"D-{r+1:03d}"))
            self.table.setItem(r, 1, QTableWidgetItem(zone or ""))
            self.table.setItem(r, 2, QTableWidgetItem(""))

            # Observations (par défaut = "Non") + remarques (désactivées sauf N/A)
            for c_obs, c_rem in ((3, 4), (5, 6), (7, 8), (9, 10)):
                cb = self._obs_combo()
                cb.setCurrentText("Non")
                self.table.setCellWidget(r, c_obs, cb)
                rem = QTableWidgetItem("")
                rem.setFlags(rem.flags() | Qt.ItemIsEditable)
                rem.setBackground(QBrush(self._rem_bg(enabled=False)))
                self.table.setItem(r, c_rem, rem)

            # Conformité
            self.table.setCellWidget(r, 11, self._combo_conformite())

            # Descriptif auto (RO) + Commentaire général
            desc = QTableWidgetItem("—")
            desc.setFlags(desc.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 12, desc)
            self.table.setItem(r, 13, QTableWidgetItem(""))

            self._update_row_descriptif(r)
        finally:
            self._updating = False
        self._enforce_row_rules(r)
        self.evaluate_live()

    def delete_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self.evaluate_live()

    def _rem_bg(self, enabled: bool) -> QColor:
        # couleur de fond subtile pour champs remarque actifs
        return QColor(255, 255, 255) if enabled else QColor(245, 245, 245)

    def _obs_value(self, r: int, c: int) -> Optional[str]:
        w = self.table.cellWidget(r, c)
        return w.currentText() if isinstance(w, QComboBox) else None

    def _remark_text(self, r: int, c_remark: int) -> str:
        it = self.table.item(r, c_remark)
        return it.text().strip() if it else ""

    def _row_allows_conforme(self, r: int) -> bool:
        if not self._protocols_ok():
            return False
        couples = ((3, 4), (5, 6), (7, 8), (9, 10))
        for obs_col, rem_col in couples:
            v = self._obs_value(r, obs_col)
            if v == "Non":
                return False
            if v == "N/A" and not self._remark_text(r, rem_col):
                return False
        return True

    def _update_row_descriptif(self, r: int) -> None:
        mapping = [
            ("Effet piston", 3, 4),
            ("Pas de stagnation", 5, 6),
            ("Fuite non observée", 7, 8),
            ("Extraction & pulsion OK", 9, 10),
        ]
        parts = []
        for label, c_obs, c_rem in mapping:
            v = self._obs_value(r, c_obs)
            if v == "Oui":
                parts.append(f"{label} : OK")
            elif v == "Non":
                parts.append(f"{label} : Non")
            elif v == "N/A":
                rem = self._remark_text(r, c_rem)
                parts.append(f"{label} : N/A{' (justifié)' if rem else ' (à justifier)'}")
            else:
                parts.append(f"{label} : —")
        text = " ; ".join(parts)
        self._updating = True
        try:
            self.table.setItem(r, 12, QTableWidgetItem(text))
        finally:
            self._updating = False

    # ---------------- Live events ----------------
    def _on_obs_changed(self, *_):
        if self._updating:
            return
        w = self.sender()
        r = self._row_of_widget(w)
        if r is None:
            return
        pairs = {3: 4, 5: 6, 7: 8, 9: 10}
        for obs_col, rem_col in pairs.items():
            if self.table.cellWidget(r, obs_col) is w:
                v = self._obs_value(r, obs_col)
                rem = self.table.item(r, rem_col)
                if rem:
                    rem.setBackground(QBrush(self._rem_bg(enabled=(v == "N/A"))))
                break
        self._update_row_descriptif(r)
        self._enforce_row_rules(r)
        self.evaluate_live()

    def _on_conformite_changed(self, *_):
        if self._updating:
            return
        cb = self.sender()
        r = self._row_of_widget(cb)
        if r is None:
            return
        if cb.currentText() == "Conforme" and not self._row_allows_conforme(r):
            QMessageBox.information(
                self,
                "Règle conformité (dynamique)",
                "Pour valider ‘Conforme’ :"
                "- Tous les protocoles doivent être cochés ‘Présent’ ;"
                "- Aucun critère en ‘Non’ ;"
                "- Chaque ‘N/A’ possède une remarque (justification)."
            )
            self._updating = True
            try:
                cb.setCurrentText("—")
            finally:
                self._updating = False
        self.evaluate_live()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating:
            return
        if item.column() in (0, 1, 2, 4, 6, 8, 10, 13):
            self._update_row_descriptif(item.row())
            self._enforce_row_rules(item.row())
        self.evaluate_live()

    # ---------------- Enforcement / Global ----------------
    def _enforce_row_rules(self, r: int) -> None:
        w = self.table.cellWidget(r, 11)
        if isinstance(w, QComboBox) and w.currentText() == "Conforme" and not self._row_allows_conforme(r):
            self._updating = True
            try:
                w.setCurrentText("—")
            finally:
                self._updating = False

    def evaluate_live(self) -> None:
        if not self._protocols_ok() or self.table.rowCount() == 0:
            set_status_pill(self.status, None)
            return
        any_nc = False
        all_ok = True
        any_set = False
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 11)
            conf = w.currentText() if isinstance(w, QComboBox) else "—"
            if conf == "Non conforme":
                any_nc = True
                any_set = True
            elif conf == "Conforme":
                any_set = True
            else:
                all_ok = False
        if any_nc:
            set_status_pill(self.status, False)
        elif all_ok and any_set:
            set_status_pill(self.status, True)
        else:
            set_status_pill(self.status, None)

    # ---------------- Save ----------------
    def on_save(self) -> None:
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez d’abord un projet.")
            return
        if not self._protocols_ok():
            QMessageBox.information(self, "Protocoles requis", "Cochez tous les protocoles (Présent) avant d'enregistrer.")
            return

        # Protocoles
        protos = []
        for r in range(self.tbl_proto.rowCount()):
            protos.append({
                "nom": self.tbl_proto.item(r, 0).text() if self.tbl_proto.item(r, 0) else "",
                "descriptif": self.tbl_proto.item(r, 1).text() if self.tbl_proto.item(r, 1) else "",
                "present": (self.tbl_proto.item(r, 2).checkState() == Qt.Checked) if self.tbl_proto.item(r, 2) else False,
            })

        # Scènes
        rows = []
        for r in range(self.table.rowCount()):
            rows.append({
                "film_id": self.table.item(r, 0).text() if self.table.item(r, 0) else "",
                "zone": self.table.item(r, 1).text() if self.table.item(r, 1) else "",
                "type_operation": self.table.item(r, 2).text() if self.table.item(r, 2) else "",
                "effet_piston": self._obs_value(r, 3),
                "rem_ep": self._remark_text(r, 4),
                "pas_de_stagnation": self._obs_value(r, 5),
                "rem_ps": self._remark_text(r, 6),
                "fuite_non_observee": self._obs_value(r, 7),
                "rem_fuite": self._remark_text(r, 8),
                "extraction_pulsion_ok": self._obs_value(r, 9),
                "rem_epuls": self._remark_text(r, 10),
                "conformite": self.table.cellWidget(r, 11).currentText() if isinstance(self.table.cellWidget(r, 11), QComboBox) else "—",
                "descriptif_auto": self.table.item(r, 12).text() if self.table.item(r, 12) else "",
                "commentaire": self.table.item(r, 13).text() if self.table.item(r, 13) else "",
            })

        any_nc = any(row["conformite"] == "Non conforme" for row in rows)
        all_ok = all(row["conformite"] == "Conforme" for row in rows if row["conformite"] in ("Conforme", "Non conforme")) and len(rows) > 0
        ok_global = False if any_nc else (True if all_ok else None)

        payload = {
            "type": "visualisation_fumee_dynamique",
            "protocoles": protos,
            "protocoles_ok": self._protocols_ok(),
            "scenes": rows,
            "conforme": ok_global,
        }

        TestManager(self.db).save_test(pid, self.TEST_KEY, ok_global, {}, payload)
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

    def __init__(self, appDB, get_project_id):
        super().__init__()
        self.db = appDB
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
        top_form.addRow("Signal amont (µg/l)", self.signal_up)
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
        # Vérifie s'il y a au moins une valeur mesurée (fuite renseignée)
        has_value = any(self._cell_float(r, 1) is not None for r in range(self.table.rowCount()))
        if not has_value:
            QMessageBox.information(self, "Info", "Saisissez au moins une fuite (%) avant d'enregistrer.")
            return

        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez d’abord un projet.")
            return

        # Correction logique conformité globale :
        # - False si au moins une fuite non conforme
        # - True si toutes les fuites renseignées sont conformes (et au moins une saisie)
        # - None sinon (pas de saisie)
        self.evaluate_live()  # met à jour _last_result
        oks = [pos.get("ok") for pos in self._last_result.get("positions", []) if pos.get("ok") is not None]
        if not oks:
            ok_global = None
        elif any(ok is False for ok in oks):
            ok_global = False
        elif all(ok is True for ok in oks):
            ok_global = True
        else:
            ok_global = None
        self._last_result["conforme"] = ok_global

        TestManager(self.db).save_test(pid, "HEPA_Leak", ok_global, {}, self._last_result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")

class ParticleClassPage(QWidget):
    """Comptage particulaire en air (ISO 14644‑1) – Évaluation LIVE **directe en /m³**

    ✔️ Logique demandée : comparaison **directe** des valeurs saisies (en **particules/m³**) aux **seuils ISO**.
       Exemple : ISO 1 @ 0,1 µm → seuil 10 /m³ : si saisie ≤ 10 → OK, sinon non conforme.

    Fonctionnement :
      1) Choisir la **classe ISO (1→9)**.
      2) Cocher une ou plusieurs **tailles** autorisées pour la classe.
      3) Saisir la **surface A (m²)**. N positions = 0 → **auto** (⌈√A⌉), sinon forcée.
      4) Saisir directement les **concentrations (/m³)** dans la grille.

    Statut global **LIVE** :
      • Par défaut : **neutre** (ni conforme, ni non conforme).
      • S'il existe au moins **une violation** : **non conforme** immédiat.
      • Quand **toutes** les cellules sont remplies **et** sans violation : **conforme**.
    """

    # ---- Table ISO 14644‑1 (valeurs / m³ ; None = non applicable) ----
    ISO_TABLE = {
        1: {0.1: 10,       0.2: None,     0.3: None,     0.5: None,      1.0: None,     5.0: None},
        2: {0.1: 100,      0.2: 24,       0.3: 10,       0.5: None,      1.0: None,     5.0: None},
        3: {0.1: 1000,     0.2: 237,      0.3: 102,      0.5: 35,        1.0: None,     5.0: None},
        4: {0.1: 10000,    0.2: 2370,     0.3: 1020,     0.5: 352,       1.0: 83,       5.0: None},
        5: {0.1: 100000,   0.2: 23700,    0.3: 10200,    0.5: 3520,      1.0: 832,      5.0: None},
        6: {0.1: 1000000,  0.2: 237000,   0.3: 102000,   0.5: 35200,     1.0: 8320,     5.0: 293},
        7: {0.1: None,     0.2: None,     0.3: None,     0.5: 352000,    1.0: 83200,    5.0: 2930},
        8: {0.1: None,     0.2: None,     0.3: None,     0.5: 3520000,   1.0: 832000,   5.0: 29300},
        9: {0.1: None,     0.2: None,     0.3: None,     0.5: 35200000,  1.0: 8320000,  5.0: 293000},
    }

    def __init__(self, appDB, get_project_id):
        super().__init__()
        self.db = appDB
        self.get_project_id = get_project_id
        self._grid_meta = None
        self._building = False  # évite les recalculs pendant construction UI

        # --------- Entrées ---------
        self.iso_class = QComboBox()
        self.iso_class.addItems([str(i) for i in range(1, 10)])

        self.size_list = QListWidget()  # tailles disponibles (checkbox)
        self.size_list.itemChanged.connect(self._on_sizes_changed)

        self.A = QDoubleSpinBox()
        self.A.setRange(0, 1e6)
        self.A.setDecimals(2)
        self.A.setValue(36.0)

        self.Npos = QSpinBox()  # 0 = auto (⌈√A⌉)
        self.Npos.setRange(0, 999)
        self.Npos.setValue(0)

        # --------- Sorties dérivées ---------
        self.out_autopos = QLabel("—")

        # --------- Grille ---------
        self.table = QTableWidget(0, 0)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemChanged.connect(self._recalc_live)

        # --------- Statut global ---------
        self.status = QLabel()
        set_status_pill(self.status, None)

        # --------- Guide ---------
        self.help = QLabel(
            "<b>Mode d'emploi :</b><br>"
            "1) Choisissez la <b>classe ISO</b> → cochez les <b>tailles</b> pertinentes.<br>"
            "2) Saisissez la <b>surface A</b>. <i>N positions</i> = 0 → <b>auto</b> (⌈√A⌉).<br>"
            "3) Remplissez les <b>concentrations (/m³)</b> : conformité <b>LIVE</b> (couleurs + pastille)."
        )
        self.help.setWordWrap(True)

        guide_box = QGroupBox("Guide rapide — Classification particulaire (/m³)")
        gbl = QVBoxLayout(guide_box)
        gbl.addWidget(self.help)

        # --------- Boutons ---------
        btn_build = QPushButton("(Re)construire la grille")
        btn_build.clicked.connect(self.build_grid)

        btn_save = QPushButton("Enregistrer")
        btn_save.clicked.connect(self.on_save)

        # --------- Layouts ---------
        form = QFormLayout()
        form.addRow("Numéro de classe ISO", self.iso_class)
        form.addRow("Tailles disponibles (cocher)", self.size_list)
        form.addRow("Surface A (m²)", self.A)
        form.addRow("N positions (0 = auto)", self.Npos)

        outs = QFormLayout()
        outs.addRow("Positions auto (⌈√A⌉)", self.out_autopos)

        left = QVBoxLayout()
        left.addLayout(form)
        left.addLayout(outs)
        left.addWidget(btn_build)
        left.addWidget(guide_box)

        right = QVBoxLayout()
        right.addWidget(self.table)
        right.addWidget(self.status)
        right.addWidget(btn_save)

        top = QHBoxLayout(self)
        top.addLayout(left, 1)
        top.addLayout(right, 2)

        # --------- Wiring ---------
        self.iso_class.currentIndexChanged.connect(self._on_class_changed)
        self.A.valueChanged.connect(self._rebuild_rows_and_recalc)
        self.Npos.valueChanged.connect(self._rebuild_rows_and_recalc)

        # --------- Init UI ---------
        self._on_class_changed()  # charge les tailles
        self.build_grid()

    # ===================== Helpers =====================
    def _on_class_changed(self):
        cls = int(self.iso_class.currentText())
        sizes_dict = self.ISO_TABLE.get(cls, {})
        sizes = [s for s, lim in sizes_dict.items() if lim is not None]
        sizes.sort()

        self._building = True
        self.size_list.clear()
        for s in sizes:
            text = f"{s:.1f} µm  (≤ {int(sizes_dict[s]):,} /m³)".replace(",", " ")
            it = QListWidgetItem(text)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)  # tout coché par défaut
            self.size_list.addItem(it)
        self._building = False

        self.build_grid()

    def _on_sizes_changed(self, item: QListWidgetItem):
        if self._building:
            return
        self.build_grid()

    def _selected_sizes(self) -> List[tuple]:
        sizes: List[tuple] = []
        cls = int(self.iso_class.currentText())
        sizes_dict = self.ISO_TABLE.get(cls, {})
        for i in range(self.size_list.count()):
            it = self.size_list.item(i)
            if it.checkState() == Qt.Checked:
                txt = it.text().split(" ")[0]
                try:
                    s = float(txt)
                    sizes.append((s, sizes_dict.get(s)))
                except Exception:
                    pass
        sizes.sort(key=lambda x: x[0])
        return sizes

    def _auto_positions(self) -> int:
        A_val = max(self.A.value(), 0.0)
        return int(math.ceil(math.sqrt(A_val))) if A_val > 0 else 1

    def _rebuild_rows_and_recalc(self):
        if self.Npos.value() == 0:
            self._set_row_count(self._auto_positions())
        self._recalc_live()

    def _set_row_count(self, n: int):
        self._building = True
        if n != self.table.rowCount():
            self.table.setRowCount(n)
            for r in range(n):
                if not self.table.item(r, 0):
                    self.table.setItem(r, 0, QTableWidgetItem(str(r + 1)))
        self._building = False

    # ===================== Build grid & LIVE =====================
    def build_grid(self):
        sizes = self._selected_sizes()
        if not sizes:
            cls = int(self.iso_class.currentText())
            sizes_dict = self.ISO_TABLE.get(cls, {})
            avail = [s for s, lim in sizes_dict.items() if lim is not None]
            avail.sort()
            if not avail:
                QMessageBox.warning(self, "Classe ISO", "Aucune taille applicable pour cette classe.")
                return

            self._building = True
            self.size_list.clear()
            for s in avail:
                text = f"{s:.1f} µm  (≤ {int(sizes_dict[s]):,} /m³)".replace(",", " ")
                it = QListWidgetItem(text)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if s == avail[0] else Qt.Unchecked)
                self.size_list.addItem(it)
            self._building = False
            sizes = [(avail[0], sizes_dict[avail[0]])]

        # Build table (concentrations directes /m³)
        self._building = True
        self.table.clear()

        headers = ["Pos"] + [f"Concentration @ {s:.1f} µm (/m³)" for s, _ in sizes]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        # Ajouter info-bulles: limites /m³
        for j, (s, lim) in enumerate(sizes, start=1):
            hdr = QTableWidgetItem(headers[j])
            hdr.setToolTip(f"Limite ISO: ≤ {int(lim):,} /m³".replace(",", " "))
            self.table.setHorizontalHeaderItem(j, hdr)

        n_rows = self.Npos.value() or self._auto_positions()
        self.table.setRowCount(n_rows)
        for r in range(n_rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(r + 1)))
            for j in range(1, len(headers)):
                if not self.table.item(r, j):
                    self.table.setItem(r, j, QTableWidgetItem(""))

        self._building = False

        # Cache pour le recalcul
        self._grid_meta = {"sizes": sizes}
        self._recalc_live()

    def _recalc_live(self, *args, **kwargs):
        if self._building or not self._grid_meta:
            return

        sizes = self._grid_meta["sizes"]

        n_rows = self.table.rowCount()
        n_sizes = len(sizes)
        n_total = n_rows * n_sizes
        n_filled = 0
        n_viol = 0

        pos_results = []

        for r in range(n_rows):
            pos_ok = True
            size_results = []

            for j, (s, lim) in enumerate(sizes, start=1):
                item = self.table.item(r, j)
                txt = (item.text() if item else "").strip()

                if txt == "":
                    # neutre visuel
                    if item:
                        item.setBackground(QColor(255, 255, 255))
                        item.setToolTip(f"Limite ISO: ≤ {int(lim):,} /m³".replace(",", " "))
                    size_results.append({
                        "size_um": s,
                        "conc_part_m3": None,
                        "limit": lim,
                        "ok": None,
                    })
                    continue

                try:
                    conc = float(txt.replace(",", "."))
                except Exception:
                    conc = 0.0

                n_filled += 1
                ok = conc <= float(lim)

                if item:
                    item.setToolTip(f"valeur = {conc:,.0f} /m³  |  limite = {int(lim):,} /m³".replace(",", " "))
                    item.setBackground(QColor(220, 255, 220) if ok else QColor(255, 220, 220))

                if not ok:
                    pos_ok = False
                    n_viol += 1

                size_results.append({
                    "size_um": s,
                    "conc_part_m3": conc,
                    "limit": lim,
                    "ok": ok,
                })

            pos_results.append({
                "position": r + 1,
                "ok": pos_ok if n_sizes == 0 else pos_ok,
                "sizes": size_results,
            })

        # Statut global progressif
        if n_filled == 0:
            glob_ok = None
        elif n_viol > 0:
            glob_ok = False
        elif n_filled < n_total:
            glob_ok = None
        else:
            glob_ok = True

        set_status_pill(self.status, glob_ok)

        self._last_result = {
            "iso_class": int(self.iso_class.currentText()),
            "sizes_selected": [{"size_um": s, "limit": lim} for (s, lim) in sizes],
            "A_m2": self.A.value(),
            "N_positions": n_rows,
            "positions": pos_results,
            "conforme": glob_ok,
        }

    # ===================== Save =====================
    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Saisissez des concentrations d'abord.")
            return

        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return

        # Correction logique conformité globale :
        # - False si au moins une violation
        # - True si toutes les cellules sont remplies et aucune violation
        # - None sinon (pas de saisie ou incomplet)
        res = self._last_result
        glob_ok = res.get("conforme")
        if glob_ok is None:
            # recalcul de secours si besoin
            n_total = res.get("N_positions", 0) * len(res.get("sizes_selected", []))
            n_filled = 0
            n_viol = 0
            for pos in res.get("positions", []):
                for sz in pos.get("sizes", []):
                    if sz.get("conc_part_m3") is not None:
                        n_filled += 1
                        if not sz.get("ok", True):
                            n_viol += 1
            if n_filled == 0:
                glob_ok = None
            elif n_viol > 0:
                glob_ok = False
            elif n_filled < n_total:
                glob_ok = None
            else:
                glob_ok = True
            self._last_result["conforme"] = glob_ok

        params = {
            "iso_class": self._last_result.get("iso_class"),
            "sizes": self._last_result.get("sizes_selected"),
            "A_m2": self._last_result.get("A_m2"),
            "N_positions": self._last_result.get("N_positions"),
        }

        TestManager(self.db).save_test(
            pid,
            "Particle_Class",
            self._last_result.get("conforme"),
            params,
            self._last_result,
        )

        QMessageBox.information(self, "OK", "Résultat enregistré.")

class RecoveryPage(QWidget):
    """Recovery time – **ultra simple** (juste comparer un temps mesuré en minutes au seuil t_max)

    • Aucune série t,C. Pas de C0. Pas de calculs de concentration.
    • On choisit la **classe ISO** et la **taille** uniquement pour traçabilité (affiche la limite ISO en info),
      mais la conformité se fait **uniquement** sur le temps mesuré vs t_max.
    • Évaluation **LIVE** (à la volée) + pastille de statut.
    """

    ISO_TABLE: Dict[int, Dict[float, float]] = {
        1: {0.1: 10,       0.2: None,     0.3: None,     0.5: None,      1.0: None,     5.0: None},
        2: {0.1: 100,      0.2: 24,       0.3: 10,       0.5: None,      1.0: None,     5.0: None},
        3: {0.1: 1000,     0.2: 237,      0.3: 102,      0.5: 35,        1.0: None,     5.0: None},
        4: {0.1: 10000,    0.2: 2370,     0.3: 1020,     0.5: 352,       1.0: 83,       5.0: None},
        5: {0.1: 100000,   0.2: 23700,    0.3: 10200,    0.5: 3520,      1.0: 832,      5.0: None},
        6: {0.1: 1000000,  0.2: 237000,   0.3: 102000,   0.5: 35200,     1.0: 8320,     5.0: 293},
        7: {0.1: None,     0.2: None,     0.3: None,     0.5: 352000,    1.0: 83200,    5.0: 2930},
        8: {0.1: None,     0.2: None,     0.3: None,     0.5: 3520000,   1.0: 832000,   5.0: 29300},
        9: {0.1: None,     0.2: None,     0.3: None,     0.5: 35200000,  1.0: 8320000,  5.0: 293000},
    }

    def __init__(self, appDB, get_project_id):
        super().__init__()
        self.db = appDB
        self.get_project_id = get_project_id

        # --- Sélection ISO + taille (pour info) ---
        self.iso_class = QComboBox(); self.iso_class.addItems([str(i) for i in range(1, 10)])
        self.size_um = QComboBox()  # tailles applicables à la classe
        self.iso_class.currentIndexChanged.connect(self._on_class_changed)
        self.size_um.currentIndexChanged.connect(self._update_iso_info)

        # --- Seuil & mesure (minutes) ---
        self.t_max = QDoubleSpinBox(); self.t_max.setRange(0, 1000); self.t_max.setDecimals(0)
        self.t_measured = QDoubleSpinBox(); self.t_measured.setRange(0, 1000); self.t_measured.setDecimals(1)
        # État initial neutre jusqu'à ce que l'utilisateur modifie t_mesuré
        self._t_touched = False
        self.t_measured.valueChanged.connect(self._on_time_changed)
        self.t_max.valueChanged.connect(self._recalc_live)

        # --- Affichages ---
        self.lbl_iso_limit = QLabel("—")  # affiche la limite ISO de la taille (pour traçabilité)
        self.lbl_margin = QLabel("—")      # marge = t_max − t_mesuré
        self.lbl_big_time = QLabel("0.0 min")
        self.lbl_big_time.setStyleSheet("font-size: 28px; font-weight: 600; padding: 6px 10px;")

        self.status = QLabel(); set_status_pill(self.status, None)

        # --- Disposition ---
        f_top = QFormLayout()
        f_top.addRow("Classe ISO", self.iso_class)
        f_top.addRow("Taille considérée (µm)", self.size_um)
        f_top.addRow("Limite ISO (réf /m³)", self.lbl_iso_limit)

        card = QGroupBox("Temps mesuré")
        fc = QFormLayout(card)
        fc.addRow("t_mesuré (min)", self.t_measured)
        fc.addRow("Seuil t_max (min)", self.t_max)
        fc.addRow("Marge (min)", self.lbl_margin)

        # bandeau grand affichage
        banner = QGroupBox("Résumé")
        vb = QVBoxLayout(banner)
        vb.addWidget(self.lbl_big_time)
        vb.addWidget(self.status)

        btn_save = QPushButton("Enregistrer")
        btn_save.clicked.connect(self.on_save)

        root = QVBoxLayout(self)
        root.addLayout(f_top)
        root.addWidget(card)
        root.addWidget(banner)
        root.addWidget(btn_save)

        self._refresh_thresholds()
        self._on_class_changed()
        self._recalc_live()

    # --- Seuil par projet ---
    def _refresh_thresholds(self):
        pid = self.get_project_id()
        tmax = TestManager(self.db).get_threshold(pid, "Recovery_Time", "t_max_cible_min", "20")
        try:
            self.t_max.setValue(float(tmax))
        except Exception:
            self.t_max.setValue(20)

    # --- Remplir tailles selon la classe ---
    def _on_class_changed(self):
        cls = int(self.iso_class.currentText())
        sizes = [s for s, lim in self.ISO_TABLE.get(cls, {}).items() if lim is not None]
        sizes.sort()
        self.size_um.blockSignals(True)
        self.size_um.clear()
        for s in sizes:
            self.size_um.addItem(f"{s:.1f}", s)
        self.size_um.blockSignals(False)
        self._update_iso_info()

    def _update_iso_info(self):
        cls = int(self.iso_class.currentText())
        if self.size_um.count() == 0:
            self.lbl_iso_limit.setText("—")
            return
        s = float(self.size_um.currentData())
        lim = self.ISO_TABLE.get(cls, {}).get(s)
        self.lbl_iso_limit.setText(f"≤ {int(lim):,} /m³".replace(",", " "))

    # --- LIVE ---
    def _on_time_changed(self, *args, **kwargs):
        # Marque que l'utilisateur a manipulé le champ temps
        self._t_touched = True
        self._recalc_live()

    def _recalc_live(self):
        t = self.t_measured.value()
        tmax = self.t_max.value()
        # État neutre tant que l'utilisateur n'a pas renseigné le temps
        if not hasattr(self, "_t_touched") or not self._t_touched:
            self.lbl_big_time.setText(f"{t:.1f} min")
            self.lbl_margin.setText("—")
            set_status_pill(self.status, None)
            self._last_result = {
                "iso_class": int(self.iso_class.currentText()),
                "size_um": float(self.size_um.currentData()) if self.size_um.count() else None,
                "t_measured_min": t,
                "t_max_min": tmax,
                "margin_min": None,
                "conforme": None,
            }
            return

        self.lbl_big_time.setText(f"{t:.1f} min")
        margin = tmax - t
        self.lbl_margin.setText(f"{margin:+.1f}")
        ok = None
        if t > 0 or tmax > 0:
            ok = t <= tmax
        set_status_pill(self.status, ok)
        self._last_result = {
            "iso_class": int(self.iso_class.currentText()),
            "size_um": float(self.size_um.currentData()) if self.size_um.count() else None,
            "t_measured_min": t,
            "t_max_min": tmax,
            "margin_min": margin,
            "conforme": ok,
        }

    # --- Save ---
    def on_save(self):
        if not hasattr(self, "_last_result"):
            QMessageBox.information(self, "Info", "Saisissez un temps mesuré.")
            return
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return

        # Correction logique conformité globale :
        # - False si t_mesuré > t_max
        # - True si t_mesuré ≤ t_max (et temps renseigné)
        # - None sinon (pas de saisie)
        res = self._last_result
        t = res.get("t_measured_min")
        tmax = res.get("t_max_min")
        ok = None
        if t is not None and t > 0 and tmax is not None and tmax > 0:
            ok = t <= tmax
        self._last_result["conforme"] = ok

        TestManager(self.db).save_test(
            pid,
            "Recovery_Time",
            ok,
            {
                "iso_class": res.get("iso_class"),
                "size_um": res.get("size_um"),
                "t_max_min": res.get("t_max_min"),
            },
            self._last_result,
        )
        QMessageBox.information(self, "OK", "Résultat enregistré.")


class SmokePage(QWidget):
    """
    Visualisation de fumée **statique** – version simple & élégante (pilotée par le technicien)

    LOGIQUE
    -------
    • 1 ligne = 1 scène/prise :
        - ID du film (référence vidéo/photo),
        - Zone/Scénario (ex: SAS, Porte ouverte, Poste A… ),
        - Coche les observations : Effet piston / Pas de stagnation / **Fuite non observée** / Extraction & pulsion OK,
        - Choisit la Conformité : — / Conforme / Non conforme,
        - Le "Descriptif" est généré automatiquement à partir des cases (modifiable via "Commentaire" si besoin).
    • Pastille globale (LIVE) :
        - Verte si **toutes les lignes** sont « Conforme »,
        - Rouge si **au moins une** ligne est « Non conforme »,
        - Tiret (—) s’il n’y a pas encore de choix de conformité.

    RÈGLE SUPPLÉMENTAIRE
    ---------------------
    • Pour pouvoir sélectionner « Conforme » sur une ligne, **toutes les cases** doivent être au vert :
        Effet piston = ✓, Pas de stagnation = ✓, Fuite non observée = ✓, Extraction & pulsion OK = ✓.
      Sinon, la sélection « Conforme » est **refusée** (alerte) et la valeur revient à « — ».
    """

    TEST_KEY = "Smoke_Visual_Static"  # clé d'enregistrement DB explicite « statique »

    def __init__(self, appDB, get_project_id):
        super().__init__()
        self.db = appDB
        self.get_project_id = get_project_id
        self._updating = False  # évite les boucles itemChanged

        # --- Guide / Aide ---
        guide = QGroupBox("Comment utiliser – Visualisation de fumée (statique)")
        gl = QVBoxLayout(guide)
        lbl = QLabel(
            "1) Ajoutez une ligne par scène/prise et renseignez l'ID du film et la zone.\n"
            "2) Cochez les observations pertinentes (effet piston, stagnation, fuite, extraction/pulsion).\n"
            "3) Sélectionnez la conformité. Le descriptif auto s’actualise.\n"
            "4) Pastille globale LIVE. ‘Conforme’ n’est autorisé que si toutes les cases sont au vert."
        )
        lbl.setWordWrap(True)
        gl.addWidget(lbl)

        # --- Tableau ---
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID Film", "Zone/Scénario",
            "Effet piston", "Pas de stagnation", "Fuite non observée", "Extraction & pulsion OK",
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
        cb.currentTextChanged.connect(self._on_conformite_changed)
        return cb

    def _row_of_widget(self, w: QComboBox) -> Optional[int]:
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 6) is w:
                return r
        return None

    def add_row(self, film_id: Optional[str] = None, zone: Optional[str] = None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._updating = True
        try:
            # ID Film
            self.table.setItem(r, 0, QTableWidgetItem(film_id or f"F-{r+1:03d}"))
            # Zone / Scénario
            self.table.setItem(r, 1, QTableWidgetItem(zone or ""))

            # Cases à cocher (par défaut : tout au vert)
            self.table.setItem(r, 2, self._make_checkbox_item(checked=True))    # Effet piston
            self.table.setItem(r, 3, self._make_checkbox_item(checked=True))    # Pas de stagnation
            self.table.setItem(r, 4, self._make_checkbox_item(checked=True))    # Fuite non observée (✓ = OK)
            self.table.setItem(r, 5, self._make_checkbox_item(checked=True))    # Extraction & pulsion OK

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

        self._enforce_row_rules(r)
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

    def _set_conformite_text(self, r: int, text: str):
        w = self.table.cellWidget(r, 6)
        if isinstance(w, QComboBox):
            self._updating = True
            try:
                w.setCurrentText(text)
            finally:
                self._updating = False

    def _row_all_checks_good(self, r: int) -> bool:
        eff_piston = self._is_checked(r, 2) is True
        no_stag    = self._is_checked(r, 3) is True
        no_leak    = self._is_checked(r, 4) is True  # « Fuite non observée » doit être cochée
        ep_ok      = self._is_checked(r, 5) is True
        return eff_piston and no_stag and no_leak and ep_ok

    def _update_row_descriptif(self, r: int):
        eff_piston = self._is_checked(r, 2)
        no_stag    = self._is_checked(r, 3)
        no_leak    = self._is_checked(r, 4)
        ep_ok      = self._is_checked(r, 5)

        phrases = []
        phrases.append("Effet piston observé" if eff_piston else "Effet piston non démontré")
        phrases.append("Pas de stagnation" if no_stag else "Stagnations visibles")
        phrases.append("Fuite non observée" if no_leak else "Fuite observée")
        phrases.append("Extraction & pulsion fonctionnelles" if ep_ok else "Anomalie extraction/pulsion")

        text = " ; ".join(phrases)
        self._updating = True
        try:
            self.table.setItem(r, 7, QTableWidgetItem(text))
        finally:
            self._updating = False

    # ---------- LIVE evaluation & enforcement ----------
    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating:
            return
        # Toute modif d'une case (2..5) ou d'un champ texte regénère le descriptif & règles
        if item.column() in (2, 3, 4, 5):
            self._update_row_descriptif(item.row())
            self._enforce_row_rules(item.row())
        self.evaluate_live()

    def _on_conformite_changed(self, *_):
        if self._updating:
            return
        # Trouver la ligne du combo émetteur
        cb = self.sender()
        r = self._row_of_widget(cb)
        if r is None:
            return
        # Si l'utilisateur choisit « Conforme » mais que toutes les cases ne sont pas ok → refuser
        if cb.currentText() == "Conforme" and not self._row_all_checks_good(r):
            QMessageBox.information(
                self,
                "Règle conformité",
                "Pour valider ‘Conforme’, toutes les cases doivent être cochées :\n"
                "- Effet piston\n- Pas de stagnation\n- Fuite non observée\n- Extraction & pulsion OK"
            )
            self._set_conformite_text(r, "—")
        self.evaluate_live()

    def _enforce_row_rules(self, r: int):
        # Si une case est décochée alors que la ligne était ‘Conforme’, on repasse à « — »
        if not self._row_all_checks_good(r) and self._conformite_text(r) == "Conforme":
            self._set_conformite_text(r, "—")

    def evaluate_live(self):
        """Met à jour la pastille globale en fonction des choix de conformité."""
        n = self.table.rowCount()
        if n == 0:
            set_status_pill(self.status, None)
            return
        any_nc = False
        all_ok = True
        any_set = False
        for r in range(n):
            conf = self._conformite_text(r)
            if conf == "Non conforme":
                any_nc = True
                any_set = True
            elif conf == "Conforme":
                any_set = True
            else:  # « — »
                all_ok = False
        if any_nc:
            set_status_pill(self.status, False)
        elif all_ok and any_set:
            set_status_pill(self.status, True)
        else:
            set_status_pill(self.status, None)

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
                "fuite_non_observee": self._is_checked(r, 4),
                "extraction_pulsion_ok": self._is_checked(r, 5),
                "conformite": self._conformite_text(r),
                "descriptif_auto": self.table.item(r, 7).text() if self.table.item(r, 7) else "",
                "commentaire": self.table.item(r, 8).text() if self.table.item(r, 8) else "",
            }
            rows.append(row)

        # Correction logique conformité globale :
        # - False si au moins une ligne "Non conforme"
        # - True si toutes les lignes sont "Conforme" (et au moins une ligne)
        # - None sinon (pas de saisie ou incomplet)
        if not rows:
            ok_global = None
        elif any(r["conformite"] == "Non conforme" for r in rows):
            ok_global = False
        elif all(r["conformite"] == "Conforme" for r in rows if r["conformite"] in ("Conforme", "Non conforme")) and any(r["conformite"] == "Conforme" for r in rows):
            ok_global = True
        else:
            ok_global = None

        result = {
            "type": "visualisation_fumee_statique",
            "scenes": rows,
            "conforme": ok_global
        }

        TestManager(self.db).save_test(pid, self.TEST_KEY, ok_global, {}, result)
        QMessageBox.information(self, "OK", "Résultat enregistré.")

class TempRHPage(QWidget):
    """
    Température & Humidité — **cible ± tolérance (même unité)**, saisie directe

    • Tu définis : T_cible (°C), tolérance T (±°C), RH_cible (%), tolérance RH (±points %).
    • Tu choisis le **nombre de points** puis « Générer ».
    • Tu saisis directement T et RH **dans le tableau** (pas de boîte de dialogue).
    • Statut ligne = "Conforme" si T et RH sont **tous deux** dans la fenêtre. Global = vert si tous les points mesurés sont conformes.
    """

    COLS = ["Point", "T (°C)", "RH (%)", "Statut", "Actions"]

    def __init__(self, db, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self._updating = False

        # -------- Cibles & tolérances (absolues, même unité) --------
        self.T_cible = QDoubleSpinBox(); self.T_cible.setRange(-100, 200); self.T_cible.setDecimals(1)
        self.tol_T   = QDoubleSpinBox(); self.tol_T.setRange(0, 50);     self.tol_T.setDecimals(1)
        self.RH_cible = QDoubleSpinBox(); self.RH_cible.setRange(0, 100); self.RH_cible.setDecimals(1)
        self.tol_RH   = QDoubleSpinBox(); self.tol_RH.setRange(0, 50);     self.tol_RH.setDecimals(1)
        self._refresh_thresholds()

        self.T_cible.setToolTip("Cible température (°C)")
        self.tol_T.setToolTip("Tolérance absolue ± (°C)")
        self.RH_cible.setToolTip("Cible humidité relative (%)")
        self.tol_RH.setToolTip("Tolérance absolue ± (points de %)")

        # Fenêtres courantes
        self.lbl_windows = QLabel(); self._update_windows_label()

        # Nombre de points
        self.n_points = QSpinBox(); self.n_points.setRange(1, 500); self.n_points.setValue(3)
        b_gen = QPushButton("Générer"); b_gen.clicked.connect(self._on_generate_points)

        # Guide
        guide = QGroupBox("Guide rapide")
        gtxt = QLabel(
            "1) Règle **T/RH cibles** et **tolérances** (absolues).\n"
            "2) Choisis le **Nombre de points** puis ‘Générer’.\n"
            "3) Saisis T et RH **dans le tableau** → conformité instantanée."
        )
        gtxt.setWordWrap(True)
        gl = QVBoxLayout(guide); gl.addWidget(gtxt)

        # Top bar
        top = QFormLayout()
        top.addRow("T cible (°C)", self.T_cible)
        top.addRow("Tolérance T (±°C)", self.tol_T)
        top.addRow("RH cible (%)", self.RH_cible)
        top.addRow("Tolérance RH (±%)", self.tol_RH)
        top.addRow("Fenêtres actuelles", self.lbl_windows)

        pts_row = QHBoxLayout()
        pts_row.addWidget(QLabel("Nombre de points"))
        pts_row.addWidget(self.n_points)
        pts_row.addWidget(b_gen)
        pts_row.addStretch(1)

        # Tableau simple (saisie directe)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked | QTableWidget.AnyKeyPressed)
        self.table.itemChanged.connect(self._on_item_changed)

        # Statut global
        self.status = QLabel(); set_status_pill(self.status, None)

        # Actions globaux
        b_add_point = QPushButton("+ Point"); b_add_point.clicked.connect(self.add_point)
        b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.on_save)
        if 'ThresholdEditor' in globals():
            b_th = QPushButton("Seuils…"); b_th.clicked.connect(self.edit_thresholds)
        else:
            b_th = None

        actions = QHBoxLayout(); actions.addWidget(b_add_point); actions.addStretch(1); actions.addWidget(b_save)
        if b_th: actions.addWidget(b_th)

        # Layout principal
        root = QVBoxLayout(self)
        root.addWidget(guide)
        root.addLayout(top)
        root.addLayout(pts_row)
        root.addWidget(self.table)
        root.addLayout(actions)
        root.addWidget(self.status)

        # Données en mémoire
        self.points: List[Dict[str, Any]] = []  # {name, T: Optional[float], RH: Optional[float]}
        self._generate_points(self.n_points.value())

        # LIVE : recalcul à chaque changement des fenêtres
        for w in (self.T_cible, self.tol_T, self.RH_cible, self.tol_RH):
            w.valueChanged.connect(self._on_targets_changed)

    # ----------------- Utils table -----------------
    def _ensure_item(self, r: int, c: int, editable: bool = False) -> QTableWidgetItem:
        it = self.table.item(r, c)
        if it is None:
            it = QTableWidgetItem("—")
            self.table.setItem(r, c, it)
        # appliquer droit d'édition
        if editable:
            it.setFlags(it.flags() | Qt.ItemIsEditable)
        else:
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    # ----------------- Seuils projet -----------------
    def _refresh_thresholds(self) -> None:
        pid = self.get_project_id()
        def _get(k: str, dflt: float) -> float:
            try:
                return float(self.db.get_threshold(pid, "Temp_RH", k, str(dflt)))
            except Exception:
                return dflt
        self.T_cible.setValue(_get("T_cible", 21.0))
        self.tol_T.setValue(_get("tol_T_degC", 2.0))
        self.RH_cible.setValue(_get("RH_cible", 50.0))
        self.tol_RH.setValue(_get("tol_RH_pct", 5.0))  # tolérance absolue en points de %

    def edit_thresholds(self) -> None:
        w = ThresholdEditor(self.db, self.get_project_id(), "Temp_RH", ["T_cible", "tol_T_degC", "RH_cible", "tol_RH_pct"])
        w.setWindowModality(Qt.ApplicationModal)
        w.setWindowTitle("Seuils – T/RH (cible ± tolérance)")
        w.show(); self._th_win = w

    # ----------------- Fenêtres -----------------
    def _current_windows(self) -> Dict[str, float]:
        return {
            "Tlo": self.T_cible.value() - self.tol_T.value(),
            "Thi": self.T_cible.value() + self.tol_T.value(),
            "RHlo": self.RH_cible.value() - self.tol_RH.value(),
            "RHhi": self.RH_cible.value() + self.tol_RH.value(),
        }

    def _update_windows_label(self) -> None:
        w = self._current_windows()
        self.lbl_windows.setText(f"T : [{w['Tlo']:.1f} ; {w['Thi']:.1f}] °C    |    RH : [{w['RHlo']:.1f} ; {w['RHhi']:.1f}] %")

    def _on_targets_changed(self) -> None:
        self._update_windows_label()
        self._update_all_rows_and_global()

    # ----------------- Points -----------------
    def _on_generate_points(self) -> None:
        n = self.n_points.value()
        if any(p.get("T") is not None or p.get("RH") is not None for p in getattr(self, "points", [])):
            ok = QMessageBox.question(self, "Remplacer les points", "Des mesures existent. Remplacer la liste des points ?", QMessageBox.Yes | QMessageBox.No)
            if ok != QMessageBox.Yes:
                return
        self._generate_points(n)

    def _generate_points(self, n: int) -> None:
        self.points = []
        self.table.setRowCount(0)
        for i in range(n):
            self.add_point(f"Point {i+1}")
        self._update_all_rows_and_global()

    def add_point(self, name: Optional[str] = None) -> None:
        self.points.append({"name": name or f"Point {len(self.points)+1}", "T": None, "RH": None})
        self._insert_row(len(self.points)-1)

    def _insert_row(self, idx: int) -> None:
        self.table.insertRow(idx)
        for c in range(len(self.COLS)):
            self._ensure_item(idx, c)  # crée les items

        # Point (éditable)
        it_name = self._ensure_item(idx, 0, editable=True)
        it_name.setText(self.points[idx]["name"]) 

        # T & RH (éditables)
        self._ensure_item(idx, 1, editable=True)
        self._ensure_item(idx, 2, editable=True)

        # Statut non éditable
        self._ensure_item(idx, 3, editable=False)

        # Actions: Supprimer
        btn_del = QPushButton("Supprimer")
        btn_del.clicked.connect(lambda _, r=idx: self._delete_point(r))
        cell = QWidget(); hl = QHBoxLayout(cell); hl.setContentsMargins(0,0,0,0); hl.addWidget(btn_del); hl.addStretch(1)
        self.table.setCellWidget(idx, 4, cell)

    def _delete_point(self, row: int) -> None:
        del self.points[row]
        self.table.removeRow(row)
        # Re-bind des boutons restants (leurs lambdas capturent l'index)
        for r in range(self.table.rowCount()):
            cell = self.table.cellWidget(r, 4)
            if not cell: continue
            btns = cell.findChildren(QPushButton)
            if not btns: continue
            try: btns[0].clicked.disconnect()
            except Exception: pass
            btns[0].clicked.connect(lambda _, rr=r: self._delete_point(rr))
        self._update_global_status()

    # ----------------- Saisie & calcul -----------------
    def _parse_cell_float(self, item: QTableWidgetItem) -> Optional[float]:
        if not item: return None
        txt = (item.text() or "").strip().lower().replace(",", ".")
        if not txt or txt == "—":
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating: return
        r, c = item.row(), item.column()
        if r >= len(self.points):
            return
        if c == 0:
            # Nom du point
            self.points[r]["name"] = (item.text() or "").strip() or f"Point {r+1}"
        elif c in (1, 2):
            # T ou RH modifié → mettre à jour le modèle puis la ligne
            val = self._parse_cell_float(item)
            key = "T" if c == 1 else "RH"
            self.points[r][key] = val
            self._update_row(r)
            self._update_global_status()
        # sinon: colonne statut non éditable, actions = boutons

    def _in_window(self, v: float, lo: float, hi: float) -> bool:
        return (v >= lo) and (v <= hi)

    def _update_row(self, idx: int) -> None:
        p = self.points[idx]
        w = self._current_windows()
        loT, hiT = w["Tlo"], w["Thi"]
        loH, hiH = w["RHlo"], w["RHhi"]

        # Afficher T / RH (re-normaliser si champ vide)
        self._updating = True
        try:
            self._ensure_item(idx, 1, editable=True).setText("—" if p.get("T") is None else f"{p['T']:.1f}")
            self._ensure_item(idx, 2, editable=True).setText("—" if p.get("RH") is None else f"{p['RH']:.1f}")
        finally:
            self._updating = False

        # Statut
        stat_it = self._ensure_item(idx, 3, editable=False)
        if p.get("T") is None or p.get("RH") is None:
            stat_it.setText("—")
            stat_it.setBackground(QBrush(Qt.transparent))
            stat_it.setForeground(QBrush(Qt.black))
        else:
            ok = self._in_window(p["T"], loT, hiT) and self._in_window(p["RH"], loH, hiH)
            stat_it.setText("Conforme" if ok else "Non conforme")
            stat_it.setBackground(QBrush(QColor(40, 167, 69) if ok else QColor(220, 53, 69)))
            stat_it.setForeground(QBrush(Qt.white))

    def _update_all_rows_and_global(self) -> None:
        for r in range(self.table.rowCount()):
            self._update_row(r)
        self._update_global_status()

    def _update_global_status(self) -> None:
        w = self._current_windows()
        any_measured = False
        any_nc = False
        for p in self.points:
            if p.get("T") is None or p.get("RH") is None:
                continue
            any_measured = True
            if not (w['Tlo'] <= p['T'] <= w['Thi'] and w['RHlo'] <= p['RH'] <= w['RHhi']):
                any_nc = True
        if any_nc:
            set_status_pill(self.status, False)
        elif any_measured:
            set_status_pill(self.status, True)
        else:
            set_status_pill(self.status, None)

    # ----------------- Save -----------------
    def on_save(self) -> None:
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez un projet.")
            return

        w = self._current_windows()
        measured = [p for p in self.points if p.get("T") is not None and p.get("RH") is not None]
        if not measured:
            ok_global = None
        elif any(not (w['Tlo'] <= p['T'] <= w['Thi'] and w['RHlo'] <= p['RH'] <= w['RHhi']) for p in measured):
            ok_global = False
        elif all((w['Tlo'] <= p['T'] <= w['Thi'] and w['RHlo'] <= p['RH'] <= w['RHhi']) for p in measured):
            ok_global = True
        else:
            ok_global = None

        payload = {
            "seuils": {
                "T_cible": self.T_cible.value(),
                "tol_T_degC": self.tol_T.value(),
                "RH_cible": self.RH_cible.value(),
                "tol_RH_pct": self.tol_RH.value(),
                "fenetres": w,
            },
            "points": [
                {"id": p["name"], "T": p.get("T"), "RH": p.get("RH")}
                for p in self.points
            ],
            "conforme": ok_global,
        }

        TestManager(self.db).save_test(pid, "Temp_RH", ok_global, {}, payload)
        QMessageBox.information(self, "OK", "Résultat enregistré.")
