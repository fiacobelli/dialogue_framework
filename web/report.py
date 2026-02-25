"""Screening classification logic — replaces microsite.py."""
import logging
import re
import json
from .config import CLASSIFY_PROMPT_FILE, FALLBACK_PROMPT

logger = logging.getLogger(__name__)


def load_prompt(filepath: str) -> str:
    try:
        with open(filepath, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return FALLBACK_PROMPT


def parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def format_conversation(history: list) -> str:
    """Format conversation history as readable transcript."""
    lines = []
    for msg in history:
        role = "Patient" if msg.get("role") == "user" else "Screener"
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def extract_patient_answers(history: list) -> str:
    """Extract only patient (user) messages for compact classification input."""
    lines = []
    for msg in history:
        if msg.get("role") == "user":
            lines.append(f"Patient: {msg.get('content', '')}")
    return "\n".join(lines)


def classify(info_state, provider) -> dict:
    """Classify screening responses into professional referral buckets."""
    history = info_state.user.query('conversation_history') or []
    conversation = extract_patient_answers(history)
    logger.info("Classify input: %d patient messages, %d chars",
                conversation.count('\n') + 1, len(conversation))

    prompt_template = load_prompt(CLASSIFY_PROMPT_FILE)
    prompt = prompt_template.format(conversation=conversation)

    raw = provider.generate([{"role": "user", "content": prompt}])
    logger.debug("Classify raw LLM response: %s", raw)

    try:
        result = parse_llm_json(raw)
        logger.info("Classify succeeded: %s", list(result.keys()))
        return result
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error("Classify JSON parse failed: %s | Raw response: %s", e, raw)
        return {
            'social_worker': 'Unable to classify — please review manually.',
            'dietitian': 'Unable to classify — please review manually.',
            'nephrologist': 'Unable to classify — please review manually.',
            'nurse_practitioner': 'Unable to classify — please review manually.',
            'verbal_summary': 'We will share your answers with your care team. Thank you for your time today, and take care of yourself.'
        }
