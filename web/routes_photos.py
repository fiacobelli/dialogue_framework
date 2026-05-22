"""Photo and QR code routes blueprint."""

from flask import Blueprint, request, jsonify, url_for
import os
import io
import base64
import hashlib

import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import PHOTOS_DIR, MAX_PHOTOS
from .session_store import get_session, has_session
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


@photos_bp.route('/upload', methods=['POST'])
def upload_photo():
    """Handle photo upload from web or mobile."""
    session_id = request.form.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session_id provided'}), 400
    if not has_session(session_id):
        return jsonify({'error': f'Session not found: {session_id[:8]}...'}), 400

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo in request'}), 400

    photo = request.files['photo']
    if not photo.filename:
        return jsonify({'error': 'Empty photo filename'}), 400

    s = get_session(session_id)
    info_state = s['info_state']

    photos = info_state.user.query('photos') or []
    if len(photos) >= MAX_PHOTOS:
        return jsonify({'error': f'Max {MAX_PHOTOS} photos already uploaded'}), 400

    photo_id = f"{session_id}_{len(photos)}.jpg"
    photo_path = os.path.join(PHOTOS_DIR, photo_id)
    try:
        width, height = _save_processed_photo(photo, photo_path)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    byte_size = os.path.getsize(photo_path)
    with open(photo_path, 'rb') as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    photos.append(photo_id)
    info_state.user.update('photos', photos)
    info_state.save_user_model()
    db.save_photo(
        info_state.user.query('visit_id'),
        photo_id,
        len(photos) - 1,
        source=request.form.get('source') or 'desktop',
        mime_type='image/jpeg',
        byte_size=byte_size,
        sha256=sha256,
        width=width,
        height=height,
    )

    if len(photos) >= MAX_PHOTOS:
        info_state.user.update('interview_phase', 'COMPLETE')
        info_state.save_user_model()
    db.update_visit_from_info_state(info_state.user.query('visit_id'), info_state)

    return jsonify({
        'status': 'ok',
        'photo_count': len(photos),
        'ready': len(photos) >= MAX_PHOTOS
    })


@photos_bp.route('/photos/<session_id>')
def get_photo_status(session_id):
    """Get photo upload status for a session (for polling)."""
    if not has_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    info_state = get_session(session_id)['info_state']
    photos = info_state.user.query('photos') or []

    return jsonify({
        'photo_count': len(photos),
        'ready': len(photos) >= MAX_PHOTOS,
        'max_photos': MAX_PHOTOS
    })


@photos_bp.route('/qr/<session_id>')
def get_qr_code(session_id):
    """Generate QR code for mobile photo upload."""
    if not has_session(session_id):
        return jsonify({'error': 'Session not found'}), 404

    upload_url = url_for('mobile_upload', session_id=session_id, _external=True)

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
        'upload_url': upload_url
    })
