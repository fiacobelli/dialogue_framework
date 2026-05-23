"""Photo and QR code routes blueprint."""

from flask import Blueprint, request, jsonify, url_for
from flask import send_from_directory
import os
import io
import base64
import hashlib

import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import PHOTOS_DIR, MAX_PHOTOS
from .session_store import ensure_session, get_session
from . import database as db

photos_bp = Blueprint('photos', __name__, url_prefix='/api')

MAX_IMAGE_EDGE = 1600
JPEG_QUALITY = 88


def _save_processed_photo(upload, photo_path: str) -> tuple[int, int]:
    """Validate, orient, resize, and save an uploaded image as JPEG."""
    try:
        image = Image.open(upload.stream)
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError):
        raise ValueError('Please upload a valid image file.')

    if image.mode not in {'RGB', 'L'}:
        image = image.convert('RGB')
    elif image.mode == 'L':
        image = image.convert('RGB')

    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    image.save(photo_path, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    return image.size


def _photo_urls(session_id: str, photos: list[str]) -> list[str]:
    return [url_for('photos.photo_preview', session_id=session_id, filename=p) for p in photos]


def _sync_session_photos(info_state, photos: list[str]) -> None:
    info_state.user.update('photos', photos)
    info_state.save_user_model()


def _current_photos(info_state) -> list[str]:
    visit_id = info_state.user.query('visit_id')
    db_photos = db.list_visit_photo_filenames(visit_id)
    if db_photos:
        if db_photos != (info_state.user.query('photos') or []):
            _sync_session_photos(info_state, db_photos)
        return db_photos
    return info_state.user.query('photos') or []


def _mobile_upload_authorized(visit_id: str | None) -> bool:
    source = request.form.get('source') or 'desktop'
    if source != 'mobile':
        return True
    return db.validate_upload_token(visit_id, request.form.get('upload_token'))


@photos_bp.route('/upload', methods=['POST'])
def upload_photo():
    """Handle photo upload from web or mobile."""
    session_id = request.form.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session_id provided'}), 400
    if not ensure_session(session_id):
        return jsonify({'error': f'Session not found: {session_id[:8]}...'}), 400

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo in request'}), 400

    photo = request.files['photo']
    if not photo.filename:
        return jsonify({'error': 'Empty photo filename'}), 400

    s = get_session(session_id)
    info_state = s['info_state']
    visit_id = info_state.user.query('visit_id')
    if not visit_id:
        return jsonify({'error': 'Visit not initialized for this session'}), 400
    if not _mobile_upload_authorized(visit_id):
        return jsonify({'error': 'Photo upload link is expired. Please scan the current QR code again.'}), 403

    existing_photos = _current_photos(info_state)
    if len(existing_photos) >= MAX_PHOTOS:
        return jsonify({'error': f'Max {MAX_PHOTOS} photos already uploaded'}), 400

    reservation = db.reserve_photo_slot(visit_id, session_id, MAX_PHOTOS)
    if not reservation:
        return jsonify({'error': f'Max {MAX_PHOTOS} photos already uploaded'}), 400

    photo_id = reservation['stored_filename']
    photo_path = os.path.join(PHOTOS_DIR, photo_id)
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        width, height = _save_processed_photo(photo, photo_path)
        byte_size = os.path.getsize(photo_path)
        with open(photo_path, 'rb') as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
    except ValueError as exc:
        db.release_photo_reservation(visit_id, photo_id)
        return jsonify({'error': str(exc)}), 400
    except OSError:
        db.release_photo_reservation(visit_id, photo_id)
        return jsonify({'error': 'Unable to save uploaded photo'}), 500

    db.finalize_photo_upload(
        visit_id,
        photo_id,
        source=request.form.get('source') or 'desktop',
        mime_type='image/jpeg',
        byte_size=byte_size,
        sha256=sha256,
        width=width,
        height=height,
    )
    photos = db.list_visit_photo_filenames(visit_id)
    _sync_session_photos(info_state, photos)

    if len(photos) >= MAX_PHOTOS:
        info_state.user.update('interview_phase', 'COMPLETE')
        info_state.user.update('photo_requirement_status', 'complete')
        info_state.save_user_model()
        db.revoke_upload_tokens(visit_id, reason='photo_requirement_complete')
    db.update_visit_from_info_state(visit_id, info_state)

    return jsonify({
        'status': 'ok',
        'photo_count': len(photos),
        'max_photos': MAX_PHOTOS,
        'photos': _photo_urls(session_id, photos),
        'ready': len(photos) >= MAX_PHOTOS
    })


@photos_bp.route('/photos/<session_id>')
def get_photo_status(session_id):
    """Get photo upload status for a session (for polling)."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    info_state = get_session(session_id)['info_state']
    token = request.args.get('token')
    visit_id = info_state.user.query('visit_id')
    if token and not db.validate_upload_token(visit_id, token, mark_used=False):
        return jsonify({'error': 'Photo upload link is expired. Please scan the current QR code again.'}), 403
    photos = _current_photos(info_state)

    return jsonify({
        'photo_count': len(photos),
        'ready': len(photos) >= MAX_PHOTOS,
        'max_photos': MAX_PHOTOS,
        'photos': _photo_urls(session_id, photos),
    })


@photos_bp.route('/photo-preview/<session_id>/<filename>')
def photo_preview(session_id, filename):
    """Serve uploaded photos for the active private review session."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404
    info_state = get_session(session_id)['info_state']
    photos = _current_photos(info_state)
    if filename not in photos:
        return jsonify({'error': 'Photo not found for this session'}), 404
    return send_from_directory(os.path.abspath(PHOTOS_DIR), filename)


@photos_bp.route('/qr/<session_id>')
def get_qr_code(session_id):
    """Generate QR code for mobile photo upload."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    info_state = get_session(session_id)['info_state']
    token = db.create_upload_token(info_state.user.query('visit_id'))
    if not token:
        return jsonify({'error': 'Visit not initialized for this session'}), 400

    upload_url = url_for(
        'mobile_upload',
        session_id=session_id,
        token=token['token'],
        _external=True,
    )

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upload_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return jsonify({
        'qr_image': f"data:image/png;base64,{qr_base64}",
        'upload_url': upload_url,
        'upload_token': token['token'],
        'expires_at': token['expires_at'],
    })
