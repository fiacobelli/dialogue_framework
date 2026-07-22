"""Screening goal - LLM-driven health screening using system prompt."""
import os
import re
import time
import logging
from datetime import datetime
from goal import Goal
from strings import MSG, BELSTR
from .config import LANGUAGE_NAMES
from . import database as db
from .screening_flow import (
    build_screening_state,
    advance_topic,
    current_topic,
    decide_next_task,
    repair_decision,
)

LOGS_DIR = 'logs'
MAX_USER_TURNS = 20
MIN_TURNS_FOR_GOODBYE = 4
logger = logging.getLogger(__name__)



EXIT_PHRASE = "It means a lot that you shared all of this with me. Your care team will have everything they need to look after you well."
URGENT_EXIT_PHRASE = (
    "I'm really glad you told me that. If you are in immediate danger or might hurt yourself "
    "or someone else, please call 911 right now. Your care team will have everything they need "
    "to look after you well."
)
SUMMARY_PREAMBLE_RE = re.compile(
    r"^\s*(I['\u2019]ll|I will|Here['\u2019]s|Here is|Sure|Okay|Of course|Certainly)[^.\n]*[.!?]\s*",
    re.IGNORECASE,
)
META_LINE_RE = re.compile(
    r"^\s*(\([^)]*(?:note|rule|instruction|move on|response|topic|follow)[^)]*\)|"
    r"(?:note|rule|instruction)\s*:.*)\s*$",
    re.IGNORECASE,
)
STREAM_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+')


