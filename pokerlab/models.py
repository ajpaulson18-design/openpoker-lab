"""Multidimensional, opportunity-based Bayesian opponent models.

Each tendency is an independent Beta-Bernoulli estimate. Archetypes only
select the initial priors: persisted observations can always overwhelm them.
Consumers receive immutable snapshots rather than database handles.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import uuid
from .contracts import (BetaPrior, ObservationEvidence, OpponentModelSnapshot,
                        OpponentTendencyEstimate, TendencyContext,
                        TendencyEvidence, Uncertainty)

TENDENCIES = ("vpip", "pfr", "three_bet", "fold_to_bet", "aggression",
              "showdown_bluff")
METRICS = TENDENCIES  # Existing server/client compatibility.
STREETS = ("all", "preflop", "flop", "turn", "river")
PRIOR_STRENGTH = 10.0
OPPONENT_MODEL_VERSION = "beta-opportunity-v2"


def _priors(vpip, pfr, three_bet, fold_to_bet, aggression, showdown_bluff):
    return dict(zip(TENDENCIES, (vpip, pfr, three_bet, fold_to_bet,
                                 aggression, showdown_bluff)))


# Starting beliefs, never classifications or fixed policies. Legacy identifiers
# remain supported so existing databases and API clients migrate safely.
ARCHETYPE_PRIORS = {
    "unknown": _priors(.26, .20, .08, .45, .45, .25),
    "calling_station": _priors(.48, .10, .03, .20, .22, .10),
    "nit": _priors(.14, .10, .03, .68, .25, .10),
    "maniac": _priors(.55, .40, .20, .25, .75, .48),
    "loose_passive": _priors(.45, .12, .04, .25, .24, .12),
    "tight_passive": _priors(.16, .09, .03, .62, .24, .09),
    "overbluffer": _priors(.34, .26, .12, .36, .66, .58),
    "underbluffer": _priors(.23, .16, .06, .52, .32, .07),
    "honest_player": _priors(.23, .16, .06, .52, .32, .07),
    "balanced": _priors(.26, .20, .08, .45, .45, .25),
    "tight": _priors(.15, .11, .04, .60, .30, .12),
    "aggressive": _priors(.42, .31, .14, .32, .68, .40),
}
PROFILES = {name: tuple(values[item] for item in TENDENCIES)
            for name, values in ARCHETYPE_PRIORS.items()}


def _prior_source(archetype):
    prefix = "profile" if archetype in {
        "balanced", "tight", "calling_station", "aggressive"
    } else "archetype"
    return f"{prefix}:{archetype}"


def _normalize_archetype(archetype):
    if not isinstance(archetype, str):
        raise ValueError("Unknown opponent archetype.")
    normalized = archetype.strip().lower().replace("-", "_").replace(" ", "_")
    return "unknown" if normalized == "default" else normalized


class OpponentDataError(ValueError):
    """Persisted opponent data is malformed or incompatible."""


def posterior(mean, successes, opportunities, strength=PRIOR_STRENGTH):
    """Return a Beta posterior summary for opportunity-based binary evidence."""
    if isinstance(mean, bool) or not isinstance(mean, (int, float)) or not 0 < mean < 1:
        raise ValueError("Prior mean must be strictly between zero and one.")
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or strength <= 0:
        raise ValueError("Prior strength must be positive.")
    if type(successes) is not int or type(opportunities) is not int:
        raise ValueError("Successes and opportunities must be integers.")
    if opportunities < 0 or not 0 <= successes <= opportunities:
        raise ValueError("Counts must satisfy 0 <= successes <= opportunities.")
    alpha = mean * strength + successes
    beta = (1 - mean) * strength + opportunities - successes
    estimate = alpha / (alpha + beta)
    sd = math.sqrt(alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1)))
    return {
        "mean": estimate,
        "interval95": [max(0.0, estimate - 1.96 * sd),
                       min(1.0, estimate + 1.96 * sd)],
        "observations": opportunities,
        "successes": successes,
        "prior_strength": strength,
        "posterior_alpha": alpha,
        "posterior_beta": beta,
        "confidence": ("low" if opportunities < 30 else
                       "moderate" if opportunities < 100 else "higher"),
        "interval_method": "normal approximation to Beta posterior",
    }


def _canonical_context(value: TendencyContext | str | None) -> TendencyContext:
    if value is None or value == "all":
        return TendencyContext()
    if isinstance(value, str):
        if value not in STREETS:
            raise ValueError("Unknown street.")
        return TendencyContext(street=value)
    if not isinstance(value, TendencyContext):
        raise ValueError("Context must be a TendencyContext, street, or None.")
    if value.street is not None and value.street not in STREETS[1:]:
        raise ValueError("Unknown street.")
    keys = [key for key, _ in value.qualifiers]
    if len(keys) != len(set(keys)):
        raise ValueError("Context qualifier keys must be unique.")
    return TendencyContext(value.street, value.position, value.action_context,
                           tuple(sorted(value.qualifiers)))


def _context_matches(observed: TendencyContext, requested: TendencyContext) -> bool:
    for attribute in ("street", "position", "action_context"):
        expected = getattr(requested, attribute)
        if expected is not None and getattr(observed, attribute) != expected:
            return False
    observed_qualifiers = dict(observed.qualifiers)
    return all(observed_qualifiers.get(key) == value
               for key, value in requested.qualifiers)


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
                CREATE TABLE IF NOT EXISTS opponent_model_metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS opponent_priors (
                    opponent_id TEXT NOT NULL REFERENCES opponents(id) ON DELETE CASCADE,
                    tendency_id TEXT NOT NULL, prior_mean REAL NOT NULL,
                    prior_strength REAL NOT NULL, source TEXT NOT NULL,
                    PRIMARY KEY (opponent_id, tendency_id),
                    CHECK (prior_mean > 0 AND prior_mean < 1),
                    CHECK (prior_strength > 0));
                CREATE TABLE IF NOT EXISTS opponent_observations (
                    id TEXT PRIMARY KEY,
                    opponent_id TEXT NOT NULL REFERENCES opponents(id) ON DELETE CASCADE,
                    tendency_id TEXT NOT NULL,
                    successes INTEGER NOT NULL,
                    opportunities INTEGER NOT NULL,
                    street TEXT, position TEXT, action_context TEXT,
                    qualifiers_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    CHECK (opportunities > 0),
                    CHECK (successes >= 0 AND successes <= opportunities));
                CREATE INDEX IF NOT EXISTS opponent_observation_lookup
                    ON opponent_observations(opponent_id, tendency_id);
            """)
            db.execute("INSERT OR REPLACE INTO opponent_model_metadata(key,value) VALUES (?,?)",
                       ("schema_version", "2"))
            self._seed_missing_priors(db)

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

    @staticmethod
    def _archetype(name):
        name = _normalize_archetype(name)
        try:
            return ARCHETYPE_PRIORS[name]
        except (KeyError, TypeError):
            raise ValueError("Unknown opponent archetype.") from None

    def _seed_missing_priors(self, db):
        for opponent in db.execute("SELECT id, profile FROM opponents"):
            try:
                priors = self._archetype(opponent["profile"])
            except ValueError as exc:
                raise OpponentDataError(
                    f"Opponent {opponent['id']!r} has unknown legacy profile "
                    f"{opponent['profile']!r}; reinitialize it explicitly.") from exc
            existing = {row[0] for row in db.execute(
                "SELECT tendency_id FROM opponent_priors WHERE opponent_id=?",
                (opponent["id"],))}
            for tendency_id, mean in priors.items():
                if tendency_id not in existing:
                    db.execute("""INSERT INTO opponent_priors
                               (opponent_id,tendency_id,prior_mean,prior_strength,source)
                               VALUES (?,?,?,?,?)""",
                               (opponent["id"], tendency_id, mean, PRIOR_STRENGTH,
                                _prior_source(opponent["profile"])))

    def create_opponent(self, name, archetype="unknown"):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Opponent name must contain 1–80 characters.")
        archetype = _normalize_archetype(archetype)
        priors = self._archetype(archetype)
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO opponents VALUES (?, ?, ?)",
                       (identity, name.strip(), archetype))
            for tendency_id, mean in priors.items():
                db.execute("""INSERT INTO opponent_priors
                           (opponent_id,tendency_id,prior_mean,prior_strength,source)
                           VALUES (?,?,?,?,?)""",
                           (identity, tendency_id, mean, PRIOR_STRENGTH,
                            _prior_source(archetype)))
        return self.get_opponent(identity)

    def add_opponent(self, name, profile="balanced"):
        """Backward-compatible alias for create_opponent."""
        return self.create_opponent(name, profile)

    def create_opponent_from_archetype(self, name, archetype):
        """Explicit constructor for callers that require an archetype prior."""
        return self.create_opponent(name, archetype)

    def _opponent_row(self, db, opponent_id):
        row = db.execute("SELECT * FROM opponents WHERE id=?", (opponent_id,)).fetchone()
        if row is None:
            raise ValueError("Opponent not found.")
        return row

    def _validate_legacy_rows(self, rows):
        for row in rows:
            if (row["metric"] not in TENDENCIES or row["street"] not in STREETS
                    or type(row["success"]) is not int or row["success"] not in (0, 1)
                    or not isinstance(row["note"], str)):
                raise OpponentDataError(
                    f"Legacy observation {row['id']!r} is malformed and was not used.")

    @staticmethod
    def _row_context(row):
        try:
            qualifiers = json.loads(row["qualifiers_json"])
            if not isinstance(qualifiers, list):
                raise ValueError
            return _canonical_context(TendencyContext(
                row["street"], row["position"], row["action_context"],
                tuple(tuple(pair) for pair in qualifiers)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OpponentDataError(
                f"Observation {row['id']!r} contains malformed context data.") from exc

    def _evidence(self, opponent_id, tendency_id, context):
        with self.connect() as db:
            self._opponent_row(db, opponent_id)
            all_legacy_rows = db.execute(
                "SELECT * FROM observations WHERE opponent_id=? ORDER BY id",
                (opponent_id,)).fetchall()
            modern_rows = db.execute(
                """SELECT * FROM opponent_observations
                   WHERE opponent_id=? AND tendency_id=? ORDER BY id""",
                (opponent_id, tendency_id)).fetchall()
        self._validate_legacy_rows(all_legacy_rows)
        legacy_rows = [row for row in all_legacy_rows
                       if row["metric"] == tendency_id]
        evidence = []
        for row in legacy_rows:
            observed_context = TendencyContext(
                street=None if row["street"] == "all" else row["street"])
            if _context_matches(observed_context, context):
                evidence.append(ObservationEvidence(
                    row["id"], row["success"], 1, observed_context,
                    row["note"], row["created_at"], True))
        for row in modern_rows:
            observed_context = self._row_context(row)
            if _context_matches(observed_context, context):
                try:
                    evidence.append(ObservationEvidence(
                        row["id"], row["successes"], row["opportunities"],
                        observed_context, row["note"], row["created_at"], False))
                except ValueError as exc:
                    raise OpponentDataError(
                        f"Observation {row['id']!r} has impossible counts.") from exc
        return tuple(sorted(evidence, key=lambda item: item.observation_id))

    def _prior(self, opponent_id, tendency_id):
        with self.connect() as db:
            self._opponent_row(db, opponent_id)
            row = db.execute("""SELECT prior_mean,prior_strength,source
                              FROM opponent_priors
                              WHERE opponent_id=? AND tendency_id=?""",
                             (opponent_id, tendency_id)).fetchone()
        if row is None:
            raise OpponentDataError(
                f"Opponent {opponent_id!r} is missing prior {tendency_id!r}.")
        try:
            return BetaPrior(row["prior_mean"], row["prior_strength"], row["source"])
        except ValueError as exc:
            raise OpponentDataError(
                f"Opponent {opponent_id!r} has a malformed {tendency_id!r} prior.") from exc

    def get_tendency_evidence(self, opponent_id, tendency_id, context=None):
        if tendency_id not in TENDENCIES:
            raise ValueError("Unknown opponent tendency.")
        requested = _canonical_context(context)
        prior = self._prior(opponent_id, tendency_id)
        observations = self._evidence(opponent_id, tendency_id, requested)
        successes = sum(item.successes for item in observations)
        opportunities = sum(item.opportunities for item in observations)
        modeled = posterior(prior.mean, successes, opportunities, prior.strength)
        estimate = OpponentTendencyEstimate(
            tendency_id, requested, successes, opportunities, prior, modeled["mean"],
            Uncertainty(modeled["interval95"][0], modeled["interval95"][1], .95,
                        modeled["interval_method"], modeled["confidence"]),
            opportunities)
        return TendencyEvidence(estimate, observations)

    def get_tendency_estimate(self, opponent_id, tendency_id, context=None):
        return self.get_tendency_evidence(opponent_id, tendency_id, context).estimate

    def opponent_snapshot(self, opponent_id, street="all", *, context=None):
        if context is not None:
            if street != "all":
                raise ValueError("Provide either street or context, not both.")
            street = context
        requested = _canonical_context(street)
        with self.connect() as db:
            opponent = self._opponent_row(db, opponent_id)
        estimates = tuple(self.get_tendency_estimate(opponent_id, tendency, requested)
                          for tendency in TENDENCIES)
        return OpponentModelSnapshot(opponent_id, opponent["profile"],
                                     OPPONENT_MODEL_VERSION, estimates)

    def get_opponent(self, identity, street="all"):
        if street not in STREETS:
            raise ValueError("Unknown street.")
        with self.connect() as db:
            row = self._opponent_row(db, identity)
        snapshot = self.opponent_snapshot(identity, street)
        metrics = {}
        for estimate in snapshot.tendencies:
            metrics[estimate.tendency_id] = {
                "mean": estimate.posterior_mean,
                "interval95": [estimate.uncertainty.lower, estimate.uncertainty.upper],
                "observations": estimate.opportunities,
                "successes": estimate.successes,
                "prior_strength": estimate.prior.strength,
                "confidence": estimate.uncertainty.confidence,
                "interval_method": estimate.uncertainty.method,
            }
        return {**dict(row), "street": street, "metrics": metrics}

    def opponents(self):
        with self.connect() as db:
            identities = [row[0] for row in db.execute(
                "SELECT id FROM opponents ORDER BY name")]
        return [self.get_opponent(identity) for identity in identities]

    def record_observation(self, opponent_id, tendency_id, successes,
                           opportunities=1, context=None, note="",
                           observation_id=None):
        if tendency_id not in TENDENCIES:
            raise ValueError("Unknown opponent tendency.")
        if type(successes) is not int or type(opportunities) is not int:
            raise ValueError("Successes and opportunities must be integers.")
        if opportunities <= 0 or not 0 <= successes <= opportunities:
            raise ValueError("Counts must satisfy 0 <= successes <= opportunities.")
        requested = _canonical_context(context)
        if (tendency_id in ("vpip", "pfr", "three_bet")
                and requested.street not in (None, "preflop")):
            raise ValueError("This tendency describes a preflop opportunity.")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Notes may contain at most 2,000 characters.")
        identity = observation_id or uuid.uuid4().hex
        if not isinstance(identity, str) or not 1 <= len(identity) <= 100:
            raise ValueError("Observation ID must contain 1–100 characters.")
        qualifiers_json = json.dumps(requested.qualifiers, separators=(",", ":"))
        values = (opponent_id, tendency_id, successes, opportunities,
                  requested.street, requested.position, requested.action_context,
                  qualifiers_json, note)
        with self.connect() as db:
            self._opponent_row(db, opponent_id)
            legacy = db.execute("SELECT * FROM observations WHERE id=?", (identity,)).fetchone()
            if legacy is not None:
                same = (opportunities == 1 and successes == legacy["success"]
                        and opponent_id == legacy["opponent_id"]
                        and tendency_id == legacy["metric"]
                        and requested.position is None and requested.action_context is None
                        and not requested.qualifiers
                        and (requested.street or "all") == legacy["street"]
                        and note == legacy["note"])
                if not same:
                    raise ValueError("Observation ID already belongs to different data.")
                return {"id": identity, "duplicate": True}
            existing = db.execute(
                "SELECT * FROM opponent_observations WHERE id=?", (identity,)).fetchone()
            if existing is not None:
                current = tuple(existing[key] for key in (
                    "opponent_id", "tendency_id", "successes", "opportunities",
                    "street", "position", "action_context", "qualifiers_json", "note"))
                if current != values:
                    raise ValueError("Observation ID already belongs to different data.")
                return {"id": identity, "duplicate": True}
            db.execute("""INSERT INTO opponent_observations
                       (id,opponent_id,tendency_id,successes,opportunities,street,
                        position,action_context,qualifiers_json,note)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""", (identity, *values))
        return {"id": identity, "duplicate": False}

    def observe(self, opponent_id, metric, success, street="all", note="", id=None):
        """Record one legacy-shaped event through the validated v2 interface."""
        if type(success) is not bool:
            raise ValueError("Provide a valid metric, street, and boolean success.")
        return self.record_observation(opponent_id, metric, int(success), 1,
                                       street, note, id)

    def reset_opponent_model(self, opponent_id, archetype="unknown",
                             clear_observations=True):
        if type(clear_observations) is not bool:
            raise ValueError("clear_observations must be boolean.")
        archetype = _normalize_archetype(archetype)
        priors = self._archetype(archetype)
        with self.connect() as db:
            self._opponent_row(db, opponent_id)
            db.execute("UPDATE opponents SET profile=? WHERE id=?", (archetype, opponent_id))
            db.execute("DELETE FROM opponent_priors WHERE opponent_id=?", (opponent_id,))
            for tendency_id, mean in priors.items():
                db.execute("""INSERT INTO opponent_priors
                           (opponent_id,tendency_id,prior_mean,prior_strength,source)
                           VALUES (?,?,?,?,?)""",
                           (opponent_id, tendency_id, mean, PRIOR_STRENGTH,
                            _prior_source(archetype)))
            if clear_observations:
                db.execute("DELETE FROM observations WHERE opponent_id=?", (opponent_id,))
                db.execute("DELETE FROM opponent_observations WHERE opponent_id=?",
                           (opponent_id,))
        return self.opponent_snapshot(opponent_id)

    def reinitialize_opponent_model(self, opponent_id, archetype="unknown",
                                    clear_observations=True):
        """Explicit alias for intentional model reset/reinitialization."""
        return self.reset_opponent_model(opponent_id, archetype,
                                         clear_observations)

    def save_analysis(self, inputs, result):
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO analyses(id,input,result) VALUES (?,?,?)",
                       (identity, json.dumps(inputs), json.dumps(result)))
        return identity

    def export(self):
        with self.connect() as db:
            opponents = [dict(row) for row in db.execute("SELECT * FROM opponents")]
            analyses = [dict(row) for row in db.execute("SELECT * FROM analyses")]
            priors = [dict(row) for row in db.execute("SELECT * FROM opponent_priors")]
            legacy = [dict(row) for row in db.execute("SELECT * FROM observations")]
            modern = [dict(row) for row in db.execute("SELECT * FROM opponent_observations")]
        return {"schema_version": 2, "opponents": opponents,
                "observations": legacy + modern, "opponent_priors": priors,
                "analyses": analyses}
