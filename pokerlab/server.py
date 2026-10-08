"""Loopback-only stdlib web app. No external services, telemetry, or API key."""
import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlparse, parse_qs, unquote
import uuid
from . import __version__
from .analysis import analyze
from .coach_analysis import adapt_practice_analysis
from .coach_grounding import (CoachGroundingError, CoachReplyPlan,
                              build_grounding_bundle, render_coach_reply,
                              validate_coach_reply_plan)
from .coach_conversation import ConversationError, ConversationLedger
from .current_study import CurrentStudyPreviewCache, build_current_study_view
from .coach_provider import CoachProviderError, OpenAIPlanSelector
from .coach_teaching import build_teaching_note
from .contracts import CoachAnalysisError, CoachDecisionAnalysis, CoachDecisionRef
from .decision_study import build_decision_study
from .equity import simulate
from .explanations import analysis_from_dict, explain
from .exploit import solve_exploitative_river
from .game import Game
from .models import OPPONENT_MODEL_VERSION, Store, PROFILES
from .practice import (advance_to_hero, analyze_decision, build_coach_explanation,
                       decision_event, render_coach_personality, visible_state)
from .personalities import CoachPersonality
from .solver import solve

WEB = Path(__file__).parent / "web"


class ActionConflict(ValueError):
    """A stale hand revision or reused client action ID conflicts with state."""


