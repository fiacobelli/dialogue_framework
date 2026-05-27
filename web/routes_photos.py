"""Photo and QR code routes blueprint."""

from flask import Blueprint, request, jsonify, url_for
from flask import send_from_directory
import os
import io
import base64
import hashlib

import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import PHOTOS_DIR, MAX_PHOTOS, MAX_PHOTO_UPLOAD_BYTES
from .session_store import ensure_session, get_session, persist_session_state
from . import database as db
from .patient_auth import is_patient_authorized, patient_token

photos_bp = Blueprint('photos', __name__, url_prefix='/api')

MAX_IMAGE_EDGE = 1600
JPEG_QUALITY = 88
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
PHOTO_ROLE_LABELS = {
    'before': 'Who I am',
    'during': 'My kidney journey',
    'hope': 'My hope after transplant',
    'general': 'Story photo',
}


def _upload_buffer(upload) -> io.BytesIO:
    """Read the uploaded file once while enforcing a raw upload size limit."""
    data = upload.stream.read(MAX_PHOTO_UPLOAD_BYTES + 1)
    if len(data) > MAX_PHOTO_UPLOAD_BYTES:
        max_mb = max(1, MAX_PHOTO_UPLOAD_BYTES // (1024 * 1024))
        raise ValueError(f'Photo is too large. Please upload an image under {max_mb} MB.')
    return io.BytesIO(data)


def _save_processed_photo(upload, photo_path: str) -> tuple[int, int]:
    """Validate, orient, resize, and save an uploaded image as JPEG."""
    try:
        image = Image.open(_upload_buffer(upload))
        if image.format not in ALLOWED_IMAGE_FORMATS:
            allowed = ', '.join(sorted(ALLOWED_IMAGE_FORMATS))
            raise ValueError(f'Please upload a JPEG, PNG, or WEBP image. Detected: {image.format or "unknown"}.')
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


def _photo_urls(session_id: str, photos: list[str], token: str | None = None) -> list[str]:
    return [
        url_for('photos.photo_preview', session_id=session_id, filename=p, patient_token=token)
        if token else url_for('photos.photo_preview', session_id=session_id, filename=p)
        for p in photos
    ]


def _photo_items(session_id: str, visit_id: str | None, token: str | None = None) -> list[dict]:
    items = []
    for photo in db.list_visit_photos(visit_id):
        role = photo.get('photo_role') or 'general'
        items.append({
            'stored_filename': photo['stored_filename'],
            'url': url_for('photos.photo_preview', session_id=session_id, filename=photo['stored_filename'], patient_token=token)
            if token else url_for('photos.photo_preview', session_id=session_id, filename=photo['stored_filename']),
            'display_order': photo['display_order'],
            'photo_role': role,
            'role_label': PHOTO_ROLE_LABELS.get(role, 'General'),
            'caption': photo.get('caption') or '',
        })
    return items


def _sync_session_photos(session_id: str, session: dict, photos: list[str]) -> None:
    info_state = session['info_state']
    info_state.user.update('photos', photos)
    persist_session_state(session_id, session)


def _current_photos(session_id: str, session: dict) -> list[str]:
    info_state = session['info_state']
    visit_id = info_state.user.query('visit_id')
    db_photos = db.list_visit_photo_filenames(visit_id)
    if db_photos:
        if db_photos != (info_state.user.query('photos') or []):
            _sync_session_photos(session_id, session, db_photos)
        return db_photos
    return info_state.user.query('photos') or []


def _mobile_upload_authorized(visit_id: str | None) -> bool:
    source = request.form.get('source') or 'desktop'
    if source != 'mobile':
        return True
    return db.validate_upload_token(visit_id, request.form.get('upload_token'))


def _replacement_photo_id(visit_id: str | None) -> str | None:
    """Return an existing photo filename requested for replacement."""
    photos = db.list_visit_photos(visit_id)
    filenames = {photo['stored_filename'] for photo in photos}
    requested = (request.form.get('replace_filename') or '').strip()
    if requested:
        return requested if requested in filenames else None

    replace_index = (request.form.get('replace_index') or '').strip()
    if replace_index.isdigit():
        index = int(replace_index)
        if 0 <= index < len(photos):
            return photos[index]['stored_filename']
    return None


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
    if (request.form.get('source') or 'desktop') != 'mobile' and not is_patient_authorized(info_state):
        return jsonify({'error': 'unauthorized_session'}), 403
    if not _mobile_upload_authorized(visit_id):
        return jsonify({'error': 'Photo upload link is expired. Please scan the current QR code again.'}), 403

    replace_photo_id = _replacement_photo_id(visit_id)
    wants_replacement = bool(request.form.get('replace_filename') or request.form.get('replace_index'))
    if wants_replacement and not replace_photo_id:
        return jsonify({'error': 'Photo to replace was not found for this session'}), 400

    existing_photos = _current_photos(session_id, s)
    if not replace_photo_id and len(existing_photos) >= MAX_PHOTOS:
        return jsonify({'error': f'Max {MAX_PHOTOS} photos already uploaded'}), 400

    reservation = None if replace_photo_id else db.reserve_photo_slot(visit_id, session_id, MAX_PHOTOS)
    if not replace_photo_id and not reservation:
        return jsonify({'error': f'Max {MAX_PHOTOS} photos already uploaded'}), 400

    photo_id = replace_photo_id or reservation['stored_filename']
    photo_path = os.path.join(PHOTOS_DIR, photo_id)
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        width, height = _save_processed_photo(photo, photo_path)
        byte_size = os.path.getsize(photo_path)
        with open(photo_path, 'rb') as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
    except ValueError as exc:
        if reservation:
            db.release_photo_reservation(visit_id, photo_id)
        return jsonify({'error': str(exc)}), 400
    except OSError:
        if reservation:
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
    _sync_session_photos(session_id, s, photos)

    if len(photos) >= MAX_PHOTOS:
        info_state.user.update('interview_phase', 'COMPLETE')
        info_state.user.update('photo_requirement_status', 'complete')
        persist_session_state(session_id, s)
        db.revoke_upload_tokens(visit_id, reason='photo_requirement_complete')
    db.update_visit_from_info_state(visit_id, info_state)

    return jsonify({
        'status': 'ok',
        'photo_count': len(photos),
        'max_photos': MAX_PHOTOS,
        'photos': _photo_urls(session_id, photos, patient_token(info_state)),
        'photo_items': _photo_items(session_id, visit_id, patient_token(info_state)),
        'replaced': bool(replace_photo_id),
        'ready': len(photos) >= MAX_PHOTOS
    })


@photos_bp.route('/photos/<session_id>')
def get_photo_status(session_id):
    """Get photo upload status for a session (for polling)."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state):
        return jsonify({'error': 'unauthorized_session'}), 403
    token = request.args.get('token')
    visit_id = info_state.user.query('visit_id')
    if token and not db.validate_upload_token(visit_id, token, mark_used=False):
        return jsonify({'error': 'Photo upload link is expired. Please scan the current QR code again.'}), 403
    photos = _current_photos(session_id, s)

    return jsonify({
        'photo_count': len(photos),
        'ready': len(photos) >= MAX_PHOTOS,
        'max_photos': MAX_PHOTOS,
        'photos': _photo_urls(session_id, photos, patient_token(info_state)),
        'photo_items': _photo_items(session_id, visit_id, patient_token(info_state)),
    })


@photos_bp.route('/photos/<session_id>/metadata', methods=['POST'])
def update_photo_metadata(session_id):
    """Update photo role/order metadata before donor-page generation."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state, request.json or {}):
        return jsonify({'error': 'unauthorized_session'}), 403
    visit_id = info_state.user.query('visit_id')
    items = (request.json or {}).get('photos') or []
    updated = db.update_visit_photo_metadata(visit_id, items)
    filenames = [item['stored_filename'] for item in updated]
    _sync_session_photos(session_id, s, filenames)
    db.update_visit_from_info_state(visit_id, info_state)

    return jsonify({
        'status': 'ok',
        'photo_count': len(updated),
        'max_photos': MAX_PHOTOS,
        'photos': _photo_urls(session_id, filenames, patient_token(info_state)),
        'photo_items': _photo_items(session_id, visit_id, patient_token(info_state)),
        'ready': len(updated) >= MAX_PHOTOS,
    })


@photos_bp.route('/photo-preview/<session_id>/<filename>')
def photo_preview(session_id, filename):
    """Serve uploaded photos for the active private review session."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404
    if db.is_session_deleted(session_id):
        return jsonify({'error': 'Session not found'}), 404
    s = get_session(session_id)
    info_state = s['info_state']
    if not is_patient_authorized(info_state):
        return jsonify({'error': 'unauthorized_session'}), 403
    photos = _current_photos(session_id, s)
    if filename not in photos:
        return jsonify({'error': 'Photo not found for this session'}), 404
    return send_from_directory(os.path.abspath(PHOTOS_DIR), filename)


@photos_bp.route('/qr/<session_id>')
def get_qr_code(session_id):
    """Generate QR code for mobile photo upload."""
    if not ensure_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    info_state = get_session(session_id)['info_state']
    if not is_patient_authorized(info_state):
        return jsonify({'error': 'unauthorized_session'}), 403
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
