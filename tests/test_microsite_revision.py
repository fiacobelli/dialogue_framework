import json
import unittest
from unittest.mock import patch

from web import microsite


class _UserState:
    def __init__(self, values):
        self.values = values

    def query(self, key):
        return self.values.get(key)

    def update(self, key, value):
        self.values[key] = value


class _InfoState:
    def __init__(self, values):
        self.user = _UserState(values)


class _Provider:
    model = 'test-model'

    def __init__(self, response):
        self.response = response
        self.prompt = ''

    def generate(self, messages, **_kwargs):
        self.prompt = messages[0]['content']
        return json.dumps(self.response)


def _content(prefix='Original'):
    return {field: f'{prefix} {field}' for field in microsite.CONTENT_FIELDS}


class MicrositeRevisionTests(unittest.TestCase):
    def setUp(self):
        draft = {'name': 'Ben', **_content(), 'hero_photo': 'hero.jpg'}
        self.info_state = _InfoState({
            'microsite_draft': draft,
            'visit_id': 'visit-1',
            'patient_token': 'token-1',
            'interview_state': {
                'story_evidence': {
                    'personal_background': [{'answer': 'I am a teacher in Chicago.', 'accepted': True}],
                },
            },
        })

    @patch('web.microsite.persist_session_state')
    @patch('web.microsite._render_preview_html', return_value='<p>preview</p>')
    @patch('web.microsite.db.list_visit_photos', return_value=[])
    def test_revision_uses_evidence_and_current_edits(self, _photos, _preview, _persist):
        provider = _Provider(_content('Revised'))
        with patch('web.microsite._generation_provider', return_value=provider):
            result = microsite.revise(
                self.info_state,
                provider,
                'Make it more informal.',
                {'headline': 'My corrected headline'},
                'session-1',
            )

        self.assertEqual(result['headline'], 'Revised headline')
        self.assertEqual(result['revision_instruction'], 'Make it more informal.')
        self.assertIn('I am a teacher in Chicago.', provider.prompt)
        self.assertIn('My corrected headline', provider.prompt)
        self.assertEqual(self.info_state.user.query('microsite_draft'), result)

    def test_revision_requires_an_instruction(self):
        with self.assertRaises(microsite.MicrositeGenerationError) as raised:
            microsite.revise(self.info_state, _Provider(_content()), '   ')
        self.assertEqual(raised.exception.error, 'invalid_revision_instruction')


if __name__ == '__main__':
    unittest.main()
