"""Bounded, in-memory ledger for same-decision coach follow-ups."""
from __future__ import annotations

from copy import deepcopy
import secrets
import threading
import time


class ConversationError(ValueError):
    def __init__(self, code: str, message: str, status: int):
        self.code = code
        self.status = status
        super().__init__(message)


class ConversationLedger:
    MAX_CONVERSATIONS = 256
    MAX_TURNS = 4
    IDLE_TTL_SECONDS = 30 * 60

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.RLock()
        self._conversations = {}
        self._first_turns = {}

    @staticmethod
    def _same_binding(left, right):
        return left == right

    def _purge(self, now):
        expired = [key for key, conversation in self._conversations.items()
                   if not conversation["in_flight"]
                   and now - conversation["last_access"] >= self.IDLE_TTL_SECONDS]
        for key in expired:
            del self._conversations[key]
        self._first_turns = {turn_id: conversation_id
                             for turn_id, conversation_id in self._first_turns.items()
                             if conversation_id in self._conversations}

    def reserve(self, conversation_id, client_turn_id, binding, payload):
        """Reserve one turn or return a cached idempotent result."""
        now = self._clock()
        with self._lock:
            self._purge(now)
            created = conversation_id is None
            if created and client_turn_id in self._first_turns:
                conversation_id = self._first_turns[client_turn_id]
                created = False
            if created:
                if len(self._conversations) >= self.MAX_CONVERSATIONS:
                    raise ConversationError("capacity", "Too many active coach conversations.", 429)
                conversation_id = secrets.token_urlsafe(24)
                conversation = {"binding": deepcopy(binding), "turns": [],
                                "last_access": now, "in_flight": False}
                self._conversations[conversation_id] = conversation
                self._first_turns[client_turn_id] = conversation_id
            else:
                conversation = self._conversations.get(conversation_id)
                if conversation is None:
                    raise ConversationError("conversation_expired",
                                             "This conversation expired. Start a new one.", 410)
                if not self._same_binding(conversation["binding"], binding):
                    raise ConversationError("binding_mismatch",
                                             "This conversation belongs to another saved decision.", 409)

            for turn in conversation["turns"]:
                if turn["client_turn_id"] == client_turn_id:
                    if turn["payload"] != payload:
                        raise ConversationError("turn_id_conflict",
                                                 "This turn ID was already used for a different request.", 409)
                    if turn["result"] is None:
                        raise ConversationError("turn_in_progress",
                                                 "A turn for this conversation is already running.", 409)
                    conversation["last_access"] = now
                    return {"conversation_id": conversation_id,
                            "cached_result": deepcopy(turn["result"]), "created": False}

            if conversation["in_flight"]:
                raise ConversationError("turn_in_progress",
                                         "A turn for this conversation is already running.", 409)
            if len(conversation["turns"]) >= self.MAX_TURNS:
                raise ConversationError("conversation_full",
                                         "This conversation has four turns. Start a new one to continue.", 409)

            conversation["in_flight"] = True
            conversation["last_access"] = now
            conversation["turns"].append({
                "client_turn_id": client_turn_id,
                "payload": deepcopy(payload),
                "question": payload["question"],
                "plan": None,
                "result": None,
            })
            return {"conversation_id": conversation_id, "cached_result": None,
                    "created": created}

    def prior_context(self, conversation_id, client_turn_id):
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                return ()
            earlier = []
            for turn in conversation["turns"]:
                if turn["client_turn_id"] == client_turn_id:
                    break
                if turn["result"] is not None and turn["plan"] is not None:
                    earlier.append({"question": turn["question"], **turn["plan"]})
            return tuple(deepcopy(earlier[-2:]))

    def complete(self, conversation_id, client_turn_id, plan, result):
        now = self._clock()
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                return
            for turn in conversation["turns"]:
                if turn["client_turn_id"] == client_turn_id:
                    turn["plan"] = deepcopy(plan)
                    turn["result"] = deepcopy(result)
                    conversation["in_flight"] = False
                    conversation["last_access"] = now
                    return

    def abort(self, conversation_id, client_turn_id):
        now = self._clock()
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                return
            conversation["turns"] = [turn for turn in conversation["turns"]
                                     if turn["client_turn_id"] != client_turn_id]
            conversation["in_flight"] = False
            conversation["last_access"] = now
            if not conversation["turns"]:
                self._conversations.pop(conversation_id, None)
                self._first_turns = {turn_id: key for turn_id, key in self._first_turns.items()
                                     if key != conversation_id}
