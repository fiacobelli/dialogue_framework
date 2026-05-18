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
    build_interview_state,
    decide_next_task,
    extract_patient_name,
    sufficiency_decision,
)
from web import microsite
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

    def test_short_story_answer_triggers_same_topic_followup(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        task = decide_next_task(state, 'okay')

        self.assertEqual(task['type'], 'ask_followup')
        self.assertEqual(task['step']['id'], 'personal_background')
        self.assertEqual(state['step_index'], 0)
        self.assertEqual(state['awaiting'], 'followup_answer')

    def test_broad_dialysis_answer_is_not_sufficient_daily_life(self):
        step = {'id': 'daily_life'}
        decision = sufficiency_decision(step, 'most of the time treatments dialysis treatment')

        self.assertFalse(decision['sufficient'])
        self.assertEqual(decision['reason'], 'broad_treatment_only')

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
            "my_story": "Sophia enjoys time with family.",
            "my_struggle": "Dialysis has made daily life difficult.",
            "my_hope": "A transplant would help Sophia regain energy."
        }"""


class InterviewGoalTests(unittest.TestCase):
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

    def test_generation_blocked_when_story_incomplete(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'STORY')
        info_state.user.update('interview_state', {'complete': False})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertFalse(ready)
        self.assertIn('story_complete', detail['missing'])

    def test_generation_blocked_without_confirmed_name(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True})
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertFalse(ready)
        self.assertIn('confirmed_name', detail['missing'])

    def test_generation_allowed_when_story_name_and_photos_ready(self):
        info_state = self._info_state()
        info_state.user.update('interview_phase', 'PHOTOS')
        info_state.user.update('interview_state', {'complete': True})
        info_state.user.update('patient_name', 'Sophia')
        info_state.user.update('patient_name_status', 'confirmed')
        info_state.user.update('photos', ['a.jpg', 'b.jpg', 'c.jpg'])

        ready, detail = validate_generation_ready(info_state)

        self.assertTrue(ready)
        self.assertEqual(detail['name'], 'Sophia')


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
                        {'my_story': 'Edited story approved by Sophia.'}
                    )

                    self.assertTrue(published['published'])
                    self.assertEqual(published['my_story'], 'Edited story approved by Sophia.')
                    self.assertTrue(os.path.exists(os.path.join(site_dir, 'unit-review.html')))


if __name__ == '__main__':
    unittest.main()
