from flask import Flask, flash, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
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
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    from app.audit import init_audit_logging
    init_audit_logging()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة'
    
    # Register blueprints
    with app.app_context():
        from app.models.audit_log import AuditLog  # noqa: F401
        from app.routes import (
            auth, workers, inventory, production, 
            sales, accounting, reports, settings, home, motors
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
        app.register_blueprint(home.bp)
        
        # Create database tables
        db.create_all()

    @app.context_processor
    def inject_site_name():
        default_name = "نظام المزرعة"
        try:
            from app.models.app_setting import AppSetting
            site_name = AppSetting.get_value("site_name", default_name)
        except Exception:
            site_name = default_name
        return {"site_name": site_name, "csrf_token": get_csrf_token()}

    @app.before_request
    def enforce_delete_csrf():
        """Require CSRF token on all delete POST handlers."""
        endpoint = request.endpoint or ""
        if request.method != "POST":
            return None

        view_func = app.view_functions.get(endpoint)
        if not view_func:
            return None

        if not view_func.__name__.startswith("delete_"):
            return None

        submitted_token = get_submitted_csrf_token()
        if validate_csrf_token(submitted_token):
            return None

        flash("رمز الأمان غير صالح، يرجى إعادة المحاولة", "danger")
        return redirect(request.referrer or url_for("home.index"))
    
    return app
