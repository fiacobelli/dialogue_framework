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
from web.interview_flow_config import INTERVIEW_STEPS
from web.interview_prompts import build_outgoing_turn_contract, ensure_expected_question
from web.nlu_web import NLUWeb


class JsonLLM:
    def __init__(self, payload=None):
        self.calls = 0
        self.messages = []
        self.system_prompts = []
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
        self.messages.append(messages)
        self.system_prompts.append(system_prompt)
        return json.dumps(self.payload)


class EvidenceThenResponseLLM:
    def __init__(self):
        self.response_prompts = []

    def generate(self, messages, system_prompt=None):
        prompt = system_prompt or ''
        user_prompt = messages[-1].get('content', '') if messages else ''
        if 'bounded NLU evidence classifier' in prompt or 'bounded NLU evidence classifier' in user_prompt:
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


class MissingQuestionLLM:
    def generate(self, messages, system_prompt=None):
        user_prompt = messages[-1].get('content', '') if messages else ''
        if 'bounded NLU evidence classifier' in user_prompt:
            return json.dumps({
                'schema_version': 1,
                'prompt_version': 'evidence-interpreter-v1',
                'input_quality': 'answer',
                'safety': {'crisis': False, 'confidence': 0.0},
                'current_step': {
                    'step_id': 'donor_message',
                    'status': 'sufficient',
                    'summary': 'Patient said they are a hopeful person.',
                    'confidence': 0.88,
                },
                'future_evidence': [],
                'final_nothing_else': False,
                'already_answered_current': False,
            })
        return 'Your optimism is really shining through.'


