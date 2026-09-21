import os
import tempfile
import unittest

from web import database as db
from web.app import app


class PublicPagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.previous_db = db.get_db_path()
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, 'pages.db')
        db.configure(self.db_path)
        db.init_db()
        self.visit_id = db.create_visit(
            'public-session', 'en', 'black_female', {'name': 'Ludi'}, participant_code='101'
        )
        db.save_draft(self.visit_id, {
            'name': 'Ben',
            'headline': 'My Story',
            'rendered_html': '<!doctype html><html><body><h1>Approved page</h1></body></html>',
            'microsite_absolute_url': 'https://ludi.a4hlab.org/microsite/site/public-session',
            'microsite_url': '/microsite/site/public-session',
        }, status='published')

    def tearDown(self):
        db.configure(self.previous_db)
        self.tempdir.cleanup()

    def test_public_route_reads_approved_html_after_database_reopen(self):
        db.configure(self.db_path)
        response = app.test_client().get('/site/public-session')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Approved page', response.data)

    def test_unpublish_immediately_blocks_public_route(self):
        self.assertTrue(db.unpublish_session('public-session'))
        response = app.test_client().get('/site/public-session')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
