"""Deterministic screening flow helpers.

The LLM should make the dialogue sound natural, but code owns the
screening contract: topic order, follow-up depth, and completion.
"""

from __future__ import annotations

import random
import re
import json
from typing import Any
from pathlib import Path


DEFAULT_POLICY = {
    'sensitivity_order': {
    'Transportation': 1, 'Physical Activity': 2, 'Sleep': 3,
    'General Health': 4, 'Physical Functioning': 5, 'Pain': 6,
    'Kidney Symptoms': 7, 'Kidney Disease Burden': 8,
    'Kidney Disease Daily Life Impact': 9, 'Dialysis Care Satisfaction': 10,
    'Education': 11, 'Work Status': 12, 'Employment': 12,
    'Disabilities': 13, 'Family and Friends Satisfaction': 14,
    'Family and Community Support': 15, 'Utilities': 16,
    'Food': 17, 'Financial Strain': 18, 'Housing': 19,
    'Substance Use': 20, 'Interpersonal Safety': 21,
    },
    'sensitive_topics': ['Housing', 'Food', 'Interpersonal Safety'],
    'short_answer_phrases': [
        'yes', 'yeah', 'yep', 'yup', 'yea',
        'no', 'nah', 'nope',
        'good', 'very good', 'pretty good', 'fair', 'poor',
        'fine', 'okay', 'ok', 'alright', 'all right',
        'none', 'none none', 'not really', 'no no',
        'i manage', "i'm good", 'im good', "i'm okay", 'im okay',
        "i'm fine", 'im fine',
    ],
    'emotional_terms': [
        'grief', 'grieving', 'passed away', 'died', 'death', 'depressed',
        'depression', 'lonely', 'alone', 'scared', 'afraid', 'fear',
        'hopeless', 'lost my', 'hard since',
    ],
    'urgent_terms': [
        'kill myself', 'suicide', 'suicidal', 'hurt myself', 'harm myself',
        'hurt someone', 'harm someone', 'unsafe at home', 'in danger',
    ],
    'person_terms': [
        'daughter', 'son', 'wife', 'husband', 'mother', 'father', 'mom', 'dad',
        'sister', 'brother', 'friend', 'neighbor', 'caregiver', 'family',
        'church', 'staff',
    ],
    'activity_terms': [
        'walk', 'walking', 'drive', 'drives', 'work', 'working', 'cook',
        'shop', 'sleep', 'pay', 'eat', 'exercise', 'appointment', 'dialysis',
        'transportation', 'bus', 'ride', 'medication', 'medicine',
    ],
    'reason_markers': ['because', 'since', 'due to', 'that helps', 'so that'],
    'time_markers': [
        'every day', 'daily', 'weekly', 'monthly', 'twice', 'once', 'usually',
        'sometimes', 'often', 'rarely', 'last year', 'last month', 'recently',
        'per week', 'a week', 'a month', 'most days',
    ],
    'min_detail_words': 10,
}

POLICY_FILE = Path(__file__).resolve().parents[1] / 'configuration' / 'screening_flow.json'


def _coerce_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    return [str(item) for item in value if str(item).strip()]


def load_policy(filepath: str | Path = POLICY_FILE) -> dict[str, Any]:
    """Load tunable screening policy with safe defaults."""
    policy = dict(DEFAULT_POLICY)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        raw = {}

    if isinstance(raw.get('sensitivity_order'), dict):
        policy['sensitivity_order'] = {
            str(k): int(v) for k, v in raw['sensitivity_order'].items()
            if isinstance(v, int) or str(v).isdigit()
        }
    for key in (
        'sensitive_topics', 'short_answer_phrases', 'emotional_terms',
        'urgent_terms', 'person_terms', 'activity_terms', 'reason_markers',
        'time_markers',
    ):
        policy[key] = _coerce_list(raw.get(key), policy[key])
    try:
        policy['min_detail_words'] = int(raw.get('min_detail_words', policy['min_detail_words']))
    except (TypeError, ValueError):
        pass
    return policy


