from .utils import dict_from_row

class ProjectManager:
    def __init__(self, db):
        self.db = db

    def get_projects(self):
        rows = self.db.conn.execute(
            """SELECT p.id, p.company_name, p.location, p.room_type, p.test_date, 
                      p.iso_class, p.validation_status, p.created_by, 
                      u.username as username
               FROM projects p
               LEFT JOIN users u ON p.created_by = u.id"""
        ).fetchall()

        columns = ["id", "company_name", "location", "room_type", "test_date",
                   "iso_class", "validation_status", "created_by", "username"]
        return [dict_from_row(row, columns) for row in rows]

    def add_project(self, company, location, room, date, created_by, iso_class, validation_status, username):
        self.db.conn.execute(
            """INSERT INTO projects 
            (company_name, location, room_type, test_date, created_by, iso_class, validation_status, username)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (company, location, room, date, created_by, iso_class, validation_status, username)
        )
        self.db.conn.commit()

    def update_project(self, project_id, company, location, room, date, created_by, iso_class, validation_status, username):
        allowed_iso_classes = [f"ISO {i}" for i in range(1, 10)]
        if iso_class not in allowed_iso_classes:
            raise ValueError(f"Cannot update project: ProjectManager.update_project() requires a valid 'username' argument and 'iso_class' must be one of {allowed_iso_classes}, got '{iso_class}'")
        if not username or not isinstance(username, str):
            raise ValueError("Cannot update project: ProjectManager.update_project() requires a valid 'username' argument")
        self.db.conn.execute(
            """UPDATE projects 
               SET company_name = ?, location = ?, room_type = ?, test_date = ?, 
                   created_by = ?, iso_class = ?, validation_status = ?, username = ?
                WHERE id = ?""",
            (company, location, room, date, created_by, iso_class, validation_status, username, project_id)
        )
        self.db.conn.commit()

    def get_project(self, project_id):
        cursor = self.db.conn.execute(
            """SELECT p.*, u.username as username 
               FROM projects p
               LEFT JOIN users u ON p.created_by = u.id
               WHERE p.id = ?""", (project_id,)
        )
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None

    def get_users_for_assignment(self):
        rows = self.db.conn.execute("SELECT id, username FROM users").fetchall()
        return [{"id": row[0], "username": row[1]} for row in rows]
