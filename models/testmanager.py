# models/testmanager.py

from typing import List, Tuple, Optional
from datetime import datetime
import json

class TestManager:
    def __init__(self, db):
        self.db = db

    # ---------- Thresholds ----------
    def get_threshold(
        self, 
        project_id: Optional[int], 
        test_type: str, 
        key: str, 
        fallback: Optional[str] = None
    ) -> Optional[str]:
        """
        Récupère la valeur d'un seuil pour un projet et un type de test donné.
        Prend la valeur spécifique au projet si elle existe, sinon la valeur par défaut.
        """
        c = self.db.conn.cursor()
        if project_id is not None:
            c.execute(
                "SELECT value FROM project_thresholds WHERE project_id=? AND test_type=? AND key=?",
                (project_id, test_type, key)
            )
            row = c.fetchone()
            if row:
                return row[0]
        c.execute(
            "SELECT value FROM default_thresholds WHERE test_type=? AND key=?",
            (test_type, key)
        )
        row = c.fetchone()
        return row[0] if row else fallback

    def set_threshold(
        self, 
        project_id: Optional[int], 
        test_type: str, 
        key: str, 
        value: str
    ) -> None:
        """
        Définit ou met à jour un seuil pour un projet ou globalement.
        """
        c = self.db.conn.cursor()
        if project_id is None:
            c.execute(
                "REPLACE INTO default_thresholds(test_type, key, value) VALUES (?,?,?)",
                (test_type, key, value)
            )
        else:
            c.execute(
                "REPLACE INTO project_thresholds(project_id, test_type, key, value) VALUES (?,?,?,?)",
                (project_id, test_type, key, value)
            )
        self.db.conn.commit()

    # ---------- Projects ----------
    def add_project(self, data: dict) -> int:
        """
        Ajoute un nouveau projet à la base de données.
        """
        c = self.db.conn.cursor()
        c.execute(
            """
            INSERT INTO projects(company, name, location, tag, work_type, test_date, contact, responsables, notes)
            VALUES(:company, :name, :location, :tag, :work_type, :test_date, :contact, :responsables, :notes)
            """,
            data
        )
        self.db.conn.commit()
        return c.lastrowid

    def list_projects(self) -> list:
        """
        Retourne la liste de tous les projets.
        """
        c = self.db.conn.cursor()
        c.execute("SELECT * FROM projects ORDER BY id DESC")
        return c.fetchall()

    # ---------- Tests ----------
    def save_test(
        self, 
        project_id: int, 
        test_type: str, 
        conformity: Optional[bool], 
        params: dict, 
        results: dict
    ) -> None:
        """
        Enregistre un test pour un projet donné.
        """
        now = datetime.utcnow().isoformat()
        c = self.db.conn.cursor()
        c.execute(
            """
            INSERT INTO tests(project_id, test_type, status, conformity, params_json, results_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                project_id, test_type, "done",
                None if conformity is None else (1 if conformity else 0),
                json.dumps(params, ensure_ascii=False),
                json.dumps(results, ensure_ascii=False),
                now, now
            )
        )
        self.db.conn.commit()
