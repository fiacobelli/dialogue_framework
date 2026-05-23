"""Microsite generation logic."""
import os
import re
import json
from flask import render_template, url_for
from .config import MICROSITES_DIR, MICROSITE_PROMPT_FILE, FALLBACK_PROMPT
from . import database as db

CONTENT_FIELDS = (
    'headline',
    'short_intro',
    'personal_identity',
    'kidney_journey',
    'daily_impact',
    'transplant_hope',
    'donor_message',
)
REQUIRED_CONTENT_FIELDS = CONTENT_FIELDS
LEGACY_FIELD_MAP = {
    'my_story': 'personal_identity',
    'my_struggle': 'daily_impact',
    'my_hope': 'transplant_hope',
}
REQUIRED_EVIDENCE_GROUPS = {
    'identity': ('personal_background',),
    'kidney_experience': ('medical_history', 'daily_life'),
    'hope': ('transplant_hope',),
    'donor_message': ('donor_message',),
}


class MicrositeGenerationError(ValueError):
    """Structured error for draft-generation failures."""

    def __init__(self, error: str, message: str, *, missing: list[str] | None = None, status_code: int = 422):
        super().__init__(message)
        self.error = error
        self.message = message
        self.missing = missing or []
        self.status_code = status_code

    def to_response(self) -> dict:
        return {
            'error': self.error,
            'message': self.message,
            'missing': self.missing,
        }


