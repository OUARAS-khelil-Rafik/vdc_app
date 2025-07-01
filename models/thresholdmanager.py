from .utils import dict_from_row

class ThresholdManager:
    def __init__(self, db):
        self.db = db

    def get_thresholds(self):
        rows = self.db.conn.execute("SELECT id, iso_class, parameter, max_value FROM thresholds").fetchall()
        columns = ["id", "iso_class", "parameter", "max_value"]
        return [dict_from_row(row, columns) for row in rows]

    def add_threshold(self, iso_class, parameter, max_value):
        self.db.conn.execute(
            "INSERT INTO thresholds (iso_class, parameter, max_value) VALUES (?, ?, ?)",
            (iso_class, parameter, max_value)
        )
        self.db.conn.commit()

    def update_threshold(self, threshold_id, iso_class, parameter, max_value):
        self.db.conn.execute(
            "UPDATE thresholds SET iso_class=?, parameter=?, max_value=? WHERE id=?",
            (iso_class, parameter, max_value, threshold_id)
        )
        self.db.conn.commit()

    def delete_threshold(self, threshold_id):
        self.db.conn.execute("DELETE FROM thresholds WHERE id = ?", (threshold_id,))
        self.db.conn.commit()

    def get_threshold(self, threshold_id):
        row = self.db.conn.execute(
            "SELECT id, iso_class, parameter, max_value FROM thresholds WHERE id = ?",
            (threshold_id,)
        ).fetchone()
        columns = ["id", "iso_class", "parameter", "max_value"]
        return dict_from_row(row, columns) if row else None