POLICY = load_policy()
SENSITIVITY_ORDER = POLICY['sensitivity_order']
SENSITIVE_TOPICS = set(POLICY['sensitive_topics'])


def load_question_topics(filepath: str) -> list[dict[str, Any]]:
    """Parse prompts/questions.txt into structured topic objects."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read().strip()
    except FileNotFoundError:
        return []

    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    topics = []
    for block in paragraphs[1:]:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].endswith(':'):
            continue
        category = lines[0].rstrip(':').strip()
        questions = []
        for line in lines[1:]:
            match = re.search(r'"(.+)"', line)
            if match:
                questions.append(match.group(1).strip())
        if questions:
            topics.append({
                'category': category,
                'questions': questions,
                'sensitivity': SENSITIVITY_ORDER.get(category, 99),
            })
    return topics


def select_topics(topics: list[dict[str, Any]], count: int = 6) -> list[dict[str, Any]]:
    """Randomly select topics, then sort least-to-most sensitive."""
    selected = random.sample(topics, min(count, len(topics))) if topics else []
    selected.sort(key=lambda t: t.get('sensitivity', 99))
    return selected


def build_screening_state(topics: list[dict[str, Any]]) -> dict[str, Any]:
    """Initial state stored in info_state.user."""
    return {
        'topics': topics,
        'topic_index': 0,
        'phase': 'INTRO',
        'awaiting': 'name',
        'followup_used': False,
        'asked_final_care_team_question': False,
        'halfway_cue_given': False,
        'last_task': 'opening',
        'last_topic_category': None,
        'last_probe_depth': None,
    }


def build_question_instructions_from_topics(topics: list[dict[str, Any]]) -> str:
    """Render selected topics for prompt context only, not control."""
    if not topics:
        return ''
    blocks = [
        'The following six topics were selected for this visit. Code will tell you which one to ask next.'
    ]
    for topic in topics:
        questions = '\n'.join(f'  - "{q}"' for q in topic.get('questions', []))
        blocks.append(f"{topic['category']}:\n{questions}")
    return '\n\n'.join(blocks)


def normalize_answer(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9'\s]", ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def has_urgent_disclosure(text: str) -> bool:
    normalized = normalize_answer(text)
    return any(term in normalized for term in POLICY['urgent_terms'])


def has_emotional_disclosure(text: str) -> bool:
    normalized = normalize_answer(text)
    return any(term in normalized for term in POLICY['emotional_terms'])


def detail_reason(text: str) -> dict[str, Any]:
    normalized = normalize_answer(text)
    for key, reason in (
        ('person_terms', 'named_person'),
        ('activity_terms', 'concrete_activity'),
        ('reason_markers', 'reason_marker'),
        ('time_markers', 'time_or_frequency'),
    ):
        for marker in POLICY[key]:
            if marker in normalized:
                return {'has_detail': True, 'reason': reason, 'matched': marker}
    word_count = len(normalized.split())
    if word_count >= POLICY['min_detail_words']:
        return {'has_detail': True, 'reason': 'word_count', 'matched': word_count}
    return {'has_detail': False, 'reason': 'no_detail', 'matched': None}


def has_concrete_detail(text: str) -> bool:
    return detail_reason(text)['has_detail']


def followup_decision(text: str) -> dict[str, Any]:
    """Return explainable follow-up policy decision for a patient answer."""
    normalized = normalize_answer(text)
    if not normalized:
        return {'needs_followup': True, 'reason': 'empty', 'matched': ''}
    if normalized in POLICY['short_answer_phrases']:
        return {'needs_followup': True, 'reason': 'short_phrase', 'matched': normalized}
    words = normalized.split()
    detail = detail_reason(normalized)
    if len(words) <= 3 and not detail['has_detail']:
        return {'needs_followup': True, 'reason': 'short_length', 'matched': len(words)}
    return {
        'needs_followup': False,
        'reason': detail['reason'] if detail['has_detail'] else 'sufficient_length',
        'matched': detail['matched'],
    }


def is_short_or_vague_answer(text: str) -> bool:
    return followup_decision(text)['needs_followup']


def current_topic(state: dict[str, Any]) -> dict[str, Any] | None:
    topics = state.get('topics') or []
    index = state.get('topic_index', 0)
    if 0 <= index < len(topics):
        return topics[index]
    return None


def current_question(state: dict[str, Any]) -> str:
    topic = current_topic(state)
    if not topic:
        return ''
    questions = topic.get('questions') or []
    return questions[0] if questions else ''


def advance_topic(state: dict[str, Any]) -> None:
    state['topic_index'] = state.get('topic_index', 0) + 1
    state['followup_used'] = False
    state['awaiting'] = 'main_answer'


def maybe_add_halfway_cue(state: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """Mark the first turn after three completed topics for reassurance."""
    if state.get('topic_index') == 3 and not state.get('halfway_cue_given'):
        state['halfway_cue_given'] = True
        task['halfway_cue'] = True
    return task


def decide_next_task(state: dict[str, Any], user_input: str) -> dict[str, Any]:
    """Update state and return the next task for the LLM/code."""
    if has_urgent_disclosure(user_input):
        state['phase'] = 'REPORT'
        state['awaiting'] = 'complete'
        state['last_followup_decision'] = {'needs_followup': False, 'reason': 'urgent_close', 'matched': None}
        return {'type': 'urgent_close', 'probe_depth': None, 'topic': current_topic(state)}

    phase = state.get('phase', 'INTRO')
    awaiting = state.get('awaiting')

    if phase == 'INTRO':
        if awaiting == 'name':
            state['awaiting'] = 'readiness'
            return {'type': 'ask_readiness', 'probe_depth': None, 'topic': None}
        state['phase'] = 'SCREENING'
        state['awaiting'] = 'main_answer'
        state['followup_used'] = False
        return {'type': 'ask_main', 'probe_depth': 0, 'topic': current_topic(state)}

    if phase == 'FINAL_QUESTION':
        state['phase'] = 'REPORT'
        state['awaiting'] = 'complete'
        return {'type': 'close', 'probe_depth': None, 'topic': None}

    if awaiting == 'followup_answer':
        advance_topic(state)
        if current_topic(state):
            return maybe_add_halfway_cue(
                state,
                {'type': 'ack_then_next', 'probe_depth': 0, 'topic': current_topic(state)},
            )
        state['phase'] = 'FINAL_QUESTION'
        state['awaiting'] = 'final_answer'
        state['asked_final_care_team_question'] = True
        return {'type': 'ask_final', 'probe_depth': None, 'topic': None}

    if awaiting == 'main_answer':
        topic = current_topic(state)
        decision = followup_decision(user_input)
        if has_emotional_disclosure(user_input):
            decision = {'needs_followup': False, 'reason': 'emotional_disclosure', 'matched': None}
        state['last_followup_decision'] = decision
        if (
            topic
            and not state.get('followup_used')
            and decision['needs_followup']
        ):
            state['followup_used'] = True
            state['awaiting'] = 'followup_answer'
            return {'type': 'ask_followup', 'probe_depth': 1, 'topic': topic, 'followup_decision': decision}

        advance_topic(state)
        if current_topic(state):
            return maybe_add_halfway_cue(
                state,
                {'type': 'ack_then_next', 'probe_depth': 0, 'topic': current_topic(state)},
            )
        state['phase'] = 'FINAL_QUESTION'
        state['awaiting'] = 'final_answer'
        state['asked_final_care_team_question'] = True
        return {'type': 'ask_final', 'probe_depth': None, 'topic': None}

    return {'type': 'ask_main', 'probe_depth': 0, 'topic': current_topic(state)}
