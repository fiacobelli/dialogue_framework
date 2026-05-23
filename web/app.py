"""Flask application entry point for the dialogue framework."""

from flask import Flask, render_template, send_from_directory, request, abort
from decouple import config
import os
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import (
    PHOTOS_DIR,
    MICROSITES_DIR,
    DB_PATH,
    FLASK_PORT,
    FLASK_DEBUG,
    AVATAR_PROFILES,
    DEFAULT_AVATAR_ID,
)
from .routes_api import api_bp
from .routes_admin import admin_bp
from .routes_photos import photos_bp
from .session_store import ensure_session
from . import database as db
from .database import configure as db_configure, init_db

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(photos_bp)

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(MICROSITES_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
db_configure(DB_PATH)
init_db()


@app.route('/')
def index():
    """Render avatar selection page."""
    return render_template('select_avatar.html', avatars=AVATAR_PROFILES)


@app.route('/interview')
def interview():
    """Render interview page with selected avatar."""
    avatar_id = request.args.get('avatar', DEFAULT_AVATAR_ID)
    if avatar_id not in AVATAR_PROFILES:
        avatar_id = DEFAULT_AVATAR_ID
    avatar_profile = AVATAR_PROFILES[avatar_id]
    return render_template(
        'interview.html',
        avatar_scene_id=avatar_profile['scene_id'],
        avatar_id=avatar_id,
        avatar_profile=avatar_profile,
    )


@app.route('/avatar-preview/<int:scene_id>')
def avatar_preview(scene_id):
    """Preview a SitePal avatar by scene ID."""
    return render_template('avatar_preview.html', scene_id=scene_id)


@app.route('/photos/<filename>')
def serve_photo(filename):
    """Serve uploaded photos only after their donor page is published."""
    if not db.is_photo_public(filename):
        abort(404)
    abs_photos_dir = os.path.abspath(PHOTOS_DIR)
    return send_from_directory(abs_photos_dir, filename)


@app.route('/upload/<session_id>')
def mobile_upload(session_id):
    """Render mobile photo upload page for a session."""
    if not ensure_session(session_id):
        return 'Session not found or expired', 404
    return render_template('upload_mobile.html', session_id=session_id)


@app.route('/site/<session_id>')
def serve_microsite(session_id):
    """Serve generated microsite HTML only when the DB marks it published."""
    if not db.is_microsite_published(session_id):
        abort(404)
    abs_microsites_dir = os.path.abspath(MICROSITES_DIR)
    return send_from_directory(abs_microsites_dir, f'{session_id}.html')


@app.route('/static/microsites/<path:filename>')
def block_raw_microsite_static(filename):
    """Prevent bypassing publication status through Flask's static route."""
    abort(404)


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
