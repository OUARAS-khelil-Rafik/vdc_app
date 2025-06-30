#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gui/thresholds.py

Dialog pour gérer les seuils de conformité par classe ISO.
Accessible aux profils Administrateur et Technicien premium.
– Affiche la liste des seuils (classe ISO, paramètre, valeur max)
– Permet d’ajouter et de supprimer des seuils :contentReference[oaicite:0]{index=0}
"""

from PyQt5.QtWidgets import (
    QDialog, QTableWidget, QTableWidgetItem, QPushButton,
    QFormLayout, QLineEdit, QHBoxLayout, QVBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt

class ThresholdsDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("Seuils de conformité")
        self.resize(600, 400)
        self._init_ui()
        self.refresh_thresholds()

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
