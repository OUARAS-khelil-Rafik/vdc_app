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
                contact_info      TEXT, -- Email + Numéro de téléphone (format libre, à parser côté app)
                work_type         TEXT NOT NULL CHECK(work_type IN ('HVAC','Thermal Mapping','Instrumentation')),
                validation_status TEXT NOT NULL DEFAULT 'En attente' CHECK(validation_status IN ('En attente','Validé')),
                -- Responsables: relation N:N via table d'association project_users
                -- Les colonnes ci-dessous sont conservées pour compatibilité, mais non utilisées pour multi-users
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
                iso_name     TEXT,   -- ISO 1, ISO 2, etc. (NULL si seuil custom)
                test_name    TEXT NOT NULL,
                value        REAL,
                UNIQUE (iso_name, test_name)
            );
            """)

            # Sessions de tests
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id       INTEGER NOT NULL,
                technician_id    INTEGER NOT NULL,
                test_name        TEXT    NOT NULL,
                measurement_date TEXT    NOT NULL,
                is_validated     INTEGER DEFAULT 0,
                validated_by     INTEGER,
                validated_date   TEXT,
                FOREIGN KEY(project_id)     REFERENCES projects(id),
                FOREIGN KEY(technician_id)  REFERENCES users(id),
                FOREIGN KEY(validated_by)   REFERENCES users(id)
            );
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
        # Validation du numéro de téléphone (obligatoire, non vide)
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

    # ----------------------------------------------------------------
    # Méthodes pour l'équipement
    # ----------------------------------------------------------------

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
