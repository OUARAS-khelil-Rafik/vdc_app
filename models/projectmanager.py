from .utils import dict_from_row

class ProjectManager:
    def __init__(self, db):
        self.db = db

    def get_projects(self):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT id, company_name, location, room_type, test_date, iso_class, validation_status
            FROM projects
            ORDER BY test_date DESC
        """)
        rows = cursor.fetchall()
        return [dict_from_row(row, [
            "id", "company_name", "location", "room_type", "test_date", "iso_class", "validation_status"
        ]) for row in rows]

    def get_project(self, project_id):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT id, company_name, location, room_type, test_date, iso_class, validation_status
            FROM projects
            WHERE id = ?
        """, (project_id,))
        row = cursor.fetchone()
        if row:
            return dict_from_row(row, [
                "id", "company_name", "location", "room_type", "test_date", "iso_class", "validation_status"
            ])
        return None

    def add_project(self, company, location, room, date, iso_class, validation_status):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO projects (company_name, location, room_type, test_date, iso_class, validation_status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (company, location, room, date, iso_class, validation_status))
        self.db.conn.commit()

    def update_project(self, project_id, company, location, room, date, iso_class, validation_status):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE projects
            SET company_name=?, location=?, room_type=?, test_date=?, iso_class=?, validation_status=?
            WHERE id=?
        """, (company, location, room, date, iso_class, validation_status, project_id))
        self.db.conn.commit()

    def delete_project(self, project_id):
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id=?", (project_id,))
        self.db.conn.commit()