"""Patient-facing wording and turn contracts for the donor-story interview."""

from __future__ import annotations

from typing import Any

from .interview_flow_config import FINAL_PHOTOS_PROMPT, FOLLOWUP_QUESTIONS, SECTION_TRANSITIONS


def _recovery_question_text(task: dict[str, Any]) -> str | None:
    step = task.get('step') or {}
    if step.get('id') == 'personal_background':
        return (
            "Can you share something about yourself outside of kidney disease, such as family, work, school, "
            "community, or something you enjoy?"
        )
    return step.get('question')


def deterministic_response(task: dict[str, Any], state: dict[str, Any]) -> str | None:
    task_type = task.get('type')
    name = state.get('patient_name') or ''
    step = task.get('step') or {}
    step_id = step.get('id')
    question = step.get('question')
    if task_type == 'repair_name':
        return "I want to make sure I show your name correctly. What name would you like shown publicly on your donor page?"
    if task_type == 'close_to_photos':
        return FINAL_PHOTOS_PROMPT
    if task_type == 'already_complete':
        return "The story interview is complete. You can continue with the photo step."
    if task_type == 'skip_to_photos':
        return f"No problem, we can skip that. {FINAL_PHOTOS_PROMPT}"
    if task_type == 'skip_then_next' and question:
        transition = SECTION_TRANSITIONS.get(step_id, 'Let us continue with the next part of your story')
        return f"No problem, we can skip that. {transition} {question}"
    if task_type == 'ask_readiness' and task.get('decision', {}).get('kind') == 'not_ready':
        return "That's okay. Take your time, and when you're ready, tell me you want to begin."
    if task_type == 'ask_readiness' and task.get('decision', {}).get('kind') == 'unclear':
        return "Before we start the story questions, are you ready to begin?"
    if task_type == 'answer_readiness_question':
        return (
            "This conversation helps create a donor page by collecting your story in your own words. "
            "You can skip anything or correct me at any point. Are you ready to begin?"
        )
    if task_type == 'ask_readiness' and name:
        return (
            f"Thank you, {name}. I'll ask about your life, your kidney journey, and what a transplant could mean for you. "
            "You can skip anything or correct me at any point. Are you ready to begin?"
        )
    if task_type == 'ask_main' and question:
        return f"{SECTION_TRANSITIONS.get(step_id, 'Let us continue with your story')} {question}"
    if task_type == 'recover_generation_evidence':
        recovery_question = _recovery_question_text(task)
        if not recovery_question:
            return None
        return (
            "Before we move to photos, I need one more detail so the donor page can reflect your story. "
            f"{recovery_question}"
        )
    if task_type == 'ask_followup' and step_id:
        return (task.get('decision') or {}).get('suggested_followup') or FOLLOWUP_QUESTIONS.get(step_id, question)
    if task_type == 'safety_response':
        question = (task.get('decision') or {}).get('question') or 'Would you like to pause here?'
        return (
            "I'm really sorry you're feeling this. This tool cannot provide crisis support. "
            "If you might hurt yourself, please call or text 988 now, or tell someone near you right away. "
            f"{question}"
        )
    if task_type == 'repair_answer' and question:
        decision = task.get('decision') or {}
        if decision.get('reason') == 'clarification_request':
            return f"Sure. I was asking about this part of your donor story: {question}"
        if decision.get('reason') == 'empty_or_no_response':
            return f"I did not catch that clearly. Please try again: {question}"
        if decision.get('reason') == 'operational_issue':
            return f"I am sorry, it sounds like the microphone had trouble. Let's try the same question again: {question}"
        return f"I only caught a little of that. {question}"
    return None


def expected_question_text(task: dict[str, Any]) -> str | None:
    """Return the exact question the backend expects this task to deliver."""
    task_type = task.get('type')
    step = task.get('step') or {}
    if task_type == 'recover_generation_evidence':
        return _recovery_question_text(task)
    if task_type in {'ask_main', 'ack_then_next', 'ask_final', 'repair_answer', 'skip_then_next'}:
        return step.get('question')
    if task_type == 'ask_followup':
        return FOLLOWUP_QUESTIONS.get(step.get('id')) or step.get('question')
    if task_type == 'safety_response':
        return (task.get('decision') or {}).get('question')
    if task_type == 'repair_name':
        return 'What name would you like shown publicly on your donor page?'
    if task_type in {'ask_readiness', 'answer_readiness_question'}:
        return 'Are you ready to begin?'
    return None


def expected_answer_kind(task: dict[str, Any], state: dict[str, Any]) -> str | None:
    task_type = task.get('type')
    if task_type == 'repair_name':
        return 'name'
    if task_type in {'ask_readiness', 'answer_readiness_question'}:
        return 'readiness'
    story_tasks = {'ask_main', 'ack_then_next', 'ask_final', 'repair_answer', 'skip_then_next', 'recover_generation_evidence'}
    if task_type in story_tasks:
        return state.get('awaiting') or 'main_answer'
    if task_type in {'ask_followup', 'safety_response'}:
        return 'followup_answer'
    return None


def build_outgoing_turn_contract(task: dict[str, Any], state: dict[str, Any], response: str, turn_id: str) -> dict[str, Any]:
    """Record what the user actually received and what answer is expected next."""
    question = expected_question_text(task)
    step = task.get('step') or {}
    delivery_validated = bool(question and question in response)
    return {
        'outgoing_turn_id': turn_id,
        'asked_step_id': step.get('id'),
        'asked_question_text': question,
        'expected_answer_kind': expected_answer_kind(task, state),
        'delivered_phase': task.get('phase'),
        'delivery_validated': delivery_validated,
        'task_type': task.get('type'),
    }


def build_runtime_directive(task: dict[str, Any]) -> str:
    """Render a turn-specific instruction block for the LLM."""
    task_type = task.get('type')
    step = task.get('step') or {}
    question = step.get('question', '')
    focus = step.get('focus', '')
    required = step.get('required', '')

    if task_type == 'ask_main':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The patient is ready to begin the donor-story interview.\n'
            f'- Ask this donor-story question in natural conversational wording: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question.'
        )
    if task_type == 'recover_generation_evidence':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The interview is almost complete, but the donor-page draft needs one missing story detail before photos.\n'
            '- Briefly explain that one more detail is needed before moving to photos.\n'
            f'- Ask this recovery question in natural conversational wording: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question. Do not move to photos yet.'
        )
    if task_type == 'ask_followup':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The previous answer was too short or missing important story detail.\n'
            '- Briefly acknowledge what the patient said.\n'
            f'- Ask one open follow-up for the same topic: {focus}.\n'
            f'- The answer should help capture: {required}.\n'
            '- Begin with What, How, or Tell me about.\n'
            '- Do not move to a new topic. Ask only one question.'
        )
    if task_type in {'ack_then_next', 'ask_final'}:
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- Briefly acknowledge one concrete detail from what the patient just shared or previously clarified.\n'
            '- If the patient says they already mentioned something, acknowledge that and use the earlier context; do not praise it as new detail.\n'
            '- Do not use stock phrases like "That gives this part of your story more depth" or "Thank you for sharing that."\n'
            f'- Then ask this next donor-story question exactly, verbatim, at the end: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question.'
        )
    return (
        'RUNTIME TURN DIRECTIVE:\n'
        '- Output only patient-facing speech.\n'
        '- Ask only one question.'
    )
