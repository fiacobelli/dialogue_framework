"""Deterministic safety checks for public donor-page content."""

from __future__ import annotations

import re
from typing import Any


EMAIL_RE = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
PHONE_RE = re.compile(r'(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}')
URL_RE = re.compile(r'\b(?:https?://|www\.)\S+', re.I)

PATTERNS = {
    'crisis_language': (
        r'\bkill myself\b',
        r'\bend my life\b',
        r'\bhurt myself\b',
        r'\bsuicidal\b',
    ),
    'medical_advice_claim': (
        r'\byou should (?:take|stop|start|change)\b',
        r'\bmust (?:take|stop|start|change) (?:medicine|medication|dose|dosage)\b',
        r'\bthis will cure\b',
        r'\bguaranteed (?:cure|transplant|match)\b',
        r'\bdonor eligibility\b',
    ),
    'coercive_donor_language': (
        r'\byou must donate\b',
        r'\byou have to donate\b',
        r'\bonly you can save\b',
        r'\bif you do not donate\b',
        r'\bdonate or\b',
    ),
}


def _text_fields(content: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (field, str(value or ''))
        for field, value in (content or {}).items()
        if isinstance(value, (str, int, float)) and str(value or '').strip()
    ]


def _issue(code: str, field: str, detail: str) -> dict[str, str]:
    return {'code': code, 'field': field, 'detail': detail}


def public_content_issues(content: dict[str, Any]) -> list[dict[str, str]]:
    """Return blocking issues that should be fixed before public publish."""
    issues = []
    for field, text in _text_fields(content):
        if EMAIL_RE.search(text):
            issues.append(_issue('contact_information', field, 'Remove email addresses from the public page.'))
        if PHONE_RE.search(text):
            issues.append(_issue('contact_information', field, 'Remove phone numbers from the public page.'))
        if URL_RE.search(text):
            issues.append(_issue('contact_information', field, 'Remove direct links unless they are approved.'))

        normalized = text.lower()
        for code, patterns in PATTERNS.items():
            if any(re.search(pattern, normalized) for pattern in patterns):
                issues.append(_issue(code, field, f'Review {code.replace("_", " ")} before publishing.'))
    return issues


def validate_public_content(content: dict[str, Any]) -> tuple[bool, list[dict[str, str]]]:
    issues = public_content_issues(content)
    return not issues, issues
