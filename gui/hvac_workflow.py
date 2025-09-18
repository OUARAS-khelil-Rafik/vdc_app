# gui/hvac_workflow.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QComboBox, QSpinBox, QMessageBox, QTabWidget, QFormLayout,
    QDialog, QDialogButtonBox, QAbstractItemView, QListWidget, QListWidgetItem, QSplitter
)

from models.testmanager import TestManager

# === tes pages HVAC existantes (comme dans ta base) ===
from test_pages.HVAC_pages import (
    ACPHPage, DeltaPPage, HEPALeakPage, ParticleClassPage, RecoveryPage,
    TempRHPage, SmokePage, SmokeDynamicPage
)

# --------- Thème ----------
THEME_PRIMARY = "#1c5ea3"
THEME_ACCENT  = "#b8d5ed"
THEME_BG      = "#f5f8fc"
CARD_BG       = "#ffffff"
CARD_BORDER   = "#dbe7f5"

def set_status_pill(label: QLabel, ok: Optional[bool]):
    if ok is None:
        label.setText("—")
        label.setStyleSheet("QLabel { background:#9e9e9e; color:white; padding:6px 12px; border-radius:12px; font-weight:600; }")
    elif ok:
        label.setText("Conforme")
        label.setStyleSheet("QLabel { background:#28a745; color:white; padding:6px 12px; border-radius:12px; font-weight:600; }")
    else:
        label.setText("Non conforme")
        label.setStyleSheet("QLabel { background:#dc3545; color:white; padding:6px 12px; border-radius:12px; font-weight:600; }")

# ---------- Registre des tests ----------
TEST_REGISTRY = [
    {"code": "ACPH",                 "label": "Débit & ACPH",                        "widget": ACPHPage},
    {"code": "DeltaP",               "label": "Cascade de pressions (ΔP)",           "widget": DeltaPPage},
    {"code": "HEPA_Leak",            "label": "Intégrité filtres HEPA",              "widget": HEPALeakPage},
    {"code": "Particle_Class",       "label": "Comptage particulaire (ISO 14644-1)", "widget": ParticleClassPage},
    {"code": "Recovery_Time",        "label": "Recovery time",                       "widget": RecoveryPage},
    {"code": "Temp_RH",              "label": "Température & Humidité",              "widget": TempRHPage},
    {"code": "Smoke_Visual_Static",  "label": "Fumée (statique)",                    "widget": SmokePage},
    {"code": "Smoke_Visual_Dynamic", "label": "Fumée (dynamique)",                   "widget": SmokeDynamicPage},
]

# ================== Sélecteur d’étalon (OK only) ==================
class StandardPicker(QDialog):
    """
    N’affiche QUE les étalons “OK” :
      - blocked == 0
      - next_cal_date vide OU >= aujourd’hui (ISO)
    """
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.selected: Optional[Dict[str, Any]] = None
        self.setWindowTitle("Choisir un étalon")
        self.resize(780, 420)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "S/N", "Nom", "Catégorie", "Modèle", "Prochaine cal."])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addWidget(btns)

        self._populate()
        self.setStyleSheet(f"""
            QDialog {{ background:{THEME_BG}; }}
            QTableWidget {{ background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:8px; }}
            QDialogButtonBox QPushButton {{ background:{THEME_PRIMARY}; color:#fff; border-radius:8px; padding:6px 14px; }}
            QDialogButtonBox QPushButton:hover {{ background:{THEME_ACCENT}; color:{THEME_PRIMARY}; }}
        """)

    @staticmethod
    def _ok_row(blocked, next_cal_date: Optional[str]) -> bool:
        if int(blocked or 0) != 0:
            return False
        if not next_cal_date:
            return True
        try:
            return datetime.fromisoformat(next_cal_date) >= datetime.utcnow()
        except Exception:
            return False

    def _populate(self):
        cur = self.db.conn.cursor()
        rows = cur.execute("""
            SELECT id, serial, name, category, model, next_cal_date, blocked
            FROM standards
            ORDER BY name ASC
        """).fetchall()
        ok_rows = [r for r in rows if self._ok_row(r["blocked"], r["next_cal_date"])]
        self.table.setRowCount(0)
        for r, row in enumerate(ok_rows):
            self.table.insertRow(r)
            vals = [
                str(row["id"] or ""),
                row["serial"] or "",
                row["name"] or "",
                row["category"] or "",
                row["model"] or "",
                row["next_cal_date"] or "—",
            ]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)

    def accept(self):
        sel = self.table.currentRow()
        if sel < 0:
            QMessageBox.warning(self, "Sélection", "Choisissez un étalon.")
            return
        self.selected = {
            "id": int(self.table.item(sel, 0).text()),
            "serial": self.table.item(sel, 1).text(),
            "name": self.table.item(sel, 2).text(),
            "category": self.table.item(sel, 3).text(),
            "model": self.table.item(sel, 4).text(),
            "next_cal_date": self.table.item(sel, 5).text(),
        }
        super().accept()

