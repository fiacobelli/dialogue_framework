"""Read-only screening database viewer and exports."""

import csv
import io
import os
import sqlite3
import tempfile
from functools import wraps
from hmac import compare_digest

from flask import (
    Blueprint,
    after_this_request,
    redirect,
    render_template,
    request,
    Response,
    send_file,
    session,
    url_for,
)

from .config import DB_PATH, SCREENING_ADMIN_PASSWORD, SCREENING_ADMIN_USERNAME

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_TABLES = {
    'patients': 'created_at DESC',
    'visits': 'started_at DESC',
    'messages': 'id DESC',
    'turn_events': 'id DESC',
    'referrals': 'classified_at DESC',
    'info_state': 'updated_at DESC',
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(sql, params).fetchall()


def _one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(sql, params).fetchone()


def _count(sql: str, params: tuple = ()) -> int:
    row = _one(sql, params)
    return int(row[0]) if row else 0


def _admin_ready() -> bool:
    return bool(SCREENING_ADMIN_PASSWORD)


def _is_admin() -> bool:
    return bool(session.get('screening_admin_authenticated'))


def _safe_next(value: str | None) -> str:
    if value and value.startswith('/admin'):
        return value
    return url_for('admin.dashboard')


def _require_admin(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _admin_ready():
            return render_template(
                'screening_admin.html',
                mode='locked',
                title='Screening Database Admin',
            ), 503
        if not _is_admin():
            return redirect(url_for('admin.login', next=request.full_path))
        return func(*args, **kwargs)
    return wrapper


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if not _admin_ready():
        return render_template(
            'screening_admin.html',
            mode='locked',
            title='Screening Database Admin',
        ), 503

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        valid_user = compare_digest(username, SCREENING_ADMIN_USERNAME)
        valid_password = compare_digest(password, SCREENING_ADMIN_PASSWORD)
        if valid_user and valid_password:
            session['screening_admin_authenticated'] = True
            return redirect(_safe_next(request.args.get('next')))
        error = 'Invalid username or password.'

    return render_template(
        'screening_admin.html',
        mode='login',
        title='Screening Database Admin',
        error=error,
    )


@admin_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('screening_admin_authenticated', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@_require_admin
def dashboard():
    recent_visits = _rows(
        """
        SELECT
            v.visit_id, v.phone_pin, v.visit_number, v.avatar_id, v.language,
            v.phase, v.started_at, v.completed_at, v.total_turns,
            COUNT(m.id) AS message_count,
            MAX(m.timestamp) AS last_message_at
        FROM visits v
        LEFT JOIN messages m ON m.visit_id = v.visit_id
        GROUP BY v.visit_id
        ORDER BY v.started_at DESC
        LIMIT 40
        """
    )
    metrics = {
        'patients': _count('SELECT COUNT(*) FROM patients'),
        'visits': _count('SELECT COUNT(*) FROM visits'),
        'completed_visits': _count(
            "SELECT COUNT(*) FROM visits WHERE phase IN ('REPORT', 'COMPLETE')"
        ),
        'messages': _count('SELECT COUNT(*) FROM messages'),
        'turn_events': _count('SELECT COUNT(*) FROM turn_events'),
        'referrals': _count('SELECT COUNT(*) FROM referrals'),
    }
    grouped = {
        'Visits by phase': _rows(
            "SELECT COALESCE(phase, 'unknown') AS label, COUNT(*) AS count "
            "FROM visits GROUP BY phase ORDER BY count DESC"
        ),
        'Visits by avatar': _rows(
            "SELECT COALESCE(avatar_id, 'unknown') AS label, COUNT(*) AS count "
            "FROM visits GROUP BY avatar_id ORDER BY count DESC"
        ),
        'Question categories': _rows(
            "SELECT COALESCE(question_category, 'uncategorized') AS label, COUNT(*) AS count "
            "FROM messages WHERE role = 'assistant' GROUP BY question_category ORDER BY count DESC"
        ),
        'Input modalities': _rows(
            "SELECT COALESCE(input_modality, 'unknown') AS label, COUNT(*) AS count "
            "FROM messages WHERE role = 'user' GROUP BY input_modality ORDER BY count DESC"
        ),
    }
    timing = _one(
        """
        SELECT
            ROUND(AVG(response_latency_ms), 1) AS avg_response_latency_ms,
            ROUND(AVG(llm_latency_ms), 1) AS avg_llm_latency_ms,
            ROUND(AVG(speech_confidence), 3) AS avg_speech_confidence
        FROM messages
        """
    )
    return render_template(
        'screening_admin.html',
        mode='dashboard',
        title='Screening Database Admin',
        tables=ALLOWED_TABLES.keys(),
        metrics=metrics,
        grouped=grouped,
        timing=timing,
        recent_visits=recent_visits,
    )


@admin_bp.route('/visit/<visit_id>')
@_require_admin
def visit_detail(visit_id: str):
    visit = _one('SELECT * FROM visits WHERE visit_id = ?', (visit_id,))
    if not visit:
        return render_template(
            'screening_admin.html',
            mode='not_found',
            title='Visit Not Found',
            message='That screening visit was not found.',
        ), 404
    messages = _rows(
        'SELECT * FROM messages WHERE visit_id = ? ORDER BY id ASC',
        (visit_id,),
    )
    events = _rows(
        'SELECT * FROM turn_events WHERE visit_id = ? ORDER BY id ASC',
        (visit_id,),
    )
    referral = _one('SELECT * FROM referrals WHERE visit_id = ?', (visit_id,))
    state = _rows(
        'SELECT * FROM info_state WHERE phone_pin = ? ORDER BY type',
        (visit['phone_pin'],),
    )
    return render_template(
        'screening_admin.html',
        mode='visit',
        title=f"Visit {visit['visit_number']} - {visit['phone_pin']}",
        tables=ALLOWED_TABLES.keys(),
        visit=visit,
        messages=messages,
        events=events,
        referral=referral,
        state=state,
    )


@admin_bp.route('/table/<table_name>')
@_require_admin
def table_view(table_name: str):
    if table_name not in ALLOWED_TABLES:
        return render_template(
            'screening_admin.html',
            mode='not_found',
            title='Table Not Found',
            message='That table is not available through this read-only viewer.',
        ), 404
    limit = min(max(request.args.get('limit', 100, type=int), 10), 1000)
    offset = max(request.args.get('offset', 0, type=int), 0)
    order_by = ALLOWED_TABLES[table_name]
    total = _count(f'SELECT COUNT(*) FROM {table_name}')
    data = _rows(
        f'SELECT * FROM {table_name} ORDER BY {order_by} LIMIT ? OFFSET ?',
        (limit, offset),
    )
    columns = data[0].keys() if data else [row['name'] for row in _rows(f'PRAGMA table_info({table_name})')]
    return render_template(
        'screening_admin.html',
        mode='table',
        title=f'{table_name} table',
        tables=ALLOWED_TABLES.keys(),
        table_name=table_name,
        rows=data,
        columns=columns,
        limit=limit,
        offset=offset,
        total=total,
    )


@admin_bp.route('/download/table/<table_name>.csv')
@_require_admin
def download_table(table_name: str):
    if table_name not in ALLOWED_TABLES:
        return Response('Unknown table', status=404)
    order_by = ALLOWED_TABLES[table_name]
    data = _rows(f'SELECT * FROM {table_name} ORDER BY {order_by}')
    columns = data[0].keys() if data else [row['name'] for row in _rows(f'PRAGMA table_info({table_name})')]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in data:
        writer.writerow([row[col] for col in columns])
    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=screening_{table_name}.csv'},
    )


@admin_bp.route('/download/database')
@_require_admin
def download_database():
    fd, tmp_path = tempfile.mkstemp(prefix='sdoh-screening-', suffix='.db')
    os.close(fd)

    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(tmp_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    @after_this_request
    def cleanup(response):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return response

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name='sdoh-screening.db',
        mimetype='application/x-sqlite3',
    )
