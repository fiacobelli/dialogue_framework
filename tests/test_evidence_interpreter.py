import json
import os
import tempfile
import unittest
from unittest.mock import patch

from information_state import InformationState
from strings import MSG
from web.evidence_interpreter import EvidenceInterpreter, empty_evidence_frame, validate_evidence_frame
from web.goal_interview import InterviewGoal
from web.interview_flow import build_interview_state
from web.nlu_web import NLUWeb


class JsonLLM:
    def __init__(self, payload=None):
        self.calls = 0
        self.payload = payload or {
            'schema_version': 1,
            'prompt_version': 'evidence-interpreter-v1',
            'input_quality': 'answer',
            'safety': {'crisis': False, 'confidence': 0.0},
            'current_step': {
                'step_id': 'personal_background',
                'status': 'sufficient',
                'summary': 'Patient says family matters.',
                'confidence': 0.9,
            },
            'future_evidence': [],
            'final_nothing_else': False,
            'already_answered_current': False,
        }

    def generate(self, messages, system_prompt=None):
        self.calls += 1
        return json.dumps(self.payload)


class EvidenceThenResponseLLM:
    def __init__(self):
        self.response_prompts = []

    def generate(self, messages, system_prompt=None):
        prompt = system_prompt or ''
        if 'bounded NLU evidence classifier' in prompt:
            return json.dumps({
                'schema_version': 1,
                'prompt_version': 'evidence-interpreter-v1',
                'input_quality': 'answer',
                'safety': {'crisis': False, 'confidence': 0.0},
                'current_step': {
                    'step_id': 'personal_background',
                    'status': 'sufficient',
                    'summary': 'Patient said their children and family keep them going.',
                    'confidence': 0.91,
                },
                'future_evidence': [],
                'final_nothing_else': False,
                'already_answered_current': False,
            })
        self.response_prompts.append(prompt)
        return (
            'I hear that your children and family are central to your story. '
            'When were you first diagnosed with kidney disease or kidney failure?'
        )


class EvidenceInterpreterTests(unittest.TestCase):
    def test_validate_evidence_frame_sanitizes_schema(self):
        frame = validate_evidence_frame({
            'schema_version': 1,
            'prompt_version': 'unit',
            'input_quality': 'answer',
            'safety': {'crisis': False, 'confidence': 2},
            'current_step': {'step_id': 'daily_life', 'status': 'sufficient', 'summary': 'x', 'confidence': 0.8},
            'future_evidence': [{'step_id': 'transplant_hope', 'status': 'thin', 'summary': 'hope', 'confidence': 0.5}],
            'final_nothing_else': False,
            'already_answered_current': False,
            'forbidden_action': 'move_to_photos',
        }, current_step_id='daily_life')

        self.assertTrue(frame['valid'])
        self.assertEqual(frame['safety']['confidence'], 1.0)
        self.assertNotIn('forbidden_action', frame)
        self.assertEqual(frame['future_evidence'][0]['step_id'], 'transplant_hope')

    def test_invalid_frame_raises(self):
        with self.assertRaises(ValueError):
            validate_evidence_frame({'schema_version': 999})

    def test_empty_evidence_frame_is_not_valid(self):
        frame = empty_evidence_frame('unit')

        self.assertFalse(frame['valid'])
        self.assertEqual(frame['fallback_reason'], 'unit')

    def test_interpreter_returns_valid_frame_from_llm_json(self):
        interpreter = EvidenceInterpreter(JsonLLM())
        frame = interpreter.interpret(
            'My family matters most.',
            {'id': 'personal_background'},
            build_interview_state(),
        )

        self.assertTrue(frame['valid'])
        self.assertEqual(frame['mode'], 'llm')
        self.assertEqual(frame['current_step']['status'], 'sufficient')


class NLUWebFrameTests(unittest.TestCase):
    def test_nlu_web_attaches_basic_nlu_frame(self):
        msg = {
            MSG.POSSIBLE_RESPONSES: [(1.0, 'My family matters.')],
            'turn_meta': {'input_modality': 'typed'},
        }

        self.assertTrue(NLUWeb().check(msg))

        self.assertEqual(msg[MSG.ORIG_TEXT], 'My family matters.')
        self.assertEqual(msg['nlu_frame']['source'], 'web_nlu')
        self.assertEqual(msg['nlu_frame']['turn_meta']['input_modality'], 'typed')


class EvidenceShadowModeTests(unittest.TestCase):
    def test_shadow_interpreter_does_not_change_transition_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            info_state = InformationState(os.path.join(tmp, 'user.pkl'), 'domains/interview.json')
            info_state.user.update('session_id', 'unit-shadow')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', {
                **build_interview_state(),
                'step_index': 0,
                'phase': 'STORY',
                'awaiting': 'main_answer',
                'patient_name': 'Sophia',
                'patient_name_status': 'confirmed',
                'current_outgoing_turn': {
                    'outgoing_turn_id': 'turn-1',
                    'asked_step_id': 'personal_background',
                    'asked_question_text': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
                    'expected_answer_kind': 'main_answer',
                    'delivered_phase': 'STORY',
                    'delivery_validated': True,
                    'task_type': 'ask_main',
                },
            })
            goal = InterviewGoal(JsonLLM(), 'You are {avatar_name}.')
            msg = {MSG.ORIG_TEXT: 'My family matters most and I am a teacher.'}

            with patch('web.goal_interview.INTERVIEW_EVIDENCE_SHADOW', True):
                goal.execute_goal(msg, info_state)

            self.assertIn('evidence_interpretation_shadow', msg)
            self.assertEqual(msg['interview_task']['type'], 'ack_then_next')
            self.assertEqual(info_state.user.query('interview_state')['last_step_id'], 'medical_history')

    def test_semantic_response_plan_adds_grounded_summary_to_nlg_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            info_state = InformationState(os.path.join(tmp, 'user.pkl'), 'domains/interview.json')
            info_state.user.update('session_id', 'unit-semantic-plan')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', {
                **build_interview_state(),
                'step_index': 0,
                'phase': 'STORY',
                'awaiting': 'main_answer',
                'patient_name': 'Sophia',
                'patient_name_status': 'confirmed',
                'current_outgoing_turn': {
                    'outgoing_turn_id': 'turn-1',
                    'asked_step_id': 'personal_background',
                    'asked_question_text': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
                    'expected_answer_kind': 'main_answer',
                    'delivered_phase': 'STORY',
                    'delivery_validated': True,
                    'task_type': 'ask_main',
                },
            })
            llm = EvidenceThenResponseLLM()
            goal = InterviewGoal(llm, 'You are {avatar_name}.')
            msg = {MSG.ORIG_TEXT: 'My kids and my family keep me going.'}

            with patch('web.goal_interview.INTERVIEW_EVIDENCE_SHADOW', True), \
                 patch('web.goal_interview.INTERVIEW_SEMANTIC_RESPONSE_PLAN', True):
                goal.execute_goal(msg, info_state)

            self.assertEqual(msg['interview_task']['type'], 'ack_then_next')
            self.assertEqual(
                msg['interview_task']['semantic_response_plan']['current_step_summary'],
                'Patient said their children and family keep them going.',
            )
            self.assertTrue(llm.response_prompts)
            self.assertIn('Use this grounded understanding of the patient answer', llm.response_prompts[-1])
            self.assertIn('Patient said their children and family keep them going.', llm.response_prompts[-1])
            self.assertEqual(info_state.user.query('interview_state')['last_step_id'], 'medical_history')


if __name__ == '__main__':
    unittest.main()
