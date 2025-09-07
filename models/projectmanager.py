from .utils import dict_from_row

class ProjectManager:
    def __init__(self, db):
        self.db = db

    def list_projects(self):
        """
        Returns a list of all projects as dictionaries.
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.company_name,
                p.location,
                p.room_tag,
                GROUP_CONCAT(u.full_name, ', ') AS assigned_to,
                p.test_date,
                p.contact_info,
                p.work_type,
                p.validation_status
            FROM projects p
            LEFT JOIN project_users pu ON p.id = pu.project_id
            LEFT JOIN users u ON pu.user_id = u.id
            GROUP BY p.id
            ORDER BY p.test_date DESC
        """)
        rows = cursor.fetchall()
        return [
            dict_from_row(row, [
                "id",
                "company_name",
                "location",
                "room_tag",
                "assigned_to",
                "test_date",
                "contact_info",
                "work_type",
                "validation_status"
            ]) for row in rows
        ]

    def get_projects(self, start_date=None, end_date=None, company_name=None):
        cursor = self.db.conn.cursor()
        query = """
            SELECT
                p.id,
                p.company_name,
                p.location,
                p.room_tag,
                GROUP_CONCAT(u.full_name, ', ') AS assigned_to,
                p.test_date,
                p.contact_info,
                p.work_type,
                p.validation_status
            FROM projects p
            LEFT JOIN project_users pu ON p.id = pu.project_id
            LEFT JOIN users u ON pu.user_id = u.id
        """
        filters = []
        params = []

        if start_date:
            filters.append("p.test_date >= ?")
            params.append(start_date)
        if end_date:
            filters.append("p.test_date <= ?")
            params.append(end_date)
        if company_name:
            filters.append("p.company_name = ?")
            params.append(company_name)

        if filters:
            query += " WHERE " + " AND ".join(filters)

        query += " GROUP BY p.id ORDER BY p.test_date DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            dict_from_row(row, [
                "id",
                "company_name",
                "location",
                "room_tag",
                "assigned_to",
                "test_date",
                "contact_info",
                "work_type",
                "validation_status"
            ]) for row in rows
        ]

    def get_project(self, project_id):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.company_name,
                p.location,
                p.room_tag,
                GROUP_CONCAT(u.full_name, ', ') AS assigned_to,
                p.test_date,
                p.contact_info,
                p.work_type,
                p.validation_status
            FROM projects p
            LEFT JOIN project_users pu ON p.id = pu.project_id
            LEFT JOIN users u ON pu.user_id = u.id
            WHERE p.id = ?
            GROUP BY p.id
        """, (project_id,))
        row = cursor.fetchone()
        if row:
            return dict_from_row(row, [
                "id",
                "company_name",
                "location",
                "room_tag",
                "assigned_to",
                "test_date",
                "contact_info",
                "work_type"
            ])
        return None

    def add_project(self, company_name, location, room_tag, test_date, contact_info, work_type, validation_status, responsables_ids):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO projects (
                company_name,
                location,
                room_tag,
                test_date,
                contact_info,
                work_type,
                validation_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company_name,
            location,
            room_tag,
            test_date,
            contact_info,
            work_type,
            "En attente"
        ))
        project_id = cursor.lastrowid
        if responsables_ids:
            for user_id in responsables_ids:
                cursor.execute(
                    "INSERT INTO project_users (project_id, user_id) VALUES (?, ?)",
                    (project_id, user_id)
                )
        self.db.conn.commit()
        return project_id

    def update_project(self, project_id, company_name, location, room_tag, test_date, contact_info, work_type, validation_status, responsables_ids):
        cursor = self.db.conn.cursor()
        cursor.execute("""
            UPDATE projects
            SET
                company_name      = ?,
                location          = ?,
                room_tag          = ?,
                test_date         = ?,
                contact_info      = ?,
                work_type         = ?,
                validation_status = ?
            WHERE id = ?
        """, (
            company_name,
            location,
            room_tag,
            test_date,
            contact_info,
            work_type,
            validation_status,
            project_id
        ))
        # Mise à jour des responsables (relation N:N)
        cursor.execute("DELETE FROM project_users WHERE project_id = ?", (project_id,))
        if responsables_ids:
            for user_id in responsables_ids:
                cursor.execute(
                    "INSERT INTO project_users (project_id, user_id) VALUES (?, ?)",
                    (project_id, user_id)
                )
        self.db.conn.commit()

    def delete_project(self, project_id):
        cursor = self.db.conn.cursor()
        # Supprimer d'abord les associations dans project_users
        cursor.execute("DELETE FROM project_users WHERE project_id = ?", (project_id,))
        # Puis supprimer le projet
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.db.conn.commit()

