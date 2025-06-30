# init_admin.py
from models.database import Database

db = Database("data/vdc.db")
db.initialize()   # crée tables si besoin

try:
    uid = db.create_user("admin", "admin", "Administrateur")
    print(f"Admin créé avec l’ID {uid}")
except Exception as e:
    print("Erreur ou admin déjà existant :", e)
