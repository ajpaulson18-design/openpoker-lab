"""One-shot structured plan selection for the optional local AI coach."""
from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .coach_grounding import CoachReplyPlan, GroundingBundle


class CoachProviderError(RuntimeError):
    """Safe, typed provider failure; never includes request or response contents."""

    CODES = {"refusal", "incomplete", "invalid_response", "invalid_plan",
             "http_error", "timeout", "network_error"}

    def __init__(self, code: str):
        if code not in self.CODES:
            code = "network_error"
        self.code = code
        super().__init__(code)


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "binding": {
            "type": "object",
            "properties": {
                "hand_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "decision_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "evidence_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "state_revision": {"type": ["integer", "null"], "minimum": 0},
            },
            "required": ["hand_id", "decision_id", "evidence_id", "state_revision"],
            "additionalProperties": False,
        },
        "intent": {"type": "string", "enum": ["recommendation", "choice", "compare",
                                                        "limits", "unavailable"]},
        "fact_ids": {"type": "array", "items": {"type": "string",
                                                       "pattern": "^f_[0-9a-f]{64}$"},
                      "maxItems": 16},
        "target_action_id": {"type": ["string", "null"], "maxLength": 256},
        "detail": {"type": "string", "enum": ["short", "normal", "technical"]},
        "audience": {"type": "string", "enum": ["beginner", "standard"]},
    },
    "required": ["schema_version", "binding", "intent", "fact_ids",
                 "target_action_id", "detail", "audience"],
    "additionalProperties": False,
}


class OpenAIPlanSelector:
    """Select a CoachReplyPlan using Responses structured output, without tools."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str, timeout: float = 12.0,
                 max_output_tokens: int = 256):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("An API key is required.")
        if not isinstance(model, str) or not model.strip() or len(model) > 128:
            raise ValueError("A configured model is required.")
        if type(timeout) not in (int, float) or not 0.1 <= timeout <= 30:
            raise ValueError("Provider timeout must be between 0.1 and 30 seconds.")
        if type(max_output_tokens) is not int or not 32 <= max_output_tokens <= 1024:
            raise ValueError("Provider output limit is outside its safe bounds.")
        self._api_key = api_key
        self.model = model.strip()
        self.timeout = float(timeout)
        self.max_output_tokens = max_output_tokens

    def select_plan(self, bundle: GroundingBundle, question: str,
                    detail: str, audience: str) -> CoachReplyPlan:
        request_data = {
            "model": self.model,
            "store": False,
            "tools": [],
            "max_output_tokens": self.max_output_tokens,
            "instructions": (
                "Select only a CoachReplyPlan for this user's one-shot question. "
                "Use the supplied binding exactly; cite only supplied fact IDs. "
                "Never produce prose, strategy, numbers, or action sizes. Choose unavailable "
                "when the saved facts do not support the question. Match the supplied detail "
                "and audience exactly."
            ),
            "input": json.dumps({
                "question": question,
                "detail": detail,
                "audience": audience,
                "binding": bundle.binding.to_dict(),
                "grounding_bundle": bundle.to_dict(),
            }, separators=(",", ":"), allow_nan=False),
            "text": {"format": {"type": "json_schema", "name": "coach_reply_plan",
                                 "strict": True, "schema": PLAN_SCHEMA}},
        }
        encoded = json.dumps(request_data, separators=(",", ":"), allow_nan=False).encode()
        request = Request(self.endpoint, data=encoded, method="POST", headers={
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_response = response.read(128 * 1024 + 1)
        except HTTPError as error:
            error.close()
            raise CoachProviderError("http_error") from None
        except (TimeoutError, socket.timeout):
            raise CoachProviderError("timeout") from None
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise CoachProviderError("timeout") from None
            raise CoachProviderError("network_error") from None
        except OSError as exc:
            if isinstance(exc, (TimeoutError, socket.timeout)):
                raise CoachProviderError("timeout") from None
            raise CoachProviderError("network_error") from None

        if len(raw_response) > 128 * 1024:
            raise CoachProviderError("invalid_response")
        try:
            response_data = json.loads(raw_response)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            raise CoachProviderError("invalid_response") from None
        if not isinstance(response_data, dict):
            raise CoachProviderError("invalid_response")
        if response_data.get("status") == "incomplete":
            raise CoachProviderError("incomplete")
        if response_data.get("status") != "completed":
            raise CoachProviderError("invalid_response")

        texts = []
        for output in response_data.get("output", []):
            if not isinstance(output, dict):
                raise CoachProviderError("invalid_response")
            if output.get("type") == "message":
                for item in output.get("content", []):
                    if not isinstance(item, dict):
                        raise CoachProviderError("invalid_response")
                    if item.get("type") == "refusal":
                        raise CoachProviderError("refusal")
                    if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                        texts.append(item["text"])
        if len(texts) != 1:
            raise CoachProviderError("invalid_response")
        try:
            return CoachReplyPlan.from_json(texts[0])
        except (ValueError, TypeError):
            raise CoachProviderError("invalid_plan") from None
