"""Flask application entry point for the dialogue framework."""

from flask import Flask, render_template, send_from_directory, request
from decouple import config
import os

from .config import PHOTOS_DIR, MICROSITES_DIR, FLASK_PORT, FLASK_DEBUG, AVATAR_PROFILES
from .routes_api import api_bp
from .routes_photos import photos_bp
from .session_store import has_session, get_session

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')

app.register_blueprint(api_bp)
app.register_blueprint(photos_bp)

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(MICROSITES_DIR, exist_ok=True)


@app.route('/')
def index():
    """Render avatar selection page."""
    return render_template('select_avatar.html', avatars=AVATAR_PROFILES)


@app.route('/interview')
def interview():
    """Render interview page with selected avatar."""
    avatar_id = request.args.get('avatar', 'mary')
    avatar_profile = AVATAR_PROFILES.get(avatar_id, AVATAR_PROFILES['mary'])
    return render_template('interview.html', avatar_scene_id=avatar_profile['scene_id'])


@app.route('/avatar-preview/<int:scene_id>')
def avatar_preview(scene_id):
    """Preview a SitePal avatar by scene ID."""
    return render_template('avatar_preview.html', scene_id=scene_id)


@app.route('/photos/<filename>')
def serve_photo(filename):
    """Serve uploaded photo files."""
    abs_photos_dir = os.path.abspath(PHOTOS_DIR)
    return send_from_directory(abs_photos_dir, filename)


@app.route('/upload/<session_id>')
def mobile_upload(session_id):
    """Render mobile photo upload page for a session."""
    if not has_session(session_id):
        return 'Session not found or expired', 404
    return render_template('upload_mobile.html', session_id=session_id)


@app.route('/site/<session_id>')
def serve_microsite(session_id):
    """Serve generated microsite HTML."""
    abs_microsites_dir = os.path.abspath(MICROSITES_DIR)
    return send_from_directory(abs_microsites_dir, f'{session_id}.html')


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
