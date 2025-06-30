#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pdf/generator.py

Génération automatique du rapport PDF final :
– Informations du projet
– Mesures et seuils
– Statut de conformité
– Noms technicien / validateur
– Dates, signatures :contentReference[oaicite:1]{index=1}
"""

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

class PDFGenerator:
    def __init__(self, db):
        self.db = db

    def generate_report(self, project_id: int, file_path: str) -> None:
        doc = SimpleDocTemplate(file_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Projet
        proj = self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        creator = self.db.conn.execute(
            "SELECT username FROM users WHERE id = ?", (proj["created_by"],)
        ).fetchone()

        story.append(Paragraph(f"Rapport de projet #{project_id}", styles["Title"]))
        story.append(Spacer(1, 12))

        info = [
            ["Entreprise", proj["company_name"]],
            ["Localisation", proj["location"]],
            ["Type de salle", proj["room_type"]],
            ["Date du test", proj["test_date"]],
            ["Créé par", creator["username"]],
        ]
        tbl_info = Table(info, hAlign="LEFT")
        tbl_info.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ]))
        story.append(tbl_info)
        story.append(Spacer(1, 12))

        # Tests et mesures
        tests = self.db.conn.execute(
            "SELECT * FROM tests WHERE project_id = ?", (project_id,)
        ).fetchall()
        for t in tests:
            tech = self.db.conn.execute(
                "SELECT username FROM users WHERE id = ?", (t["technician_id"],)
            ).fetchone()
            status = "Validé" if t["is_validated"] else "Non validé"
            story.append(Paragraph(
                f"Test #{t['id']} – {t['measurement_date']} – Technicien : {tech['username']} – Statut : {status}",
                styles["Heading3"]
            ))
            story.append(Spacer(1, 6))

            data = [["Point", "Paramètre", "Valeur", "Seuil max", "Conformité"]]
            rows = self.db.conn.execute(
                """
                SELECT m.point_name, m.parameter, m.value, th.max_value
                FROM measurements m
                JOIN thresholds th
                  ON th.iso_class = ?
                 AND th.parameter = m.parameter
                WHERE m.test_id = ?
                """, (proj["room_type"], t["id"])
            ).fetchall()

            for r in rows:
                compliant = "✓" if r["value"] <= r["max_value"] else "✗"
                data.append([
                    r["point_name"],
                    r["parameter"],
                    f"{r['value']}",
                    f"{r['max_value']}",
                    compliant
                ])

            tbl = Table(data, hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, colors.black),
                ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 12))

        # Génération finale
        doc.build(story)
