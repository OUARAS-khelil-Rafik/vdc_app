from .utils import dict_from_row

class ProjectManager:
    def __init__(self, db):
        self.db = db

    def get_projects(self):
        rows = self.db.conn.execute(
            "SELECT id, company_name, location, room_type, test_date FROM projects"
        ).fetchall()
        columns = ["id", "company_name", "location", "room_type", "test_date"]
        return [dict_from_row(row, columns) for row in rows]

    def add_project(self, company, location, room, date, user_id):
        self.db.conn.execute(
            "INSERT INTO projects (company_name, location, room_type, test_date, created_by) VALUES (?, ?, ?, ?, ?)",
            (company, location, room, date, user_id)
        )
        self.db.conn.commit()

    def update_project(self, project_id, company, location, room, date):
        self.db.conn.execute(
            "UPDATE projects SET company_name=?, location=?, room_type=?, test_date=? WHERE id=?",
            (company, location, room, date, project_id)
        )
        self.db.conn.commit()

    def delete_project(self, project_id):
        self.db.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.db.conn.commit()

    def get_project(self, project_id):
        cursor = self.db.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,))
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None