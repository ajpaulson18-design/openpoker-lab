"""Opportunity-based Beta models and SQLite persistence.

Each observation records one opportunity, not an inferred absence of action.
Profiles are subjective priors, with an explicit effective sample size of 10.
"""
import json
import math
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid

METRICS = ("vpip", "pfr", "three_bet", "fold_to_bet", "aggression", "showdown_bluff")
PROFILES = {
    "balanced": (.26, .20, .08, .45, .45, .25),
    "tight": (.15, .11, .04, .60, .30, .12),
    "calling_station": (.48, .10, .03, .20, .22, .10),
    "aggressive": (.42, .31, .14, .32, .68, .40),
}
STREETS = ("all", "preflop", "flop", "turn", "river")


def posterior(mean, successes, opportunities, strength=10):
    a = mean*strength + successes
    b = (1-mean)*strength + opportunities-successes
    m = a/(a+b)
    sd = math.sqrt(a*b/((a+b)**2*(a+b+1)))
    return {"mean": m, "interval95": [max(0, m-1.96*sd), min(1, m+1.96*sd)],
            "observations": opportunities, "successes": successes,
            "prior_strength": strength, "confidence": "low" if opportunities < 30 else "moderate" if opportunities < 100 else "higher",
            "interval_method": "normal approximation to Beta posterior"}


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS opponents (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, opponent_id TEXT NOT NULL REFERENCES opponents(id),
                    metric TEXT NOT NULL, street TEXT NOT NULL, success INTEGER NOT NULL,
                    note TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, input TEXT NOT NULL, result TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def add_opponent(self, name, profile="balanced"):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Opponent name must contain 1–80 characters.")
        if profile not in PROFILES:
            raise ValueError("Unknown opponent profile.")
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO opponents VALUES (?, ?, ?)", (identity, name.strip(), profile))
        return self.get_opponent(identity)

    def get_opponent(self, identity, street="all"):
        if street not in STREETS:
            raise ValueError("Unknown street.")
        with self.connect() as db:
            row = db.execute("SELECT * FROM opponents WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise ValueError("Opponent not found.")
            query = "SELECT metric, SUM(success) AS successes, COUNT(*) AS n FROM observations WHERE opponent_id=?"
            args = [identity]
            if street != "all":
                query += " AND street=?"
                args.append(street)
            rows = db.execute(query+" GROUP BY metric", args).fetchall()
        counts = {r["metric"]: (r["successes"], r["n"]) for r in rows}
        return {**dict(row), "street": street, "metrics": {
            m: posterior(prior, *counts.get(m, (0, 0)))
            for m, prior in zip(METRICS, PROFILES[row["profile"]])}}

    def opponents(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM opponents ORDER BY name")]
        return [self.get_opponent(i) for i in ids]

    def observe(self, opponent_id, metric, success, street="all", note="", id=None):
        self.get_opponent(opponent_id)
        if metric not in METRICS or street not in STREETS or type(success) is not bool:
            raise ValueError("Provide a valid metric, street, and boolean success.")
        if metric in ("vpip", "pfr", "three_bet") and street not in ("all", "preflop"):
            raise ValueError("This statistic describes a preflop opportunity.")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Notes may contain at most 2,000 characters.")
        identity = id or uuid.uuid4().hex
        if not isinstance(identity, str) or not 1 <= len(identity) <= 100:
            raise ValueError("Observation ID must contain 1–100 characters.")
        with self.connect() as db:
            existing = db.execute("SELECT * FROM observations WHERE id=?", (identity,)).fetchone()
            values = (opponent_id, metric, street, int(success), note)
            if existing:
                if tuple(existing[k] for k in ("opponent_id", "metric", "street", "success", "note")) != values:
                    raise ValueError("Observation ID already belongs to different data.")
                return {"id": identity, "duplicate": True}
            db.execute("INSERT INTO observations (id,opponent_id,metric,street,success,note) VALUES (?,?,?,?,?,?)",
                       (identity, *values))
        return {"id": identity, "duplicate": False}

    def save_analysis(self, inputs, result):
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO analyses(id,input,result) VALUES (?,?,?)",
                       (identity, json.dumps(inputs), json.dumps(result)))
        return identity

    def export(self):
        with self.connect() as db:
            return {"schema_version": 1, **{table: [dict(r) for r in db.execute(f"SELECT * FROM {table}")]
                                          for table in ("opponents", "observations", "analyses")}}
