# pdf/generator.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pdf/generator.py

Générateur de rapport PDF pour VDC Engineering, basé sur ReportLab.
Inclut données projet, mesures, conformité, et signatures.
"""

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

class PDFGenerator:
    def __init__(self, db):
        self.db = db

    def _get_username(self, user_id: int) -> str:
        row = self.db.conn.execute(
            "SELECT username FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        return row["username"] if row else "Inconnu"

    def generate_report(self, project_id: int, save_path: str) -> None:
        # 1) Charger les informations du projet
        proj = self.db.conn.execute(
            "SELECT company_name, location, room_type, test_date FROM projects WHERE id = ?",
            (project_id,)
        ).fetchone()
        if not proj:
            raise ValueError(f"Projet {project_id} introuvable.")

        # 2) Charger les sessions de test
        tests = self.db.conn.execute(
            """SELECT id, technician_id, is_validated, validated_by, validated_date
               FROM tests WHERE project_id = ?""",
            (project_id,)
        ).fetchall()

        # 3) Préparer les données pour le tableau
        data = [["Point", "Paramètre", "Seuil", "Valeur", "Conforme"]]
        for t in tests:
            rows = self.db.conn.execute(
                """SELECT m.point_name, m.parameter, m.value, th.max_value
                   FROM measurements m
                   JOIN thresholds th 
                     ON th.iso_class = ? AND th.parameter = m.parameter
                   WHERE m.test_id = ?""",
                (proj["room_type"], t["id"])
            ).fetchall()
            for m in rows:
                point, param, val, seuil = m
                ok = "✓" if val <= seuil else "✗"
                data.append([point, param, seuil, val, ok])

        # 4) Générer le PDF
        doc = SimpleDocTemplate(save_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elems = []

        # En-tête projet
        title = f"Projet : {proj['company_name']} – {proj['location']}"
        subtitle = f"Type de salle : {proj['room_type']} — Date : {proj['test_date']}"
        elems.append(Paragraph(title, styles['Title']))
        elems.append(Paragraph(subtitle, styles['Normal']))
        elems.append(Spacer(1, 12))

        # Tableau des mesures
        table = Table(data, hAlign='LEFT')
        elems.append(table)
        elems.append(Spacer(1, 24))

        # Signatures
        # On prend la dernière session pour la signature
        last = tests[-1] if tests else None
        if last:
            tech = self._get_username(last["technician_id"])
            elems.append(Paragraph(f"Technicien : {tech}", styles['Normal']))
            if last["is_validated"]:
                valid = self._get_username(last["validated_by"])
                elems.append(Paragraph(f"Validé par : {valid} le {last['validated_date']}", styles['Normal']))

        # Sauvegarde
        doc.build(elems)
