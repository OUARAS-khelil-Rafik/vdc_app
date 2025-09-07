# pdf/generator.py

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

class PDFGenerator:
    def __init__(self, db):
        self.db = db

    def _get_username(self, user_id: int) -> str:
        row = self.db.conn.execute(
            "SELECT username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["username"] if row else "Inconnu"

    def _get_responsables(self, project_id: int):
        # Utilise la table project_users pour récupérer les responsables
        rows = self.db.conn.execute(
            """SELECT u.role, u.username
               FROM project_users pu
               JOIN users u ON pu.user_id = u.id
               WHERE pu.project_id = ?""",
            (project_id,)
        ).fetchall()
        return [(r["role"], r["username"]) for r in rows]

    def _get_standards(self, project_id: int):
        # Si vous n'avez pas de table project_standards, affichez tous les standards
        rows = self.db.conn.execute(
            "SELECT name, category, manufacturer, model FROM standards"
        ).fetchall()
        return rows

    def generate_report(self, project_id: int, save_path: str) -> None:
        # Charger les informations du projet
        proj = self.db.conn.execute(
            "SELECT company_name, location, room_tag, test_date, contact_info, work_type FROM projects WHERE id = ?",
            (project_id,)
        ).fetchone()
        if not proj:
            raise ValueError(f"Projet {project_id} introuvable.")

        # Charger les sessions de test
        tests = self.db.conn.execute(
            """SELECT id, test_type, status, conformity, created_at
               FROM tests WHERE project_id = ?""",
            (project_id,)
        ).fetchall()

        # Charger les responsables
        responsables = self._get_responsables(project_id)

        # Charger les étalons/standards
        standards = self._get_standards(project_id)

        # Styles personnalisés
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='SectionTitle', fontSize=14, leading=18, spaceAfter=10, textColor=colors.HexColor('#003366'), fontName='Helvetica-Bold'))
        styles.add(ParagraphStyle(name='Small', fontSize=9, leading=11))
        styles.add(ParagraphStyle(name='NormalBold', fontSize=11, fontName='Helvetica-Bold'))

        doc = SimpleDocTemplate(save_path, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        elems = []

        # Logo (optionnel)
        elems.append(Image("icons/vdc_logo.png", width=4*cm, height=2*cm))

        # En-tête projet
        elems.append(Paragraph("Rapport de Validation – VDC Engineering", styles['Title']))
        elems.append(Spacer(1, 8))
        elems.append(Paragraph(f"<b>Projet :</b> {proj['company_name']}<br/><b>Lieu :</b> {proj['location']}", styles['Normal']))
        elems.append(Paragraph(f"<b>Type de salle :</b> {proj['room_tag']}<br/><b>Date :</b> {proj['test_date']}", styles['Normal']))
        if "contact_info" in proj and proj["contact_info"]:
            elems.append(Paragraph(f"<b>Contact :</b> {proj['contact_info']}", styles['Small']))
        elems.append(Spacer(1, 12))

        # Responsables
        elems.append(Paragraph("Responsables du projet", styles['SectionTitle']))
        if responsables:
            data_resp = [["Rôle", "Nom"]]
            data_resp += [[r, n] for r, n in responsables]
            table_resp = Table(data_resp, hAlign='LEFT', style=[
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#003366')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ])
            elems.append(table_resp)
        else:
            elems.append(Paragraph("Aucun responsable renseigné.", styles['Small']))
        elems.append(Spacer(1, 12))

        # Standards / Étalons
        elems.append(Paragraph("Normes et étalons appliqués", styles['SectionTitle']))
        if standards:
            data_std = [["Nom", "Catégorie", "Fabricant", "Modèle"]]
            data_std += [[s["name"], s["category"], s["manufacturer"], s["model"]] for s in standards]
            table_std = Table(data_std, hAlign='LEFT', style=[
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0055A4')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ])
            elems.append(table_std)
        else:
            elems.append(Paragraph("Aucune norme renseignée.", styles['Small']))
        elems.append(Spacer(1, 16))

        # Rapport de chaque test
        for idx, t in enumerate(tests, 1):
            elems.append(Paragraph(f"Test n°{idx}", styles['SectionTitle']))
            elems.append(Paragraph(f"<b>Type de test :</b> {t['test_type']}", styles['Normal']))
            elems.append(Paragraph(f"<b>Status :</b> {t['status']}", styles['Normal']))
            elems.append(Paragraph(f"<b>Date :</b> {t['created_at']}", styles['Normal']))
            elems.append(Spacer(1, 6))

            # Mesures du test
            data = [["Point", "Paramètre", "Seuil", "Valeur", "Conforme"]]
            rows = self.db.conn.execute(
                """SELECT m.point_name, m.parameter, m.value, th.value as threshold
                   FROM measurements m
                   LEFT JOIN thresholds th 
                     ON th.iso_name = ? AND th.test_name = m.parameter
                   WHERE m.test_id = ?""",
                (proj["room_tag"], t["id"])
            ).fetchall()
            for m in rows:
                point, param, val, seuil = m["point_name"], m["parameter"], m["value"], m["threshold"]
                if seuil is not None:
                    ok = "✓" if val <= seuil else "✗"
                else:
                    ok = "N/A"
                data.append([point, param, seuil if seuil is not None else "-", val, ok])

            table = Table(data, hAlign='LEFT', style=[
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0055A4')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (1,0), (-1,-1), [colors.whitesmoke, colors.lightgrey])
            ])
            elems.append(table)
            elems.append(Spacer(1, 18))

        # Signature finale
        elems.append(PageBreak())
        elems.append(Paragraph("Signatures", styles['SectionTitle']))
        for r, n in responsables:
            elems.append(Paragraph(f"{r} : {n}", styles['Normal']))
            elems.append(Spacer(1, 24))

        # Génération du PDF
        doc.build(elems)
