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

from .config import (
    DB_PATH,
    SCREENING_ADMIN_COHORT_ALIAS_MAP,
    SCREENING_ADMIN_COHORT_CANONICAL_IDS,
    SCREENING_ADMIN_COHORT_EXCLUDED_ALIAS_MAP,
    SCREENING_ADMIN_COHORT_NAME,
    SCREENING_ADMIN_PASSWORD,
    SCREENING_ADMIN_USERNAME,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ALLOWED_TABLES = {
    'patients': 'created_at DESC',
    'visits': 'started_at DESC',
    'messages': 'id DESC',
    'turn_events': 'id DESC',
    'referrals': 'classified_at DESC',
    'info_state': 'updated_at DESC',
}

def _split_ids(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(',') if item.strip())


def _parse_alias_map(value: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in value.split(','):
        if not item.strip() or ':' not in item:
            continue
        alias, canonical = item.split(':', 1)
        aliases[alias.strip()] = canonical.strip()
    return aliases


COHORT_CANONICAL_IDS = _split_ids(SCREENING_ADMIN_COHORT_CANONICAL_IDS)
COHORT_USABLE_ALIAS_IDS = _parse_alias_map(SCREENING_ADMIN_COHORT_ALIAS_MAP)
COHORT_EXCLUDED_ALIAS_IDS = _parse_alias_map(SCREENING_ADMIN_COHORT_EXCLUDED_ALIAS_MAP)
COHORT_INCLUDED_IDS = COHORT_CANONICAL_IDS + tuple(COHORT_USABLE_ALIAS_IDS.keys())


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


def _cohort_filter(column: str) -> tuple[str, tuple[str, ...]]:
    if not COHORT_INCLUDED_IDS:
        return '1 = 0', ()
    placeholders = ','.join('?' for _ in COHORT_INCLUDED_IDS)
    return f'{column} IN ({placeholders})', COHORT_INCLUDED_IDS


def _visit_cohort_clause(alias: str = 'v') -> tuple[str, tuple[str, ...]]:
    return _cohort_filter(f'{alias}.phone_pin')


def _table_columns(table_name: str) -> list[str]:
    return [row['name'] for row in _rows(f'PRAGMA table_info({table_name})')]


def _cohort_table_sql(table_name: str, *, count: bool = False) -> tuple[str, tuple[str, ...]]:
    fields = 'COUNT(*)' if count else f'{table_name}.*'
    where, params = _cohort_filter('phone_pin')
    if table_name in {'messages', 'turn_events', 'referrals'}:
        where, params = _visit_cohort_clause('v')
        return (
            f'SELECT {fields} FROM {table_name} '
            f'JOIN visits v ON v.visit_id = {table_name}.visit_id '
            f'WHERE {where}',
            params,
        )
    if table_name in {'patients', 'visits', 'info_state'}:
        return f'SELECT {fields} FROM {table_name} WHERE {where}', params
    raise ValueError(f'Unsupported admin table: {table_name}')


def _query_table(table_name: str, limit: int | None = None, offset: int = 0) -> list[sqlite3.Row]:
    base_sql, params = _cohort_table_sql(table_name)
    order_by = ALLOWED_TABLES[table_name]
    sql = f'{base_sql} ORDER BY {order_by}'
    if limit is not None:
        sql += ' LIMIT ? OFFSET ?'
        params = params + (limit, offset)
    return _rows(sql, params)


def _count_table(table_name: str) -> int:
    sql, params = _cohort_table_sql(table_name, count=True)
    return _count(sql, params)


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
    where, cohort_params = _visit_cohort_clause('v')
    recent_visits = _rows(
        f"""
        SELECT
            v.visit_id, v.phone_pin, v.visit_number, v.avatar_id, v.language,
            v.phase, v.started_at, v.completed_at, v.total_turns,
            COUNT(m.id) AS message_count,
            MAX(m.timestamp) AS last_message_at
        FROM visits v
        LEFT JOIN messages m ON m.visit_id = v.visit_id
        WHERE {where}
        GROUP BY v.visit_id
        ORDER BY v.started_at DESC
        LIMIT 40
        """,
        cohort_params,
    )
    metrics = {
        'cohort_subjects': len(COHORT_CANONICAL_IDS),
        'patient_records': _count_table('patients'),
        'visits': _count_table('visits'),
        'completed_visits': _count(
            f"SELECT COUNT(*) FROM visits v WHERE {where} AND phase IN ('REPORT', 'COMPLETE')",
            cohort_params,
        ),
        'messages': _count_table('messages'),
        'turn_events': _count_table('turn_events'),
        'referrals': _count_table('referrals'),
    }
    grouped = {
        'Visits by phase': _rows(
            "SELECT COALESCE(phase, 'unknown') AS label, COUNT(*) AS count "
            f"FROM visits v WHERE {where} GROUP BY phase ORDER BY count DESC",
            cohort_params,
        ),
        'Visits by avatar': _rows(
            "SELECT COALESCE(avatar_id, 'unknown') AS label, COUNT(*) AS count "
            f"FROM visits v WHERE {where} GROUP BY avatar_id ORDER BY count DESC",
            cohort_params,
        ),
        'Question categories': _rows(
            "SELECT COALESCE(question_category, 'uncategorized') AS label, COUNT(*) AS count "
            "FROM messages JOIN visits v ON v.visit_id = messages.visit_id "
            f"WHERE {where} AND role = 'assistant' "
            "GROUP BY question_category ORDER BY count DESC",
            cohort_params,
        ),
        'Input modalities': _rows(
            "SELECT COALESCE(input_modality, 'unknown') AS label, COUNT(*) AS count "
            "FROM messages JOIN visits v ON v.visit_id = messages.visit_id "
            f"WHERE {where} AND role = 'user' "
            "GROUP BY input_modality ORDER BY count DESC",
            cohort_params,
        ),
    }
    timing = _one(
        f"""
        SELECT
            ROUND(AVG(response_latency_ms), 1) AS avg_response_latency_ms,
            ROUND(AVG(llm_latency_ms), 1) AS avg_llm_latency_ms,
            ROUND(AVG(speech_confidence), 3) AS avg_speech_confidence
        FROM messages
        JOIN visits v ON v.visit_id = messages.visit_id
        WHERE {where}
        """,
        cohort_params,
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
        cohort_name=SCREENING_ADMIN_COHORT_NAME,
        cohort_aliases=COHORT_USABLE_ALIAS_IDS,
        cohort_excluded_aliases=COHORT_EXCLUDED_ALIAS_IDS,
        cohort_configured=bool(COHORT_INCLUDED_IDS),
    )


@admin_bp.route('/visit/<visit_id>')
@_require_admin
def visit_detail(visit_id: str):
    where, params = _visit_cohort_clause()
    visit = _one(f'SELECT * FROM visits v WHERE visit_id = ? AND {where}', (visit_id,) + params)
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
    total = _count_table(table_name)
    data = _query_table(table_name, limit=limit, offset=offset)
    columns = data[0].keys() if data else _table_columns(table_name)
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
    data = _query_table(table_name)
    columns = data[0].keys() if data else _table_columns(table_name)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in data:
        writer.writerow([row[col] for col in columns])
    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=screening_cohort_{table_name}.csv'},
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

    with sqlite3.connect(tmp_path) as conn:
        if COHORT_INCLUDED_IDS:
            placeholders = ','.join('?' for _ in COHORT_INCLUDED_IDS)
            excluded_visits = f'SELECT visit_id FROM visits WHERE phone_pin NOT IN ({placeholders})'
            conn.execute(f'DELETE FROM messages WHERE visit_id IN ({excluded_visits})', COHORT_INCLUDED_IDS)
            conn.execute(f'DELETE FROM turn_events WHERE visit_id IN ({excluded_visits})', COHORT_INCLUDED_IDS)
            conn.execute(f'DELETE FROM referrals WHERE visit_id IN ({excluded_visits})', COHORT_INCLUDED_IDS)
            conn.execute(f'DELETE FROM visits WHERE phone_pin NOT IN ({placeholders})', COHORT_INCLUDED_IDS)
            conn.execute(f'DELETE FROM patients WHERE phone_pin NOT IN ({placeholders})', COHORT_INCLUDED_IDS)
            conn.execute(f'DELETE FROM info_state WHERE phone_pin NOT IN ({placeholders})', COHORT_INCLUDED_IDS)
        else:
            for table in ('messages', 'turn_events', 'referrals', 'visits', 'patients', 'info_state'):
                conn.execute(f'DELETE FROM {table}')
        conn.commit()
        conn.execute('VACUUM')

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
        download_name='sdoh-screening-cohort.db',
        mimetype='application/x-sqlite3',
    )
