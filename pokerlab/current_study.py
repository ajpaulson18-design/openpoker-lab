"""Safe, bounded presentation view for a pre-action practice estimate."""

from collections import OrderedDict
from copy import deepcopy
import threading
import time

from .situation_teaching import build_situation_teaching


SCHEMA_VERSION = 1
SOURCE_LABEL = "Practice estimate · current decision preview"


def build_current_study_view(analysis):
    """Project validated immutable evidence into a small browser-safe shape."""
    if getattr(analysis, "source_kind", None) != "practice_estimate":
        raise ValueError("Current study requires a practice estimate.")

    context = analysis.context
    evs = {item.action_id: item.value for item in analysis.action_evs}
    modeled_actions = []
    for action in analysis.modeled_actions:
        row = {
            "action_id": action.action_id,
            "name": action.name,
            "amount": action.amount,
            "amount_semantics": action.amount_semantics,
            "estimated_ev_chips": evs.get(action.action_id),
        }
        if action.name == "raise":
            legal = next((item for item in analysis.legal_actions
                          if item.name == "raise"), None)
            row["size_note"] = "EV evaluates the minimum legal raise only."
            row["minimum_legal_total"] = legal.minimum_total if legal else None
            row["maximum_legal_total"] = legal.maximum_total if legal else None
        modeled_actions.append(row)

    assumptions = ["Live opponents use random card ranges in the practice estimate."]
    if analysis.opponent_assumptions:
        for assumption in analysis.opponent_assumptions:
            assumptions.append(
                f"Fold-to-bet estimate: {assumption.value:.1%} "
                f"({assumption.evidence_count} observed opportunities; uncertainty remains)."
            )
    else:
        assumptions.append("Without a selected model, fold-to-bet is an illustrative 45% assumption.")

    limitations = list(analysis.limitations)
    limitations.extend(analysis.warnings)
    if analysis.quality.equity_exact is True:
        limitations.append("Equity is exactly enumerated for this supported state; the practice EV model is still simplified, not a solved strategy.")
    elif analysis.quality.equity_exact is False:
        limitations.append("Equity is sampled; results are estimates, not a solved strategy.")
    else:
        limitations.append("Equity exactness is unavailable; results are estimates, not a solved strategy.")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "binding": {
            "hand_id": analysis.ref.hand_id,
            "decision_id": analysis.ref.decision_id,
            "evidence_id": analysis.evidence_id,
            "state_revision": analysis.ref.state_revision,
        },
        "source_label": SOURCE_LABEL,
        "heading": "Current turn decision",
        "context": {
            "street": context.street,
            "hero_cards": list(context.hero_cards),
            "board": list(context.board),
            "pot_chips": context.pot,
        },
        "situation": build_situation_teaching(analysis),
        "recommended_action_id": analysis.recommended_action_id,
        "modeled_actions": modeled_actions,
        "assumptions": assumptions,
        "limitations": list(dict.fromkeys(limitations)),
    }


class CurrentStudyPreviewCache:
    """Small expiring cache that retains immutable evidence with its safe view."""

    def __init__(self, *, max_entries=64, ttl_seconds=60, clock=None):
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._entries = OrderedDict()

    def _prune(self, now):
        for key, entry in list(self._entries.items()):
            if now - entry["created"] >= self._ttl_seconds:
                self._entries.pop(key, None)

    def get(self, key):
        now = self._clock()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry["evidence"], deepcopy(entry["view"])

    def put(self, key, evidence, view):
        binding = view.get("binding") if isinstance(view, dict) else None
        if (not isinstance(binding, dict)
                or set(binding) != {"hand_id", "decision_id", "evidence_id", "state_revision"}
                or any(not isinstance(binding.get(name), str) or not binding[name].strip()
                       for name in ("hand_id", "decision_id", "evidence_id"))
                or type(binding.get("state_revision")) is not int
                or binding != {
                    "hand_id": evidence.ref.hand_id,
                    "decision_id": evidence.ref.decision_id,
                    "evidence_id": evidence.evidence_id,
                    "state_revision": evidence.ref.state_revision,
                }):
            raise ValueError("Preview cache view must match its immutable evidence binding.")
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._entries[key] = {
                "created": now,
                "evidence": evidence,
                "view": deepcopy(view),
            }
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def resolve(self, *, hand_id, decision_id, evidence_id, state_revision):
        now = self._clock()
        with self._lock:
            self._prune(now)
            for entry in self._entries.values():
                evidence = entry["evidence"]
                if (evidence.ref.hand_id == hand_id
                        and evidence.ref.decision_id == decision_id
                        and evidence.evidence_id == evidence_id
                        and evidence.ref.state_revision == state_revision):
                    return evidence
        return None
