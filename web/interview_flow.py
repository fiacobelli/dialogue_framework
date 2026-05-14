"""Deterministic donor-story interview flow helpers.

The LLM should make the interview sound natural, but code owns the
story-section order and the transition into photo upload.
"""

from __future__ import annotations

from typing import Any


INTERVIEW_STEPS: list[dict[str, str]] = [
    {
        'id': 'personal_background',
        'phase': 'BEFORE',
        'question': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
        'focus': 'who the patient is as a person, including family, work, community, hobbies, or identity',
    },
    {
        'id': 'medical_history',
        'phase': 'BEFORE',
        'question': 'When were you first diagnosed with kidney disease or kidney failure?',
        'focus': 'the beginning of the kidney disease journey',
    },
    {
        'id': 'daily_life',
        'phase': 'DURING',
        'question': 'How has kidney failure affected your daily life, physically or emotionally?',
        'focus': 'dialysis, symptoms, daily limits, emotional burden, and what has changed',
    },
    {
        'id': 'transplant_hope',
        'phase': 'HOPE',
        'question': 'How would receiving a kidney transplant change your life?',
        'focus': 'specific hopes, activities, family moments, work, travel, energy, or independence',
    },
    {
        'id': 'donor_message',
        'phase': 'HOPE',
        'question': 'What would you want a potential donor to know about you as a person?',
        'focus': 'a direct message to potential donors and what makes the story personal',
    },
    {
        'id': 'support_network',
        'phase': 'HOPE',
        'question': 'Do you have family, friends, or a community supporting you through this?',
        'focus': 'support network, community ties, and people who may be part of the story',
    },
    {
        'id': 'final_details',
        'phase': 'HOPE',
        'question': 'Is there anything else about your story, or any further details on something in particular, that you would like included?',
        'focus': 'final details, tone, quotes, photos, or personal stories before photo upload',
    },
]


def build_interview_state() -> dict[str, Any]:
    """Initial state stored in info_state.user."""
    return {
        'step_index': 0,
        'phase': 'WELCOME',
        'awaiting': 'name',
        'last_task': 'opening',
        'last_step_id': None,
        'complete': False,
    }


def current_step(state: dict[str, Any]) -> dict[str, str] | None:
    steps = INTERVIEW_STEPS
    index = int(state.get('step_index') or 0)
    if 0 <= index < len(steps):
        return steps[index]
    return None


def decide_next_task(state: dict[str, Any]) -> dict[str, Any]:
    """Update state and return the next code-owned task."""
    if state.get('complete'):
        return {'type': 'already_complete', 'phase': 'PHOTOS', 'step': None}

    if state.get('awaiting') == 'name':
        step = current_step(state)
        state['awaiting'] = 'story_answer'
        state['phase'] = step['phase'] if step else 'PHOTOS'
        state['last_task'] = 'ask_step'
        state['last_step_id'] = step['id'] if step else None
        return {'type': 'ask_step', 'phase': state['phase'], 'step': step, 'acknowledge': True}

    index = int(state.get('step_index') or 0) + 1
    state['step_index'] = index
    step = current_step(state)
    if step:
        state['awaiting'] = 'story_answer'
        state['phase'] = step['phase']
        state['last_task'] = 'ask_step'
        state['last_step_id'] = step['id']
        return {'type': 'ask_step', 'phase': state['phase'], 'step': step, 'acknowledge': True}

    state['awaiting'] = 'photos'
    state['phase'] = 'PHOTOS'
    state['complete'] = True
    state['last_task'] = 'close_to_photos'
    state['last_step_id'] = None
    return {'type': 'close_to_photos', 'phase': 'PHOTOS', 'step': None}


def build_runtime_directive(task: dict[str, Any]) -> str:
    """Render a turn-specific instruction block for the LLM."""
    task_type = task.get('type')
    if task_type == 'close_to_photos':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The patient has answered the final story question.\n'
            '- Thank them warmly for sharing their story.\n'
            '- Tell them the story interview is complete and the next step is uploading three photos for the donor page.\n'
            '- Do not ask another story question.\n'
            '- Keep the response to 2 short sentences.'
        )

    step = task.get('step') or {}
    question = step.get('question', '')
    focus = step.get('focus', '')
    return (
        'RUNTIME TURN DIRECTIVE:\n'
        '- Briefly acknowledge what the patient just shared.\n'
        f'- Ask this next donor-story question, in natural conversational wording: "{question}"\n'
        f'- Listen for details about: {focus}.\n'
        '- Ask only one question.\n'
        '- Do not skip ahead and do not ask about photo upload yet.\n'
        '- Keep the response to 2 short sentences.'
    )


def build_opening_directive() -> str:
    """Runtime instruction for the first assistant message."""
    return (
        'RUNTIME TURN DIRECTIVE:\n'
        '- Greet the patient and introduce yourself by name.\n'
        '- Explain that you will ask about their life and kidney journey to help create a donor webpage.\n'
        '- Reassure them they can share as much or as little as they want.\n'
        '- Ask only for their name.\n'
        '- Do not ask any story-section question yet.\n'
        '- Keep the response to 2 short sentences.'
    )
