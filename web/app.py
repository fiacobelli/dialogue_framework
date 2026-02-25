"""Flask application entry point for the SDoH screening framework."""

import logging
from flask import Flask, render_template, request
from decouple import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)

from .config import FLASK_PORT, FLASK_DEBUG, AVATAR_PROFILES
from .routes_api import api_bp

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')

app.register_blueprint(api_bp)


@app.route('/')
def index():
    """Render avatar selection page."""
    return render_template('select_avatar.html', avatars=AVATAR_PROFILES)


@app.route('/screening')
def screening():
    """Render screening page with selected avatar."""
    avatar_id = request.args.get('avatar', 'mary')
    avatar_profile = AVATAR_PROFILES.get(avatar_id, AVATAR_PROFILES['mary'])
    return render_template('screening.html', avatar_scene_id=avatar_profile['scene_id'])


@app.route('/avatar-preview/<int:scene_id>')
def avatar_preview(scene_id):
    """Preview a SitePal avatar by scene ID."""
    return render_template('avatar_preview.html', scene_id=scene_id)


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
