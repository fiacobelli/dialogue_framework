"""Flask application entry point for the SDoH screening framework."""

import logging
from flask import Flask, render_template, request
from decouple import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)

from .config import FLASK_PORT, FLASK_DEBUG, AVATAR_PROFILES, DB_PATH
from .routes_api import api_bp
from .database import configure as db_configure, init_db

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')

app.register_blueprint(api_bp)

# Ensure storage directories exist
import os
os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
db_configure(DB_PATH)
init_db()


@app.route('/')
def index():
    """Render avatar selection page."""
    return render_template('select_avatar.html', avatars=AVATAR_PROFILES)


@app.route('/screening')
def screening():
    """Render screening page with selected avatar."""
    scene_id = request.args.get('a', '2756814')
    # Find avatar_id by scene_id for session tracking
    avatar_id = next((k for k, v in AVATAR_PROFILES.items() if str(v['scene_id']) == scene_id), 'mary')
    avatar_profile = AVATAR_PROFILES[avatar_id]
    return render_template(
        'screening.html',
        avatar_scene_id=int(scene_id),
        avatar_id=avatar_id,
        avatar_profile=avatar_profile,
    )


@app.route('/avatar-preview/<int:scene_id>')
def avatar_preview(scene_id):
    """Preview a SitePal avatar by scene ID."""
    return render_template('avatar_preview.html', scene_id=scene_id)


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