def _validated_decision(store, decision_id):
    """Load and validate a saved decision once for every read projection."""
    record = store.decision_record(decision_id)
    if record is None:
        return {"status": "missing"}
    if record["envelope"] is None:
        return {
            "status": "unavailable",
            "reason": "Versioned coach evidence was not captured for this decision.",
        }
    try:
        analysis = CoachDecisionAnalysis.from_json(record["envelope"])
        event = json.loads(record["event"])
        if (analysis.ref.hand_id != record["session_id"]
                or analysis.ref.decision_id != record["id"]):
            raise CoachAnalysisError("invalid_contract", "Stored evidence reference is invalid.")
        detail = event.get("chosen_action_detail")
        status = event.get("assessment_status")
        if (not isinstance(detail, dict)
                or set(detail) != {"name", "amount", "amount_semantics"}
                or detail.get("name") not in ("fold", "check", "call", "raise")
                or event.get("chosen_action") != detail.get("name")
                or detail.get("amount_semantics") not in ("chips_added", "street_total")
                or status not in ("assessed", "unassessed_size")):
            raise ValueError("Stored choice is malformed.")
        amount = detail["amount"]
        if type(amount) is not int or amount < 0:
            raise ValueError("Stored choice is malformed.")
        action_name = detail["name"]
        expected_semantics = "street_total" if action_name == "raise" else "chips_added"
        modeled_id = event.get("assessed_modeled_action_id")
        expected_modeled_id = "raise:min" if action_name == "raise" else action_name
        legal_action = next((item for item in analysis.legal_actions
                             if item.name == action_name), None)
        if legal_action is None or detail["amount_semantics"] != expected_semantics:
            raise ValueError("Stored choice is malformed.")
        if action_name == "raise":
            if not legal_action.minimum_total <= amount <= legal_action.maximum_total:
                raise ValueError("Stored choice is malformed.")
            should_be_assessed = amount == legal_action.minimum_total
        else:
            if amount != legal_action.amount:
                raise ValueError("Stored choice is malformed.")
            should_be_assessed = True
        if (status == "assessed") != should_be_assessed:
            raise ValueError("Stored choice is malformed.")
        if status == "assessed" and modeled_id != expected_modeled_id:
            raise ValueError("Stored choice is malformed.")
        if status == "unassessed_size" and (action_name != "raise" or modeled_id is not None):
            raise ValueError("Stored choice is malformed.")
        ev_loss = event.get("ev_loss")
        if ev_loss is not None and (type(ev_loss) not in (int, float)
                                    or not math.isfinite(ev_loss) or ev_loss < 0):
            raise ValueError("Stored choice is malformed.")
        if ((status == "unassessed_size" and ev_loss is not None)
                or (status == "assessed" and ev_loss is None)):
            raise ValueError("Stored choice is malformed.")
        if status == "assessed":
            action_values = {item.action_id: item.value for item in analysis.action_evs}
            recommended_id = analysis.recommended_action_id
            if (recommended_id is None or modeled_id not in action_values
                    or recommended_id not in action_values
                    or action_values[modeled_id] is None
                    or action_values[recommended_id] is None):
                raise ValueError("Stored choice is malformed.")
            expected_loss = max(0.0, action_values[recommended_id] - action_values[modeled_id])
            if ev_loss != expected_loss:
                raise ValueError("Stored choice is malformed.")
        choice = {
            "name": detail["name"], "amount": amount,
            "amount_semantics": detail["amount_semantics"],
            "assessed_modeled_action_id": modeled_id,
            "assessment_status": status, "ev_loss": ev_loss,
        }
        return {"status": "ready", "analysis": analysis, "choice": choice}
    except Exception:
     =Ó^­¢G§²ÚîÆ­yØYˆY[]H›Ý[ˆØ[Y\Î‚ˆ˜Z\ÙH˜[YQ\œ›ÜŠ’[™^\™YÈX[H™]È[™ˆŠBˆØ[YHHØ[Y\ÖÚY[]WBˆXÝ[ÛˆH]K™Ù]
˜XÝ[ÛˆŠBˆYˆXÝ[Ûˆ›Ý[ˆ
™›Û‹˜ÚXÚÈ‹˜Ø[‹œ˜Z\ÙHŠN‚ˆ˜Z\ÙH˜[YQ\œ›ÜŠ•]XÝ[Ûˆ\È›ÝYØ[\™KˆŠBˆ[[Ý[H]K™Ù]
˜[[Ý[ŠHYˆXÝ[ÛˆOHœ˜Z\ÙHˆ[ÙH›Û™BˆÜÛ™[ÚYH]K™Ù]
›ÜÛ™[ÚYŠHÜˆ›Û™BˆÛY[ØXÝ[Û—ÚYH]K™Ù]
˜ÛY[ØXÝ[Û—ÚYŠBˆYˆÛY[ØXÝ[Û—ÚY\È›Ý›Û™H[™
ˆ›Ý\Ú[œÝ[˜ÙJÛY[ØXÝ[Û—ÚYÝŠBˆÜˆ›ÝHH[ŠÛY[ØXÝ[Û—ÚY
HHLŽˆÜˆ›ÝÛY[ØXÝ[Û—ÚYœÝš\

JN‚ˆ˜Z\ÙH˜[YQ\œ›ÜŠÛY[XÝ[ÛˆQ]\ÝÛÛZ[ˆx $ÌLŽÚ\˜XÝ\œËˆŠBˆ\×Ù^XÝYÜ™]š\Ú[ÛˆH™^XÝYÜ™]š\Ú[Ûˆˆ[ˆ]Bˆ^XÝYÜ™]š\Ú[ÛˆH]K™Ù]
™^XÝYÜ™]š\Ú[ÛˆŠBˆYˆ\×Ù^XÝYÜ™]š\Ú[Ûˆ[™
ˆ\J^XÝYÜ™]š\Ú[ÛŠH\È›Ý[Üˆ^XÝYÜ™]š\Ú[Ûˆ
N‚ˆ˜Z\ÙH˜[YQ\œ›ÜŠ‘^XÝY™]š\Ú[Ûˆ]\Ý™HH›Û‹[™YØ]]™H[YÙ\‹ˆŠBˆÛØXÚÝš\ÚX›HH]K™Ù]
˜ÛØXÚÝš\ÚX›H‹˜[ÙJBˆYˆ\JÛØXÚÝš\ÚX›JH\È›Ý›ÛÛ‚ˆ˜Z\ÙH˜[YQ\œ›ÜŠ˜ÛØXÚÝš\ÚX›H]\Ý™H›ÛÛX[‹ˆŠBˆ\œÛÛ˜[]HHÛØXÚ\œÛÛ˜[]J]K™Ù]
œ\œÛÛ˜[]H‹™Üš[™\ˆŠJBˆ›Ü›X[^™YÜ™\]Y\ÝH
XÝ[Û‹[[Ý[ÜÛ™[ÚYˆ\œÛÛ˜[]K˜[YKÛØXÚÝš\ÚX›JBˆØXÚWÚÙ^HH
Y[]KÛY[ØXÝ[Û—ÚY
HYˆÛY[ØXÝ[Û—ÚY\È›Ý›Û™H[ÙH›Û™BˆYˆØXÚWÚÙ^H\È›Ý›Û™H[™ØXÚWÚÙ^H[ˆXØÙ\YØXÝ[ÛœÎ‚ˆØXÚYHXØÙ\YØXÝ[ÛœÖØØXÚWÚÙ^WBˆYˆØXÚYÈœ™\]Y\Ý—HOH›Ü›X[^™YÜ™\]Y\Ý‚ˆ˜Z\ÙHXÝ[ÛÛÛ™›XÝ
ÛY[XÝ[ÛˆQØ\È[™XYH\ÙY›ÜˆHY™™\™[XÝ[Û‹ˆŠBˆ™]\›ˆÛÜK™Y\ÛÜJØXÚYÈœ™\ÜÛœÙH—JBˆÝ\œ™[Ü™]š\Ú[ÛˆH[™Ü™]š\Ú[ÛœÖÚY[]WBˆYˆ\×Ù^XÝYÜ™]š\Ú[Ûˆ[™^XÝYÜ™]š\Ú[ÛˆOHÝ\œ™[Ü™]š\Ú[ÛŽ‚ˆ˜Z\ÙHXÝ[ÛÛÛ™›XÝ
’[™Ú[™ÙY™Y›Ü™H\ÈXÝ[Û‹ˆ™Yœ™\Ú[™žHYØZ[‹ˆŠBˆYˆØ[YK™Û™HÜˆØ[YK˜XÝÜˆOH‚ˆ˜Z\ÙH˜[YQ\œ›ÜŠ•H\›È\È›Ý]ØZ][™ÈHXÚ\Ú[Û‹ˆŠBˆÜÛ™[H›Û™BˆYˆÜÛ™[ÚY‚ˆÜÛ™[HÝÜ™K™Ù]ÛÜÛ™[
ÜÛ™[ÚYØ[YKœÝ™Y]
BˆÜÛ™[È›[Ù[Ý™\œÚ[Ûˆ—HHÔÓ‘S•ÓSÑSÕ‘T”ÒSÓ‚ˆ[˜[\Ú\ÈH[˜[^™WÙXÚ\Ú[ÛŠØ[YKÜÛ™[
BˆXÚ\Ú[Û—ÚYH]ZY]ZY

Kš^ˆ]šY[˜ÙHHY\Ü˜XÝXÙWØ[˜[\Ú\Êˆ[˜[\Ú\Ë™YPÛØXÚXÚ\Ú[Û”™YŠY[]KXÚ\Ú[Û—ÚYÝ\œ™[Ü™]š\Ú[ÛŠJBˆ]™[HXÚ\Ú[Û—Ù]™[
Ø[YK[˜[\Ú\ËXÝ[Û‹ÜÛ™[[[Ý[
Bˆ]™[ÈœÝ]WÜ™]š\Ú[Ûˆ—HHÝ\œ™[Ü™]š\Ú[Û‚ˆ™\\™YHÛÜK™Y\ÛÜJØ[YJBˆ™\\™Y˜XÝ
XÝ[Û‹[[Ý[
BˆY˜[˜ÙWÝ×Ú\›Ê™\\™Y
BˆÛØXÚH›Û™BˆYˆÛØXÚÝš\ÚX›N‚ˆÛØXÚHÛÜK™Y\ÛÜJ[˜[\Ú\ÊBˆÛØXÚÈ™^[˜][Û—Ü^[ØY—HHZ[ØÛØXÚÙ^[˜][ÛŠÛØXÚ
K×ÙXÝ

BˆÛØXÚÈœ\œÛÛ˜[]H—HH™[™\—ØÛØXÚÜ\œÛÛ˜[]JÛØXÚ\œÛÛ˜[]JBˆÜÝÜ™]š\Ú[ÛˆHÝ\œ™[Ü™]š\Ú[Ûˆ
ÈBˆ™\ÜÛœÙHHÈšYŽˆY[]K
Šš\ÚX›WÜÝ]J™\\™Y
Kˆœ™]š\Ú[ÛˆŽˆÜÝÜ™]š\Ú[Û‹ˆ™XÚ\Ú[ÛˆŽˆÂˆ™XÚ\Ú[Û—ÚYŽˆXÚ\Ú[Û—ÚYš[™ÚYŽˆY[]KˆœÝ]WÜ™]š\Ú[ÛˆŽˆÝ\œ™[Ü™]š\Ú[Û‹ˆ™]šY[˜ÙWÚYŽˆ]šY[˜ÙK™]šY[˜ÙWÚYˆ˜ÚÜÙ[—ØXÝ[Û—Ù]Z[Žˆ]™[È˜ÚÜÙ[—ØXÝ[Û—Ù]Z[—Kˆ˜\ÜÙ\ÜÙYÛ[Ù[YØXÝ[Û—ÚYŽˆ]™[È˜\ÜÙ\ÜÙYÛ[Ù[YØXÝ[Û—ÚY—Kˆ˜\ÜÙ\ÜÛY[ÜÝ]\ÈŽˆ]™[È˜\ÜÙ\ÜÛY[ÜÝ]\È—Kˆ™]—ÛÜÜÈŽˆ]™[È™]—ÛÜÜÈ—Kˆ_BˆYˆÛØXÚ\È›Ý›Û™N‚ˆ™\ÜÛœÙVÈ˜ÛØXÚ—HHÛØXÚˆÝÜ™YHÝÜ™KœØ]™WÙXÚ\Ú[ÛŠˆY[]K]™[XÚ\Ú[Û—ÚYYXÚ\Ú[Û—ÚYˆÛØXÚØ[˜[\Ú\ÏY]šY[˜ÙKÛÛ\]WÚ[™\™\\™Y™Û™JBˆ™\ÜÛœÙVÈ™XÚ\Ú[Û—ÛÜ™\ˆ—HHÝÜ™YÈ™XÚ\Ú[Û—ÛÜ™\ˆ—BˆØ[Y\ÖÚY[]WHH™\\™Yˆ[™Ü™]š\Ú[ÛœÖÚY[]WHHÜÝÜ™]š\Ú[Û‚ˆYˆØXÚWÚÙ^H\È›Ý›Û™N‚ˆXØÙ\YØXÝ[ÛœÖØØXÚWÚÙ^WHHÂˆœ™\]Y\ÝŽˆ›Ü›X[^™YÜ™\]Y\Ýˆœ™\ÜÛœÙHŽˆÛÜK™Y\ÛÜJ™\ÜÛœÙJKˆBˆ™]\›ˆ™\ÜÛœÙBˆ˜Z\ÙH˜[YQ\œ›ÜŠ•[šÛ›ÝÛˆ[™Ú[ˆŠB‚ˆ™]\›ˆ™XY[™ÒÙ\™\Š
ŒLËŒŒŒH‹Ü
K[™\ŠB‚‚™YˆXZ[Š
N‚ˆ\œÙ\ˆH\™Ü\œÙK\™Ý[Y[\œÙ\Š\ØÜš\[ÛH“Ü[”ÚÙ\ˆXˆ8 %ØØ[ÚÙ\ˆ™\ÙX\˜ÚŠBˆ\œÙ\‹˜YØ\™Ý[Y[
‹K\Ü‹\OZ[Y˜][NÍJBˆ\œÙ\‹˜YØ\™Ý[Y[
‹KY]X˜\ÙH‹Y˜][H™]KÜÚÙ\›X‹œÜ[]LÈŠBˆ\™ÜÈH\œÙ\‹œ\œÙWØ\™ÜÊ
BˆÙ\™\ˆHXZÙWÜÙ\™\Š\™ÜËœÜ\™ÜË™]X˜\ÙJBˆš[
ˆ“Ü[”ÚÙ\ˆXˆ\È™XYH]‹ËÌLËŒŒŒNžÜÙ\™\‹œÙ\™\—ÜÜH‹›\ÚUYJBˆžN‚ˆÙ\™\‹œÙ\™WÙ›Ü™]™\Š
Bˆ^Ù\Ù^X›Ø\™[\œ\‚ˆ\ÜÂˆš[˜[N‚ˆÙ\™\‹œÙ\™\—ØÛÜÙJ
B‚‚šYˆ×Û˜[YW×ÈOH—×ÛXZ[—×ÈŽ‚ˆXZ[Š
B