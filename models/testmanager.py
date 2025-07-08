from typing import List, Tuple, Optional
from datetime import date
from .thresholdmanager import ThresholdManager

class TestManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, project_id: int) -> List[Tuple[str, Optional[float], Optional[float]]]:
        rows = self.db.conn.execute(
            "SELECT test_name, min_value, max_value "
            "FROM thresholds WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        return [
            (row["test_name"], row["min_value"], row["max_value"])
            for row in rows
        ]

    def create_test(self, project_id: int, technician_id: int, test_name: str) -> int:
        """
        Crée une nouvelle session de test et retourne son ID.
        """
        cur = self.db.conn.execute(
            "INSERT INTO tests (project_id, technician_id, test_name, measurement_date) "
            "VALUES (?, ?, ?, ?)",
            (project_id, technician_id, test_name, date.today().isoformat())
        )
        self.db.conn.commit()
        return cur.lastrowid

    def save_test(self,
                  project_id: int,
                  technician_id: int,
                  test_name: str,
                  measurements: List[Tuple[str, float, Optional[float], Optional[float]]]
                  ) -> int:
        """
        Enregistre une session de test + ses mesures.
        Si une session existe déjà pour ce (project, technician), on la remplace.
        Retourne l'ID de la session.
        """
        # Supprimer ancienne session (et mesures) si existante
        existing = self.get_latest_test(project_id, technician_id)
        if existing:
            test_id = existing["id"]
            self.db.conn.execute("DELETE FROM measurements WHERE test_id = ?", (test_id,))
        else:
            test_id = self.create_test(project_id, technician_id, test_name)

        # Insertion des mesures
        for parameter, value, _, _ in measurements:
            self.db.conn.execute(
                "INSERT INTO measurements (test_id, point_name, parameter, value) "
                "VALUES (?, ?, ?, ?)",
                (test_id, parameter, parameter, value)
            )
        self.db.conn.commit()
        return test_id

    def get_required_points(self, project_id: int) -> int:
        row = self.db.conn.execute(
            "SELECT cleanroom_area FROM projects WHERE id = ?",
            (project_id,)
        ).fetchone()
        if not row or row["cleanroom_area"] is None:
            return 0
        return ThresholdManager(self.db).compute_required_points(row["cleanroom_area"])

    def get_latest_test(self, project_id: int, technician_id: int) -> Optional[dict]:
        """
        Récupère la dernière session de test pour ce projet et ce technicien.
        """
        row = self.db.conn.execute(
            "SELECT * FROM tests "
            "WHERE project_id = ? AND technician_id = ? "
            "ORDER BY measurement_date DESC, id DESC LIMIT 1",
            (project_id, technician_id)
        ).fetchone()
        return dict(row) if row else None

    def get_measurements(self, test_id: int) -> List[dict]:
        """
        Récupère toutes les mesures d'une session de test.
        """
        rows = self.db.conn.execute(
            "SELECT id, point_name, parameter, value "
            "FROM measurements WHERE test_id = ? ORDER BY id",
            (test_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_measurement(self, measurement_id: int, value: float) -> None:
        """
        Met à jour la valeur d'une mesure existante.
        """
        self.db.conn.execute(
            "UPDATE measurements SET value = ? WHERE id = ?",
            (value, measurement_id)
        )
        self.db.conn.commit()

    def validate_test(self, test_id: int, admin_id: int) -> None:
        """
        Marque une session comme validée par l'admin.
        """
        self.db.conn.execute(
            "UPDATE tests SET is_validated = 1, validated_by = ?, validated_date = ? "
            "WHERE id = ?",
            (admin_id, date.today().isoformat(), test_id)
        )
        self.db.conn.commit()