# ================== Wrapper 2 phases (As Found / As Left) ==================
class TwoPhaseWrapper(QWidget):
    """
    Présentation très claire :
      - Bandeau Contexte (Projet + Etalon choisi sous forme de badge + bouton “Changer…”)
      - Onglets As Found / As Left
      - Barre d’actions en bas (copie AF→AL, pastilles, sauvegardes)
    """
    def __init__(self, db, get_project_id, test_code: str, widget_cls):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self.test_code = test_code
        self.widget_cls = widget_cls
        self.tm = TestManager(db)
        self.standard: Optional[Dict[str, Any]] = None

        # ==== Bandeau contexte (carte fine)
        ctx = QGroupBox("Contexte")
        f = QFormLayout(ctx)
        self.lbl_project = QLabel("Aucun projet sélectionné")
        self.badge_std   = QLabel("Étalon non choisi")
        self.badge_std.setStyleSheet("QLabel{background:#e3eaf6;color:#2c3e50;padding:6px 10px;border-radius:12px;}")
        self.btn_pick = QPushButton("Choisir / Changer d’étalon…")
        self.btn_pick.clicked.connect(self.pick_standard)
        f.addRow("Projet :", self.lbl_project)
        f.addRow("Étalon :", self.badge_std)
        f.addRow("", self.btn_pick)

        # ==== Pages de test
        self.tabs = QTabWidget()
        self.as_found = self.widget_cls(self.db, self.get_project_id)
        self.as_left  = self.widget_cls(self.db, self.get_project_id)
        self.tabs.addTab(self.as_found, "As Found")
        self.tabs.addTab(self.as_left,  "As Left")

        # ==== Barre d’actions
        actions = QHBoxLayout()
        self.btn_copy       = QPushButton("As Left = As Found")
        self.btn_save_found = QPushButton("Enregistrer As Found")
        self.btn_save_left  = QPushButton("Enregistrer As Left")
        self.btn_copy.clicked.connect(self.copy_as_found)
        self.btn_save_found.clicked.connect(lambda: self.save_phase("as_found"))
        self.btn_save_left.clicked.connect(lambda: self.save_phase("as_left"))

        self.pill_found = QLabel(); set_status_pill(self.pill_found, None)
        self.pill_left  = QLabel(); set_status_pill(self.pill_left,  None)

        actions.addWidget(self.btn_copy)
        actions.addStretch(1)
        actions.addWidget(QLabel("As Found"))
        actions.addWidget(self.pill_found)
        actions.addSpacing(12)
        actions.addWidget(QLabel("As Left"))
        actions.addWidget(self.pill_left)
        actions.addSpacing(12)
        actions.addWidget(self.btn_save_found)
        actions.addWidget(self.btn_save_left)

        # ==== Layout
        root = QVBoxLayout(self)
        root.addWidget(ctx)
        root.addWidget(self.tabs)
        root.addLayout(actions)

        self.setStyleSheet(f"""
            QWidget {{ background:{THEME_BG}; }}
            QGroupBox {{
                background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:12px;
                margin-top:10px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color:{THEME_PRIMARY}; }}
            QTabBar::tab {{ padding:8px 14px; font-weight:600; }}
            QTableWidget {{ background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:8px; }}
            QPushButton {{ background:{THEME_PRIMARY}; color:#fff; border-radius:8px; padding:8px 16px; font-weight:600; }}
            QPushButton:hover {{ background:{THEME_ACCENT}; color:{THEME_PRIMARY}; }}
            QLabel {{ color:#163b66; }}
        """)

        self.apply_lock()
        self.refresh_header()

    # ---------- Contexte
    def refresh_header(self):
        pid = self.get_project_id()
        if pid is None:
            self.lbl_project.setText("Aucun projet sélectionné")
        else:
            row = self.db.conn.execute(
                "SELECT company_name, location, room_tag, test_date FROM projects WHERE id=?", (pid,)
            ).fetchone()
            if row:
                self.lbl_project.setText(f"{row['company_name']} – {row['location'] or ''} – {row['room_tag'] or ''} (test: {row['test_date']})")
            else:
                self.lbl_project.setText("Projet introuvable")

        if self.standard:
            s = self.standard
            self.badge_std.setText(f"{s.get('name','')} ({s.get('model','')}, S/N {s.get('serial','')})")
            self.badge_std.setStyleSheet("QLabel{background:#e7f6ea;color:#0b6b33;padding:6px 10px;border-radius:12px;}")
        else:
            self.badge_std.setText("Étalon non choisi")
            self.badge_std.setStyleSheet("QLabel{background:#fff3cd;color:#7a5c00;padding:6px 10px;border-radius:12px;}")

    def pick_standard(self):
        dlg = StandardPicker(self.db, self)
        if dlg.exec_() == QDialog.Accepted and dlg.selected:
            self.standard = dlg.selected
        self.refresh_header()
        self.apply_lock()

    def apply_lock(self):
        ok = (self.standard is not None)
        for w in (self.tabs, self.btn_copy, self.btn_save_found, self.btn_save_left):
            w.setEnabled(ok)

    # ---------- Phases
    def copy_as_found(self):
        if not hasattr(self.as_found, "_last_result"):
            QMessageBox.information(self, "As Found manquant", "Saisissez d’abord le As Found.")
            return
        self.as_left._last_result = dict(self.as_found._last_result)
        QMessageBox.information(self, "Copie", "As Left = As Found.")
        self.refresh_pills()

    def _phase_payload(self, phase: str) -> Tuple[Optional[bool], Dict[str, Any]]:
        page = self.as_found if phase == "as_found" else self.as_left
        if not hasattr(page, "_last_result"):
            return None, {}
        res = dict(page._last_result)
        ok = res.get("conforme", res.get("ok"))
        return ok, res

    def refresh_pills(self):
        def pill(page):
            if hasattr(page, "_last_result"):
                return page._last_result.get("conforme", page._last_result.get("ok"))
            return None
        set_status_pill(self.pill_found, pill(self.as_found))
        set_status_pill(self.pill_left,  pill(self.as_left))

    def save_phase(self, phase: str):
        pid = self.get_project_id()
        if pid is None:
            QMessageBox.warning(self, "Projet", "Sélectionnez d’abord un projet.")
            return
        if not self.standard:
            QMessageBox.critical(self, "Étalon requis", "Choisissez un étalon (OK) avant d’enregistrer.")
            return

        ok, payload = self._phase_payload(phase)
        if payload == {}:
            QMessageBox.information(self, "Données manquantes", f"Aucune donnée '{phase}'.")
            return

        payload["conforme"] = (True if ok is True else False if ok is False else None)
        params = {
            "phase": phase,
            "standard_id": self.standard.get("id"),
            "standard_info": self.standard
        }
        TestManager(self.db).save_test(pid, self.test_code, payload["conforme"], params, payload)
        QMessageBox.information(self, "OK", f"{self.test_code} – {phase} enregistré.")
        self.refresh_pills()


