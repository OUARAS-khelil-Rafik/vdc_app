# models/projectmanager.py

from .utils import dict_from_row

class ProjectManager:
    def __init__(self, db):
        self.db = db

    def get_projects(self):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.company_name,
                p.location,
                p.room_type,
                p.cleanroom_area,
                p.test_date,
                p.iso_class,
                p.validation_status,
                p.assigned_to,               -- ajouté pour filtrage et usage
                u.full_name AS assigned_user
            FROM projects p
            LEFT JOIN users u ON p.assigned_to = u.id
            ORDER BY p.test_date DESC
        """)
        rows = cursor.fetchall()
        return [dict_from_row(row, [
            "id",
            "company_name",
            "location",
            "room_type",
            "cleanroom_area",
            "test_date",
            "iso_class",
            "validation_status",
            "assigned_to",                # ajouté
            "assigned_user"
        ]) for row in rows]

    def get_project(self, project_id):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.company_name,
                p.location,
                p.room_type,
                p.cleanroom_area,
                p.test_date,
                p.iso_class,
                p.validation_status,
                p.assigned_to,
                u.full_name AS assigned_user
            FROM projects p
            LEFT JOIN users u ON p.assigned_to = u.id
            WHERE p.id = ?
        """, (project_id,))
        row = cursor.fetchone()
        if row:
            return dict_from_row(row, [
                "id",
                "company_name",
                "location",
                "room_type",
                "cleanroom_area",
                "test_date",
                "iso_class",
                "validation_status",
                "assigned_to",
                "assigned_user"
            ])
        return None

    def add_project(self, company, location, room, cleanroom_area, date, iso_class, validation_status, assigned_to):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO projects (
                company_name,
                location,
                room_type,
                cleanroom_area,
                test_date,
                iso_class,
                validation_status,
                assigned_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company,
            location,
            room,
            cleanroom_area,
            date,
            iso_class,
            validation_status,
            assigned_to
        ))
        self.db.conn.commit()

    def update_project(self, project_id, company, location, room, cleanroom_area, date, iso_class, validation_status, assigned_to):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE projects
            SET
                company_name     = ?,
                location         = ?,
                room_type        = ?,
                cleanroom_area   = ?,
                test_date        = ?,
                iso_class        = ?,
                validation_status= ?,
                assigned_to      = ?
            WHERE id = ?
        """, (
            company,
            location,
            room,
            cleanroom_area,
            date,
            iso_class,
            validation_status,
            assigned_to,
            project_id
        ))
        self.db.conn.commit()

    def delete_project(self, project_id):
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.db.conn.commit()
