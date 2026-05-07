"""MVP filename-based game detection for uploaded gameplay clips."""

from __future__ import annotations

from typing import Any

from services.template_service import list_templates


GAME_RULES = [
    {
        "tokens": ("apex", "apexlegends", "apex_legends"),
        "gameId": "apex_legends",
        "gameName": "Apex Legends",
        "confidence": 0.82,
        "recommendedTemplateId": "apex_ranked_br_fullscreen_v1",
        "verticalTemplateId": "apex_native_vertical_v1",
    },
    {
        "tokens": ("valorant", "val"),
        "gameId": "valorant",
        "gameName": "Valorant",
        "confidence": 0.8,
        "recommendedTemplateId": "valorant_fullscreen_v1",
        "verticalTemplateId": "valorant_native_vertical_v1",
    },
]


def detect_game_from_filename(filename: str, *, is_vertical_source: bool = False) -> dict[str, Any]:
    """Return the recommended game/template using a deliberately simple MVP heuristic."""
    normalized = filename.lower().replace("-", "_").replace(" ", "_")
    template_ids = {str(template.get("id")) for template in list_templates()}

    for rule in GAME_RULES:
        if any(token in normalized for token in rule["tokens"]):
            recommendation = dict(rule)
            if is_vertical_source:
                recommendation["recommendedTemplateId"] = recommendation["verticalTemplateId"]
            if recommendation["recommendedTemplateId"] not in template_ids:
                recommendation["recommendedTemplateId"] = "generic_vertical_v1"
            return recommendation

    generic_recommendation = "generic_native_vertical_v1" if is_vertical_source else "generic_vertical_v1"
    if generic_recommendation not in template_ids:
        generic_recommendation = "generic_vertical_v1"

    return {
        "gameId": "generic",
        "gameName": "Unknown",
        "confidence": 0.35,
        "recommendedTemplateId": generic_recommendation,
    }