class EvidenceInterpreterTests(unittest.TestCase):
    def test_validate_evidence_frame_sanitizes_schema(self):
        frame = validate_evidence_frame({
            'schema_version': 1,
            'prompt_version': 'unit',
            'input_quality': 'answer',
            'safety': {'crisis': False, 'confidence': 2},
            'current_step': {'step_id': 'daily_life', 'status': 'sufficient', 'summary': 'x', 'confidence': 0.8},
            'future_evidence': [{'step_id': 'transplant_hope', 'status': 'thin', 'summary': 'hope', 'confidence': 0.5}],
            'slots': {
                'public_name': 'John Snow',
                'public_name_confidence': 0.92,
                'readiness': 'ready',
                'readiness_confidence': 0.87,
            },
            'final_nothing_else': False,
            'already_answered_current': False,
            'forbidden_action': 'move_to_photos',
        }, current_step_id='daily_life')

        self.assertTrue(frame['valid'])
        self.assertEqual(frame['safety']['confidence'], 1.0)
        self.assertNotIn('forbidden_action', frame)
        self.assertEqual(frame['future_evidence'][0]['step_id'], 'transplant_hope')
        self.assertEqual(frame['slots']['public_name'], 'John Snow')
        self.assertEqual(frame['slots']['readiness'], 'ready')

    def test_invalid_frame_raises(self):
        with self.assertRaises(ValueError):
            validate_evidence_frame({'schema_version': 999})

    def test_empty_evidence_frame_is_not_valid(self):
        frame = empty_evidence_frame('unit')

        self.assertFalse(frame['valid'])
        self.assertEqual(frame['fallback_reason'], 'unit')

    def test_interpreter_returns_valid_frame_from_llm_json(self):
        llm = JsonLLM()
        interpreter = EvidenceInterpreter(llm)
        frame = interpreter.interpret(
            'My family matters most.',
            {'id': 'personal_background'},
            build_interview_state(),
        )

        self.assertTrue(frame['valid'])
        self.assertEqual(frame['mode'], 'llm')
        self.assertEqual(frame['current_step']['status'], 'sufficient')
        self.assertIn('bounded NLU evidence classifier', llm.messages[-1][-1]['content'])
        self.assertIn('Return only valid JSON', llm.system_prompts[-1])


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
            llm = JsonLLM()
            goal = InterviewGoal(llm, 'You are {avatar_name}.')
            msg = {MSG.POSSIBLE_RESPONSES: [(1.0, 'My family matters most and I am a teacher.')]}

            with patch('web.nlu_web.INTERVIEW_EVIDENCE_SHADOW', True):
                self.assertTrue(NLUWeb(info_state, llm).check(msg))
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
            msg = {MSG.POSSIBLE_RESPONSES: [(1.0, 'My kids and my family keep me going.')]}

            with patch('web.nlu_web.INTERVIEW_EVIDENCE_SHADOW', True), \
                 patch('web.goal_interview.INTERVIEW_SEMANTIC_RESPONSE_PLAN', True):
                self.assertTrue(NLUWeb(info_state, llm).check(msg))
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

    def test_missing_required_question_is_appended_after_semantic_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            info_state = InformationState(os.path.join(tmp, 'user.pkl'), 'domains/interview.json')
            info_state.user.update('session_id', 'unit-question-contract')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', {
                **build_interview_state(),
                'step_index': 4,
                'phase': 'STORY',
                'awaiting': 'main_answer',
                'patient_name': 'Sophia',
                'patient_name_status': 'confirmed',
                'current_outgoing_turn': {
                    'outgoing_turn_id': 'turn-1',
                    'asked_step_id': 'donor_message',
                    'asked_question_text': 'What would you want a potential donor to know about you as a person?',
                    'expected_answer_kind': 'main_answer',
                    'delivered_phase': 'STORY',
                    'delivery_validated': True,
                    'task_type': 'ask_main',
                },
            })
            llm = MissingQuestionLLM()
            goal = InterviewGoal(llm, 'You are {avatar_name}.')
            msg = {MSG.POSSIBLE_RESPONSES: [(1.0, 'I am a hopeful person.')]}

            with patch('web.nlu_web.INTERVIEW_EVIDENCE_SHADOW', True), \
                 patch('web.goal_interview.INTERVIEW_SEMANTIC_RESPONSE_PLAN', True):
                self.assertTrue(NLUWeb(info_state, llm).check(msg))
                goal.execute_goal(msg, info_state)

            expected = 'Do you have family, friends, or a community supporting you through this?'
            self.assertEqual(msg['interview_task']['type'], 'ack_then_next')
            self.assertIn('Your optimism is really shining through.', msg[MSG.RESPONSE])
            self.assertIn(expected, msg[MSG.RESPONSE])
            self.assertTrue(msg['interview_context']['outgoing_turn']['delivery_validated'])

    def test_name_turn_uses_existing_nlu_slot(self):
        payload = {
            'schema_version': 1,
            'prompt_version': 'evidence-interpreter-v1',
            'input_quality': 'answer',
            'safety': {'crisis': False, 'confidence': 0.0},
            'current_step': {'step_id': None, 'status': 'not_addressed', 'summary': '', 'confidence': 0.0},
            'future_evidence': [],
            'slots': {'public_name': 'John Snow', 'public_name_confidence': 0.94},
            'final_nothing_else': False,
            'already_answered_current': False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            info_state = InformationState(os.path.join(tmp, 'user.pkl'), 'domains/interview.json')
            info_state.user.update('session_id', 'unit-name-slot')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', build_interview_state())
            llm = JsonLLM(payload)
            goal = InterviewGoal(llm, 'You are {avatar_name}.')
            msg = {MSG.POSSIBLE_RESPONSES: [(1.0, 'John Snow is my name.')]}

            with patch('web.nlu_web.INTERVIEW_EVIDENCE_SHADOW', True):
                self.assertTrue(NLUWeb(info_state, llm).check(msg))
                goal.execute_goal(msg, info_state)

            state = info_state.user.query('interview_state')
            self.assertEqual(msg['interview_task']['type'], 'ask_readiness')
            self.assertEqual(state['patient_name'], 'John Snow')
            self.assertEqual(state['last_decision']['name']['reason'], 'nlu_slot')


class ResponseContractTests(unittest.TestCase):
    def test_extra_llm_question_is_removed_before_required_question(self):
        task = {'type': 'ack_then_next', 'step': INTERVIEW_STEPS[1], 'phase': 'STORY'}
        response = (
            'Your family sounds close to you. '
            'You mentioned being a student; are they supporting you through school as well?'
        )

        fixed = ensure_expected_question(response, task)

        self.assertEqual(
            fixed,
            'Your family sounds close to you. When were you first diagnosed with kidney disease or kidney failure?',
        )

    def test_case_insensitive_existing_question_is_not_duplicated(self):
        task = {'type': 'ack_then_next', 'step': INTERVIEW_STEPS[5], 'phase': 'STORY'}
        response = (
            'Your positivity is inspiring. I think you mentioned your family is supporting you; '
            'do you have family, friends, or a community supporting you through this?'
        )

        fixed = ensure_expected_question(response, task)
        contract = build_outgoing_turn_contract(task, {}, fixed, 'turn-1')

        self.assertEqual(fixed.count('supporting you through this'), 1)
        self.assertTrue(contract['delivery_validated'])

    def test_extra_question_is_removed_even_when_required_question_is_present(self):
        task = {'type': 'ack_then_next', 'step': INTERVIEW_STEPS[1], 'phase': 'STORY'}
        response = (
            'Your family sounds close to you. '
            'Are they supporting you through school as well? '
            'When were you first diagnosed with kidney disease or kidney failure?'
        )

        fixed = ensure_expected_question(response, task)

        self.assertNotIn('supporting you through school', fixed)
        self.assertEqual(fixed.count('?'), 1)
        self.assertTrue(fixed.endswith('When were you first diagnosed with kidney disease or kidney failure?'))


if __name__ == '__main__':
    unittest.main()
