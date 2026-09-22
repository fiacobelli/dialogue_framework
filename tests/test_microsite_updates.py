import unittest
from unittest.mock import Mock, patch

from web.goal_interview import _can_probe, _required_followup_question, instruction_for
from web.interview_flow_config import INTERVIEW_STEPS, MAX_FOLLOWUPS_PER_SECTION
from web.llm_provider import AzureOpenAIProvider
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

    def test_second_followup_is_selective_and_bounded(self):
        step = INTERVIEW_STEPS[2]
        state = {'followup_count': 1}

        self.assertEqual(MAX_FOLLOWUPS_PER_SECTION, 2)
        self.assertTrue(_can_probe(state, 'followup_answer', step, 'I feel tired after dialysis.'))
        self.assertFalse(_can_probe(state, 'followup_answer', step, "I don't know."))
        self.assertFalse(_can_probe({'followup_count': 2}, 'followup_answer', step, 'I feel tired.'))

        directive = instruction_for(state, 'followup_answer', step, can_probe=True)
        self.assertIn('useful concrete detail', directive)
        self.assertIn('one important part unclear', directive)
        self.assertNotIn('If it is still vague', directive)

    @patch('web.llm_provider.OpenAI')
    def test_azure_provider_uses_responses_api(self, openai_client):
        response = Mock(output_text='{"ack":"Thank you."}')
        openai_client.return_value.responses.create.return_value = response
        provider = AzureOpenAIProvider('gpt-6-astra', 'test-key', 'https://example.test/openai/v1/')

        result = provider.generate(
            [{'role': 'user', 'content': 'Hello'}],
            system_prompt='Return JSON.',
            json_mode=True,
            temperature=0.4,
        )

        self.assertEqual(result, response.output_text)
        request = openai_client.return_value.responses.create.call_args.kwargs
        self.assertEqual(request['model'], 'gpt-6-astra')
        self.assertEqual(request['instructions'], 'Return JSON.')
        self.assertEqual(request['text'], {'format': {'type': 'json_object'}})
        self.assertNotIn('temperature', request)


if __name__ == '__main__':
    unittest.main()
