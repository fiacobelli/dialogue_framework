"""Minimal authenticated staff admin routes."""

from __future__ import annotations

import hmac

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from .config import ADMIN_PASSWORD, ADMIN_USERNAME
from . import database as db

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
    return render_template('admin_sessions.html', visits=visits)


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
