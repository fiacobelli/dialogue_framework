"""A Spanish session hears Spanish scripted text; English sessions are unchanged.

Offline and deterministic: no server, no network, fake LLM.
"""

import json
import os
import tempfile
import unittest

from information_state import InformationState
from strings import MSG
from web.config import AVATAR_PROFILES, avatar_profile_for
from web.goal_interview import InterviewGoal, InterviewGoalManager
from web.i18n import CATALOG, tr
from web.interview_flow_config import INTERVIEW_STEPS
from web.interview_state import _crisis_detected, normalize_answer


class _PayloadLLM:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, messages, system_prompt=None, **kwargs):
        self.prompts.append(system_prompt or '')
        return json.dumps(self.payload)


def _run_turn(lang, state, payload, text):
    with tempfile.TemporaryDirectory() as tmp:
        info_state = InformationState(os.path.join(tmp, 'user.pkl'), 'domains/interview.json')
        info_state.user.update('session_id', 'lang-test')
        info_state.user.update('language', lang)
        info_state.user.update('avatar_profile', {'name': 'Ludi'})
        info_state.user.update('conversation_history', [{'role': 'assistant', 'content': 'prev'}])
        info_state.user.update('interview_state', state)
        llm = _PayloadLLM(payload)
        msg = {MSG.ORIG_TEXT: text, 'turn_meta': {}}
        InterviewGoal(llm, 'You are {avatar_name}.').execute_goal(msg, info_state)
        return msg[MSG.RESPONSE], info_state.user.query('interview_state'), llm


def _readiness_state():
    return {'step_index': 0, 'phase': 'INTRO', 'awaiting': 'readiness', 'patient_name': 'Rosa',
            'followup_count': 0, 'story_evidence': {}, 'current_outgoing_turn': {}}


class SpanishSessionTests(unittest.TestCase):
    def test_opening_is_spanish(self):
        with tempfile.TemporaryDirectory() as tmp:
            info_state = InformationState(os.path.join(tmp, 'user.pkl'), 'domains/interview.json')
            opening = InterviewGoalManager(None, '').get_opening(info_state, 'es', 'Ludi')
        self.assertTrue(opening.startswith('Hola, soy Ludi.'))

    def test_si_starts_first_question_in_spanish(self):
        reply, state, llm = _run_turn('es', _readiness_state(), {'reply': 'unused'}, 'Sí, estoy lista')
        self.assertEqual(state['awaiting'], 'main_answer')
        self.assertEqual(reply, tr(INTERVIEW_STEPS[0]['question'], 'es'))
        self.assertEqual(llm.prompts, [])
        # Research analytics keep the English canonical question.
        self.assertEqual(state['current_outgoing_turn']['asked_question_text'], INTERVIEW_STEPS[0]['question'])

    def test_todavia_no_waits(self):
        reply, state, _llm = _run_turn('es', _readiness_state(), {'reply': 'unused'}, 'Todavía no')
        self.assertEqual(state['awaiting'], 'readiness')
        self.assertTrue(reply.startswith('No hay problema.'))

    def test_spanish_session_prompt_names_language(self):
        state = {**_readiness_state(), 'phase': 'STORY', 'awaiting': 'main_answer', 'step_index': 1}
        _reply, _state, llm = _run_turn('es', state, {'reply': 'Gracias por contarme.'}, 'En el 2019.')
        self.assertIn('Respond entirely in Spanish', llm.prompts[0])

    def test_english_session_unchanged(self):
        reply, _state, _llm = _run_turn('en', _readiness_state(), {'reply': 'unused'}, 'Yes')
        self.assertEqual(reply, INTERVIEW_STEPS[0]['question'])

    def test_accents_and_spanish_crisis(self):
        self.assertEqual(normalize_answer('Sí'), 'si')
        self.assertEqual(normalize_answer("I'm ready"), "i'm ready")
        self.assertTrue(_crisis_detected('A veces quiero morirme'))

    def test_every_question_and_avatar_has_spanish(self):
        for step in INTERVIEW_STEPS:
            self.assertIn(step['question'], CATALOG['es'])
        for avatar_id in AVATAR_PROFILES:
            profile = avatar_profile_for(avatar_id, 'es')
            self.assertEqual((profile['lang'], profile['language']), ('es', 2))


if __name__ == '__main__':
    unittest.main()
