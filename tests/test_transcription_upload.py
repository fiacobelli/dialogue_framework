import io
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from web import routes_transcribe


class TranscriptionUploadTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(routes_transcribe.transcribe_bp)
        self.client = app.test_client()

    def _post_audio(self, size):
        response = Mock()
        response.json.return_value = {'text': 'transcribed answer'}
        with (
            patch.object(routes_transcribe, 'GROQ_API_KEY', 'test-key'),
            patch.object(routes_transcribe, 'ensure_session', return_value=True),
            patch.object(routes_transcribe, 'get_session', return_value={'info_state': object()}),
            patch.object(routes_transcribe, 'is_patient_authorized', return_value=True),
            patch.object(routes_transcribe.http_requests, 'post', return_value=response) as groq_post,
        ):
            result = self.client.post('/api/transcribe', data={
                'session_id': 'session-1',
                'audio': (io.BytesIO(b'0' * size), 'audio.wav'),
            })
        return result, groq_post

    def test_accepts_audio_over_previous_one_megabyte_limit(self):
        result, groq_post = self._post_audio(2 * 1024 * 1024)

        self.assertEqual(result.status_code, 200)
        groq_post.assert_called_once()

    def test_rejects_audio_over_three_megabytes(self):
        result, groq_post = self._post_audio(routes_transcribe.MAX_TRANSCRIBE_AUDIO_BYTES + 1)

        self.assertEqual(result.status_code, 413)
        groq_post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
