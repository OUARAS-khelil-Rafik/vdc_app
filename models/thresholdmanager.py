#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
models/thresholdmanager.py

Gestion des seuils de conformité par projet et par nom de test.
"""
import sqlite3
from typing import List, Dict, Any, Optional

class ThresholdManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Si project_id est fourni, ne renvoie que les seuils pour ce projet.
        Sinon, renvoie tous les seuils.
        """
        if project_id is not None:
            rows = self.db.conn.execute(
                "SELECT id, project_id, test_name, min_value, max_value "
                "FROM thresholds WHERE project_id = ?",
                (project_id,)
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT id, project_id, test_name, min_value, max_value "
                "FROM thresholds"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_threshold(self, threshold_id: int) -> Optional[Dict[str, Any]]:
        """
        Renvoie un seuil unique par son ID, ou None s’il n’existe pas.
        """
        row = self.db.conn.execute(
            "SELECT id, project_id, test_name, min_value, max_value "
            "FROM thresholds WHERE id = ?",
            (threshold_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_threshold(self,
                      project_id: int,
                      test_name: str,
                      min_value: Optional[float],
                      max_value: Optional[float]) -> None:
        """
        Crée un nouveau seuil pour un projet et un test donné.
        """
        self.db.conn.execute(
            "INSERT INTO thresholds (project_id, test_name, min_value, max_value) "
            "VALUES (?, ?, ?, ?)",
            (project_id, test_name, min_value, max_value)
        )
        self.db.conn.commit()

    def update_threshold(self,
                         threshold_id: int,
                         project_id: int,
                         test_name: str,
                         min_value: Optional[float],
                         max_value: Optional[float]) -> None:
        """
        Met à jour un seuil existant.
        """
        self.db.conn.execute(
            "UPDATE thresholds "
            "SET project_id = ?, test_name = ?, min_value = ?, max_value = ? "
            "WHERE id = ?",
            (project_id, test_name, min_value, max_value, threshold_id)
        )
        self.db.conn.commit()

    def delete_threshold(self, threshold_id: int) -> None:
        """
        Supprime un seuil.
        """
        self.db.conn.execute(
            "DELETE FROM thresholds WHERE id = ?",
            (threshold_id,)
        )
        self.db.conn.commit()
