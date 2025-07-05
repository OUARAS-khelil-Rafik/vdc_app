#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
models/database.py

Gestion de la base SQLite pour le MVP VDC Engineering :
– Création des tables (users, projects, thresholds, tests, measurements)
– Authentification des utilisateurs avec rôles
– Gestion des mots de passe (hachage SHA-256)
"""
import sqlite3
import hashlib
from typing import Optional, Dict, Any

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
                role            TEXT NOT NULL
                                 CHECK(role IN ('Administrateur','Technicien','Technicien premium')),
                validate_user   TEXT NOT NULL DEFAULT 'Non validé'
                                 CHECK(validate_user IN ('Validé','Non validé'))
            );
            """)

            # Projets
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name    TEXT NOT NULL,
                location        TEXT,
                room_type       TEXT,
                test_date       TEXT NOT NULL,
                created_by      INTEGER NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );
            """)

            # Seuils : on supprime l'ancienne table et on la recrée
            self.conn.execute("DROP TABLE IF EXISTS thresholds;")
            self.conn.execute("""
            CREATE TABLE thresholds (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                test_name    TEXT    NOT NULL,
                min_value    REAL,
                max_value    REAL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
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
                FOREIGN KEY(project_id)    REFERENCES projects(id),
                FOREIGN KEY(technician_id) REFERENCES users(id),
                FOREIGN KEY(validated_by)  REFERENCES users(id)
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

    def _hash_password(self, password: str) -> str:
        """
        Retourne le hash SHA-256 de la chaîne fournie.
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def create_user(self,
                    username: str,
                    password: str,
                    role: str,
                    validate_user: str = "Non validé") -> int:
        """
        Crée un nouvel utilisateur et renvoie son ID.
        Lève sqlite3.IntegrityError si le username existe déjà.
        """
        pwd_hash = self._hash_password(password)
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO users (username, password_hash, role, validate_user) "
                "VALUES (?, ?, ?, ?)",
                (username, pwd_hash, role, validate_user)
            )
        return cursor.lastrowid

    def authenticate_user(self,
                          username: str,
                          password: str) -> Optional[Dict[str, Any]]:
        """
        Vérifie les identifiants, et renvoie un dict {id, username, role}
        si OK, ou None sinon. Seuls les utilisateurs validés peuvent se connecter.
        """
        pwd_hash = self._hash_password(password)
        cursor = self.conn.execute(
            "SELECT id, username, role "
            "FROM users "
            "WHERE username = ? AND password_hash = ? AND validate_user = 'Validé'",
            (username, pwd_hash)
        )
        row = cursor.fetchone()
        if row:
            return {"id": row["id"], "username": row["username"], "role": row["role"]}
        return None
