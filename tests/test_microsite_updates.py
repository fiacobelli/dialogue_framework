import unittest

from web.goal_interview import _required_followup_question
from web.interview_flow_config import INTERVIEW_STEPS
from web.routes_api import _valid_participant_code


class MicrositeUpdateTests(unittest.TestCase):
    def test_accepts_numeric_and_alphanumeric_participant_ids(self):
        self.assertTrue(_valid_participant_code('101'))
        self.assertTrue(_valid_participant_code('BB1'))
        self.assertFalse(_valid_participant_code('BB 1'))

    def test_vague_answer_gets_topic_example(self):
        question = _required_followup_question(INTERVIEW_STEPS[3], 'It would be better.')
        self.assertIn('having more energy', question)
        self.assertEqual(_required_followup_question(INTERVIEW_STEPS[3], 'More energy.'), '')


if __name__ == '__main__':
    unittest.main()
