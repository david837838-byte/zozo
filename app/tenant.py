from functools import lru_cache

from flask import has_request_context, session as flask_session
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session, with_loader_criteria

from app import db
from app.models.account import Account

_TENANT_INIT_DONE = False
_TENANT_TABLES = (
    "user",
    "worker_family",
    "worker",
    "shift",
    "work_log",
    "motor_log",
    "attendance",
    "monthly_attendance",
    "expense_category",
    "transaction",
    "closed_worker_account",
    "box_type",
    "box_usage",
    "box_purchase",
    "inventory_item",
    "inventory_transaction",
    "general_consumption",
    "inventory_purchase",
    "crop",
    "crop_consumption",
    "production",
    "sales",
    "crop_health",
    "production_batch",
    "production_cost",
    "production_stage",
    "production_inventory",
    "motors",
    "operator_quotas",
    "motor_usages",
    "motor_costs",
    "audit_logs",
    "user_sessions",
    "ai_conversation",
    "ai_conversation_message",
)
_EXTRA_SCHEMA_COLUMNS = {
    "worker": {
        "family_id": "INTEGER",
        "gender": "VARCHAR(20)",
        "use_family_rates": "BOOLEAN DEFAULT 0",
    },
    "user": {
        "is_super_admin": "BOOLEAN DEFAULT 0",
        "can_use_ai_assistant": "BOOLEAN DEFAULT 0",
        "can_view_ai_history": "BOOLEAN DEFAULT 0",
        "can_use_ai_upload": "BOOLEAN DEFAULT 0",
        "can_use_ai_voice": "BOOLEAN DEFAULT 0",
        "can_view_ai_reports": "BOOLEAN DEFAULT 0",
    },
    "inventory_item": {
        "active_ingredient": "VARCHAR(200)",
        "common_usage": "TEXT",
        "safety_notes": "TEXT",
    },
    "sales": {
        "quality": "VARCHAR(50) DEFAULT 'متوسطة'",
        "discount_percent": "FLOAT DEFAULT 0",
        "discount_amount": "FLOAT DEFAULT 0",
        "transport_cost": "FLOAT DEFAULT 0",
        "invoice_group_key": "VARCHAR(64)",
    },
}


def get_current_account_id():
    """Return current authenticated account id when available."""
    if not has_request_context():
        return None

    raw_account_id = flask_session.get("account_id")
    if raw_account_id in (None, ""):
        return None

    try:
        return int(raw_account_id)
    except (TypeError, ValueError):
        return None


def is_current_user_super_admin():
    """Check Super Admin status from session to avoid ORM recursion."""
    if not has_request_context():
        return False
    return bool(flask_session.get("is_super_admin", False))


def _is_tenant_scoped_model(model_class):
    return hasattr(model_class, "account_id")


def _is_tenant_scoped_instance(instance):
    return hasattr(instance, "account_id")


