from flask import Flask, flash, redirect, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from app.security import get_csrf_token, get_submitted_csrf_token, validate_csrf_token

db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_name='development'):
    """Application factory"""
    app = Flask(__name__)
    
    # Import config
    if config_name == 'development':
        from config import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    elif config_name == 'testing':
        from config import TestingConfig
        app.config.from_object(TestingConfig)
    else:
        from config import ProductionConfig
        app.config.from_object(ProductionConfig)

    from config import DEFAULT_INSECURE_SECRET_KEY
    if (
        config_name == 'production'
        and app.config.get('SECRET_KEY') == DEFAULT_INSECURE_SECRET_KEY
    ):
        raise RuntimeError(
            'SECRET_KEY must be set in production and cannot use the default value.'
        )

    if app.config.get('SECRET_KEY') == DEFAULT_INSECURE_SECRET_KEY:
        app.logger.warning(
            'Using default insecure SECRET_KEY. Set SECRET_KEY in environment.'
        )
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    from app.audit import init_audit_logging
    from app.tenant import init_tenant_isolation
    init_audit_logging()
    init_tenant_isolation()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'ÙŠØ±Ø¬Ù‰ ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø¯Ø®ÙˆÙ„ Ù„Ù„ÙˆØµÙˆÙ„ Ø¥Ù„Ù‰ Ù‡Ø°Ù‡ Ø§Ù„ØµÙØ­Ø©'
    
    # Register blueprints
    with app.app_context():
        import importlib

        importlib.import_module('app.models')
        from app.models.audit_log import AuditLog  # noqa: F401
        from app.tenant import ensure_multi_tenant_schema
        from app.routes import (
            auth, workers, inventory, production, 
            sales, accounting, reports, settings, home, motors, admin_accounts, ai_assistant
        )
        
        app.register_blueprint(auth.bp)
        app.register_blueprint(workers.bp)
        app.register_blueprint(inventory.bp)
        app.register_blueprint(motors.motors_bp)
        app.register_blueprint(production.bp)
        app.register_blueprint(sales.bp)
        app.register_blueprint(accounting.bp)
        app.register_blueprint(reports.bp)
        app.register_blueprint(settings.bp)
        app.register_blueprint(ai_assistant.bp)
        app.register_blueprint(home.bp)
        app.register_blueprint(admin_accounts.bp)
        
        # Create database tables
        db.create_all()
        ensure_multi_tenant_schema()

    @app.context_processor
    def inject_site_name():
        default_name = "Ù†Ø¸Ø§Ù… Ø§Ù„Ù…Ø²Ø±Ø¹Ø©"
        try:
            from app.models.app_setting import AppSetting

            account_id = None
            if getattr(current_user, 'is_authenticated', False):
                account_id = getattr(current_user, 'account_id', None)

            if account_id:
                scoped_key = f"account:{account_id}:site_name"
                site_name = AppSetting.get_value(
                    scoped_key,
                    AppSetting.get_value("site_name", default_name),
                )
            else:
                site_name = AppSetting.get_value("site_name", default_name)
        except Exception:
            site_name = default_name
        return {"site_name": site_name, "csrf_token": get_csrf_token()}

    @app.before_request
    def sync_account_scope_session():
        """Keep current account id in session for tenant filters."""
        if not getattr(current_user, 'is_authenticated', False):
            session.pop('account_id', None)
            session.pop('is_super_admin', None)
            return None

        account_id = getattr(current_user, 'account_id', None)
        session['is_super_admin'] = bool(getattr(current_user, 'is_super_admin', False))

        if account_id is None:
            session.pop('account_id', None)
            return None

        if session.get('account_id') != account_id:
            session['account_id'] = int(account_id)
        return None

    @app.before_request
    def track_active_device_session():
        """Keep tracked user device session alive while browsing."""
        if not getattr(current_user, 'is_authenticated', False):
            return None
        try:
            from app.session_tracker import ensure_current_session_tracked

            ensure_current_session_tracked()
        except Exception:
            db.session.rollback()
        return None

    @app.before_request
    def enforce_csrf_for_state_changes():
        """Require CSRF token on all state-changing requests."""
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None

        endpoint = request.endpoint or ""
        if endpoint.startswith("static"):
            return None

        submitted_token = get_submitted_csrf_token()
        if validate_csrf_token(submitted_token):
            return None

        if request.is_json:
            return {"error": "رمز الأمان غير صالح أو مفقود"}, 400

        flash("رمز الأمان غير صالح، يرجى إعادة المحاولة", "danger")
        return redirect(request.referrer or url_for("home.index"))

    @app.after_request
    def set_security_headers(response):
        """Attach baseline security headers for every response."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self';"
        )
        response.headers.setdefault("Content-Security-Policy", csp)

        if not app.debug:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
    @app.errorhandler(PermissionError)
    def handle_permission_error(error):
        try:
            db.session.rollback()
        except Exception:
            pass

        flash("Ù„Ø§ ÙŠÙ…ÙƒÙ†Ùƒ Ø§Ù„ÙˆØµÙˆÙ„ Ø£Ùˆ Ø§Ù„ØªØ¹Ø¯ÙŠÙ„ Ø¹Ù„Ù‰ Ø¨ÙŠØ§Ù†Ø§Øª Ø­Ø³Ø§Ø¨ Ø¢Ø®Ø±", "danger")
        return redirect(request.referrer or url_for("home.index"))
    
    return app

