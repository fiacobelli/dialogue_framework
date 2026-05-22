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
    sufficiency_decision,
)
from web import microsite
from web import database as db
from web.routes_api import validate_generation_ready


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


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, messages, system_prompt=None):
        self.calls += 1
        return 'How would receiving a kidney transplant change your life?'


class FakeMicrositeLLM:
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
                    self.assertFalse(os.path.exists(os.path.join(site_dir, 'unit-review.html')))

                    published = microsite.publish(
                        info_state,
                        'unit-review',
                        {'personal_identity': 'Edited story approved by Sophia.'}
                    )

                    self.assertTrue(published['published'])
                    self.assertEqual(published['personal_identity'], 'Edited story approved by Sophia.')
                    self.assertEqual(published['my_story'], 'Edited story approved by Sophia.')
                    self.assertTrue(os.path.exists(os.path.join(site_dir, 'unit-review.html')))


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
                'content': '{"ok": true}',
            },
            status='draft',
            generation_latency_ms=55,
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
        self.assertEqual(version, 1)


if __name__ == '__main__':
    unittest.main()
