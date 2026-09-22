import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image
from web import database as db
from web import routes_photos
from web.app import app


class PhotoReservationTests(unittest.TestCase):
    def setUp(self):
        self.previous_db = db.get_db_path()
        self.tempdir = tempfile.TemporaryDirectory()
        db.configure(os.path.join(self.tempdir.name, 'photos.db'))
        db.init_db()
        self.visit_id = db.create_visit(
            'photo-session', 'en', 'black_female', {'name': 'Ludi'}, participant_code='101'
        )

    def tearDown(self):
        db.configure(self.previous_db)
        self.tempdir.cleanup()

    def test_failed_upload_releases_slot_for_retry(self):
        reservation = db.reserve_photo_slot(self.visit_id, 'photo-session', 3)
        db.release_photo_reservation(self.visit_id, reservation['stored_filename'])

        retry = db.reserve_photo_slot(self.visit_id, 'photo-session', 3)

        self.assertEqual(retry['display_order'], 0)
        self.assertEqual(retry['stored_filename'], reservation['stored_filename'])

    def test_qr_token_can_replace_photo_but_not_cross_visits(self):
        token = db.create_upload_token(self.visit_id)['token']
        values = {'visit_id': self.visit_id, 'photos': [], 'patient_token': 'patient-token'}
        user = Mock()
        user.query.side_effect = values.get
        user.update.side_effect = values.__setitem__
        session = {'info_state': Mock(user=user)}

        def photo(color):
            output = BytesIO()
            Image.new('RGB', (8, 8), color).save(output, format='JPEG')
            output.seek(0)
            return output

        def upload(color, replace_index=None):
            data = {
                'session_id': 'photo-session',
                'source': 'mobile',
                'upload_token': token,
                'photo': (photo(color), 'photo.jpg'),
            }
            if replace_index is not None:
                data['replace_index'] = str(replace_index)
            return app.test_client().post('/api/upload', data=data, content_type='multipart/form-data')

        with (
            patch.object(routes_photos, 'PHOTOS_DIR', self.tempdir.name),
            patch.object(routes_photos, 'ensure_session', return_value=session),
            patch.object(routes_photos, 'get_session', return_value=session),
            patch.object(routes_photos, 'persist_session_state'),
        ):
            for color in ('red', 'green', 'blue'):
                self.assertEqual(upload(color).status_code, 200)

            before = db.list_visit_photos(self.visit_id)[1]['sha256']
            response = upload('yellow', replace_index=1)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['replaced'])
        self.assertEqual(response.get_json()['photo_count'], 3)
        self.assertNotEqual(db.list_visit_photos(self.visit_id)[1]['sha256'], before)
        self.assertTrue(db.validate_upload_token(self.visit_id, token, mark_used=False))

        other_visit = db.create_visit(
            'other-photo-session', 'en', 'black_female', {'name': 'Ludi'}, participant_code='102'
        )
        self.assertFalse(db.validate_upload_token(other_visit, token, mark_used=False))
        db.revoke_upload_tokens(self.visit_id, reason='published')
        self.assertFalse(db.validate_upload_token(self.visit_id, token, mark_used=False))


if __name__ == '__main__':
    unittest.main()
