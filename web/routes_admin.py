"""Minimal authenticated staff admin routes."""

from __future__ import annotations

import hmac
import csv
import os
import tempfile
from io import BytesIO, StringIO

from flask import (
    Blueprint,
    Response,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from .config import ADMIN_PASSWORD, ADMIN_USERNAME
from . import database as db
from . import database_admin as admin_db
from . import takedown

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _admin_enabled() -> bool:
    return bool(ADMIN_PASSWORD)


def _is_authenticated() -> bool:
    return bool(session.get('admin_authenticated'))


def _require_admin():
    if not _admin_enabled():
        abort(503)
    if not _is_authenticated():
        return redirect(url_for('admin.login', next=request.path))
    return None


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticate staff with a configured deployment password."""
    if not _admin_enabled():
        return render_template('admin_login.html', admin_enabled=False), 503

    error = ''
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user_ok = hmac.compare_digest(username, ADMIN_USERNAME)
        password_ok = hmac.compare_digest(password, ADMIN_PASSWORD)
        if user_ok and password_ok:
            session['admin_authenticated'] = True
            session['admin_username'] = username
            return redirect(request.args.get('next') or url_for('admin.sessions'))
        error = 'Invalid admin username or password.'

    return render_template('admin_login.html', admin_enabled=True, error=error)


@admin_bp.route('/logout', methods=['POST'])
def logout():
    """Clear admin session."""
    session.pop('admin_authenticated', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
def sessions():
    """Show recent microsite sessions."""
    guard = _require_admin()
    if guard:
        return guard
    visits = db.list_admin_visits(limit=100)
    return render_template('admin_sessions.html', visits=visits, tables=admin_db.list_admin_tables())


@admin_bp.route('/reports')
def reports():
    """Show lightweight study/database summaries."""
    guard = _require_admin()
    if guard:
        return guard
    return render_template('admin_reports.html', report=admin_db.get_admin_report())


@admin_bp.route('/tables/<table_name>')
def table(table_name):
    """Browse one allowlisted database table."""
    guard = _require_admin()
    if guard:
        return guard
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        table_data = admin_db.get_admin_table(table_name, limit=limit, offset=offset)
    except (TypeError, ValueError):
        abort(404)
    return render_template('admin_table.html', table=table_data)


@admin_bp.route('/download/table/<table_name>.csv')
def download_table_csv(table_name):
    """Download one allowlisted database table as CSV."""
    guard = _require_admin()
    if guard:
        return guard
    try:
        columns, rows = admin_db.get_admin_table_export(table_name)
    except ValueError:
        abort(404)

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    filename = f'microsite_{table_name}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@admin_bp.route('/download/database')
def download_database():
    """Download a consistent SQLite backup of the microsite database."""
    guard = _require_admin()
    if guard:
        return guard

    handle = tempfile.NamedTemporaryFile(prefix='microsite_db_', suffix='.db', delete=False)
    handle.close()
    try:
        admin_db.create_admin_database_backup(handle.name)
        with open(handle.name, 'rb') as backup:
            payload = BytesIO(backup.read())
        payload.seek(0)
    finally:
        try:
            os.remove(handle.name)
        except OSError:
            pass

    return send_file(
        payload,
        as_attachment=True,
        download_name='microsite_database_backup.db',
        mimetype='application/octet-stream',
        max_age=0,
    )


@admin_bp.route('/session/<session_id>')
def session_detail(session_id):
    """Show one session timeline and publication state."""
    guard = _require_admin()
    if guard:
        return guard
    detail = db.get_admin_visit(session_id)
    if not detail:
        abort(404)
    return render_template('admin_session_detail.html', detail=detail)


@admin_bp.route('/session/<session_id>/unpublish', methods=['POST'])
def admin_unpublish(session_id):
    """Unpublish a donor page from the admin interface."""
    guard = _require_admin()
    if guard:
        return guard
    reason = request.form.get('reason') or 'admin_request'
    actor = session.get('admin_username') or 'admin'
    if not db.unpublish_session(session_id, reason=reason, actor=actor):
        abort(404)
    return redirect(url_for('admin.session_detail', session_id=session_id))


@admin_bp.route('/session/<session_id>/delete', methods=['POST'])
def admin_delete(session_id):
    """Soft-delete a donor page and its public assets from the admin interface."""
    guard = _require_admin()
    if guard:
        return guard
    reason = request.form.get('reason') or 'admin_delete'
    actor = session.get('admin_username') or 'admin'
    if not takedown.delete_session(session_id, reason=reason, actor=actor):
        abort(404)
    return redirect(url_for('admin.session_detail', session_id=session_id))
