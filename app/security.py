import hmac
import secrets

from flask import request, session

CSRF_SESSION_KEY = "_csrf_token"


def get_csrf_token():
    """Return a stable per-session CSRF token."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(submitted_token):
    """Validate submitted CSRF token using constant-time compare."""
    if not submitted_token:
        return False

    session_token = session.get(CSRF_SESSION_KEY)
    if not session_token:
        return False

    try:
        return hmac.compare_digest(str(session_token), str(submitted_token))
    except Exception:
        return False


def get_submitted_csrf_token():
    """Read CSRF token from form first, then request headers."""
    token = request.form.get("csrf_token")
    if token:
        return token
    return request.headers.get("X-CSRF-Token")