def ensure_multi_tenant_schema():
    """Best-effort bootstrap migration for adding account isolation columns."""
    Account.__table__.create(bind=db.engine, checkfirst=True)

    engine_inspector = inspect(db.engine)
    existing_tables = set(engine_inspector.get_table_names())

    for table_name in _TENANT_TABLES:
        if table_name not in existing_tables:
            continue
        columns = {column["name"] for column in engine_inspector.get_columns(table_name)}
        if "account_id" in columns:
            continue
        db.session.execute(
            text(f'ALTER TABLE "{table_name}" ADD COLUMN account_id INTEGER')
        )

    for table_name, columns_map in _EXTRA_SCHEMA_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        table_columns = {column["name"] for column in engine_inspector.get_columns(table_name)}
        for column_name, column_sql in columns_map.items():
            if column_name in table_columns:
                continue
            db.session.execute(
                text(f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {column_sql}')
            )

    db.session.commit()

    default_account = (
        Account.query.order_by(Account.id.asc()).first()
    )
    if not default_account:
        default_account = Account(name="Ø§Ù„Ø­Ø³Ø§Ø¨ Ø§Ù„Ø§ÙØªØ±Ø§Ø¶ÙŠ")
        db.session.add(default_account)
        db.session.commit()

    default_account_id = default_account.id
    if default_account_id is None:
        return

    for table_name in _TENANT_TABLES:
        if table_name not in existing_tables:
            continue
        db.session.execute(
            text(f'UPDATE "{table_name}" SET account_id = :aid WHERE account_id IS NULL'),
            {"aid": default_account_id},
        )

    db.session.execute(
        text(
            'UPDATE "user" SET is_super_admin = 0 '
            'WHERE is_super_admin IS NULL'
        )
    )
    db.session.execute(
        text(
            'UPDATE "sales" SET quality = :default_quality '
            'WHERE quality IS NULL OR TRIM(quality) = \'\''
        ),
        {"default_quality": "متوسطة"},
    )
    db.session.execute(
        text(
            'UPDATE "sales" SET discount_percent = 0 '
            'WHERE discount_percent IS NULL'
        )
    )
    db.session.execute(
        text(
            'UPDATE "sales" SET discount_amount = 0 '
            'WHERE discount_amount IS NULL'
        )
    )
    db.session.execute(
        text(
            'UPDATE "sales" SET transport_cost = 0 '
            'WHERE transport_cost IS NULL'
        )
    )

    super_admin_count = db.session.execute(
        text('SELECT COUNT(*) FROM "user" WHERE is_super_admin = 1')
    ).scalar() or 0
    if super_admin_count == 0:
        first_admin_id = db.session.execute(
            text(
                'SELECT id FROM "user" '
                'WHERE is_admin = 1 '
                'ORDER BY id ASC LIMIT 1'
            )
        ).scalar()
        if first_admin_id is not None:
            db.session.execute(
                text('UPDATE "user" SET is_super_admin = 1 WHERE id = :uid'),
                {"uid": first_admin_id},
            )

    db.session.commit()
    _tenant_model_classes.cache_clear()


@lru_cache(maxsize=1)
def _tenant_model_classes():
    classes = []
    for mapper in db.Model.registry.mappers:
        model_class = mapper.class_
        if _is_tenant_scoped_model(model_class):
            classes.append(model_class)
    return tuple(classes)


def _default_account_id_for_session(session):
    result = session.execute(
        select(Account.id).order_by(Account.id.asc()).limit(1)
    ).scalar()
    return result


def init_tenant_isolation():
    """Initialize tenant filtering and write guards once."""
    global _TENANT_INIT_DONE
    if _TENANT_INIT_DONE:
        return

    @event.listens_for(Session, "do_orm_execute")
    def _tenant_do_orm_execute(orm_execute_state):
        if not orm_execute_state.is_select:
            return
        if orm_execute_state.execution_options.get("tenant_skip", False):
            return

        if is_current_user_super_admin():
            return

        account_id = get_current_account_id()
        if not account_id:
            return

        statement = orm_execute_state.statement
        for model_class in _tenant_model_classes():
            statement = statement.options(
                with_loader_criteria(
                    model_class,
                    lambda cls: cls.account_id == account_id,
                    include_aliases=True,
                )
            )
        orm_execute_state.statement = statement

    @event.listens_for(Session, "before_flush")
    def _tenant_before_flush(session, flush_context, instances):  # noqa: ARG001
        request_account_id = get_current_account_id()
        is_super_admin = is_current_user_super_admin()
        fallback_account_id = None

        for instance in session.new:
            if not _is_tenant_scoped_instance(instance):
                continue

            instance_account_id = getattr(instance, "account_id", None)
            if instance_account_id is None:
                target_account_id = request_account_id
                if target_account_id is None:
                    if fallback_account_id is None:
                        fallback_account_id = _default_account_id_for_session(session)
                    target_account_id = fallback_account_id
                if target_account_id is not None:
                    setattr(instance, "account_id", target_account_id)
                    instance_account_id = target_account_id

            # Super Admin can write to any account
            if is_super_admin:
                continue
            
            if (
                request_account_id is not None
                and instance_account_id is not None
                and instance_account_id != request_account_id
            ):
                raise PermissionError("Cross-account write blocked")

        if request_account_id is None:
            return

        for instance in list(session.dirty) + list(session.deleted):
            if not _is_tenant_scoped_instance(instance):
                continue
            instance_account_id = getattr(instance, "account_id", None)
            if instance_account_id is None:
                continue
            
            # Super Admin can modify any account
            if is_super_admin:
                continue
            
            if instance_account_id != request_account_id:
                raise PermissionError("Cross-account mutation blocked")

    _TENANT_INIT_DONE = True

