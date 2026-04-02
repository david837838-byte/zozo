import json
from datetime import date, datetime
from decimal import Decimal

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

_AUDIT_INITIALIZED = False
_AUDIT_IN_PROGRESS_KEY = "_audit_in_progress"
_AUDIT_ENTRIES_KEY = "_audit_entries"
_SENSITIVE_FIELDS = {"password_hash", "csrf_token"}
_IGNORED_UPDATE_FIELDS = {"updated_at"}
_MAX_VALUE_LENGTH = 300


def _is_simple(value):
    return value is None or isinstance(value, (bool, int, float, str))


def _serialize_value(value):
    """Convert any value to JSON-friendly payload."""
    if _is_simple(value):
        serialized = value
    elif isinstance(value, Decimal):
        serialized = float(value)
    elif isinstance(value, (datetime, date)):
        serialized = value.isoformat()
    else:
        serialized = str(value)

    if isinstance(serialized, str) and len(serialized) > _MAX_VALUE_LENGTH:
        return f"{serialized[:_MAX_VALUE_LENGTH]}..."
    return serialized


def _mask_if_sensitive(key, value):
    if key in _SENSITIVE_FIELDS:
        return "***"
    return _serialize_value(value)


def _should_track(instance):
    if isinstance(instance, AuditLog):
        return False

    mapper = getattr(instance, "__mapper__", None)
    if mapper is None:
        return False

    # Skip very noisy session tables if ever added.
    table_name = getattr(instance, "__tablename__", "")
    if table_name in {"alembic_version"}:
        return False
    return True


def _instance_identity(instance):
    inspected = sa_inspect(instance)
    identity = inspected.identity
    if identity:
        if len(identity) == 1:
            return str(identity[0])
        return ",".join(str(part) for part in identity)

    # Fallback for transient objects.
    pk_values = []
    for column in inspected.mapper.primary_key:
        value = getattr(instance, column.key, None)
        pk_values.append(str(value) if value is not None else "")
    return ",".join(pk_values) if pk_values else None


def _serialize_instance(instance):
    payload = {}
    inspected = sa_inspect(instance)
    for column_attr in inspected.mapper.column_attrs:
        key = column_attr.key
        value = getattr(instance, key, None)
        payload[key] = _mask_if_sensitive(key, value)
    return payload


def _serialize_changes(instance):
    payload = {}
    inspected = sa_inspect(instance)

    for column_attr in inspected.mapper.column_attrs:
        key = column_attr.key
        if key in _IGNORED_UPDATE_FIELDS:
            continue

        history = inspected.attrs[key].history
        if not history.has_changes():
            continue

        old_value = history.deleted[0] if history.deleted else None
        new_value = history.added[0] if history.added else getattr(instance, key, None)

        old_serialized = _mask_if_sensitive(key, old_value)
        new_serialized = _mask_if_sensitive(key, new_value)

        if old_serialized == new_serialized:
            continue

        payload[key] = {"from": old_serialized, "to": new_serialized}

    return payload


def _resolve_actor():
    if not has_request_context():
        return None, "system"

    if getattr(current_user, "is_authenticated", False):
        user_id = getattr(current_user, "id", None)
        username = getattr(current_user, "username", None) or "user"
        return user_id, username
    return None, "anonymous"


def _resolve_request_metadata():
    if not has_request_context():
        return None, None

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.remote_addr

    return request.endpoint, ip_address


def _build_summary(action, instance):
    label = getattr(instance, "name", None) or getattr(instance, "title", None)
    if not label:
        label = getattr(instance, "description", None)
    if label:
        text = str(label).strip()
        if len(text) > 120:
            text = f"{text[:120]}..."
        return f"{action}:{text}"
    return action


def _capture_pending_audit_entries(session):
    entries = []

    for instance in session.new:
        if not _should_track(instance):
            continue
        entries.append(
            {
                "action": "create",
                "instance": instance,
                "changes": None,
            }
        )

    for instance in session.dirty:
        if not _should_track(instance):
            continue
        if not session.is_modified(instance, include_collections=False):
            continue
        changes = _serialize_changes(instance)
        if not changes:
            continue
        entries.append(
            {
                "action": "update",
                "instance": instance,
                "changes": changes,
            }
        )

    for instance in session.deleted:
        if not _should_track(instance):
            continue
        entries.append(
            {
                "action": "delete",
                "instance": instance,
                "changes": _serialize_instance(instance),
            }
        )

    if not entries:
        return

    existing = session.info.get(_AUDIT_ENTRIES_KEY, [])
    session.info[_AUDIT_ENTRIES_KEY] = existing + entries


def _write_audit_entries(session):
    entries = session.info.pop(_AUDIT_ENTRIES_KEY, [])
    if not entries:
        return

    user_id, username = _resolve_actor()
    endpoint, ip_address = _resolve_request_metadata()

    logs = []
    for entry in entries:
        instance = entry["instance"]
        if entry["action"] == "create" and entry["changes"] is None:
            changes_payload = _serialize_instance(instance)
        else:
            changes_payload = entry["changes"]

        logs.append(
            AuditLog(
                user_id=user_id,
                username=username or "system",
                action=entry["action"],
                entity_type=instance.__class__.__name__,
                entity_id=_instance_identity(instance),
                summary=_build_summary(entry["action"], instance),
                changes=json.dumps(changes_payload, ensure_ascii=False),
                endpoint=endpoint,
                ip_address=ip_address,
            )
        )

    if not logs:
        return

    session.info[_AUDIT_IN_PROGRESS_KEY] = True
    try:
        session.add_all(logs)
    finally:
        session.info[_AUDIT_IN_PROGRESS_KEY] = False


def init_audit_logging():
    """Register SQLAlchemy listeners once per process."""
    global _AUDIT_INITIALIZED
    if _AUDIT_INITIALIZED:
        return

    @event.listens_for(Session, "before_flush")
    def _audit_before_flush(session, flush_context, instances):  # noqa: ARG001
        if session.info.get(_AUDIT_IN_PROGRESS_KEY):
            return
        _capture_pending_audit_entries(session)

    @event.listens_for(Session, "after_flush_postexec")
    def _audit_after_flush_postexec(session, flush_context):  # noqa: ARG001
        if session.info.get(_AUDIT_IN_PROGRESS_KEY):
            return
        _write_audit_entries(session)

    @event.listens_for(Session, "after_rollback")
    def _audit_after_rollback(session):
        session.info.pop(_AUDIT_ENTRIES_KEY, None)
        session.info.pop(_AUDIT_IN_PROGRESS_KEY, None)

    _AUDIT_INITIALIZED = True
