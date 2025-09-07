# models/database.py

"""
Gestion de la base SQLite pour le MVP VDC Engineering :
– Création des tables (users, projects, thresholds, tests, measurements, equipment)
– Authentification des utilisateurs avec rôles
– Gestion des mots de passe (hachage SHA-256)
– Nouvelles méthodes pour enregistrer les sessions de tests, leurs mesures et équipements
"""

import sqlite3
import hashlib
from typing import Optional, Dict, Any, List

class Database:
    def __init__(self, db_path: str):
        """
        Initialise la connexion SQLite et configure le row factory
        pour accéder aux colonnes par nom.
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    # ------------------- Initialisation & Tables -------------------
    def initialize(self) -> None:
        """
        Crée (ou recrée) les tables nécessaires pour l'application.
        """
        with self.conn:
            # Utilisateurs
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                full_name       TEXT NOT NULL,
                role            TEXT NOT NULL
                                 CHECK(role IN ('Administrateur','Technicien','Superviseur', 'Technicien responsable')),
                email           TEXT UNIQUE NOT NULL
                                 CHECK(email GLOB '*@*.*'),
                phone_number    TEXT NOT NULL,
                validate_user   TEXT NOT NULL DEFAULT 'Non validé'
                                 CHECK(validate_user IN ('Validé','Non validé'))
            );
            """)

            # Projets
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name      TEXT NOT NULL,
                location          TEXT,
                room_tag          TEXT,
                test_date         TEXT NOT NULL,
                contact_info      TEXT,
                work_type         TEXT NOT NULL CHECK(work_type IN ('HVAC','Thermal Mapping','Instrumentation')),
                validation_status TEXT NOT NULL DEFAULT 'En attente' CHECK(validation_status IN ('En attente','Validé')),
                assigned_to       INTEGER,
                FOREIGN KEY (assigned_to) REFERENCES users(id)
            );
            """)
            # Table d'association projets <-> utilisateurs (responsables multiples)
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS project_users (
                project_id INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                PRIMARY KEY (project_id, user_id),
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """)

            # Seuils ISO / personnalisés
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS thresholds (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                iso_name     TEXT,
                test_name    TEXT NOT NULL,
                value        REAL,
                UNIQUE (iso_name, test_name)
            );
            """)

            # Sessions de tests
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                test_type TEXT,
                status TEXT,
                conformity INTEGER,
                params_json TEXT,
                results_json TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            """)

            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS default_thresholds (
                test_type TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY(test_type, key)
            );
            """)

            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS project_thresholds (
                project_id INTEGER,
                test_type TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY(project_id, test_type, key)
            )
            """)

            # Points de mesure
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id     INTEGER NOT NULL,
                point_name  TEXT    NOT NULL,
                parameter   TEXT    NOT NULL,
                value       REAL    NOT NULL,
                FOREIGN KEY(test_id) REFERENCES tests(id)
            );
            """)

            # Étalons & étalonnages
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS standards (
                id INTEGER PRIMARY KEY,
                serial TEXT UNIQUE,
                name TEXT,
                category TEXT,
                manufacturer TEXT,
                model TEXT,
                location TEXT,
                owner_id INTEGER,
                tags TEXT,
                interval_months INTEGER,
                last_cal_date TEXT,
                next_cal_date TEXT,
                status TEXT,
                blocked INTEGER,
                block_reason TEXT,
                certificate_path TEXT,
                certificate_id TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            );
            """)
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS calibrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_id INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
                cal_date TEXT,
                due_date TEXT,
                on_site INTEGER,
                method TEXT,
                certificate_id TEXT,
                certificate_path TEXT,
                pass_fail INTEGER,
                results_json TEXT,
                notes TEXT,
                created_at TEXT
            );
            """)

            # Equipements des tests
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS equipment (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id          INTEGER NOT NULL,
                name             TEXT    NOT NULL,
                calibration_date TEXT    NOT NULL,
                periodicity      TEXT    NOT NULL,
                FOREIGN KEY(test_id) REFERENCES tests(id)
            );
            """)

    # ------------------- Utilisateurs -------------------
    def _hash_password(self, password: str) -> str:
        """
        Retourne le hash SHA-256 de la chaîne fournie.
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def create_user(
        self,
        username: str,
        password: str,
        full_name: str,
        role: str,
        email: str,
        phone_number: str,
        validate_user: str = "Non validé"
    ) -> int:
        """
        Crée un nouvel utilisateur (avec email et téléphone obligatoires) et renvoie son ID.
        """
        if phone_number is None or str(phone_number).strip() == "":
            raise ValueError("Le numéro de téléphone est obligatoire.")
        phone_number = str(phone_number).strip()

        pwd_hash = self._hash_password(password)
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role, email, phone_number, validate_user) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, pwd_hash, full_name, role, email, phone_number, validate_user)
            )
            return cursor.lastrowid

    def authenticate_user(
        self,
        username_or_email: str,
        password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Authentifie un utilisateur avec son username OU son email.
        Ne renvoie un dict que si l'utilisateur est 'Validé'.
        """
        pwd_hash = self._hash_password(password)
        row = self.conn.execute(
            "SELECT id, username, full_name, role, email, phone_number "
            "FROM users "
            "WHERE (username = ? OR email = ?) AND password_hash = ? AND validate_user = 'Validé'",
            (username_or_email, username_or_email, pwd_hash)
        ).fetchone()
        if row:
            return {
                "id": row["id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
                "email": row["email"],
                "phone_number": row["phone_number"],
            }
        return None

    # ------------------- Projets & Tests -------------------
    def create_test(
        self,
        project_id: int,
        technician_id: int,
        test_name: str,
        measurement_date: str
    ) -> int:
        """
        Crée une session de test et renvoie l'ID généré.
        """
        cursor = self.conn.execute(
            "INSERT INTO tests (project_id, technician_id, test_name, measurement_date) "
            "VALUES (?, ?, ?, ?)",
            (project_id, technician_id, test_name, measurement_date)
        )
        self.conn.commit()
        return cursor.lastrowid

    # ------------------- Mesures -------------------
    def add_measurement(
        self,
        test_id: int,
        point_name: str,
        parameter: str,
        value: float
    ) -> None:
        """
        Enregistre une mesure pour un point donné dans une session de test.
        """
        self.conn.execute(
            "INSERT INTO measurements (test_id, point_name, parameter, value) "
            "VALUES (?, ?, ?, ?)",
            (test_id, point_name, parameter, value)
        )
        self.conn.commit()

    # ------------------- Equipements -------------------
    def add_equipment(
        self,
        test_id: int,
        name: str,
        calibration_date: str,
        periodicity: str
    ) -> int:
        """
        Ajoute un équipement pour une session de test.
        """
        cursor = self.conn.execute(
            "INSERT INTO equipment (test_id, name, calibration_date, periodicity) "
            "VALUES (?, ?, ?, ?)",
            (test_id, name, calibration_date, periodicity)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_equipments(self, test_id: int) -> List[Dict[str, Any]]:
        """
        Récupère tous les équipements liés à une session de test.
        """
        rows = self.conn.execute(
            "SELECT id, name, calibration_date, periodicity "
            "FROM equipment WHERE test_id = ?",
            (test_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def update_equipment(
        self,
        equipment_id: int,
        name: str,
        calibration_date: str,
        periodicity: str
    ) -> None:
        """
        Met à jour un équipement existant.
        """
        self.conn.execute(
            "UPDATE equipment SET name = ?, calibration_date = ?, periodicity = ? "
            "WHERE id = ?",
            (name, calibration_date, periodicity, equipment_id)
        )
        self.conn.commit()

    # ------------------- Seuils -------------------
    def set_threshold(self, project_id: Optional[int], test_type: str, key: str, value: str) -> None:
        """
        Définit ou met à jour un seuil pour un projet et un type de test donné.
        Si project_id est None, met à jour la table default_thresholds.
        Sinon, met à jour la table project_thresholds.
        """
        if project_id is None:
            self.conn.execute(
                """
                INSERT INTO default_thresholds (test_type, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(test_type, key) DO UPDATE SET value=excluded.value
                """,
                (test_type, key, value)
            )
        else:
            self.conn.execute(
                """
                INSERT INTO project_thresholds (project_id, test_type, key, value)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, test_type, key) DO UPDATE SET value=excluded.value
                """,
                (project_id, test_type, key, value)
            )
        self.conn.commit()