# ================== Checklist draggable (ultra propre) ==================
class DraggableChecklist(QListWidget):
    """
    Chaque item = test. Checkable + ré-ordonnable par glisser-déposer.
    L’ordre visuel = ordre d’exécution.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(f"""
            QListWidget {{
                background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:10px;
            }}
            QListWidget::item {{ padding:8px 10px; }}
            QListWidget::item:selected {{ background:{THEME_ACCENT}; color:{THEME_PRIMARY}; }}
        """)

    def add_test(self, code: str, label: str, checked=True):
        it = QListWidgetItem(label)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        it.setData(Qt.UserRole, code)
        self.addItem(it)

    def sequence(self) -> List[str]:
        seq: List[str] = []
        for i in range(self.count()):
            it = self.item(i)
            if it.checkState() == Qt.Checked:
                seq.append(it.data(Qt.UserRole))
        return seq


# ================== Orchestrateur principal ==================
class HVACWorkflow(QWidget):
    """
    Sidebar gauche (Projet + Plan d’essais) / Contenu à droite (onglets tests)
    - Checklist des tests avec drag&drop, case à cocher et bouton “Appliquer”
    - Étalon obligatoire par test (dans le wrapper)
    - Pastille de conformité globale projet
    """
    def __init__(self, db, get_project_id):
        super().__init__()
        self.db = db
        self.get_project_id = get_project_id
        self.tm = TestManager(db)
        self._wrappers: Dict[str, TwoPhaseWrapper] = {}

        # ===== Side bar (carte projet + plan)
        self.card_project = QGroupBox("Projet sélectionné")
        pf = QFormLayout(self.card_project)
        self.lbl_proj_main = QLabel("Aucun projet sélectionné")
        self.lbl_proj_hint = QLabel("Sélectionnez un projet dans l’onglet « Projets », puis revenez ici.")
        self.lbl_proj_hint.setStyleSheet("color:#6b7280;")
        self.btn_proj_refresh = QPushButton("Actualiser")
        self.btn_proj_refresh.clicked.connect(self._refresh_project_card)
        pf.addRow("Détails :", self.lbl_proj_main)
        pf.addRow("", self.lbl_proj_hint)
        pf.addRow("", self.btn_proj_refresh)

        self.plan_box = QGroupBox("Plan d’essais HVAC")
        pl = QVBoxLayout(self.plan_box)
        self.plan = DraggableChecklist()
        for meta in TEST_REGISTRY:
            self.plan.add_test(meta["code"], meta["label"], checked=True)
        buttons = QHBoxLayout()
        self.btn_all   = QPushButton("Tout cocher")
        self.btn_none  = QPushButton("Tout décocher")
        self.btn_apply = QPushButton("Appliquer la sélection")
        self.btn_all.clicked.connect(lambda: self._check_all(True))
        self.btn_none.clicked.connect(lambda: self._check_all(False))
        self.btn_apply.clicked.connect(self._apply_sequence)
        buttons.addWidget(self.btn_all); buttons.addWidget(self.btn_none); buttons.addStretch(1); buttons.addWidget(self.btn_apply)
        pl.addWidget(self.plan)
        pl.addLayout(buttons)

        # ===== Contenu (onglets de tests)
        self.stack = QTabWidget()

        # ===== Nav + conformité
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Précédent")
        self.btn_next = QPushButton("Suivant ▶")
        self.btn_prev.clicked.connect(lambda: self._nav(-1))
        self.btn_next.clicked.connect(lambda: self._nav(+1))
        self.btn_refresh_glob = QPushButton("Recalculer conformité projet")
        self.btn_refresh_glob.clicked.connect(self.refresh_project_status)
        self.glob_status = QLabel(); set_status_pill(self.glob_status, None)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        nav.addWidget(QLabel("Conformité projet :"))
        nav.addWidget(self.glob_status)
        nav.addWidget(self.btn_refresh_glob)

        # ===== Disposition globale (splitter)
        split = QSplitter()
        left = QWidget(); left_l = QVBoxLayout(left); left_l.addWidget(self.card_project); left_l.addWidget(self.plan_box); left_l.addStretch(1)
        right = QWidget(); right_l = QVBoxLayout(right); right_l.addWidget(self.stack); right_l.addLayout(nav)
        split.addWidget(left); split.addWidget(right)
        split.setSizes([380, 920])

        root = QVBoxLayout(self)
        root.addWidget(split)

        # ---- Style
        self.setStyleSheet(f"""
            QWidget {{ background:{THEME_BG}; }}
            QGroupBox {{
                background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:12px;
                margin-top:10px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color:{THEME_PRIMARY}; font-weight:700; }}
            QLabel {{ color:#163b66; }}
            QPushButton {{ background:{THEME_PRIMARY}; color:#fff; border-radius:8px; padding:8px 16px; font-weight:600; }}
            QPushButton:hover {{ background:{THEME_ACCENT}; color:{THEME_PRIMARY}; }}
            QTabBar::tab {{ padding:10px 16px; font-weight:600; }}
        """)

        # build initial
        self._apply_sequence()
        self._refresh_project_card()

    # ---------- Sidebar helpers ----------
    def _check_all(self, state: bool):
        for i in range(self.plan.count()):
            it = self.plan.item(i)
            it.setCheckState(Qt.Checked if state else Qt.Unchecked)

    def _selected_sequence(self) -> List[str]:
        return self.plan.sequence()

    def _ensure_wrapper(self, code: str) -> TwoPhaseWrapper:
        if code not in self._wrappers:
            meta = next(m for m in TEST_REGISTRY if m["code"] == code)
            self._wrappers[code] = TwoPhaseWrapper(self.db, self.get_project_id, meta["code"], meta["widget"])
        return self._wrappers[code]

    def _apply_sequence(self):
        seq = self._selected_sequence()
        if not seq:
            QMessageBox.information(self, "Plan d’essais", "Coche au moins un test.")
            return
        self.stack.blockSignals(True)
        try:
            self.stack.clear()
            for code in seq:
                meta = next(m for m in TEST_REGISTRY if m["code"] == code)
                w = self._ensure_wrapper(code)
                w.refresh_header()
                self.stack.addTab(w, meta["label"])
        finally:
            self.stack.blockSignals(False)

    def _nav(self, delta: int):
        if self.stack.count() == 0:
            return
        i = self.stack.currentIndex()
        self.stack.setCurrentIndex(max(0, min(self.stack.count()-1, i + delta)))

    # ---------- Carte projet / conformité ----------
    def _refresh_project_card(self):
        pid = self.get_project_id()
        if pid is None:
            self.lbl_proj_main.setText("Aucun projet sélectionné")
            self.lbl_proj_hint.setText("Sélectionnez un projet dans l’onglet « Projets », puis revenez sur « Tests ».")
            return
        row = self.db.conn.execute(
            "SELECT company_name, location, room_tag, test_date FROM projects WHERE id=?", (pid,)
        ).fetchone()
        if not row:
            self.lbl_proj_main.setText("Projet introuvable")
            self.lbl_proj_hint.setText("")
            return
        self.lbl_proj_main.setText(f"{row['company_name']} – {row['location'] or ''} – {row['room_tag'] or ''} (test: {row['test_date']})")
        self.lbl_proj_hint.setText("Seuils, étalons et enregistrements sont spécifiques à ce projet.")
        for w in self._wrappers.values():
            w.refresh_header()

    def refresh_project_status(self):
        pid = self.get_project_id()
        if pid is None:
            set_status_pill(self.glob_status, None)
            QMessageBox.information(self, "Projet", "Sélectionnez d’abord un projet.")
            return
        ok = None
        try:
            ok = self.tm.project_conformity(pid)  # si dispo dans ton TestManager
        except Exception:
            # fallback neutre si la méthode n'existe pas encore chez toi
            ok = None
        set_status_pill(self.glob_status, ok)

    # appelé par dashboard quand on ouvre l’onglet
    def rebuild_for_current_project(self):
        self._refresh_project_card()
        for w in self._wrappers.values():
            w.refresh_header()
        self.refresh_project_status()
