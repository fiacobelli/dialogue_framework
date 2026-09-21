"""Flask application entry point for the dialogue framework."""

from flask import Flask, Response, render_template, send_from_directory, request, abort, url_for
from decouple import config
import os
from urllib.parse import quote
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
from .routes_publication import publication_bp
from .routes_transcribe import transcribe_bp
from .session_store import ensure_session
from . import database as db
from . import microsite
from .database import configure as db_configure, init_db

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(photos_bp)
app.register_blueprint(publication_bp)
app.register_blueprint(transcribe_bp)

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


def _dev_photo(filename: str, role: str, label: str, caption: str) -> dict:
    """A dev-preview photo backed by a real avatar PNG (stand-in for a patient photo)."""
    return {
        'url': url_for('static', filename=f'photos/avatars/{filename}'),
        'stored_filename': filename,
        'photo_role': role,
        'role_label': label,
        'caption': caption,
    }


# Dev-preview photo specs (override count with ?photos=0..3 to test fallback).
_DEV_PHOTO_SPECS = (
    ('2774646.png', 'before', 'Who I am', 'Me and the people who matter most.'),
    ('2774647.png', 'during', 'My kidney journey', 'Life around dialysis and treatment.'),
    ('2774648.png', 'hope', 'My hope after transplant', 'The life I hope to get back.'),
)


@app.route('/dev/microsite-preview')
def dev_microsite_preview():
    """Render a local-only campaign preview without running the interview.

    Uses the SAME shared builder as the real page (microsite._campaign_context) so the
    preview can never drift from production. Add ?photos=0..3 to test photo fallback.
    """
    if not FLASK_DEBUG and not config('ENABLE_DEV_ROUTES', default=False, cast=bool):
        abort(404)

    name = request.args.get('name', 'Miles Davidson').strip() or 'Miles Davidson'
    try:
        photo_count = max(0, min(3, int(request.args.get('photos', 3))))
    except (TypeError, ValueError):
        photo_count = 3

    content = {
        'headline': "I want more time with the people I love.",
        'short_intro': (
            "I'm living with kidney failure, and a living-donor transplant would give me back time, energy, "
            "and everyday moments with the people I love. Sharing my story might help me find a match."
        ),
        'personal_identity': (
            "I'm a husband, father, and friend, and being there for my family is what matters most to me. "
            "The people closest to me would say I'm steady, hopeful, and always showing up for the people I love."
        ),
        'kidney_journey': (
            "Kidney failure has become part of my daily life. Treatment, appointments, and careful health "
            "decisions now shape the rhythm of every week."
        ),
        'daily_impact': (
            "The fatigue, the diet limits, the pain, and the hours treatment takes can make ordinary days hard. "
            "Even simple things, like climbing the stairs or having the energy for family time, can be a struggle."
        ),
        'transplant_hope': (
            "A transplant could give me fuller days again: playing with my kids, working more consistently, "
            "being active, and feeling strong enough to be present for my family."
        ),
        'donor_message': (
            "A donor wouldn't just be helping me. Your generosity could give my whole family more time, more "
            "hope, and a chance to imagine life beyond kidney failure."
        ),
    }
    photo_items = [_dev_photo(*spec) for spec in _DEV_PHOTO_SPECS[:photo_count]]
    if request.args.get('headline') == 'long':
        content['headline'] = (
            "I am hoping with all my heart to find a living kidney donor so I can keep being here for my family"
        )
    hero_choice = None
    try:
        hi = request.args.get('hero')
        if hi is not None and photo_items:
            hero_choice = photo_items[max(0, min(len(photo_items) - 1, int(hi)))]['stored_filename']
    except (TypeError, ValueError):
        hero_choice = None
    url = request.url
    campaign = microsite._campaign_context(name, content, url, photo_items, preview=True, hero_choice=hero_choice)
    hero = (campaign.get('photos') or {}).get('hero') or {}
    return render_template(
        'microsite.html',
        name=name,
        content=content,
        photos=[item['url'] for item in photo_items],
        photo_items=photo_items,
        url=url,
        campaign=campaign,
        meta_title=f'{name} Needs a Kidney | Can You Help?',
        meta_description=content['short_intro'],
        meta_image=hero.get('url') or (photo_items[0]['url'] if photo_items else ''),
        share_text=f"Please read and share {name}'s kidney donor story: {url}",
    )


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
    session = ensure_session(session_id)
    if not session:
        return 'Session not found or expired', 404
    token = request.args.get('token')
    info_state = session['info_state']
    visit_id = info_state.user.query('visit_id')
    if not db.validate_upload_token(visit_id, token, mark_used=False):
        abort(404)
    return render_template('upload_mobile.html', session_id=session_id, upload_token=token)


@app.route('/site/<session_id>')
def serve_microsite(session_id):
    """Serve the approved donor page stored in the database."""
    page = db.get_published_page(session_id)
    if not page:
        abort(404)
    if page.get('rendered_html'):
        return Response(page['rendered_html'], mimetype='text/html')

    # Compatibility for pages published before rendered HTML moved into SQLite.
    abs_microsites_dir = os.path.abspath(MICROSITES_DIR)
    return send_from_directory(abs_microsites_dir, f'{session_id}.html')


@app.route('/static/microsites/<path:filename>')
def block_raw_microsite_static(filename):
    """Prevent bypassing publication status through Flask's static route."""
    abort(404)


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
