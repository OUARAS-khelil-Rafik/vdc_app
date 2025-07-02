# models/testmanager.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models/testmanager.py

Gestion de la saisie des tests et de leurs mesures.
"""
from typing import List, Tuple, Optional
from datetime import date

class TestManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, project_id: int) -> List[Tuple[str, Optional[float], Optional[float]]]:
        """
        Renvoie une liste de tuples (test_name, min_value, max_value)
        pour les seuils définis sur le projet donné.
        """
        rows = self.db.conn.execute(
            "SELECT test_name, min_value, max_value "
            "FROM thresholds WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        return [
            (row["test_name"], row["min_value"], row["max_value"])
            for row in rows
        ]

    def save_test(self,
                  project_id: int,
                  technician_id: int,
                  point_name: str,
                  measurements: List[Tuple[str, float, Optional[float], Optional[float]]]
                  ) -> None:
        """
        Enregistre une session de test + ses mesures.
        measurements = list de (test_name, value, min_value, max_value)
        """
        # 1) Création de la session
        cur = self.db.conn.execute(
            "INSERT INTO tests (project_id, technician_id, measurement_date) "
            "VALUES (?, ?, ?)",
            (project_id, technician_id, date.today().isoformat())
        )
        test_id = cur.lastrowid

        # 2) Insertion des mesures
        for test_name, value, _, _ in measurements:
            self.db.conn.execute(
                "INSERT INTO measurements (test_id, point_name, parameter, value) "
                "VALUES (?, ?, ?, ?)",
                (test_id, point_name, test_name, value)
            )

        self.db.conn.commit()
