from flask import Flask, request, jsonify, render_template, send_from_directory
from decouple import config
import uuid
import os

from strings import MSG
from .config import PHOTOS_DIR, MICROSITES_DIR, AVATAR_PROFILES, WELCOME_BACK, MAX_PHOTOS, FLASK_PORT, FLASK_DEBUG
from .session import create_session
from . import microsite

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')

sessions = {}

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(MICROSITES_DIR, exist_ok=True)


@app.route('/')
def index():
    return render_template('interview.html')


@app.route('/api/session', methods=['GET', 'POST'])
def new_session():
    patient_id = None
    lang = request.args.get('lang', 'en')
    avatar_id = request.args.get('avatar', 'sitepal')

    if request.method == 'POST' and request.json:
        patient_id = request.json.get('patient_id')
        lang = request.json.get('lang', lang)
        avatar_id = request.json.get('avatar', avatar_id)

    session_id = patient_id or str(uuid.uuid4())
    sessions[session_id] = create_session(session_id)

    info_state = sessions[session_id]['info_state']
    goal_mgr = sessions[session_id]['goal_mgr']

    avatar_profile = AVATAR_PROFILES.get(avatar_id, AVATAR_PROFILES['sitepal'])
    if lang == 'en' and avatar_profile['lang'] != 'en':
        lang = avatar_profile['lang']

    info_state.user.update('language', lang)
    info_state.user.update('avatar', avatar_id)
    info_state.user.update('avatar_profile', avatar_profile)
    info_state.save_user_model()

    phase = info_state.user.query('interview_phase') or 'WELCOME'
    is_returning = phase != 'WELCOME'

    avatar_name = avatar_profile.get('name', 'Assistant')
    opening = goal_mgr.get_opening(info_state, lang, avatar_name)
    if is_returning:
        opening = f"{WELCOME_BACK.get(lang, WELCOME_BACK['en'])} {opening}"

    return jsonify({
        'session_id': session_id,
        'prompt': opening,
        'phase': phase,
        'returning': is_returning,
        'avatar': avatar_profile
    })


@app.route('/api/avatars')
def get_avatars():
    return jsonify(AVATAR_PROFILES)


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    session_id = data.get('session_id')
    user_input = data.get('input', '').strip()

    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    s = sessions[session_id]
    info_state = s['info_state']
    dialogue_mgr = s['dialogue_mgr']
    nlu = s['nlu']
    nlg = s['nlg']
    msg = s['msg']

    msg[MSG.POSSIBLE_RESPONSES] = [(1.0, user_input)]

    if nlu.check(msg):
        dialogue_mgr.manage(msg)

    phase = info_state.user.query('interview_phase') or 'WELCOME'
    done = phase in ['PHOTOS', 'COMPLETE']
    prompt = nlg.get_prompt(msg)

    info_state.save_user_model()

    return jsonify({
        'prompt': prompt,
        'phase': phase,
        'done': done
    })


@app.route('/api/upload', methods=['POST'])
def upload_photo():
    session_id = request.form.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session_id provided'}), 400
    if session_id not in sessions:
        return jsonify({'error': f'Session not found: {session_id[:8]}...'}), 400

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo in request'}), 400

    photo = request.files['photo']
    if not photo.filename:
        return jsonify({'error': 'Empty photo filename'}), 400

    info_state = sessions[session_id]['info_state']

    photos = info_state.user.query('photos') or []
    if len(photos) >= MAX_PHOTOS:
        return jsonify({'error': f'Max {MAX_PHOTOS} photos already uploaded'}), 400

    photo_id = f"{session_id}_{len(photos)}.jpg"
    photo_path = os.path.join(PHOTOS_DIR, photo_id)
    photo.save(photo_path)

    photos.append(photo_id)
    info_state.user.update('photos', photos)
    info_state.save_user_model()

    if len(photos) >= MAX_PHOTOS:
        info_state.user.update('interview_phase', 'COMPLETE')
        info_state.save_user_model()

    return jsonify({
        'status': 'ok',
        'photo_count': len(photos),
        'ready': len(photos) >= 3
    })


@app.route('/api/generate', methods=['POST'])
def generate_microsite():
    data = request.json
    session_id = data.get('session_id')

    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    s = sessions[session_id]
    info_state = s['info_state']
    provider = s['goal_mgr'].goal.llm
    name = data.get('name', 'Patient')
    base_url = request.host_url.rstrip('/')

    try:
        result = microsite.generate(info_state, provider, name, base_url, session_id)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/photos/<filename>')
def serve_photo(filename):
    abs_photos_dir = os.path.abspath(PHOTOS_DIR)
    return send_from_directory(abs_photos_dir, filename)


@app.route('/site/<session_id>')
def serve_microsite(session_id):
    abs_microsites_dir = os.path.abspath(MICROSITES_DIR)
    return send_from_directory(abs_microsites_dir, f'{session_id}.html')


if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
