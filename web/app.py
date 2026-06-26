"""Flask application entry point for the dialogue framework."""

from flask import Flask, render_template, send_from_directory, request, abort
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


def _dev_photo(label: str, fill: str) -> dict:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">'
        f'<rect width="1200" height="900" fill="{fill}"/>'
        '<circle cx="920" cy="130" r="220" fill="rgba(255,255,255,0.35)"/>'
        '<circle cx="240" cy="730" r="260" fill="rgba(255,255,255,0.25)"/>'
        '<rect x="120" y="230" width="960" height="440" rx="42" fill="rgba(255,255,255,0.52)"/>'
        f'<text x="600" y="430" text-anchor="middle" font-family="Montserrat, Arial, sans-serif" '
        f'font-size="54" font-weight="800" fill="#113459">{label}</text>'
        '<text x="600" y="500" text-anchor="middle" font-family="Montserrat, Arial, sans-serif" '
        'font-size="28" font-weight="600" fill="#526173">Sample image for design preview</text>'
        '</svg>'
    )
    return {
        'url': f'data:image/svg+xml;charset=UTF-8,{quote(svg)}',
        'role_label': label,
        'caption': label,
        'photo_role': 'general',
    }


@app.route('/dev/microsite-preview')
def dev_microsite_preview():
    """Render a local-only campaign preview without running the interview."""
    if not FLASK_DEBUG and not config('ENABLE_DEV_ROUTES', default=False, cast=bool):
        abort(404)

    name = request.args.get('name', 'Miles Davidson').strip() or 'Miles Davidson'
    content = {
        'headline': f'{name} Is Searching for a Living Kidney Donor',
        'short_intro': (
            f'{name} is sharing this story while living with kidney failure. A kidney transplant could help '
            'restore time, energy, and the everyday family moments that matter most.'
        ),
        'personal_identity': (
            f'{name} is a husband, father, and community member who cares deeply about being present for family. '
            'The people closest to him describe him as steady, hopeful, and committed to the people he loves.'
        ),
        'kidney_journey': (
            'Kidney failure has become part of daily life, with treatment, appointments, and health decisions '
            'shaping the rhythm of each week.'
        ),
        'daily_impact': (
            'The physical strain, diet limits, pain, and time required for treatment can make ordinary routines '
            'feel difficult. Even simple activities, like climbing stairs or having enough energy for family time, '
            'can become harder.'
        ),
        'transplant_hope': (
            'A transplant could make it possible to return to fuller days: playing with children, working more '
            'consistently, being active again, and feeling stronger for family life.'
        ),
        'donor_message': (
            'A donor would not just be helping one person. Their generosity could give a family more time, more hope, '
            'and a chance to imagine life beyond kidney failure.'
        ),
    }
    photo_items = [
        _dev_photo('Who I am', '#DAE7F7'),
        _dev_photo('My kidney journey', '#E6F2E2'),
        _dev_photo('Hope after transplant', '#C7E3FF'),
    ]
    url = request.url
    share_text = f"Please read and share {name}'s kidney donor story: {url}"
    share_url = quote(url, safe='')
    encoded_share_text = quote(share_text, safe='')
    campaign = {
        'preview': True,
        'title': f'{name} Needs a Kidney',
        'story_highlight': content['donor_message'],
        'donor_callout': 'Sharing this page can help more people learn about the need for a living kidney donor and the difference support can make.',
        'primary_cta': {'label': 'Share This Page', 'href': '#share'},
        'secondary_cta': {'label': 'Learn About Living Donation', 'href': 'https://www.kidney.org/kidney-topics/living-donation'},
        'share': {
            'facebook': f'https://www.facebook.com/sharer/sharer.php?u={share_url}',
            'whatsapp': f'https://wa.me/?text={encoded_share_text}',
            'email': f'mailto:?subject={quote(f"{name} Needs a Kidney", safe="")}&body={encoded_share_text}',
        },
    }
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
        meta_image='',
        share_text=share_text,
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
