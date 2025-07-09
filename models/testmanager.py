# models/testmanager.py

from typing import List, Tuple, Optional
from datetime import date
from .thresholdmanager import ThresholdManager

class TestManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, iso_class: str) -> List[str]:
        """
        Retourne la liste des paramètres de test pour une classe ISO donnée.
        """
        rows = self.db.conn.execute(
            "SELECT test_name FROM thresholds WHERE iso_name = ?",
            (iso_class,)
        ).fetchall()
        return [row["test_name"] for row in rows]

    def get_required_points(self, project_id: int) -> int:
        """
        Retourne le nombre de points requis pour un projet donné.
        """
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

    def add_measurement(self, test_id: int, point_name: str, parameter: str, value: float) -> None:
        """
        Ajoute une nouvelle mesure à une session existante.
        """
        self.db.add_measurement(test_id, point_name, parameter, value)

    def save_test(
        self,
        project_id: int,
        technician_id: int,
        test_name: str,
        measurements: List[Tuple[str, str, float, Optional[int]]]
    ) -> int:
        """
        Crée une nouvelle session de test et enregistre toutes les mesures.
        Si une session existe déjà pour ce (project, technician), elle n'est pas supprimée.
        """
        test_id = self.db.create_test(
            project_id, technician_id, test_name, date.today().isoformat()
        )
        for point_name, parameter, value, _ in measurements:
            if value is not None:
                self.db.add_measurement(test_id, point_name, parameter, value)
        return test_id

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

    # ----------------------------------------------------------------
    # Gestion de l'équipement
    # ----------------------------------------------------------------

    def add_equipment(
        self,
        test_id: int,
        name: str,
        calibration_date: str,
        periodicity: str
    ) -> int:
        """
        Crée un enregistrement d'équipement pour une session de test.
        """
        return self.db.add_equipment(test_id, name, calibration_date, periodicity)

    def get_equipments(self, test_id: int) -> List[dict]:
        """
        Liste les équipements d'une session.
        """
        return self.db.get_equipments(test_id)

    def update_equipment(
        self,
        equipment_id: int,
        name: str,
        calibration_date: str,
        periodicity: str
    ) -> None:
        """
        Met à jour les infos d'un équipement.
        """
        self.db.update_equipment(equipment_id, name, calibration_date, periodicity)
