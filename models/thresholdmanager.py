from typing import List, Dict, Any, Optional
import math

class ThresholdManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        If project_id is provided, returns only the thresholds for that project.
        Otherwise, returns all thresholds.
        """
        query = (
            "SELECT id, iso_name, project_id, test_name, value "
            "FROM thresholds"
        )
        params = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (project_id,)
        rows = self.db.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_threshold(self, threshold_id: int) -> Optional[Dict[str, Any]]:
        """
        Returns a single threshold by its ID.
        """
        row = self.db.conn.execute(
            "SELECT id, iso_name, project_id, test_name, value "
            "FROM thresholds WHERE id = ?",
            (threshold_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_threshold(
        self,
        iso_name: Optional[str],
        project_id: Optional[int],
        test_name: str,
        value: Optional[float]
    ) -> None:
        """
        Creates a new threshold for a given project and test.
        iso_name: set for ISO thresholds, None for custom thresholds.
        project_id: set for custom thresholds, None for ISO thresholds.
        """
        if project_id is None and iso_name is None:
            raise ValueError("Either project_id or iso_name must be provided.")
        self.db.conn.execute(
            "INSERT INTO thresholds (iso_name, project_id, test_name, value) "
            "VALUES (?, ?, ?, ?)",
            (iso_name, project_id, test_name, value)
        )
        self.db.conn.commit()

    def update_threshold(
        self,
        threshold_id: int,
        iso_name: Optional[str],
        project_id: Optional[int],
        test_name: str,
        value: Optional[float]
    ) -> None:
        if project_id is None and iso_name is None:
            raise ValueError("Either project_id or iso_name must be provided.")
        self.db.conn.execute(
            "UPDATE thresholds "
            "SET iso_name = ?, project_id = ?, test_name = ?, value = ? "
            "WHERE id = ?",
            (iso_name, project_id, test_name, value, threshold_id)
        )
        self.db.conn.commit()

    def delete_threshold(self, threshold_id: int) -> None:
        """
        Deletes a threshold.
        """
        self.db.conn.execute(
            "DELETE FROM thresholds WHERE id = ?",
            (threshold_id,)
        )
        self.db.conn.commit()

    def compute_required_points(self, area_m2: float) -> int:
        """
        Nombre minimal de points de prélèvement (NL) selon Tableau A.1 de la norme.
        Si area_m2 > 1000, applique la formule (A.1).
        """
        # Tableau A.1 : (surface_max, NL)
        table = [
            (2,   1),  (4,   2),  (6,   3),  (8,   4),
            (10,  5),  (24,  6),  (28,  7),  (32,  8),
            (36,  9),  (52, 10),  (56, 11),  (64, 12),
            (68, 13),  (72, 14),  (76, 15),  (104,16),
            (108,17),  (116,18),  (148,19),  (156,20),
            (192,21),  (232,22),  (276,23),  (352,24),
            (436,25),  (636,26),  (1000,27)
        ]
        for max_area, nl in table:
            if area_m2 <= max_area:
                return nl
        # Pour A > 1000 m² : formule (A.1)
        return math.ceil(27 * (area_m2 / 1000) ** 0.5)
