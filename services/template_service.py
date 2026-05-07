"""JSON-backed template and preset catalog for vertical gameplay layouts."""

from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import PRESET_DIR, TEMPLATE_DIR


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def _template_sort_key(template: dict[str, Any]) -> tuple[str, str]:
    game = str(template.get("game", ""))
    name = str(template.get("name", ""))
    return (game == "Generic", game.lower(), name.lower())


def list_templates() -> list[dict[str, Any]]:
    """Return all built-in templates ordered with game-specific layouts first."""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    templates = [_read_json(path) for path in sorted(TEMPLATE_DIR.glob("*.json"))]
    return sorted(templates, key=_template_sort_key)


def get_template(template_id: str) -> dict[str, Any]:
    """Load one template by ID."""
    for template in list_templates():
        if template.get("id") == template_id:
            return template
    raise ValueError(f"Unknown templateId: {template_id}")


def get_template_defaults(template: dict[str, Any]) -> dict[str, float]:
    """Extract default control parameters from a template."""
    defaults: dict[str, float] = {}
    controls = template.get("controls", [])
    if not isinstance(controls, list):
        return defaults

    for control in controls:
        if not isinstance(control, dict):
            continue
        control_id = str(control.get("id", "")).strip()
        if not control_id:
            continue
        defaults[control_id] = float(control.get("default", 0))
    return defaults


def normalize_template_params(template: dict[str, Any], params: dict[str, Any] | None) -> dict[str, float]:
    """Merge request params with defaults and clamp slider values to template bounds."""
    normalized = get_template_defaults(template)
    params = params or {}
    controls = template.get("controls", [])
    if not isinstance(controls, list):
        return normalized

    for control in controls:
        if not isinstance(control, dict):
            continue
        control_id = str(control.get("id", "")).strip()
        if not control_id or control_id not in params:
            continue

        try:
            value = float(params[control_id])
        except (TypeError, ValueError):
            continue

        minimum = control.get("min")
        maximum = control.get("max")
        if isinstance(minimum, (int, float)):
            value = max(float(minimum), value)
        if isinstance(maximum, (int, float)):
            value = min(float(maximum), value)
        normalized[control_id] = value

    return normalized


def list_presets() -> list[dict[str, Any]]:
    """Return saved user presets from local JSON storage."""
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    presets: list[dict[str, Any]] = []
    for path in sorted(PRESET_DIR.glob("*.json")):
        try:
            presets.append(_read_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return sorted(presets, key=lambda preset: str(preset.get("updatedAt", "")), reverse=True)


def save_preset(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a new user preset that references a base template."""
    base_template_id = str(payload.get("baseTemplateId") or payload.get("templateId") or "").strip()
    if not base_template_id:
        raise ValueError("Missing required field: baseTemplateId")

    template = get_template(base_template_id)
    params = normalize_template_params(template, payload.get("params") if isinstance(payload.get("params"), dict) else {})
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    raw_name = str(payload.get("name") or "").strip()
    name = raw_name or f"{template.get('game', 'Gaming')} Layout"

    preset = {
        "id": f"preset_custom_{uuid.uuid4().hex[:12]}",
        "baseTemplateId": base_template_id,
        "name": name,
        "game": str(payload.get("game") or template.get("game") or "Generic"),
        "gameId": str(payload.get("gameId") or template.get("gameId") or "generic"),
        "category": str(payload.get("category") or template.get("category") or "Custom"),
        "description": str(payload.get("description") or "").strip(),
        "params": params,
        "createdAt": now,
        "updatedAt": now,
    }

    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", preset["id"]).strip("._")
    preset_path = PRESET_DIR / f"{safe_name}.json"
    preset_path.write_text(json.dumps(preset, indent=2), encoding="utf-8")
    return deepcopy(preset)
