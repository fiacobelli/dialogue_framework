"""Microsite generation logic."""
import os
import re
import json
from flask import render_template, url_for
from .config import MICROSITES_DIR, MICROSITE_PROMPT_FILE, FALLBACK_PROMPT


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


def generate(info_state, provider, name: str, session_id: str) -> dict:
    """Generate microsite content and save HTML file."""
    # Get conversation history
    history = info_state.user.query('conversation_history') or []
    conversation = format_conversation(history)
    photos = info_state.user.query('photos') or []

    # Generate content via LLM
    prompt_template = load_prompt(MICROSITE_PROMPT_FILE)
    prompt = prompt_template.format(name=name, conversation=conversation)
    raw_content = provider.generate([{"role": "user", "content": prompt}])

    # Parse JSON from response
    try:
        content_json = parse_llm_json(raw_content)
    except (json.JSONDecodeError, AttributeError):
        content_json = {
            'headline': f"{name} needs a kidney donor",
            'my_story': raw_content[:500] if raw_content else "My story...",
            'my_struggle': "Living with kidney disease has been challenging...",
            'my_hope': "A kidney transplant would change my life..."
        }

    # Build URLs
    microsite_url = url_for('serve_microsite', session_id=session_id, _external=True)
    microsite_path = url_for('serve_microsite', session_id=session_id)
    photo_urls = [url_for('serve_photo', filename=p) for p in photos]

    # Render and save HTML
    html = render_template('microsite.html',
        name=name,
        headline=content_json.get('headline', ''),
        my_story=content_json.get('my_story', ''),
        my_struggle=content_json.get('my_struggle', ''),
        my_hope=content_json.get('my_hope', ''),
        photos=photo_urls,
        url=microsite_url
    )

    filepath = os.path.join(MICROSITES_DIR, f'{session_id}.html')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    # Build response - spread content_json first so our values take precedence
    result = {
        **content_json,
        'name': name,
        'content': raw_content,
        'photos': photo_urls,
        'microsite_url': microsite_path,
        'microsite_absolute_url': microsite_url,
    }

    info_state.user.update('microsite', result)
    info_state.save_user_model()

    return result
