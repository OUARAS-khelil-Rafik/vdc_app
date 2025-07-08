# models/usermanager.py

import sqlite3
import hashlib

class UserManager:
    DB_PATH = "data/vdc.db"

    @staticmethod
    def fetch_users():
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, username, full_name, role, validate_user FROM users")
            users = cursor.fetchall()
        except Exception:
            users = []
        finally:
            conn.close()
        return users

    @staticmethod
    def username_exists(username, exclude_id=None):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            if exclude_id:
                cursor.execute("SELECT 1 FROM users WHERE username=? AND id!=?", (username, exclude_id))
            else:
                cursor.execute("SELECT 1 FROM users WHERE username=?", (username,))
            exists = cursor.fetchone() is not None
        finally:
            conn.close()
        return exists

    @staticmethod
    def add_user(username, password, full_name, role):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            cursor.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (username, password_hash, full_name, role)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def update_user(user_id, username, full_name, role):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET username=?, full_name=?, role=? WHERE id=?",
                (username, full_name, role, user_id)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def delete_user(user_id):
        conn = sqlite3.connect(UserManager.DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE id=? AND role!='admin'", (user_id,))
            conn.commit()
        finally:
            conn.close()
