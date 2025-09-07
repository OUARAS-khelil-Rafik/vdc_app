import json
import math
import sqlite3
import statistics as stats
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QWidget, QLabel, QFormLayout, QHBoxLayout, QVBoxLayout,
    QTableWidget, QTableWidgetItem, QGroupBox, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QHeaderView, QScrollArea, QLineEdit, QPlainTextEdit,
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QTabWidget, QCheckBox, QFileDialog
)

from models.projectmanager import ProjectManager
from models.testmanager    import TestManager
from test_pages.HVAC_pages import (
    ACPHPage, DeltaPPage, HEPALeakPage, SmokePage, SmokeDynamicPage,
    ParticleClassPage, RecoveryPage, TempRHPage
)
from test_pages.Thermal_Mapping_pages import ThermalMappingPage
from test_pages.Instrumentation_pages import InstrumentationPage

# --------------------------- Main Window ------------------------------

class TestWidget(QWidget):
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user

        # Top bar: project selector
        top = QWidget(); top_l = QHBoxLayout(top)
        self.cb_projects = QComboBox(); top_l.addWidget(QLabel("Projet:")); top_l.addWidget(self.cb_projects, 1)

        # Left tree
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        # Ajoute les racines principales pour chaque type de test
        self.roots = {
            "HVAC": QTreeWidgetItem(["HVAC – Tests"]),
            "Thermal Mapping": QTreeWidgetItem(["Thermal Mapping – Tests"]),
            "Instrumentation": QTreeWidgetItem(["Instrumentation – Tests"]),
        }
        for root in self.roots.values():
            self.tree.addTopLevelItem(root)
        # Utilise la racine HVAC pour les tests existants
        self.tests = [
            ("ACPH", "1) Débit & ACPH"),
            ("DeltaP", "2) Cascade de pressions (ΔP)"),
            ("HEPA_Leak", "3) Intégrité filtres HEPA"),
            ("Smoke_Visual_stat", "4) Visualisation de flux Statique"),
            ("Smoke_Visual_dyn", "5) Visualisation de flux Dynamique"),
            ("Particle_Class", "6) Comptage particulaire en air"),
            ("Recovery_Time", "7) Recovery time (100:1)"),
            ("Temp_RH", "8) Température & Humidité"),
        ]
        self.key_by_item = {}
        for key, label in self.tests:
            it = QTreeWidgetItem([label]); self.roots["HVAC"].addChild(it); self.key_by_item[id(it)] = key

        # Ajoute les tests pour Thermal Mapping
        self.thermal_tests = [
            ("Thermal_Mapping", "1) Thermal Mapping"),
        ]
        for key, label in self.thermal_tests:
            it = QTreeWidgetItem([label]); self.roots["Thermal Mapping"].addChild(it); self.key_by_item[id(it)] = key

        # Ajoute les tests pour Instrumentation
        self.instrumentation_tests = [
            ("Instrumentation", "1) Instrumentation"),
        ]
        for key, label in self.instrumentation_tests:
            it = QTreeWidgetItem([label]); self.roots["Instrumentation"].addChild(it); self.key_by_item[id(it)] = key

        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self.on_tree_change)

        # Stacked pages with scroll areas for each page
        def get_pid():
            data = self.cb_projects.currentData()
            return int(data) if data is not None else None

        self.pages: Dict[str, QWidget] = {
            "ACPH": ACPHPage(self.db, get_pid),
            "DeltaP": DeltaPPage(self.db, get_pid),
            "HEPA_Leak": HEPALeakPage(self.db, get_pid),
            "Smoke_Visual_stat": SmokePage(self.db, get_pid),
            "Smoke_Visual_dyn": SmokeDynamicPage(self.db, get_pid),
            "Particle_Class": ParticleClassPage(self.db, get_pid),
            "Recovery_Time": RecoveryPage(self.db, get_pid),
            "Temp_RH": TempRHPage(self.db, get_pid),
            "Thermal_Mapping": ThermalMappingPage(self.db, get_pid),
            "Instrumentation": InstrumentationPage(self.db, get_pid),
        }

        # Wrap each page in a QScrollArea for better visual and scrolling
        self.scroll_areas: Dict[str, QScrollArea] = {}
        # Ajoute toutes les pages dans l'ordre des items de l'arbre
        all_test_keys = [k for k, _ in self.tests] + [k for k, _ in self.thermal_tests] + [k for k, _ in self.instrumentation_tests]
        for k in all_test_keys:
            page = self.pages[k]
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            # Style for better visual (light background, no border, rounded corners)
            scroll.setStyleSheet("""
                QScrollArea {
                    background: transparent;
                    border: none;
                }
                QScrollBar:vertical, QScrollBar:horizontal {
                    background: #e0e0e0;
                    border-radius: 6px;
                    width: 12px;
                    margin: 2px;
                }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                    background: #b8d5ed;
                    border-radius: 6px;
                    min-height: 30px;
                    min-width: 30px;
                }
                QScrollBar::add-line, QScrollBar::sub-line {
                    background: none;
                    border: none;
                }
            """)
            self.scroll_areas[k] = scroll

        self.stack = QStackedWidget()
        self.key_to_index: Dict[str, int] = {}
        for i, k in enumerate(all_test_keys):
            self.stack.addWidget(self.scroll_areas[k])
            self.key_to_index[k] = i

        # Central layout
        central_l = QVBoxLayout(self)
        central_l.addWidget(top)
        body = QHBoxLayout(); body.addWidget(self.tree, 2); body.addWidget(self.stack, 7)
        central_l.addLayout(body)

        self.reload_projects()
        # Select first test by default
        self.tree.setCurrentItem(self.roots["HVAC"].child(0))

        # Connect project change to update tree visibility
        self.cb_projects.currentIndexChanged.connect(self.update_tree_visibility)

    # ---- Projects ----
    def reload_projects(self):
        self.cb_projects.clear()
        pm = ProjectManager(self.db)
        rows = pm.list_projects()
        self.cb_projects.addItem("— Aucun projet —", None)
        for r in rows:
            label = f"{r['id']} • {r.get('company_name', '') or ''} {r.get('room_tag', '') or ''} [{r.get('location', '') or ''}]".strip()
            self.cb_projects.addItem(label, r["id"])
        self.update_tree_visibility()

    def update_tree_visibility(self):
        # Hide all roots by default
        for root in self.roots.values():
            root.setHidden(True)
        # Get selected project
        pm = ProjectManager(self.db)
        pid = self.cb_projects.currentData()
        if pid is None:
            return
        project = pm.get_project(pid)
        if not project:
            return
        work_type = project.get("work_type")
        # Show only the root matching work_type
        root = self.roots.get(work_type)
        if root:
            root.setHidden(False)
            self.tree.setCurrentItem(root.child(0) if root.childCount() > 0 else root)

    # ---- Navigation ----
    def on_tree_change(self, cur: QTreeWidgetItem, prev: QTreeWidgetItem):
        if not cur: return
        key = self.key_by_item.get(id(cur))
        if not key: return
        idx = self.key_to_index.get(key, 0)
        self.stack.setCurrentIndex(idx)
