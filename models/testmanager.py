# models/testmanager.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

class TestManager:
    """
    Pont unique entre l'UI et la DB pour:
      • Seuils (fallback: projet -> défauts -> valeur passée)
      • Sauvegarde de tests (params_json inclut phase, standard_id, etc.)
      • Lecture des derniers résultats par test
      • Conformité globale d'un projet (préférence As Left)
    """

    def __init__(self, db):
        self.db = db
        self.conn = db.conn

    # ----------------- Seuils -----------------
    def get_threshold(self, project_id: Optional[int], test_type: str, key: str, default_val: Any = None) -> Any:
        """
        Cherche d'abord dans project_thresholds, sinon default_thresholds.
        Si rien => default_val (fourni par l'appelant).
        """
        cur = self.conn.cursor()
        if project_id is not None:
            row = cur.execute("""
                SELECT value FROM project_thresholds
                WHERE project_id=? AND test_type=? AND key=?
            """, (project_id, test_type, key)).fetchone()
            if row and row["value"] is not None:
                return row["value"]
        row = cur.execute("""
            SELECT value FROM default_thresholds
            WHERE test_type=? AND key=?
        """, (test_type, key)).fetchone()
        if row and row["value"] is not None:
            return row["value"]
        return default_val

    def set_threshold(self, project_id: Optional[int], test_type: str, key: str, value: str) -> None:
        self.db.set_threshold(project_id, test_type, key, value)

    # ----------------- Sauvegarde test -----------------
    def save_test(
        self,
        project_id: int,
        test_type: str,
        conformity: Optional[bool],
        params: Dict[str, Any],
        results: Dict[str, Any],
    ) -> int:
        """
        Ecrit dans la table tests sans changer le schéma.
        On sérialise params/results en JSON.
        """
        now = datetime.utcnow().isoformat(timespec="seconds")
        pj = json.dumps(params or {}, ensure_ascii=False)
        rj = json.dumps(results or {}, ensure_ascii=False)

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO tests (project_id, test_type, status, conformity, params_json, results_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, test_type, "done", (1 if conformity is True else (0 if conformity is False else None)),
              pj, rj, now, now))
        self.conn.commit()
        return cur.lastrowid

    # ----------------- Lecture -----------------
    def latest_by_type(self, project_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Renvoie pour chaque test_type la dernière ligne (updated_at max).
        NOTE: Ici on renvoie *toutes* les lignes triées & on sélectionne par test_type/phase au besoin côté appelant.
        """
        cur = self.conn.cursor()
        rows = cur.execute("""
            SELECT id, test_type, conformity, params_json, results_json, created_at, updated_at
            FROM tests
            WHERE project_id=?
            ORDER BY updated_at DESC, id DESC
        """, (project_id,)).fetchall()
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            tt = row["test_type"]
            if tt not in out:  # conserve la plus récente
                out[tt] = {
                    "id": row["id"],
                    "test_type": tt,
                    "conformity": (True if row["conformity"] == 1 else False if row["conformity"] == 0 else None),
                    "params": json.loads(row["params_json"] or "{}"),
                    "results": json.loads(row["results_json"] or "{}"),
                    "updated_at": row["updated_at"],
                }
        return out

    def all_for_project(self, project_id: int) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        rows = cur.execute("""
            SELECT id, test_type, conformity, params_json, results_json, created_at, updated_at
            FROM tests
            WHERE project_id=?
            ORDER BY updated_at DESC, id DESC
        """, (project_id,)).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "test_type": r["test_type"],
                "conformity": (True if r["conformity"] == 1 else False if r["conformity"] == 0 else None),
                "params": json.loads(r["params_json"] or "{}"),
                "results": json.loads(r["results_json"] or "{}"),
                "updated_at": r["updated_at"],
            })
        return out

    # ----------------- Conformité globale projet -----------------
    def project_conformity(self, project_id: int) -> Optional[bool]:
        """
        Règle:
          • pour chaque test logique, on préfère la phase 'as_left' si elle existe (même test_type),
            sinon on prend 'as_found';
          • si au moins un test sélectionné est False => False,
          • si aucun test n'a été saisi => None,
          • si tout est True => True,
          • sinon => None.
        On accepte que test_type contienne le même nom (ex: 'ACPH') et que params.phase ∈ {'as_found','as_left'}.
        """
        rows = self.all_for_project(project_id)
        # regrouper par test logique (clé: test_type sans phase)
        grouped: Dict[str, Dict[str, Optional[bool]]] = {}
        for r in rows:
            base = r["test_type"]  # on garde tel quel; la phase est dans params
            phase = (r.get("params", {}) or {}).get("phase")
            if base not in grouped:
                grouped[base] = {"as_found": None, "as_left": None}
            grouped[base][phase if phase in ("as_found", "as_left") else "as_found"] = r["conformity"]

        picked: List[Optional[bool]] = []
        for base, phases in grouped.items():
            picked.append(phases["as_left"] if phases["as_left"] is not None else phases["as_found"])

        if not picked:
            return None
        if any(v is False for v in picked if v is not None):
            return False
        if all(v is True for v in picked if v is not None) and any(v is True for v in picked):
            return True
        return None
