import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from information_state import InformationState
from strings import MSG
from web.app import app
from web.goal_interview import InterviewGoal
from web.interview_flow import (
    FINAL_PHOTOS_PROMPT,
    build_outgoing_turn_contract,
    build_interview_state,
    decide_next_task,
    deterministic_response,
    extract_patient_name,
    input_guard_decision,
    progress_snapshot,
    sufficiency_decision,
)
from web import microsite
from web import database as db
from web import routes_photos
from web import routes_admin
from web import session as session_module
from web import session_store
from web.routes_api import (
    PUBLICATION_CONSENT_VERSION,
    validate_generation_ready,
    validate_publication_consent,
)


class InterviewFlowTests(unittest.TestCase):
    def test_incomplete_name_is_not_captured(self):
        result = extract_patient_name('hi my name is')
        self.assertIsNone(result['name'])
        self.assertEqual(result['reason'], 'incomplete_marker')

    def test_clear_name_moves_to_readiness(self):
        state = build_interview_state()
        task = decide_next_task(state, 'my name is Sophia')

        self.assertEqual(task['type'], 'ask_readiness')
        self.assertEqual(state['patient_name'], 'Sophia')
        self.assertEqual(state['patient_name_status'], 'confirmed')
        self.assertEqual(state['awaiting'], 'readiness')

    def test_readiness_yes_starts_first_story_question(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        task = decide_next_task(state, 'yes I am ready')

        self.assertEqual(task['type'], 'ask_main')
        self.assertEqual(task['step']['id'], 'personal_background')
        self.assertEqual(state['awaiting'], 'main_answer')

    def test_readiness_not_ready_does_not_start_story(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        task = decide_next_task(state, 'not ready')

        self.assertEqual(task['type'], 'ask_readiness')
        self.assertEqual(state['awaiting'], 'readiness')
        self.assertEqual(state['phase'], 'INTRO')

    def test_acknowledgement_only_story_answer_repairs_without_advancing(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        task = decide_next_task(state, 'okay')

        self.assertEqual(task['type'], 'repair_answer')
        self.assertEqual(task['step']['id'], 'personal_background')
        self.assertEqual(state['step_index'], 0)
        self.assertEqual(state['awaiting'], 'main_answer')

    def test_detailed_but_insufficient_answer_triggers_same_topic_followup(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        task = decide_next_task(state, 'I like my family')

        self.assertEqual(task['type'], 'ask_followup')
        self.assertEqual(task['step']['id'], 'personal_background')
        self.assertEqual(state['step_index'], 0)
        self.assertEqual(state['awaiting'], 'followup_answer')

    def test_structured_evaluator_can_accept_meaningful_answer_without_keywords(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        def evaluator(step, answer, heuristic):
            return {
                'evidence_present': True,
                'missing_detail': '',
                'safe_to_advance': True,
                'suggested_followup': '',
            }

        task = decide_next_task(
            state,
            'I restore old cars with my nephews every weekend',
            answer_evaluator=evaluator,
        )

        self.assertEqual(task['type'], 'ack_then_next')
        self.assertEqual(task['step']['id'], 'medical_history')
        decision = state['story_evidence']['personal_background'][-1]['sufficiency']
        self.assertEqual(decision['reason'], 'structured_evaluator')

    def test_structured_evaluator_can_supply_grounded_followup(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        def evaluator(step, answer, heuristic):
            return {
                'evidence_present': False,
                'missing_detail': 'needs concrete meaning',
                'safe_to_advance': False,
                'suggested_followup': 'When you say peace, what would feel different in your day?',
            }

        task = decide_next_task(state, 'I want peace', answer_evaluator=evaluator)
        response = deterministic_response(task, state)

        self.assertEqual(task['type'], 'ask_followup')
        self.assertIn('When you say peace', response)

    def test_sufficient_answer_can_trigger_bounded_story_deepening(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        def planner(step, answer, current_state):
            return {
                'should_deepen': True,
                'reason': 'children are central to identity',
                'evidence_quote': 'family friends kids',
                'followup_question': 'You mentioned your kids; what would you want people to understand about your kids?',
            }

        task = decide_next_task(state, 'yes my family my friends my kids', deepening_decider=planner)
        response = deterministic_response(task, state)

        self.assertEqual(task['type'], 'ask_deepening')
        self.assertEqual(state['awaiting'], 'followup_answer')
        self.assertEqual(state['last_followup_kind'], 'deepening')
        self.assertIn('your kids', response)

    def test_deepening_followup_answer_then_advances_to_next_story_section(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        decide_next_task(
            state,
            'yes my family my friends my kids',
            deepening_decider=lambda *_: {
                'should_deepen': True,
                'reason': 'children are central to identity',
                'evidence_quote': 'kids',
                'followup_question': 'You mentioned your kids; what would you want people to understand about your kids?',
            },
        )

        task = decide_next_task(state, 'I try to be present for my kids and support them every day')

        self.assertEqual(task['type'], 'ack_then_next')
        self.assertEqual(task['step']['id'], 'medical_history')
        self.assertEqual(state['awaiting'], 'main_answer')
        evidence = state['story_evidence']['personal_background']
        self.assertEqual(evidence[-1]['answer_kind'], 'followup_answer')
        self.assertEqual(evidence[-1]['followup_kind'], 'deepening')

    def test_invalid_deepening_planner_output_is_ignored(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        task = decide_next_task(
            state,
            'yes my family my friends my kids',
            deepening_decider=lambda *_: {
                'should_deepen': True,
                'reason': 'invented',
                'evidence_quote': 'marathon runner',
                'followup_question': 'How did running marathons shape your life?',
            },
        )

        self.assertEqual(task['type'], 'ack_then_next')
        self.assertEqual(task['step']['id'], 'medical_history')
        self.assertNotEqual(state.get('last_followup_kind'), 'deepening')

    def test_broad_dialysis_answer_is_not_sufficient_daily_life(self):
        step = {'id': 'daily_life'}
        decision = sufficiency_decision(step, 'most of the time treatments dialysis treatment')

        self.assertFalse(decision['sufficient'])
        self.assertEqual(decision['reason'], 'broad_treatment_only')

    def test_final_details_no_nothing_really_closes(self):
        state = build_interview_state()
        state.update({
            'step_index': 6,
            'phase': 'FINAL_DETAILS',
            'awaiting': 'main_answer',
            'patient_name': 'Sophia',
            'patient_name_status': 'confirmed',
        })

        task = decide_next_task(state, 'No, nothing really.')

        self.assertEqual(task['type'], 'close_to_photos')
        self.assertTrue(state['complete'])

    def test_final_details_no_thank_you_closes(self):
        state = build_interview_state()
        state.update({
            'step_index': 6,
            'phase': 'FINAL_DETAILS',
            'awaiting': 'main_answer',
            'patient_name': 'Sophia',
            'patient_name_status': 'confirmed',
        })

        task = decide_next_task(state, 'No, thank you.')

        self.assertEqual(task['type'], 'close_to_photos')
        self.assertTrue(state['complete'])

    def test_skip_story_question_records_skip_and_advances(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        task = decide_next_task(state, '[skip]', {'skip_requested': True})
        response = deterministic_response(task, state)

        self.assertEqual(task['type'], 'skip_then_next')
        self.assertEqual(task['step']['id'], 'medical_history')
        self.assertEqual(state['awaiting'], 'main_answer')
        self.assertEqual(state['skipped_steps']['personal_background']['reason'], 'patient_requested_skip')
        self.assertIn('No problem, we can skip that.', response)

    def test_skip_final_details_closes_to_photos(self):
        state = build_interview_state()
        state.update({
            'step_index': 6,
            'phase': 'FINAL_DETAILS',
            'awaiting': 'main_answer',
            'patient_name': 'Sophia',
            'patient_name_status': 'confirmed',
        })

        task = decide_next_task(state, 'skip this question')

        self.assertEqual(task['type'], 'skip_to_photos')
        self.assertTrue(state['complete'])
        self.assertIn('final_details', state['skipped_steps'])

    def test_operational_complaint_repairs_without_advancing(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        decide_next_task(state, 'My family matters most and I am a teacher in my community')

        task = decide_next_task(state, "It has trouble picking stuff up. It needs more time to pick stuff up.")

        self.assertEqual(task['type'], 'repair_answer')
        self.assertEqual(task['decision']['reason'], 'operational_issue')
        self.assertEqual(state['last_step_id'], 'medical_history')
        self.assertNotIn('medical_history', state.get('story_evidence', {}))

    def test_long_operational_answer_is_not_sufficient_daily_life(self):
        guard = input_guard_decision(
            {'id': 'daily_life'},
            "It's hard. It has trouble picking stuff up. It needs more time to pick stuff up.",
        )

        self.assertTrue(guard['repair'])
        self.assertEqual(guard['reason'], 'operational_issue')

    def test_no_response_repairs_same_question(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        task = decide_next_task(state, '[no speech detected]', {'no_response': True})
        response = deterministic_response(task, state)

        self.assertEqual(task['type'], 'repair_answer')
        self.assertEqual(task['decision']['reason'], 'empty_or_no_response')
        self.assertIn(task['step']['question'], response)
        self.assertEqual(state['step_index'], 0)

    def test_old_story_answer_state_normalizes(self):
        state = {
            'step_index': 1,
            'phase': 'BEFORE',
            'awaiting': 'story_answer',
            'complete': False,
        }
        task = decide_next_task(state, '2 years ago')

        self.assertIn(task['type'], {'ack_then_next', 'ask_followup'})
        self.assertNotEqual(state['awaiting'], 'story_answer')
        self.assertEqual(state['version'], 2)

    def test_active_story_turn_contains_exact_canonical_question(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        task = decide_next_task(state, 'yes')
        response = deterministic_response(task, state)

        self.assertIn(task['step']['question'], response)
        self.assertEqual(response.count(task['step']['question']), 1)

    def test_outgoing_turn_contract_records_delivered_question(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        task = decide_next_task(state, 'yes')
        response = deterministic_response(task, state)
        contract = build_outgoing_turn_contract(task, state, response, 'turn-1')

        self.assertEqual(contract['outgoing_turn_id'], 'turn-1')
        self.assertEqual(contract['asked_step_id'], 'personal_background')
        self.assertEqual(contract['asked_question_text'], task['step']['question'])
        self.assertEqual(contract['expected_answer_kind'], 'main_answer')
        self.assertTrue(contract['delivery_validated'])

    def test_story_evidence_tracks_only_accepted_answers(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        decide_next_task(state, 'My family matters most and I am a teacher in my community')

        evidence = state['story_evidence']['personal_background']
        self.assertIsInstance(evidence, list)
        self.assertTrue(evidence[-1]['accepted'])

    def test_progress_snapshot_reports_story_step(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')

        progress = progress_snapshot(state, 'STORY')

        self.assertEqual(progress['label'], 'Story interview')
        self.assertEqual(progress['current_step'], 1)
        self.assertEqual(progress['total_steps'], 7)
        self.assertEqual(progress['current_step_id'], 'personal_background')


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, messages, system_prompt=None):
        self.calls += 1
        return 'How would receiving a kidney transplant change your life?'


class FakeMicrositeLLM:
    model = 'fake-microsite-model'

    def generate(self, messages, system_prompt=None):
        return """{
            "headline": "Sophia is looking for a kidney donor",
            "short_intro": "Sophia is sharing her story while looking for a living kidney donor.",
            "personal_identity": "Sophia enjoys time with family.",
            "kidney_journey": "Sophia shared that dialysis is part of her kidney journey.",
            "daily_impact": "Dialysis has made daily life difficult.",
            "transplant_hope": "A transplant would help Sophia regain energy.",
            "donor_message": "Sophia wants potential donors to know that their help would matter."
        }"""


class FakeDeepeningPlannerLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, messages, system_prompt=None):
        self.calls += 1
        return """{
            "should_deepen": true,
            "reason": "children are central to identity",
            "evidence_quote": "kids",
            "followup_question": "You mentioned your kids; what would you want people to understand about your kids?"
        }"""


class InterviewGoalTests(unittest.TestCase):
    def test_active_story_question_is_deterministic_and_does_not_call_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_file = os.path.join(tmp, 'user.pkl')
            info_state = InformationState(user_file, 'domains/interview.json')
            info_state.user.update('session_id', 'unit-active')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', {
                'version': 2,
                'step_index': 0,
                'phase': 'INTRO',
                'awaiting': 'readiness',
                'followup_count': 0,
                'repair_count': 0,
                'last_task': 'ask_readiness',
                'last_step_id': None,
                'complete': False,
                'story_evidence': {},
                'thin_evidence': {},
                'patient_name': 'Sophia',
                'patient_name_status': 'confirmed',
                'patient_name_source': 'user_explicit',
                'last_decision': None,
                'current_outgoing_turn': {
                    'outgoing_turn_id': 'opening-turn',
                    'expected_answer_kind': 'readiness',
                    'asked_question_text': 'Are you ready to begin?',
                    'delivery_validated': True,
                },
            })

            fake = FakeLLM()
            goal = InterviewGoal(fake, 'You are {avatar_name}.')
            msg = {MSG.ORIG_TEXT: 'yes'}

            goal.execute_goal(msg, info_state)

            self.assertEqual(fake.calls, 0)
            self.assertIn('Can you tell me a little about yourself', msg[MSG.RESPONSE])
            context = msg['interview_context']
            self.assertEqual(context['answered_outgoing_turn_id'], 'opening-turn')
            self.assertTrue(context['outgoing_turn']['delivery_validated'])

    def test_final_close_is_deterministic_and_does_not_use_llm_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_file = os.path.join(tmp, 'user.pkl')
            info_state = InformationState(user_file, 'domains/interview.json')
            info_state.user.update('session_id', 'unit-final')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', {
                'version': 2,
                'step_index': 6,
                'phase': 'FINAL_DETAILS',
                'awaiting': 'main_answer',
                'followup_count': 0,
                'repair_count': 0,
                'last_task': 'ask_final',
                'last_step_id': 'final_details',
                'complete': False,
                'story_evidence': {},
                'thin_evidence': {},
                'patient_name': 'Sophia',
                'patient_name_status': 'confirmed',
                'patient_name_source': 'user_explicit',
                'last_decision': None,
            })

            fake = FakeLLM()
            goal = InterviewGoal(fake, 'You are {avatar_name}.')
            msg = {MSG.ORIG_TEXT: 'nothing else'}

            goal.execute_goal(msg, info_state)

            self.assertEqual(fake.calls, 0)
            self.assertEqual(msg[MSG.RESPONSE], FINAL_PHOTOS_PROMPT)
            self.assertEqual(info_state.user.query('interview_phase'), 'PHOTOS')

    def test_interview_goal_uses_planner_for_story_deepening(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_file = os.path.join(tmp, 'user.pkl')
            info_state = InformationState(user_file, 'domains/interview.json')
            info_state.user.update('session_id', 'unit-deepening')
            info_state.user.update('avatar_profile', {'name': 'Ludi'})
            info_state.user.update('interview_state', {
                'version': 2,
                'step_index': 0,
                'phase': 'STORY',
                'awaiting': 'main_answer',
                'followup_count': 0,
                'repair_count': 0,
                'last_task': 'ask_main',
                'last_step_id': 'personal_background',
                'complete': False,
                'story_evidence': {},
                'thin_evidence': {},
                'patient_name': 'Sophia',
                'patient_name_status': 'confirmed',
                'patient_name_source': 'user_explicit',
                'last_decision': None,
                'current_outgoing_turn': {
                    'outgoing_turn_id': 'story-turn',
                    'asked_step_id': 'personal_background',
                    'asked_question_text': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
                    'expected_answer_kind': 'main_answer',
                    'delivered_phase': 'STORY',
                    'delivery_validated': True,
                    'task_type': 'ask_main',
                },
            })

            fake = FakeDeepeningPlannerLLM()
            goal = InterviewGoal(fake, 'You are {avatar_name}.')
            msg = {MSG.ORIG_TEXT: 'yes my family my friends my kids'}

            goal.execute_goal(msg, info_state)

            state = info_state.user.query('interview_state')
            self.assertEqual(fake.calls, 1)
            self.assertEqual(msg['interview_task']['type'], 'ask_deepening')
            self.assertEqual(state['awaiting'], 'followup_answer')
            self.assertIn('your kids', msg[MSG.RESPONSE])


class GenerationGateTests(unittest.TestCase):
    def _info_state(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return InformationState(os.path.join(tmp.name, 'user.pkl'), 'domains/interview.json')

    def _accepted_evidence(self):
        return {
            'personal_background': [{'answer': 'I am Sophia and my family matters most.', 'accepted': True}],
            'daily_life': [{'answer': 'Dialysis makes me tired and limits my schedule.', 'accepted': True}],
            'transplant_hope': [{'answer': 'A transplant would help me have more energy.', 'accepted': True}],
            'donor_message': [{'answer': 'I want donors to know their help would matter.', 'accepted': True}],
        }

    def test_generation_blocked_when_story_incomplete(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'STORY')
        info_state.user.update('interview_state', {'complete': False, 'story_evidence': self._accepted_evidence()})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertFalse(ready)
        self.assertIn('story_complete', detail['missing'])

    def test_generation_blocked_without_confirmed_name(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True, 'story_evidence': self._accepted_evidence()})
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertFalse(ready)
        self.assertIn('confirmed_name', detail['missing'])

    def test_generation_allowed_when_story_name_and_photos_ready(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True, 'story_evidence': self._accepted_evidence()})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertTrue(ready)
        self.assertEqual(detail['name'], 'Sophia')

    def test_generation_blocked_with_partial_photos_without_confirmation(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True, 'story_evidence': self._accepted_evidence()})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertFalse(ready)
        self.assertIn('photos', detail['missing'])
        self.assertTrue(detail['partial_photos_allowed'])

    def test_generation_allowed_with_partial_photo_confirmation(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True, 'story_evidence': self._accepted_evidence()})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg'])

        ready, detail = validate_generation_ready(info_state, allow_partial_photos=True)

        self.assertTrue(ready)
        self.assertEqual(detail['photo_requirement_status'], 'partial_confirmed')

    def test_generation_blocked_when_story_evidence_is_too_thin(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True, 'story_evidence': {}})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertFalse(ready)
        self.assertIn('story_evidence', detail['missing'])
        self.assertIn('identity', detail['missing_story_sections'])

    def test_generation_allowed_when_required_section_was_skipped(self):
        info_state = self._info_state()
        evidence = self._accepted_evidence()
        evidence.pop('donor_message')
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {
            'complete': True,
            'story_evidence': evidence,
            'skipped_steps': {
                'donor_message': {
                    'reason': 'patient_requested_skip',
                    'question': 'What would you want a potential donor to know about you as a person?',
                }
            },
        })
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertTrue(ready)
        self.assertEqual(detail['name'], 'Sophia')


class PublicationConsentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, 'test.db')
        db.configure(self.db_path)
        db.init_db()

    def _info_state_with_visit(self):
        info_state = InformationState(os.path.join(self.tmp.name, 'user.pkl'), 'domains/interview.json')
        visit_id = db.create_visit('consent-session', 'en', 'black_female', {'name': 'Ludi'})
        info_state.user.update('visit_id', visit_id)
        return info_state, visit_id

    def test_publication_consent_required(self):
        info_state, _ = self._info_state_with_visit()

        ready, detail = validate_publication_consent(info_state, {})

        self.assertFalse(ready)
        self.assertEqual(detail['error'], 'publication_consent_required')

    def test_publication_consent_saved_when_accepted(self):
        info_state, visit_id = self._info_state_with_visit()

        ready, detail = validate_publication_consent(
            info_state,
            {'publication_consent': {'accepted': True, 'version': PUBLICATION_CONSENT_VERSION}},
            user_agent='unit-test',
        )

        self.assertTrue(ready)
        self.assertEqual(detail['consent_version'], PUBLICATION_CONSENT_VERSION)
        self.assertTrue(db.has_consent(visit_id, 'publication', PUBLICATION_CONSENT_VERSION))


class PublicationControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, 'test.db')
        db.configure(self.db_path)
        db.init_db()

    def _result(self):
        return {
            'name': 'Sophia',
            'headline': 'Sophia is sharing her kidney donor story',
            'short_intro': 'Sophia is sharing her story.',
            'personal_identity': 'Sophia values her family.',
            'kidney_journey': 'Sophia is living with kidney disease.',
            'daily_impact': 'Dialysis affects her schedule.',
            'transplant_hope': 'A transplant could help her regain energy.',
            'donor_message': 'Sophia wants potential donors to know their help matters.',
            'my_story': 'Sophia values her family.',
            'my_struggle': 'Dialysis affects her schedule.',
            'my_hope': 'A transplant could help her regain energy.',
            'content': '{}',
            'microsite_url': '/site/published-session',
            'microsite_absolute_url': 'https://example.test/site/published-session',
        }

    def test_publication_status_controls_page_and_photos(self):
        visit_id = db.create_visit('published-session', 'en', 'black_female', {'name': 'Ludi'})
        db.save_photo(visit_id, 'published-session_0.jpg', 0)

        self.assertFalse(db.is_microsite_published('published-session'))
        self.assertFalse(db.is_photo_public('published-session_0.jpg'))

        db.save_draft(visit_id, self._result(), status='published')

        self.assertTrue(db.is_microsite_published('published-session'))
        self.assertTrue(db.is_photo_public('published-session_0.jpg'))

        self.assertTrue(db.unpublish_session('published-session'))
        self.assertFalse(db.is_microsite_published('published-session'))
        self.assertFalse(db.is_photo_public('published-session_0.jpg'))

    def test_admin_visit_detail_includes_session_artifacts_and_audit_events(self):
        visit_id = db.create_visit('published-session', 'en', 'black_female', {'name': 'Ludi'})
        db.save_message(visit_id, 'user', 'My family is important to me.', turn_number=1, phase='STORY')
        db.save_photo(visit_id, 'published-session_0.jpg', 0, byte_size=42)
        db.save_draft(visit_id, self._result(), status='published')

        self.assertTrue(db.unpublish_session('published-session', reason='admin_review', actor='admin'))

        visits = db.list_admin_visits()
        detail = db.get_admin_visit('published-session')

        self.assertEqual(visits[0]['session_id'], 'published-session')
        self.assertEqual(detail['visit']['publication_status'], 'unpublished')
        self.assertEqual(detail['messages'][0]['content'], 'My family is important to me.')
        self.assertEqual(detail['photos'][0]['stored_filename'], 'published-session_0.jpg')
        self.assertEqual(detail['drafts'][0]['status'], 'unpublished')
        self.assertEqual(detail['audit_events'][0]['action'], 'unpublish')
        self.assertEqual(detail['audit_events'][0]['actor'], 'admin')
        self.assertEqual(detail['audit_events'][0]['reason'], 'admin_review')

    def test_admin_routes_require_login_and_can_unpublish(self):
        visit_id = db.create_visit('published-session', 'en', 'black_female', {'name': 'Ludi'})
        db.save_draft(visit_id, self._result(), status='published')

        with patch.object(routes_admin, 'ADMIN_USERNAME', 'admin'):
            with patch.object(routes_admin, 'ADMIN_PASSWORD', 'secret'):
                with app.test_client() as client:
                    protected = client.get('/admin/')
                    self.assertEqual(protected.status_code, 302)
                    self.assertIn('/admin/login', protected.headers['Location'])

                    login = client.post(
                        '/admin/login',
                        data={'username': 'admin', 'password': 'secret'},
                        follow_redirects=False,
                    )
                    self.assertEqual(login.status_code, 302)

                    listing = client.get('/admin/')
                    self.assertEqual(listing.status_code, 200)
                    self.assertIn(b'published-session', listing.data)

                    detail = client.get('/admin/session/published-session')
                    self.assertEqual(detail.status_code, 200)
                    self.assertIn(b'Unpublish Page', detail.data)

                    unpublish = client.post(
                        '/admin/session/published-session/unpublish',
                        data={'reason': 'supervisor_review'},
                        follow_redirects=False,
                    )
                    self.assertEqual(unpublish.status_code, 302)

        detail = db.get_admin_visit('published-session')
        self.assertEqual(detail['visit']['publication_status'], 'unpublished')
        self.assertEqual(detail['audit_events'][0]['actor'], 'admin')
        self.assertEqual(detail['audit_events'][0]['reason'], 'supervisor_review')


class ClientDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, 'test.db')
        db.configure(self.db_path)
        db.init_db()

    def test_client_events_endpoint_saves_microphone_preflight_diagnostics(self):
        with app.test_client() as client:
            session_response = client.get('/api/session?lang=en&avatar=black_female')
            self.assertEqual(session_response.status_code, 200)
            session_id = session_response.get_json()['session_id']

            event_response = client.post('/api/client-events', json={
                'session_id': session_id,
                'events': [{
                    'type': 'mic_preflight_result',
                    'ts': 1234,
                    'metadata': {
                        'status': 'ready',
                        'permission_state': 'granted',
                        'audioinput_count': 2,
                        'device_labels_available': True,
                        'active_track_label': 'Bluetooth Headset',
                        'bluetooth_input_detected': True,
                        'unapproved_field': 'ignored',
                    }
                }]
            })

            self.assertEqual(event_response.status_code, 200)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        row = conn.execute("SELECT * FROM turn_events WHERE event_type = 'mic_preflight_result'").fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row['client_ts_ms'], 1234)
        self.assertIn('"status": "ready"', row['metadata_json'])
        self.assertIn('"active_track_label": "Bluetooth Headset"', row['metadata_json'])
        self.assertNotIn('unapproved_field', row['metadata_json'])

        detail = db.get_admin_visit(session_id)
        self.assertEqual(detail['turn_events'][0]['event_type'], 'mic_preflight_result')
        self.assertIn('Bluetooth Headset', detail['turn_events'][0]['metadata_json'])


class SessionRehydrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.user_models_dir = os.path.join(self.tmp.name, 'user_models')
        self.db_path = os.path.join(self.tmp.name, 'test.db')
        db.configure(self.db_path)
        db.init_db()
        session_store.clear_sessions()
        self.addCleanup(session_store.clear_sessions)

    def test_ensure_session_rehydrates_from_persisted_user_model(self):
        with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
            with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                session = session_module.create_session('rehydrate-session')
                session['info_state'].user.update('photos', ['rehydrate-session_0.jpg'])
                session['info_state'].save_user_model()
                session_store.set_session('rehydrate-session', session)

                session_store.clear_sessions()
                self.assertFalse(session_store.has_session('rehydrate-session'))

                restored = session_store.ensure_session('rehydrate-session')

                self.assertIsNotNone(restored)
                self.assertTrue(session_store.has_session('rehydrate-session'))
                self.assertEqual(restored['info_state'].user.query('photos'), ['rehydrate-session_0.jpg'])

    def test_photo_status_route_survives_in_memory_session_loss(self):
        with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
            with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                session = session_module.create_session('photo-rehydrate-session')
                visit_id = db.create_visit('photo-rehydrate-session', 'en', 'black_female', {'name': 'Ludi'})
                session['info_state'].user.update('visit_id', visit_id)
                session['info_state'].user.update('photos', ['photo-rehydrate-session_0.jpg'])
                session['info_state'].save_user_model()
                session_store.set_session('photo-rehydrate-session', session)

                session_store.clear_sessions()

                with app.test_client() as client:
                    response = client.get('/api/photos/photo-rehydrate-session')

                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data['photo_count'], 1)
                self.assertIn('photo-rehydrate-session_0.jpg', data['photos'][0])


class PhotoUploadPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.user_models_dir = os.path.join(self.tmp.name, 'user_models')
        self.photos_dir = os.path.join(self.tmp.name, 'photos')
        os.makedirs(self.photos_dir, exist_ok=True)
        self.db_path = os.path.join(self.tmp.name, 'test.db')
        db.configure(self.db_path)
        db.init_db()
        session_store.clear_sessions()
        self.addCleanup(session_store.clear_sessions)

    def _jpeg_upload(self, name='photo.jpg'):
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', (20, 20), color=(80, 120, 160)).save(buf, format='JPEG')
        buf.seek(0)
        return buf, name

    def _create_photo_session(self, session_id='photo-session'):
        with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
            with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                session = session_module.create_session(session_id)
                visit_id = db.create_visit(session_id, 'en', 'black_female', {'name': 'Ludi'})
                session['info_state'].user.update('visit_id', visit_id)
                session['info_state'].save_user_model()
                session_store.set_session(session_id, session)
                return session, visit_id

    def test_photo_slots_are_reserved_and_limited_by_database(self):
        visit_id = db.create_visit('slot-session', 'en', 'black_female', {'name': 'Ludi'})

        first = db.reserve_photo_slot(visit_id, 'slot-session', 3)
        db.finalize_photo_upload(visit_id, first['stored_filename'], source='mobile')
        second = db.reserve_photo_slot(visit_id, 'slot-session', 3)
        db.finalize_photo_upload(visit_id, second['stored_filename'], source='mobile')
        third = db.reserve_photo_slot(visit_id, 'slot-session', 3)
        db.finalize_photo_upload(visit_id, third['stored_filename'], source='mobile')

        self.assertEqual(first['display_order'], 0)
        self.assertEqual(second['display_order'], 1)
        self.assertEqual(third['display_order'], 2)
        self.assertIsNone(db.reserve_photo_slot(visit_id, 'slot-session', 3))
        self.assertEqual(
            db.list_visit_photo_filenames(visit_id),
            ['slot-session_0.jpg', 'slot-session_1.jpg', 'slot-session_2.jpg'],
        )
        self.assertEqual(
            [item['photo_role'] for item in db.list_visit_photos(visit_id)],
            ['before', 'during', 'hope'],
        )

    def test_photo_metadata_update_reorders_and_sets_roles(self):
        visit_id = db.create_visit('role-session', 'en', 'black_female', {'name': 'Ludi'})
        db.save_photo(visit_id, 'role-session_0.jpg', 0)
        db.save_photo(visit_id, 'role-session_1.jpg', 1)
        db.save_photo(visit_id, 'role-session_2.jpg', 2)

        updated = db.update_visit_photo_metadata(visit_id, [
            {'stored_filename': 'role-session_2.jpg', 'photo_role': 'hope'},
            {'stored_filename': 'role-session_0.jpg', 'photo_role': 'before'},
            {'stored_filename': 'role-session_1.jpg', 'photo_role': 'during'},
        ])

        self.assertEqual(
            [item['stored_filename'] for item in updated],
            ['role-session_2.jpg', 'role-session_0.jpg', 'role-session_1.jpg'],
        )
        self.assertEqual([item['display_order'] for item in updated], [0, 1, 2])
        self.assertEqual([item['photo_role'] for item in updated], ['hope', 'before', 'during'])

    def test_failed_upload_releases_reserved_slot(self):
        session_id = 'failed-photo-session'
        session, visit_id = self._create_photo_session(session_id)
        upload_token = db.create_upload_token(visit_id)['token']

        with patch.object(routes_photos, 'PHOTOS_DIR', self.photos_dir):
            with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
                with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                    with app.test_client() as client:
                        response = client.post(
                            '/api/upload',
                            data={
                                'session_id': session_id,
                                'source': 'mobile',
                                'upload_token': upload_token,
                                'photo': (io.BytesIO(b'not an image'), 'bad.txt'),
                            },
                            content_type='multipart/form-data',
                        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.list_visit_photo_filenames(visit_id), [])
        self.assertEqual(session['info_state'].user.query('photos') or [], [])

    def test_photo_status_prefers_database_and_syncs_stale_user_model(self):
        session_id = 'db-photo-session'
        session, visit_id = self._create_photo_session(session_id)
        session['info_state'].user.update('photos', [])
        session['info_state'].save_user_model()
        db.save_photo(visit_id, 'db-photo-session_0.jpg', 0, source='mobile')

        with patch.object(routes_photos, 'PHOTOS_DIR', self.photos_dir):
            with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
                with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                    with app.test_client() as client:
                        response = client.get(f'/api/photos/{session_id}')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['photo_count'], 1)
        self.assertIn('db-photo-session_0.jpg', data['photos'][0])
        self.assertEqual(session['info_state'].user.query('photos'), ['db-photo-session_0.jpg'])

    def test_successful_upload_persists_photo_metadata(self):
        session_id = 'upload-photo-session'
        session, visit_id = self._create_photo_session(session_id)
        upload_token = db.create_upload_token(visit_id)['token']

        with patch.object(routes_photos, 'PHOTOS_DIR', self.photos_dir):
            with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
                with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                    with app.test_client() as client:
                        response = client.post(
                            '/api/upload',
                            data={
                                'session_id': session_id,
                                'source': 'mobile',
                                'upload_token': upload_token,
                                'photo': self._jpeg_upload(),
                            },
                            content_type='multipart/form-data',
                        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['photo_count'], 1)
        self.assertFalse(data['ready'])
        self.assertEqual(data['photo_items'][0]['photo_role'], 'before')
        self.assertEqual(db.list_visit_photo_filenames(visit_id), ['upload-photo-session_0.jpg'])
        self.assertEqual(session['info_state'].user.query('photos'), ['upload-photo-session_0.jpg'])
        self.assertTrue(os.path.exists(os.path.join(self.photos_dir, 'upload-photo-session_0.jpg')))

    def test_photo_metadata_route_updates_roles_and_session_order(self):
        session_id = 'metadata-photo-session'
        session, visit_id = self._create_photo_session(session_id)
        db.save_photo(visit_id, 'metadata-photo-session_0.jpg', 0)
        db.save_photo(visit_id, 'metadata-photo-session_1.jpg', 1)
        session['info_state'].user.update('photos', [
            'metadata-photo-session_0.jpg',
            'metadata-photo-session_1.jpg',
        ])

        with app.test_client() as client:
            response = client.post(
                f'/api/photos/{session_id}/metadata',
                json={
                    'photos': [
                        {'stored_filename': 'metadata-photo-session_1.jpg', 'photo_role': 'hope'},
                        {'stored_filename': 'metadata-photo-session_0.jpg', 'photo_role': 'before'},
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [item['stored_filename'] for item in data['photo_items']],
            ['metadata-photo-session_1.jpg', 'metadata-photo-session_0.jpg'],
        )
        self.assertEqual(session['info_state'].user.query('photos'), [
            'metadata-photo-session_1.jpg',
            'metadata-photo-session_0.jpg',
        ])

    def test_mobile_upload_rejects_missing_token(self):
        session_id = 'token-required-session'
        self._create_photo_session(session_id)

        with patch.object(routes_photos, 'PHOTOS_DIR', self.photos_dir):
            with app.test_client() as client:
                response = client.post(
                    '/api/upload',
                    data={
                        'session_id': session_id,
                        'source': 'mobile',
                        'photo': self._jpeg_upload(),
                    },
                    content_type='multipart/form-data',
                )

        self.assertEqual(response.status_code, 403)

    def test_qr_link_contains_valid_upload_token(self):
        session_id = 'qr-token-session'
        self._create_photo_session(session_id)

        with patch.object(session_module, 'USER_MODELS_DIR', self.user_models_dir):
            with patch.object(session_store, 'USER_MODELS_DIR', self.user_models_dir):
                with app.test_client() as client:
                    qr_response = client.get(f'/api/qr/{session_id}')

                    self.assertEqual(qr_response.status_code, 200)
                    qr_data = qr_response.get_json()
                    self.assertIn('/upload/qr-token-session?token=', qr_data['upload_url'])
                    self.assertTrue(qr_data['upload_token'])

                    missing_token = client.get(f'/upload/{session_id}')
                    valid_link = client.get(f'/upload/{session_id}?token={qr_data["upload_token"]}')

        self.assertEqual(missing_token.status_code, 404)
        self.assertEqual(valid_link.status_code, 200)


class MicrositeEvidenceTests(unittest.TestCase):
    def test_format_story_evidence_excludes_rejected_operational_turns(self):
        state = {
            'story_evidence': {
                'daily_life': [
                    {
                        'answer': "It has trouble picking stuff up and it is frustrating.",
                        'accepted': False,
                        'sufficiency': {'sufficient': False, 'reason': 'operational_issue'},
                    },
                    {
                        'answer': 'Dialysis leaves me tired after treatment and limits my work schedule.',
                        'accepted': True,
                        'sufficiency': {'sufficient': True, 'reason': 'required_evidence'},
                    },
                ]
            }
        }

        transcript = microsite.format_story_evidence(state)

        self.assertIn('Dialysis leaves me tired', transcript)
        self.assertNotIn('picking stuff up', transcript)

    def test_format_story_evidence_marks_skipped_sections(self):
        state = {
            'story_evidence': {
                'daily_life': [
                    {
                        'answer': 'Dialysis leaves me tired after treatment and limits my work schedule.',
                        'accepted': True,
                    },
                ]
            },
            'skipped_steps': {
                'donor_message': {'reason': 'patient_requested_skip'},
            },
        }

        transcript = microsite.format_story_evidence(state)

        self.assertIn('Daily Life: Dialysis leaves me tired', transcript)
        self.assertIn('Donor Message: The patient chose to skip this section.', transcript)


class MicrositeReviewTests(unittest.TestCase):
    def _info_state(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        info_state = InformationState(os.path.join(tmp.name, 'user.pkl'), 'domains/interview.json')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])
        return info_state

    def test_generate_creates_draft_and_publish_writes_public_page(self):
        info_state = self._info_state()
        with tempfile.TemporaryDirectory() as site_dir:
            with patch.object(microsite, 'MICROSITES_DIR', site_dir):
                with app.test_request_context('/microsite'):
                    draft = microsite.generate(info_state, FakeMicrositeLLM(), 'Sophia', 'unit-review')
                    self.assertFalse(draft['published'])
                    self.assertIsNone(draft['microsite_url'])
                    self.assertEqual(draft['prompt_version'], microsite.MICROSITE_PROMPT_VERSION)
                    self.assertEqual(draft['llm_model'], 'fake-microsite-model')
                    self.assertRegex(draft['evidence_hash'], r'^[0-9a-f]{64}$')
                    self.assertEqual(draft['evidence_snapshot']['source'], 'conversation_history')
                    self.assertEqual(draft['evidence_snapshot']['evidence_hash'], draft['evidence_hash'])
                    self.assertFalse(os.path.exists(os.path.join(site_dir, 'unit-review.html')))

                    published = microsite.publish(
                        info_state,
                        'unit-review',
                        {'personal_identity': 'Edited story approved by Sophia.'}
                    )

                    self.assertTrue(published['published'])
                    self.assertEqual(published['personal_identity'], 'Edited story approved by Sophia.')
                    self.assertEqual(published['my_story'], 'Edited story approved by Sophia.')
                    self.assertEqual(published['prompt_version'], draft['prompt_version'])
                    self.assertEqual(published['llm_model'], draft['llm_model'])
                    self.assertEqual(published['evidence_hash'], draft['evidence_hash'])
                    self.assertEqual(published['evidence_snapshot'], draft['evidence_snapshot'])
                    self.assertEqual(published['review_edits']['changed_fields'], ['personal_identity'])
                    html_path = os.path.join(site_dir, 'unit-review.html')
                    self.assertTrue(os.path.exists(html_path))
                    with open(html_path, encoding='utf-8') as f:
                        html = f.read()
                    self.assertIn('<meta name="description"', html)
                    self.assertIn('<link rel="canonical"', html)
                    self.assertIn('name="twitter:description"', html)
                    self.assertIn('Ludi Donor Stories', html)


class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db.configure(os.path.join(self.tmp.name, 'transplant.db'))
        db.init_db()

    def test_visit_messages_events_photo_and_draft_are_saved(self):
        visit_id = db.create_visit(
            'session-1',
            'en',
            'black_male',
            {'name': 'Ludi', 'voice': 196},
            user_agent='unit-test',
        )
        user_message_id = db.save_message(
            visit_id,
            'user',
            'My name is Sophia',
            turn_number=1,
            phase='INTRO',
            task_type='ask_readiness',
            answered_outgoing_turn_id='turn-0',
            answered_question_text='What name would you like shown publicly on your donor page?',
            input_modality='typed',
            response_latency_ms=1200,
            answer_duration_ms=3000,
            retry_count=1,
        )
        db.save_message(
            visit_id,
            'assistant',
            'Thank you, Sophia. Are you ready to begin?',
            turn_number=1,
            phase='INTRO',
            task_type='ask_readiness',
            outgoing_turn_id='turn-1',
            asked_question_text='Are you ready to begin?',
            expected_answer_kind='readiness',
            delivery_validated=True,
            input_modality='system',
        )
        db.save_turn_events(
            visit_id,
            user_message_id,
            1,
            [
                {'type': 'typed_started', 'ts': 100},
                {'type': 'typed_sent', 'ts': 3100},
                {'type': 'not_allowed', 'ts': 3200},
            ],
        )
        db.save_photo(visit_id, 'session-1_0.jpg', 0, byte_size=42, sha256='abc')
        version = db.save_draft(
            visit_id,
            {
                'name': 'Sophia',
                'headline': 'Sophia needs a kidney donor',
                'short_intro': 'Intro',
                'personal_identity': 'Story',
                'kidney_journey': 'Journey',
                'daily_impact': 'Struggle',
                'transplant_hope': 'Hope',
                'donor_message': 'Message',
                'my_story': 'Story',
                'my_struggle': 'Struggle',
                'my_hope': 'Hope',
                'evidence_hash': 'a' * 64,
                'evidence_snapshot': {'version': 1, 'source': 'story_evidence'},
                'review_edits': {'version': 1, 'changed_fields': ['my_story']},
                'content': '{"ok": true}',
            },
            status='draft',
            generation_latency_ms=55,
            llm_model='fake-microsite-model',
            prompt_version='microsite-public-page-v2',
        )

        import sqlite3
        conn = sqlite3.connect(os.path.join(self.tmp.name, 'transplant.db'))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)

        self.assertEqual(conn.execute('SELECT COUNT(*) FROM visits').fetchone()[0], 1)
        user_row = conn.execute("SELECT * FROM messages WHERE role = 'user'").fetchone()
        assistant_row = conn.execute("SELECT * FROM messages WHERE role = 'assistant'").fetchone()
        self.assertEqual(user_row['answer_duration_ms'], 3000)
        self.assertEqual(user_row['answered_outgoing_turn_id'], 'turn-0')
        self.assertEqual(assistant_row['outgoing_turn_id'], 'turn-1')
        self.assertEqual(assistant_row['asked_question_text'], 'Are you ready to begin?')
        self.assertEqual(assistant_row['delivery_validated'], 1)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM turn_events').fetchone()[0], 2)
        self.assertEqual(conn.execute('SELECT photo_count FROM visits').fetchone()[0], 1)
        draft_row = conn.execute('SELECT * FROM donor_page_drafts').fetchone()
        self.assertEqual(draft_row['llm_model'], 'fake-microsite-model')
        self.assertEqual(draft_row['prompt_version'], 'microsite-public-page-v2')
        self.assertEqual(draft_row['generation_latency_ms'], 55)
        draft_content = json.loads(draft_row['content_json'])
        self.assertEqual(draft_content['evidence_hash'], 'a' * 64)
        self.assertEqual(draft_content['evidence_snapshot']['source'], 'story_evidence')
        self.assertEqual(draft_content['review_edits']['changed_fields'], ['my_story'])
        self.assertEqual(version, 1)


if __name__ == '__main__':
    unittest.main()
