"""Microsite generation logic."""
import os
import re
import json
from flask import render_template, url_for
from .config import MICROSITES_DIR, MICROSITE_PROMPT_FILE, FALLBACK_PROMPT

CONTENT_FIELDS = ('headline', 'my_story', 'my_struggle', 'my_hope')


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
    return "\n\n".join(lines)


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
    """Return complete draft fields with safe fallbacks for missing LLM keys."""
    content = content or {}
    normalized = {field: _clean_text(content.get(field)) for field in CONTENT_FIELDS}
    if not normalized['headline']:
        normalized['headline'] = f"{name} needs a kidney donor"
    if not normalized['my_story']:
        normalized['my_story'] = (
            "I am sharing my story because finding a living kidney donor could make a meaningful difference in my life. "
            "The details I shared are personal, and I hope this page helps others understand why this matters."
        )
    if not normalized['my_struggle']:
        normalized['my_struggle'] = (
            "Living with kidney disease has brought challenges that affect daily life and future plans. "
            "I am doing my best to keep moving forward while looking for a path toward better health."
        )
    if not normalized['my_hope']:
        normalized['my_hope'] = (
            "A kidney transplant could offer more stability, more possibility, and more time to focus on the people and parts of life that matter most. "
            "If you are able to learn more, consider sharing this page or exploring living donation."
        )
    return normalized


def _photo_urls(photos: list) -> list:
    return [url_for('serve_photo', filename=p) for p in photos]


def _render_and_save(session_id: str, name: str, content: dict, photo_urls: list) -> tuple[str, str]:
    microsite_url = url_for('serve_microsite', session_id=session_id, _external=True)
    microsite_path = url_for('serve_microsite', session_id=session_id)

    html = render_template('microsite.html',
        name=name,
        headline=content.get('headline', ''),
        my_story=content.get('my_story', ''),
        my_struggle=content.get('my_struggle', ''),
        my_hope=content.get('my_hope', ''),
        photos=photo_urls,
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
        'microsite_url': microsite_path,
        'microsite_absolute_url': microsite_url,
        'published': published,
    }
    return result


def generate(info_state, provider, name: str, session_id: str) -> dict:
    """Generate donor-page draft content without publishing the public page."""
    history = info_state.user.query('conversation_history') or []
    state = info_state.user.query('interview_state') or {}
    conversation = format_story_evidence(state) or format_conversation(history)
    photos = info_state.user.query('photos') or []

    prompt_template = load_prompt(MICROSITE_PROMPT_FILE)
    prompt = prompt_template.format(name=name, conversation=conversation)
    raw_content = provider.generate([{"role": "user", "content": prompt}])

    try:
        content_json = parse_llm_json(raw_content)
    except (json.JSONDecodeError, AttributeError, TypeError):
        content_json = {
            'headline': f"{name} needs a kidney donor",
            'my_story': raw_content[:500] if raw_content else "My story is still being written.",
            'my_struggle': "Living with kidney disease has been challenging.",
            'my_hope': "A kidney transplant would change my life."
        }

    content = _normalize_content(content_json, name)
    result = _build_result(content, name, raw_content, _photo_urls(photos), published=False)

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
    photos = info_state.user.query('photos') or []
    photo_urls = _photo_urls(photos)
    microsite_path, microsite_url = _render_and_save(session_id, name, content, photo_urls)

    result = _build_result(
        content,
        name,
        draft.get('content', ''),
        photo_urls,
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
