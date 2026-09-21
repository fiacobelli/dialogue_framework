import os
import tempfile
import unittest

from web import database as db


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


if __name__ == '__main__':
    unittest.main()