def log_screening(session_id: str, entry: str):
    """Append a log entry for debugging screenings."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    filepath = os.path.join(LOGS_DIR, f'screening_{session_id}.txt')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {entry}\n")


class ScreeningGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str, first_time_prompt: str = '', subsequent_prompt: str = ''):
        self.llm = llm_provider
        self.system_prompt = system_prompt
        self.first_time_prompt = first_time_prompt
        self.subsequent_prompt = subsequent_prompt

    def is_complete(self, info_state) -> bool:
        return info_state.user.query('screening_phase') == 'REPORT'

    def _build_prompt(self, info_state, avatar_name: str, language: str) -> str:
        """Concatenate the right intro + shared screener + runtime values."""
        visit_number = info_state.user.query('visit_number') or 1
        is_returning = visit_number > 1 and bool(info_state.user.query('last_summary'))
        intro = self.subsequent_prompt if is_returning else self.first_time_prompt
        full = f"{intro}\n\n{self.system_prompt}" if intro else self.system_prompt

        question_block = info_state.user.query('question_instructions') or DEFAULT_QUESTION_BLOCK
        prompt = full.replace('{avatar_name}', avatar_name)
        prompt = prompt.replace('{question_instructions}', question_block)
        last_summary = info_state.user.query('last_summary')
        if is_returning and last_summary:
            prompt += f"\n\nSummary of last session:\n{last_summary}"
        if language != 'en':
            lang_name = LANGUAGE_NAMES.get(language, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."
        return prompt

    def execute_goal(self, msg, info_state):
        context = self._prepare_turn(msg, info_state)
        response, latency = self._generate_for_task(context)
        self._finalize_turn(msg, info_state, context, response, latency, stream=False)

    def execute_goal_stream(self, msg, info_state):
        """Yield a full retried LLM response for route-level sentence streaming."""
        context = self._prepare_turn(msg, info_state)

        response, latency = self._generate_for_task(context)
        self._finalize_turn(msg, info_state, context, response, latency, stream=True)
        yield msg[MSG.RESPONSE]

    def _prepare_turn(self, msg, info_state) -> dict:
        history = info_state.user.query('conversation_history') or []
        user_input = msg.get(MSG.ORIG_TEXT, '')
        language = info_state.user.query('language') or 'en'
        session_id = info_state.user.query('session_id') or 'unknown'
        turn_meta = msg.get('turn_meta') or {}
        no_response = turn_meta.get('no_response', False)
        state = self._get_screening_state(info_state)
        awaiting = state.get('awaiting')
        answered_topic = (
            current_topic(state)
            if state.get('phase') == 'SCREENING' and awaiting in {'main_answer', 'followup_answer'}
            else None
        )
        answered_probe_depth = 1 if awaiting == 'followup_answer' else (0 if answered_topic else None)
        repair = repair_decision(user_input)

        if user_input and repair['is_repair']:
            task = {
                'type': 'repair',
                'probe_depth': None,
                'topic': None,
                'repair_intent': repair['intent'],
                'repair_matched': repair['matched'],
            }
            state['last_task'] = task['type']
            state['last_topic_category'] = None
            state['last_probe_depth'] = None
            state['last_repair_decision'] = repair
            info_state.user.update('screening_state', state)
            info_state.user.update('screening_phase', 'REPORT' if state.get('phase') == 'REPORT' else 'SCREENING')
            log_screening(session_id, f"REPAIR_DECISION: {repair} | TEXT: {user_input}")
            user_turn_count = sum(1 for m in history if m.get('role') == 'user')
            avatar_profile = info_state.user.query('avatar_profile') or {}
            return {
                'history': history,
                'user_input': user_input,
                'language': language,
                'session_id': session_id,
                'turn_meta': turn_meta,
                'no_response': no_response,
                'user_turn_count': user_turn_count,
                'avatar_profile': avatar_profile,
                'prompt': '',
                'task': task,
                'state': state,
                'answered_topic': None,
                'answered_probe_depth': None,
            }

        if user_input:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)
            log_screening(session_id, f"USER: {user_input}")

        if no_response:
            task = self._skip_current_question(state)
        else:
            task = decide_next_task(state, user_input)

        state['last_task'] = task['type']
        topic = task.get('topic')
        state['last_topic_category'] = topic.get('category') if topic else None
        state['last_probe_depth'] = task.get('probe_depth')
        info_state.user.update('screening_state', state)
        info_state.user.update('screening_phase', 'REPORT' if state.get('phase') == 'REPORT' else 'SCREENING')
        decision = state.get('last_followup_decision')
        if decision:
            log_screening(session_id, f"FOLLOWUP_DECISION: {decision}")

        user_turn_count = sum(1 for m in history if m.get('role') == 'user')
        avatar_profile = info_state.user.query('avatar_profile') or {}
        avatar_name = avatar_profile.get('name', 'Assistant')
        prompt = self._build_runtime_prompt(info_state, avatar_name, language, task, user_input)

        return {
            'history': history,
            'user_input': user_input,
            'language': language,
            'session_id': session_id,
            'turn_meta': turn_meta,
            'no_response': no_response,
            'user_turn_count': user_turn_count,
            'avatar_profile': avatar_profile,
            'prompt': prompt,
            'task': task,
            'state': state,
            'answered_topic': answered_topic,
            'answered_probe_depth': answered_probe_depth,
        }

    def _generate_for_task(self, context: dict) -> tuple[str, int]:
        task_type = context['task']['type']
        if task_type == 'repair':
            return self._repair_response(context), 0
        if task_type == 'urgent_close':
            return URGENT_EXIT_PHRASE, 0

        t0 = time.perf_counter()
        response = self.llm.generate(context['history'], context['prompt'], temperature=0.75)
        llm_latency_ms = int((time.perf_counter() - t0) * 1000)
        return response, llm_latency_ms

    def _finalize_turn(self, msg, info_state, context: dict, response: str,
                       llm_latency_ms: int, stream: bool) -> None:
        history = context['history']
        session_id = context['session_id']
        user_turn_count = context['user_turn_count']
        cleaned = self._clean_spoken_response(response)
        if cleaned != response:
            log_screening(session_id, f"CLEANED RESPONSE: {cleaned}")
        response = cleaned or EXIT_PHRASE

        log_label = "LLM (%sms) [stream]" if stream else "LLM (%sms)"
        log_screening(session_id, f"{log_label % llm_latency_ms}: {response}")

        if context['task']['type'] == 'repair':
            msg[MSG.RESPONSE] = response
            self._save_repair_event(info_state, context)
            return

        is_ending = context['state'].get('phase') == 'REPORT' or self._is_goodbye(response, user_turn_count)
        if not is_ending and user_turn_count >= MAX_USER_TURNS:
            log_screening(session_id, f"FORCED ENDING at turn {user_turn_count}")
            response = EXIT_PHRASE
            is_ending = True
        log_screening(session_id, f"_is_goodbye check: {is_ending}")

        if is_ending:
            info_state.user.update('screening_phase', 'REPORT')
            log_screening(session_id, "PHASE CHANGED TO: REPORT")
            try:
                summary = self._generate_summary(history, response)
                info_state.user.update('last_summary', summary)
                log_screening(session_id, f"SUMMARY: {summary}")
            except Exception as exc:
                log_screening(session_id, f"SUMMARY FAILED: {exc}")
                logger.warning("Summary generation failed for %s: %s", session_id, exc)

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg[MSG.RESPONSE] = response
        self._save_turn(info_state, context, response, llm_latency_ms)

    def _save_turn(self, info_state, context: dict, response: str, llm_latency_ms: int) -> None:
        visit_id = info_state.user.query('visit_id')
        phone_pin = info_state.user.query('patient_pin')
        avatar_profile = context['avatar_profile']
        phase = info_state.user.query('screening_phase') or 'WELCOME'
        agent = info_state.user.query('avatar') or 'unknown'
        voice = avatar_profile.get('lang', context['language'])
        history = context['history']
        turn_meta = context['turn_meta']
        user_input = context['user_input']
        answered_topic = context['answered_topic'] or {}
        assistant_topic = context['task'].get('topic') or {}

        if visit_id:
            turn = len(history)
            if user_input:
                db.save_message(
                    visit_id, 'user', user_input, turn - 2, agent, voice,
                    input_modality=turn_meta.get('input_modality'),
                    response_latency_ms=turn_meta.get('response_latency_ms'),
                    response_latency_source=turn_meta.get('response_latency_source'),
                    speech_confidence=turn_meta.get('speech_confidence'),
                    client_sent_at=turn_meta.get('client_sent_at'),
                    question_category=answered_topic.get('category'),
                    probe_depth=context['answered_probe_depth'],
                )
                if not context['no_response']:
                    db.increment_visit_turns(visit_id)
                    events = turn_meta.get('events') or []
                    if events:
                        db.save_turn_events(visit_id, turn - 2, events)
            db.save_message(
                visit_id, 'assistant', response, turn - 1, agent, voice,
                llm_latency_ms=llm_latency_ms,
                question_category=assistant_topic.get('category'),
                probe_depth=context['task'].get('probe_depth'),
            )
            db.update_visit_phase(visit_id, phase)
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

    def _save_repair_event(self, info_state, context: dict) -> None:
        visit_id = info_state.user.query('visit_id')
        phone_pin = info_state.user.query('patient_pin')
        if visit_id:
            turn_number = len(context['history'])
            db.save_turn_events(visit_id, turn_number, [{
                'event_type': 'repair_detected',
                'client_ts_ms': int(time.time() * 1000),
                'metadata': {
                    'intent': context['task'].get('repair_intent'),
                    'matched': context['task'].get('repair_matched'),
                    'text': context['user_input'],
                },
            }])
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

    def _get_screening_state(self, info_state) -> dict:
        state = info_state.user.query('screening_state')
        if state:
            return state
        topics = []
        question_block = info_state.user.query('question_instructions') or ''
        for block in [p for p in question_block.split('\n\n') if ':' in p]:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            category = lines[0].rstrip(':')
            questions = []
            for line in lines[1:]:
                match = re.search(r'"(.+)"', line)
                if match:
                    questions.append(match.group(1))
            if questions:
                topics.append({'category': category, 'questions': questions, 'sensitivity': 99})
        state = build_screening_state(topics)
        info_state.user.update('screening_state', state)
        return state

    def _skip_current_question(self, state: dict) -> dict:
        if state.get('phase') == 'INTRO':
            state['phase'] = 'SCREENING'
            state['awaiting'] = 'main_answer'
            return {'type': 'ask_main', 'probe_depth': 0, 'topic': current_topic(state)}
        advance_topic(state)
        if current_topic(state):
            return {'type': 'ack_then_next', 'probe_depth': 0, 'topic': current_topic(state)}
        state['phase'] = 'FINAL_QUESTION'
        state['awaiting'] = 'final_answer'
        state['asked_final_care_team_question'] = True
        return {'type': 'ask_final', 'probe_depth': None, 'topic': None}

    def _build_runtime_prompt(self, info_state, avatar_name: str, language: str,
                              task: dict, user_input: str) -> str:
        prompt = self._build_prompt(info_state, avatar_name, language)
        prompt += "\n\nRUNTIME TURN DIRECTIVE:\n"
        prompt += self._task_directive(task, user_input)
        prompt += "\n\nIMPORTANT: Do not include the text 'RUNTIME TURN DIRECTIVE' or any directive labels in your response. Output only patient-facing speech."
        return prompt

    def _task_directive(self, task: dict, user_input: str) -> str:
        task_type = task['type']
        topic = task.get('topic') or {}
        category = topic.get('category', '')
        question = topic.get('selected_question') or (topic.get('questions', [''])[0] if topic else '')

        if task_type == 'ask_readiness':
            return (
                "The patient just gave their name or introduced themselves. "
                "Briefly greet them by name if you know it, then ask if they are ready to begin. "
                "Do not ask a screening question yet. Ask only one question."
            )
        if task_type == 'ask_name_retry':
            return (
                "The patient has not clearly shared their name yet. "
                "Briefly say you did not catch their name, then ask for their name again. "
                "Do not ask if they are ready yet. Do not ask a screening question. Ask only one question."
            )
        if task_type == 'ask_main':
            return (
                f"Current task: ask the main screening question for {category}. "
                f"Ask this source question in patient-friendly spoken language: \"{question}\" "
                f"{self._sensitive_topic_instruction(category)}"
                "Ask only one question."
            )
        if task_type == 'ask_followup':
            return (
                f"Current task: ask one conversational follow-up for {category}. "
                f"The patient just answered: \"{user_input}\". "
                "Do not move to the next topic yet. "
                "Do not ask another listed source screening question. "
                "Briefly reflect what they said, then ask one open follow-up that helps the care team understand what that answer means in daily life. "
                "Begin the follow-up with What, How, or Tell me about. Ask only one question."
            )
        if task_type == 'ack_then_next':
            halfway = (
                'Also include this reassurance once, naturally: '
                '"We\'re about halfway through, and you\'re doing well." '
                if task.get('halfway_cue') else ''
            )
            return (
                f"Current task: move to the next topic, {category}. "
                f"Briefly acknowledge the patient's last answer. {halfway}"
                f"Then ask this source question in patient-friendly spoken language: \"{question}\" "
                f"{self._sensitive_topic_instruction(category)}"
                "Ask only one question."
            )
        if task_type == 'ask_final':
            return (
                "All six screening topics are complete. Briefly acknowledge the patient's last answer. "
                "Then ask: Are there any other issues you would like your care team to know about "
                "in any other aspects of your life, or any further details on something in particular? "
                "Ask only that one question."
            )
        if task_type == 'close':
            return (
                "Current task: give the final response and end the screening. "
                f"The patient just answered the care-team question with: \"{user_input}\". "
                "Briefly acknowledge what they said, including if they said they had nothing else to add. "
                "Thank them for answering the questions and say their answers will be shared with their care team. "
                f"End with this exact sentence: \"{EXIT_PHRASE}\" "
                "Do not ask another question. This is the final spoken response."
            )
        if task_type == 'repair':
            return "Current task: handle an operational repair request. Do not advance the screening."
        return "Output only patient-facing speech. Ask only one question."

    def _repair_response(self, context: dict) -> str:
        history = context['history']
        last_assistant = next(
            (m.get('content', '') for m in reversed(history) if m.get('role') == 'assistant'),
            '',
        )
        intent = context['task'].get('repair_intent')
        if intent in {'repeat', 'louder'} and last_assistant:
            return f"No problem, I'll repeat that. {last_assistant}"
        if intent == 'pause':
            return "No problem. We can pause for a moment. When you're ready, you can continue."
        return "No problem. Let's try that again. Please answer the last question when you're ready."

    def _sensitive_topic_instruction(self, category: str) -> str:
        if category in {'Housing', 'Food', 'Interpersonal Safety'}:
            return (
                f"Before the question, add one brief normalizing sentence about {category.lower()} challenges being common during treatment. "
            )
        return ''

    def _clean_spoken_response(self, text: str) -> str:
        lines = []
        for line in (text or '').splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if META_LINE_RE.match(stripped):
                continue
            lines.append(stripped)
        cleaned = ' '.join(lines)
        cleaned = re.sub(r'\s*RUNTIME TURN DIRECTIVE[^\n]*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\s*\([^)]*(?:note|rule|instruction|move on|response|topic|follow)[^)]*\)\s*",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        return re.sub(r'\s+', ' ', cleaned).strip()

    def _generate_summary(self, history: list, last_response: str) -> str:
        """Ask the LLM for a one-paragraph summary. Strip any preamble."""
        instruction = (
            "You are a clinical documentation assistant. "
            "Write a one-paragraph summary of the patient screening conversation above. "
            "Begin with the patient's name if they provided it. "
            "List the topics discussed (e.g. housing, food, transportation, financial "
            "strain, kidney disease burden, family support), what the patient said about "
            "each, and any concerns or positive notes. "
            "Start directly with the content — do NOT preface with 'Here is a summary', "
            "'I'll summarize', 'Sure', or anything similar. "
            "Do NOT end with a question or request for feedback."
        )
        # End with a user turn so the LLM responds as a summariser, not as the avatar.
        full_history = history + [
            {"role": "assistant", "content": last_response},
            {"role": "user", "content": "Please write a summary of our conversation for the care team."},
        ]
        raw = self.llm.generate(full_history, instruction)
        cleaned = SUMMARY_PREAMBLE_RE.sub('', raw or '', count=1)
        return cleaned.strip()

    def _is_goodbye(self, text: str, user_turn_count: int) -> bool:
        """Check if the response signals end of screening (with min-turn guard)."""
        if user_turn_count < MIN_TURNS_FOR_GOODBYE:
            return False
        text_lower = text.lower()
        end_phrases = [
            'it means a lot that you shared',
            'care team will have everything they need',
            'thank you for sharing that with me',
            'let me review your answers',
        ]
        return any(phrase in text_lower for phrase in end_phrases)

    def get_next_prompt(self, msg, info_state) -> dict:
        msg[MSG.PROMPT] = msg.get(MSG.RESPONSE, '')
        return msg


class ScreeningGoalManager:
    def __init__(self, llm_provider, system_prompt: str, first_time_prompt: str = '', subsequent_prompt: str = ''):
        self.goal = ScreeningGoal(llm_provider, system_prompt, first_time_prompt, subsequent_prompt)
        self.system_prompt = system_prompt
        self.first_time_prompt = first_time_prompt
        self.subsequent_prompt = subsequent_prompt

    def update(self, msg, info_state):
        if self.goal.is_complete(info_state):
            info_state.bel.add(BELSTR.DONE, True)
            return
        self.goal.execute_goal(msg, info_state)
        self.goal.get_next_prompt(msg, info_state)

    def get_opening(self, info_state, lang: str = 'en', avatar_name: str = 'Assistant', is_returning: bool = False) -> str:
        """Generate opening greeting using LLM."""
        prompt = self.goal._build_prompt(info_state, avatar_name, lang)
        existing = info_state.user.query('conversation_history') or []
        opening = self.goal._clean_spoken_response(self.goal.llm.generate(existing, prompt))
        existing.append({"role": "assistant", "content": opening})
        info_state.user.update('conversation_history', existing)

        phone_pin = info_state.user.query('patient_pin')
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

        return opening


DEFAULT_QUESTION_BLOCK = "\n".join([
    'Housing: "What is your living situation today? Do you have a steady place to live?"',
    'Food: "Within the past 12 months, have you worried that your food would run out before you got money to buy more?"',
    'Safety: "Do you feel physically and emotionally safe where you currently live?"',
    'Daily Living: "Do you need help with daily activities such as bathing, preparing meals, shopping, or managing medications?"',
])