def load_prompt(filepath: str) -> str:
    try:
        with open(filepath, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return FALLBACK_PROMPT


def parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to extract from markdown code block first
    match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Find the first { and last } to extract JSON object
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def format_conversation(history: list) -> str:
    """Format conversation history as readable transcript."""
    lines = []
    for msg in history:
        role = "Patient" if msg.get("role") == "user" else "Interviewer"
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def format_story_evidence(state: dict) -> str:
    """Format accepted story evidence as a generation transcript."""
    evidence = (state or {}).get('story_evidence') or {}
    if not isinstance(evidence, dict):
        return ''

    lines = []
    for step_id, entries in evidence.items():
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            continue
        accepted_answers = [
            (entry or {}).get('answer', '').strip()
            for entry in entries
            if isinstance(entry, dict) and entry.get('accepted') and (entry.get('answer') or '').strip()
        ]
        if not accepted_answers:
            continue
        label = step_id.replace('_', ' ').title()
        for answer in accepted_answers:
            lines.append(f"{label}: {answer}")
    skipped = (state or {}).get('skipped_steps') or {}
    if isinstance(skipped, dict):
        for step_id in skipped:
            label = step_id.replace('_', ' ').title()
            lines.append(f"{label}: The patient chose to skip this section.")
    return "\n\n".join(lines)


def story_evidence_ready(state: dict) -> dict:
    """Return whether accepted story evidence can support a donor-page draft."""
    evidence = (state or {}).get('story_evidence') or {}
    if not isinstance(evidence, dict):
        evidence = {}
    skipped = (state or {}).get('skipped_steps') or {}
    if not isinstance(skipped, dict):
        skipped = {}

    missing = []
    accepted_count = 0
    for label, step_ids in REQUIRED_EVIDENCE_GROUPS.items():
        has_accepted = False
        for step_id in step_ids:
            entries = evidence.get(step_id) or []
            if isinstance(entries, dict):
                entries = [entries]
            if any(
                isinstance(entry, dict)
                and entry.get('accepted')
                and _clean_text(entry.get('answer'))
                for entry in entries
            ):
                has_accepted = True
                accepted_count += 1
                break
        has_skip = any(step_id in skipped for step_id in step_ids)
        if not has_accepted and not has_skip:
            missing.append(label)

    if accepted_count == 0:
        missing.append('story_content')

    return {'ready': not missing, 'missing': missing}


def extract_name_from_conversation(history: list, provider) -> str:
    """Extract patient name from conversation using LLM."""
    if not history:
        return "Patient"

    conversation = format_conversation(history)
    prompt = """From this conversation, extract ONLY the patient's first name.
Return just the name, nothing else. If no name is found, return "Patient".

Conversation:
""" + conversation

    try:
        name = provider.generate([{"role": "user", "content": prompt}])
        name = name.strip().split()[0] if name else "Patient"  # Take first word only
        # Validate it looks like a name (capitalized, reasonable length)
        if name and 2 <= len(name) <= 20 and name[0].isupper():
            return name
    except Exception:
        pass
    return "Patient"


def _clean_text(value) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _normalize_content(content: dict, name: str) -> dict:
    """Return complete draft fields without fabricating patient-specific story."""
    content = content or {}
    normalized = {}
    for legacy, target in LEGACY_FIELD_MAP.items():
        if not _clean_text(content.get(target)) and _clean_text(content.get(legacy)):
            content[target] = content.get(legacy)
    if not _clean_text(content.get('short_intro')) and _clean_text(content.get('my_story')):
        content['short_intro'] = content.get('my_story')
    if not _clean_text(content.get('kidney_journey')) and _clean_text(content.get('my_struggle')):
        content['kidney_journey'] = content.get('my_struggle')
    if not _clean_text(content.get('donor_message')) and _clean_text(content.get('my_hope')):
        content['donor_message'] = content.get('my_hope')
    for field in CONTENT_FIELDS:
        normalized[field] = _clean_text(content.get(field))

    missing = [field for field in REQUIRED_CONTENT_FIELDS if not normalized.get(field)]
    if missing:
        raise MicrositeGenerationError(
            'draft_content_incomplete',
            'The donor-page draft is missing required story sections. Please regenerate or edit the draft before publishing.',
            missing=missing,
        )

    normalized.update(_legacy_fields(normalized))
    return normalized


def _legacy_fields(content: dict) -> dict:
    """Keep old field names available while the UI and DB migrate."""
    return {
        'my_story': content.get('personal_identity', ''),
        'my_struggle': content.get('daily_impact', ''),
        'my_hope': content.get('transplant_hope', ''),
    }


PHOTO_ROLE_LABELS = {
    'before': ('Before', 'The life, people, and identity that matter beyond kidney disease.'),
    'during': ('During treatment', 'The kidney journey and the daily impact of treatment.'),
    'hope': ('Hope after transplant', 'The hope of returning to more of what matters.'),
    'general': ('Story photo', 'A photo chosen to help tell this story.'),
}


def _photo_url(filename: str, session_id: str | None = None, *, preview: bool = False) -> str:
    if preview and session_id:
        return url_for('photos.photo_preview', session_id=session_id, filename=filename)
    return url_for('serve_photo', filename=filename)


def _photo_items(photos: list, session_id: str | None = None, *, preview: bool = False) -> list[dict]:
    items = []
    for index, photo in enumerate(photos or []):
        if isinstance(photo, dict):
            filename = photo.get('stored_filename')
            role = photo.get('photo_role') or 'general'
            caption = photo.get('caption') or ''
        else:
            filename = str(photo)
            role = ('before', 'during', 'hope')[index] if index < 3 else 'general'
            caption = ''
        if not filename:
            continue
        label, default_caption = PHOTO_ROLE_LABELS.get(role, PHOTO_ROLE_LABELS['general'])
        items.append({
            'stored_filename': filename,
            'url': _photo_url(filename, session_id, preview=preview),
            'photo_role': role,
            'role_label': label,
            'caption': caption or default_caption,
        })
    return items


def _photo_urls(photos: list, session_id: str | None = None, *, preview: bool = False) -> list:
    return [item['url'] for item in _photo_items(photos, session_id, preview=preview)]


def _render_and_save(session_id: str, name: str, content: dict, photo_items: list[dict]) -> tuple[str, str]:
    microsite_url = url_for('serve_microsite', session_id=session_id, _external=True)
    microsite_path = url_for('serve_microsite', session_id=session_id)
    photo_urls = [item['url'] for item in photo_items]

    html = render_template('microsite.html',
        name=name,
        content=content,
        photos=photo_urls,
        photo_items=photo_items,
        url=microsite_url
    )

    filepath = os.path.join(MICROSITES_DIR, f'{session_id}.html')
    tmp_filepath = f"{filepath}.tmp"
    with open(tmp_filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    os.replace(tmp_filepath, filepath)

    return microsite_path, microsite_url


def _build_result(
    content: dict,
    name: str,
    raw_content: str,
    photo_urls: list,
    *,
    microsite_path: str | None = None,
    microsite_url: str | None = None,
    published: bool = False,
) -> dict:
    result = {
        **content,
        'name': name,
        'content': raw_content,
        'photos': photo_urls,
        'photo_items': _photo_items(photo_urls),
        'microsite_url': microsite_path,
        'microsite_absolute_url': microsite_url,
        'published': published,
    }
    if photo_urls and isinstance(photo_urls[0], dict):
        result['photo_items'] = photo_urls
        result['photos'] = [item['url'] for item in photo_urls]
    return result


def generate(info_state, provider, name: str, session_id: str) -> dict:
    """Generate donor-page draft content without publishing the public page."""
    history = info_state.user.query('conversation_history') or []
    state = info_state.user.query('interview_state') or {}
    conversation = format_story_evidence(state) or format_conversation(history)
    visit_id = info_state.user.query('visit_id')
    photos = db.list_visit_photos(visit_id) or (info_state.user.query('photos') or [])

    prompt_template = load_prompt(MICROSITE_PROMPT_FILE)
    prompt = prompt_template.format(name=name, conversation=conversation)
    raw_content = provider.generate([{"role": "user", "content": prompt}])

    try:
        content_json = parse_llm_json(raw_content)
    except (json.JSONDecodeError, AttributeError, TypeError):
        raise MicrositeGenerationError(
            'invalid_draft_json',
            'The page draft could not be generated in the required format. Please try again.',
        )

    content = _normalize_content(content_json, name)
    result = _build_result(content, name, raw_content, _photo_items(photos, session_id, preview=True), published=False)

    info_state.user.update('microsite_draft', result)
    info_state.user.update('microsite_draft_status', 'draft')
    info_state.save_user_model()

    return result


def publish(info_state, session_id: str, edits: dict | None = None) -> dict:
    """Publish the reviewed donor-page draft and return its public URL."""
    draft = info_state.user.query('microsite_draft')
    if not draft:
        raise ValueError('No donor-page draft is available to publish.')

    edits = edits or {}
    name = _clean_text(edits.get('name')) or _clean_text(draft.get('name')) or 'Patient'
    content_input = {
        field: _clean_text(edits.get(field)) or _clean_text(draft.get(field))
        for field in CONTENT_FIELDS
    }
    content = _normalize_content(content_input, name)
    visit_id = info_state.user.query('visit_id')
    photos = db.list_visit_photos(visit_id) or (info_state.user.query('photos') or [])
    photo_items = _photo_items(photos)
    microsite_path, microsite_url = _render_and_save(session_id, name, content, photo_items)

    result = _build_result(
        content,
        name,
        draft.get('content', ''),
        photo_items,
        microsite_path=microsite_path,
        microsite_url=microsite_url,
        published=True,
    )

    if name != draft.get('name'):
        info_state.user.update('patient_name', name)
        info_state.user.update('patient_name_status', 'corrected')
        info_state.user.update('patient_name_source', 'review_edit')

    info_state.user.update('microsite_draft', result)
    info_state.user.update('microsite_draft_status', 'published')
    info_state.user.update('microsite', result)
    info_state.user.update('interview_phase', 'COMPLETE')
    info_state.save_user_model()

    return result
