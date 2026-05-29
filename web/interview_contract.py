"""Minimal interview turn contract: runtime directive + plain-reply JSON.

the LLM only *voices* the turn — a warm
acknowledgement plus the next question code told it to ask, and (on the intro
turn) the patient's `name`. Code owns all flow control, so the turn can never
stall. One question per section; no follow-up loop, no word counts, no classifier.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _text(value: Any, limit: int = 1000) -> str:
    return str(value or '').strip()[:limit]


def build_turn_directive(instruction: str) -> str:
    """Append the per-turn instruction + output format. Persona and voice rules
    live in prompts/interviewer.txt (the system prompt), not here."""
    return (
        'RUNTIME TURN DIRECTIVE\n'
        f'{instruction.strip()}\n\n'
        'Return ONLY a JSON object (no other text):\n'
        '{\n'
        '  "reply": "what you say to the patient, following the voice rules above",\n'
        '  "name": "the patient\'s name if they just gave it, otherwise an empty string"\n'
        '}'
    )


def parse_turn(raw: str) -> dict | None:
    """Extract a JSON object from the model output, tolerating code fences."""
    text = (raw or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def validate_turn(data: dict | None) -> dict:
    """Sanitize the model output into {reply, name, valid}."""
    data = data if isinstance(data, dict) else {}
    name = re.sub(r'\s+', ' ', _text(data.get('name'), 80)).strip()
    if len(name.split()) > 5:
        name = ''
    reply = _text(data.get('reply'))
    return {'reply': reply, 'name': name, 'valid': bool(reply)}
