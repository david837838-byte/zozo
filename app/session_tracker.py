import logging
import secrets
from datetime import datetime, timedelta

from flask import request, session
from flask_login import current_user

from app import db
from app.models.user_session import UserSession

logger = logging.getLogger(__name__)

SESSION_TOKEN_KEY = "device_session_token"
SESSION_LAST_TOUCH_KEY = "_device_session_last_touch"
TOUCH_INTERVAL = timedelta(minutes=5)
MAX_USER_AGENT_LENGTH = 500


def _safe_user_agent():
    raw = (request.user_agent.string or request.headers.get("User-Agent") or "").strip()
    if not raw:
        return "Unknown"
    return raw[:MAX_USER_AGENT_LENGTH]


def _safe_ip_address():
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr


def _detect_device_type(user_agent):
    ua = user_agent.lower()

    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    if any(token in ua for token in ("mobile", "iphone", "ipod", "android", "windows phone")):
        return "Phone"
    if any(token in ua for token in ("windows", "macintosh", "linux", "x11", "cros")):
        return "Desktop"
    return "Unknown"


def _detect_device_name(user_agent):
    ua = user_agent.lower()

    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android Device"
    if "windows" in ua:
        return "Windows PC"
    if "macintosh" in ua or "mac os x" in ua:
        return "Mac"
    if "linux" in ua:
        return "Linux Device"
    return "Unknown Device"


def _detect_operating_system(user_agent):
    ua = user_agent.lower()

    if "iphone" in ua or "ipad" in ua:
        return "iOS"
    if "android" in ua:
        return "Android"
    if "windows" in ua:
        return "Windows"
    if "macintosh" in ua or "mac os x" in ua:
        return "macOS"
    if "linux" in ua:
        return "Linux"
    return "Unknown OS"


def _detect_browser(user_agent):
    ua = user_agent.lower()

    if "edg/" in ua:
        return "Edge"
    if "opr/" in ua or "opera" in ua:
        return "Opera"
    if "chrome/" in ua and "edg/" not in ua and "opr/" not in ua:
        return "Chrome"
    if "firefox/" in ua:
        return "Firefox"
    if "safari/" in ua and "chrome/" not in ua:
        return "Safari"
    if "trident/" in ua or "msie" in ua:
        return "Internet Explorer"
    return "Unknown Browser"


def _build_session_entry(user, token):
    user_agent = _safe_user_agent()
    now = datetime.utcnow()
    return UserSession(
        user_id=user.id,
        account_id=user.account_id,
        session_token=token,
        device_type=_detect_device_type(user_agent),
        device_name=_detect_device_name(user_agent),
        operating_system=_detect_operating_system(user_agent),
        browser=_detect_browser(user_agent),
        ip_address=_safe_ip_address(),
        user_agent=user_agent,
        is_active=True,
        login_at=now,
        last_seen_at=now,
        logged_out_at=None,
    )


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _mark_touch_time(now):
    session[SESSION_LAST_TOUCH_KEY] = now.isoformat()


def _should_touch(now):
    last_touch = _parse_iso_datetime(session.get(SESSION_LAST_TOUCH_KEY))
    if not last_touch:
        return True
    return now - last_touch >= TOUCH_INTERVAL


def create_login_session(user):
    """Create a tracked device session after successful authentication."""
    token = secrets.token_urlsafe(32)
    session[SESSION_TOKEN_KEY] = token

    entry = _build_session_entry(user, token)
    db.session.add(entry)
    db.session.commit()
    _mark_touch_time(entry.last_seen_at)
    return entry


def ensure_current_session_tracked():
    """Ensure authenticated request has an active tracked session."""
    if not getattr(current_user, "is_authenticated", False):
        return

    now = datetime.utcnow()
    token = session.get(SESSION_TOKEN_KEY)

    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_TOKEN_KEY] = token
        entry = _build_session_entry(current_user, token)
        db.session.add(entry)
        db.session.commit()
        _mark_touch_time(now)
        return

    entry = UserSession.query.filter(
        UserSession.user_id == current_user.id,
        UserSession.session_token == token,
    ).first()

    if not entry:
        entry = _build_session_entry(current_user, token)
        db.session.add(entry)
        db.session.commit()
        _mark_touch_time(now)
        return

    if not entry.is_active:
        entry.is_active = True
        entry.logged_out_at = None

    if not _should_touch(now):
        return

    entry.last_seen_at = now
    ip_address = _safe_ip_address()
    if ip_address and entry.ip_address != ip_address:
        entry.ip_address = ip_address
    db.session.commit()
    _mark_touch_time(now)


def mark_current_session_logged_out(user_id=None):
    """Mark current tracked session as inactive and remove local session keys."""
    token = session.get(SESSION_TOKEN_KEY)

    session.pop(SESSION_TOKEN_KEY, None)
    session.pop(SESSION_LAST_TOUCH_KEY, None)

    if not token:
        return

    query = UserSession.query.filter(UserSession.session_token == token)
    if user_id is not None:
        query = query.filter(UserSession.user_id == user_id)

    entry = query.first()
    if not entry:
        return

    now = datetime.utcnow()
    entry.is_active = False
    entry.last_seen_at = now
    entry.logged_out_at = now

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to mark user session as logged out")
