from flask import Flask, request, jsonify, render_template, send_from_directory
from decouple import config
import uuid
import os
import json
import re

from information_state import InformationState
from dialogue_manager import DialogueManager
from nlu_web import NLUWeb
from nlg import NLG
from rules_web import RuleManagerWeb
from goal_interview import InterviewGoalManager
from llm_provider import get_provider
from strings import MSG, BELSTR

app = Flask(__name__)
app.secret_key = config('FLASK_SECRET_KEY', default='dev-secret')

sessions = {}

# Config
KB_FILE = config('KB_FILE', default='domains/dialysis_chat.json')
USER_MODELS_DIR = config('USER_MODELS_DIR', default='user_models')
PHOTOS_DIR = config('PHOTOS_DIR', default='photos')
MICROSITES_DIR = config('MICROSITES_DIR', default='static/microsites')
SYSTEM_PROMPT_FILE = config('SYSTEM_PROMPT_FILE', default='prompts/interviewer.txt')

# Language names for LLM instruction
LANGUAGE_NAMES = {'en': 'English', 'es': 'Spanish', 'ar': 'Arabic'}

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(MICROSITES_DIR, exist_ok=True)


def load_prompt(filepath: str) -> str:
    try:
        with open(filepath, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return 'You are a helpful assistant.'


def create_session(session_id: str) -> dict:
    user_file = os.path.join(USER_MODELS_DIR, f'{session_id}.pkl')

    info_state = InformationState(user_file, KB_FILE)
    info_state.bel.add(BELSTR.DONE, False)

    nlu = NLUWeb()

    nlg = NLG()
    nlg.setup(info_state.special_texts)

    rule_mgr = RuleManagerWeb()
    rule_mgr.setup()

    provider_name = config('LLM_PROVIDER', default='ollama')
    provider_kwargs = {'model': config('LLM_MODEL', default='mistral:7b-instruct')}
    if provider_name == 'groq':
        provider_kwargs['api_key'] = config('GROQ_API_KEY')
    provider = get_provider(provider_name, **provider_kwargs)
    goal_mgr = InterviewGoalManager(provider, load_prompt(SYSTEM_PROMPT_FILE))

    dialogue_mgr = DialogueManager()
    dialogue_mgr.setup(info_state, rule_mgr, goal_mgr)

    return {
        'info_state': info_state,
        'dialogue_mgr': dialogue_mgr,
        'goal_mgr': goal_mgr,
        'nlu': nlu,
        'nlg': nlg,
        'msg': {}
    }


@app.route('/')
def index():
    return render_template('interview.html')


@app.route('/api/session', methods=['GET', 'POST'])
def new_session():
    patient_id = None
    lang = request.args.get('lang', 'en')

    if request.method == 'POST' and request.json:
        patient_id = request.json.get('patient_id')
        lang = request.json.get('lang', lang)

    session_id = patient_id or str(uuid.uuid4())
    sessions[session_id] = create_session(session_id)

    info_state = sessions[session_id]['info_state']
    goal_mgr = sessions[session_id]['goal_mgr']

    # Store language preference in session
    info_state.user.update('language', lang)
    info_state.save_user_model()

    phase = info_state.user.query('interview_phase') or 'BEFORE'
    is_returning = phase != 'BEFORE'

    opening = goal_mgr.get_opening(info_state, lang)
    if is_returning:
        welcome_back = {'en': 'Welcome back!', 'es': '¡Bienvenido de nuevo!', 'ar': 'مرحباً بعودتك!'}
        opening = f"{welcome_back.get(lang, 'Welcome back!')} {opening}"

    return jsonify({
        'session_id': session_id,
        'prompt': opening,
        'phase': phase,
        'returning': is_returning
    })


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

    phase = info_state.user.query('interview_phase') or 'BEFORE'
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
    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo'}), 400

    photo = request.files['photo']
    info_state = sessions[session_id]['info_state']

    photos = info_state.user.query('photos') or []
    if len(photos) >= 3:
        return jsonify({'error': 'Max 3 photos'}), 400

    # Save photo
    photo_id = f"{session_id}_{len(photos)}.jpg"
    photo_path = os.path.join(PHOTOS_DIR, photo_id)
    photo.save(photo_path)

    photos.append(photo_id)
    info_state.user.update('photos', photos)
    info_state.save_user_model()

    if len(photos) >= 3:
        info_state.user.update('interview_phase', 'COMPLETE')
        info_state.save_user_model()

    return jsonify({
        'status': 'ok',
        'photo_count': len(photos),
        'ready': len(photos) >= 3
    })


MICROSITE_PROMPT_FILE = config('MICROSITE_PROMPT_FILE', default='prompts/microsite.txt')


def parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in code block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    # Try to find raw JSON
    match = re.search(r'\{[^{}]*"headline"[^{}]*\}', text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


@app.route('/api/generate', methods=['POST'])
def generate_microsite():
    data = request.json
    session_id = data.get('session_id')

    if not session_id or session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    s = sessions[session_id]
    info_state = s['info_state']
    provider = s['goal_mgr'].goal.llm  # Reuse existing provider

    # Gather interview data
    before = ' '.join(info_state.user.query('interview_before') or [])
    during = ' '.join(info_state.user.query('interview_during') or [])
    hope = ' '.join(info_state.user.query('interview_hope') or [])
    photos = info_state.user.query('photos') or []
    name = data.get('name', 'Patient')

    # Load and format prompt
    prompt_template = load_prompt(MICROSITE_PROMPT_FILE)
    prompt = prompt_template.format(name=name, before=before, during=during, hope=hope)

    raw_content = provider.generate([{"role": "user", "content": prompt}])

    # Parse JSON from LLM response
    try:
        content_json = parse_llm_json(raw_content)
    except (json.JSONDecodeError, AttributeError):
        # Fallback if JSON parsing fails
        content_json = {
            'headline': f"{name} needs a kidney donor",
            'my_story': raw_content[:500] if raw_content else "My story...",
            'my_struggle': "Living with kidney disease has been challenging...",
            'my_hope': "A kidney transplant would change my life..."
        }

    # Build microsite URL
    base_url = request.host_url.rstrip('/')
    microsite_url = f"{base_url}/site/{session_id}"

    # Render HTML template
    photo_urls = [f"/photos/{p}" for p in photos]
    html = render_template('microsite.html',
        name=name,
        headline=content_json.get('headline', ''),
        my_story=content_json.get('my_story', ''),
        my_struggle=content_json.get('my_struggle', ''),
        my_hope=content_json.get('my_hope', ''),
        photos=photo_urls,
        url=microsite_url
    )

    # Save to file
    filepath = os.path.join(MICROSITES_DIR, f'{session_id}.html')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    # Build response data
    microsite = {
        'name': name,
        'content': raw_content,
        'photos': photo_urls,
        'before': before,
        'during': during,
        'hope': hope,
        'microsite_url': f'/site/{session_id}',
        **content_json
    }

    info_state.user.update('microsite', microsite)
    info_state.save_user_model()

    return jsonify(microsite)


@app.route('/photos/<filename>')
def serve_photo(filename):
    return send_from_directory(PHOTOS_DIR, filename)


@app.route('/site/<session_id>')
def serve_microsite(session_id):
    return send_from_directory(MICROSITES_DIR, f'{session_id}.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
