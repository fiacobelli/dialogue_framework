import unittest
from unittest.mock import Mock, patch

from web.goal_interview import _can_probe, _required_followup_question, instruction_for
from web.interview_flow_config import FOLLOWUP_EXAMPLES, INTERVIEW_STEPS, MAX_FOLLOWUPS_PER_SECTION
from web.llm_provider import AzureOpenAIProvider
from web.microsite import format_story_evidence, story_evidence_ready
from web.routes_api import _valid_participant_code


class MicrositeUpdateTests(unittest.TestCase):
    def test_accepts_numeric_and_alphanumeric_participant_ids(self):
        self.assertTrue(_valid_participant_code('101'))
        self.assertTrue(_valid_participant_code('BB1'))
        self.assertFalse(_valid_participant_code('BB 1'))

    def test_vague_answer_gets_topic_example(self):
        question = _required_followup_question(INTERVIEW_STEPS[3], 'It would be better.')
        self.assertEqual(question, FOLLOWUP_EXAMPLES['transplant_hope'])
        self.assertEqual(_required_followup_question(INTERVIEW_STEPS[3], 'More energy.'), '')

    def test_second_followup_is_bounded_and_stops_on_decline(self):
        step = INTERVIEW_STEPS[2]
        state = {'followup_count': 1}

        self.assertEqual(MAX_FOLLOWUPS_PER_SECTION, 2)
        self.assertTrue(_can_probe(state, 'followup_answer', step, "It's hard."))
        self.assertFalse(_can_probe(state, 'followup_answer', step, "I don't know."))
        self.assertFalse(_can_probe(state, 'followup_answer', step, 'No.'))
        self.assertFalse(_can_probe({'followup_count': 2}, 'followup_answer', step, 'I feel tired.'))

        directive = instruction_for(state, 'followup_answer', step, can_probe=True)
        self.assertIn('second and last', directive)
        self.assertIn(step['required'], directive)

    def test_decline_on_a_main_answer_is_never_probed(self):
        step = INTERVIEW_STEPS[2]
        state = {'followup_count': 0}

        for answer in ("I don't know.", "I'm not sure.", 'I\u2019d rather not say.', 'Can we skip that?'):
            self.assertFalse(_can_probe(state, 'main_answer', step, answer), answer)
        self.assertEqual(_required_followup_question(step, "I don't know."), '')
        # "No" answers a main question; a long answer that happens to say "I don't know" is content.
        self.assertTrue(_can_probe(state, 'main_answer', step, 'No.'))
        self.assertTrue(_can_probe(
            state, 'main_answer', step,
            "I don't know how I would manage without my wife who drives me to every appointment.",
        ))

    def test_fallback_followups_cover_probing_steps_without_repeating_the_question(self):
        probing = [s for s in INTERVIEW_STEPS if s['allow_follow_up']]
        self.assertEqual({s['id'] for s in probing}, set(FOLLOWUP_EXAMPLES))
        for step in probing:
            self.assertNotEqual(FOLLOWUP_EXAMPLES[step['id']], step['question'])
        non_probing = {s['id'] for s in INTERVIEW_STEPS if not s['allow_follow_up']}
        self.assertEqual(non_probing, {'medical_history', 'final_details'})

    def test_page_evidence_keeps_probed_answers_with_their_questions(self):
        state = {
            'story_evidence': {
                'support_network': [
                    {'question': 'Who, if anyone, is supporting you through this?',
                     'answer': 'my wife and kids', 'accepted': False},
                    {'question': 'What is one thing they do that helps?',
                     'answer': 'They drive me to dialysis.', 'accepted': True},
                ],
                'medical_history': [{'answer': 'Ten years ago.', 'accepted': True}],
                'daily_life': [{'question': 'How has it affected you?', 'answer': 'but', 'accepted': False}],
            },
            'skipped_steps': {'daily_life': {}, 'donor_message': {}},
        }
        text = format_story_evidence(state)

        self.assertLess(text.index('my wife and kids'), text.index('They drive me to dialysis.'))
        self.assertIn('Interviewer asked: What is one thing they do that helps?', text)
        self.assertIn('Medical History: Ten years ago.', text)
        self.assertIn('Donor Message: The patient chose to skip this section.', text)
        self.assertNotIn('Daily Life: The patient chose to skip', text)

    def test_readiness_still_counts_only_accepted_answers(self):
        mk = lambda accepted: [{'question': 'q', 'answer': 'something', 'accepted': accepted}]
        evidence = {step: mk(True) for step in ('personal_background', 'medical_history', 'transplant_hope')}
        evidence['donor_message'] = mk(False)
        self.assertEqual(story_evidence_ready({'story_evidence': evidence})['missing'], ['donor_message'])

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
        self.assertEqual(request['input'][0], {'role': 'system', 'content': 'Return valid JSON.'})
        self.assertEqual(request['text'], {'format': {'type': 'json_object'}})
        self.assertNotIn('temperature', request)


if __name__ == '__main__':
    unittest.main()
