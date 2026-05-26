import unittest

from web.interview_flow import build_interview_state, decide_next_task, deterministic_response


class PriorReferenceFlowTests(unittest.TestCase):
    def _start_story(self):
        state = build_interview_state()
        decide_next_task(state, 'Sophia')
        decide_next_task(state, 'yes')
        return state

    def test_prior_reference_after_deepening_reuses_existing_evidence_without_recording(self):
        state = self._start_story()
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
        self.assertEqual(len(state['story_evidence']['personal_background']), 1)

        task = decide_next_task(state, 'I did mention it before')

        self.assertEqual(task['type'], 'ack_then_next')
        self.assertEqual(task['step']['id'], 'medical_history')
        self.assertEqual(task['decision']['reason'], 'prior_reference_existing_evidence')
        self.assertEqual(task['decision']['turn_interpretation']['category'], 'prior_reference')
        self.assertEqual(len(state['story_evidence']['personal_background']), 1)

    def test_prior_reference_without_existing_evidence_repairs_without_recording(self):
        state = self._start_story()

        task = decide_next_task(state, 'I already mentioned that')
        response = deterministic_response(task, state)

        self.assertEqual(task['type'], 'repair_answer')
        self.assertEqual(task['decision']['reason'], 'prior_reference_without_evidence')
        self.assertEqual(task['decision']['turn_interpretation']['category'], 'prior_reference')
        self.assertEqual(state['step_index'], 0)
        self.assertEqual(state.get('story_evidence'), {})
        self.assertIn('I may have missed that earlier', response)


if __name__ == '__main__':
    unittest.main()
