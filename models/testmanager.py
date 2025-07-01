from PyQt5.QtCore import QDateTime

class TestManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self, iso_class):
        rows = self.db.conn.execute("SELECT parameter, max_value FROM thresholds WHERE iso_class = ?", (iso_class,)).fetchall()
        return [(r["parameter"], r["max_value"]) for r in rows]

    def save_test(self, project_id, user_id, point_name, measurements):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        cursor = self.db.conn.execute(
            "INSERT INTO tests (project_id, technician_id, measurement_date) VALUES (?, ?, ?)",
            (project_id, user_id, timestamp)
        )
        test_id = cursor.lastrowid
        compliant = True
        for param, value, max_val in measurements:
            self.db.conn.execute(
                "INSERT INTO measurements (test_id, point_name, parameter, value) VALUES (?, ?, ?, ?)",
                (test_id, point_name, param, value)
            )
            if value > max_val:
                compliant = False
        self.db.conn.commit()
        return compliant