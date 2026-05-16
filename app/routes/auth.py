from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models.account import Account
from app.models.login_attempt import LoginAttempt
from app.models.user import User
from app.security import get_submitted_csrf_token, validate_csrf_token
from app.session_tracker import create_login_session, mark_current_session_logged_out

bp = Blueprint('auth', __name__, url_prefix='/auth')

_LOGIN_FAILURE_THRESHOLD = 7
_LOCKOUT_BASE_MINUTES = 5
_LOCKOUT_ESCALATION_EVERY = 3
_LOCKOUT_MAX_MINUTES = 120
_DUMMY_PASSWORD_HASH = generate_password_hash('not-the-user-password')


def _client_ip():
    trust_proxy_headers = bool(current_app.config.get('TRUST_PROXY_HEADERS', False))
    forwarded_for = (request.headers.get('X-Forwarded-For') or '').strip()
    if trust_proxy_headers and forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return (request.remote_addr or 'unknown').strip()


def _normalize_username(value):
    return (value or '').strip().lower()


def _get_or_create_login_attempt(username, ip_address):
    attempt = LoginAttempt.query.filter_by(username=username, ip_address=ip_address).first()
    if attempt:
        return attempt

    attempt = LoginAttempt(
        username=username,
        ip_address=ip_address,
    )
    db.session.add(attempt)
    db.session.flush()
    return attempt


def _remaining_lock_minutes(blocked_until, now):
    if not blocked_until or blocked_until <= now:
        return 0
    remaining_seconds = int((blocked_until - now).total_seconds())
    return max(1, (remaining_seconds + 59) // 60)


def _grant_full_permissions(user):
    """Grant full management permissions for account owner/admin."""
    user.is_admin = True
    user.is_super_admin = False
    user.is_active = True
    user.can_manage_workers = True
    user.can_manage_inventory = True
    user.can_manage_production = True
    user.can_manage_sales = True
    user.can_manage_accounting = True
    user.can_manage_reports = True
    user.can_delete = True
    user.can_edit = True
    user.can_manage_crop_health = True
    user.can_manage_production_batches = True
    user.can_manage_production_costs = True
    user.can_manage_production_stages = True
    user.can_view_analytics = True
    user.can_use_ai_assistant = True
    user.can_view_ai_history = True
    user.can_use_ai_upload = True
    user.can_use_ai_voice = True
    user.can_view_ai_reports = True


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """تسجيل الدخول."""
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        submitted_token = get_submitted_csrf_token()
        if not validate_csrf_token(submitted_token):
            flash('رمز الأمان غير صالح، يرجى المحاولة مرة أخرى', 'danger')
            return redirect(url_for('auth.login'))

        username_input = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        normalized_username = _normalize_username(username_input)

        if not username_input or not password:
            flash('اسم المستخدم وكلمة المرور مطلوبان', 'danger')
            return redirect(url_for('auth.login'))

        now = datetime.utcnow()
        ip_address = _client_ip()
        login_attempt = _get_or_create_login_attempt(
            username=normalized_username,
            ip_address=ip_address,
        )

        if login_attempt.is_blocked(now):
            lock_minutes = login_attempt.apply_failure(
                threshold=_LOGIN_FAILURE_THRESHOLD,
                base_minutes=_LOCKOUT_BASE_MINUTES,
                escalation_every=_LOCKOUT_ESCALATION_EVERY,
                max_minutes=_LOCKOUT_MAX_MINUTES,
                now=now,
            )
            db.session.commit()
            remaining = _remaining_lock_minutes(login_attempt.blocked_until, now)
            flash(
                f'تم حظر تسجيل الدخول مؤقتاً. حاول بعد {remaining} دقيقة. '
                f'مدة الحظر الحالية: {lock_minutes} دقيقة.',
                'danger',
            )
            return redirect(url_for('auth.login'))

        user = User.query.filter_by(username=username_input).first()
        password_ok = False
        if user:
            password_ok = user.check_password(password)
        else:
            # Avoid fast-fail timing difference for unknown usernames.
            check_password_hash(_DUMMY_PASSWORD_HASH, password)

        if user and password_ok:
            if not user.is_active:
                flash('حسابك معطل. يرجى التواصل مع الإدارة.', 'danger')
                return redirect(url_for('auth.login'))

            if user.account and not user.account.is_active:
                flash('هذا الحساب متوقف حالياً، تواصل مع الإدارة.', 'danger')
                return redirect(url_for('auth.login'))

            login_attempt.reset()
            db.session.commit()

            login_user(user)
            session['account_id'] = user.account_id
            try:
                create_login_session(user)
            except Exception:
                db.session.rollback()
                flash('تم تسجيل الدخول لكن تعذر تسجيل معلومات الجهاز حالياً', 'warning')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home.index'))

        lock_minutes = login_attempt.apply_failure(
            threshold=_LOGIN_FAILURE_THRESHOLD,
            base_minutes=_LOCKOUT_BASE_MINUTES,
            escalation_every=_LOCKOUT_ESCALATION_EVERY,
            max_minutes=_LOCKOUT_MAX_MINUTES,
            now=now,
        )
        db.session.commit()

        if login_attempt.failure_count >= _LOGIN_FAILURE_THRESHOLD:
            remaining = _remaining_lock_minutes(login_attempt.blocked_until, now)
            flash(
                f'تم تجاوز الحد المسموح للمحاولات ({_LOGIN_FAILURE_THRESHOLD}). '
                f'الحظر الحالي {lock_minutes} دقيقة. حاول بعد {remaining} دقيقة.',
                'danger',
            )
        else:
            attempts_left = _LOGIN_FAILURE_THRESHOLD - login_attempt.failure_count
            flash(
                f'اسم المستخدم أو كلمة المرور غير صحيحة. '
                f'المحاولات المتبقية قبل الحظر: {attempts_left}.',
                'danger',
            )

    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    """ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø®Ø±ÙˆØ¬."""
    try:
        mark_current_session_logged_out(user_id=current_user.id)
    except Exception:
        db.session.rollback()
    logout_user()
    session.pop('account_id', None)
    flash('ØªÙ… ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø®Ø±ÙˆØ¬ Ø¨Ù†Ø¬Ø§Ø­', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """ØªØºÙŠÙŠØ± ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ± Ø§Ù„Ø´Ø®ØµÙŠØ©."""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ± Ø§Ù„Ø­Ø§Ù„ÙŠØ© ØºÙŠØ± ØµØ­ÙŠØ­Ø©', 'danger')
            return redirect(url_for('auth.change_password'))

        if new_password != confirm_password:
            flash('ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ± Ø§Ù„Ø¬Ø¯ÙŠØ¯Ø© ÙˆØ§Ù„ØªØ£ÙƒÙŠØ¯ ØºÙŠØ± Ù…ØªØ·Ø§Ø¨Ù‚ÙŠÙ†', 'danger')
            return redirect(url_for('auth.change_password'))

        if len(new_password) < 6:
            flash('ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ± ÙŠØ¬Ø¨ Ø£Ù† ØªÙƒÙˆÙ† Ø¹Ù„Ù‰ Ø§Ù„Ø£Ù‚Ù„ 6 Ø£Ø­Ø±Ù', 'danger')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('ØªÙ… ØªØºÙŠÙŠØ± ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ± Ø¨Ù†Ø¬Ø§Ø­', 'success')
        return redirect(url_for('home.index'))

    return render_template('auth/change_password.html')


@bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    """
    Register flow is admin-only:
    - Super admin can create new customer accounts.
    - Any admin can create users within their current account.
    """
    if not current_user.is_admin:
        flash('Ù„ÙŠØ³ Ù„Ø¯ÙŠÙƒ ØµÙ„Ø§Ø­ÙŠØ© Ù„Ø¥Ù†Ø´Ø§Ø¡ Ø­Ø³Ø§Ø¨Ø§Øª Ø£Ùˆ Ù…Ø³ØªØ®Ø¯Ù…ÙŠÙ†', 'danger')
        return redirect(url_for('home.index'))

    requested_mode = (request.values.get('mode') or '').strip().lower()
    if current_user.is_super_admin:
        mode = 'user' if requested_mode == 'user' else 'account'
    else:
        mode = 'user'

    is_account_mode = mode == 'account'

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        full_name = (request.form.get('full_name') or '').strip()
        account_name = (request.form.get('account_name') or '').strip()

        if not username or not email or not password or not full_name:
            flash('ÙŠØ±Ø¬Ù‰ ØªØ¹Ø¨Ø¦Ø© ÙƒÙ„ Ø§Ù„Ø­Ù‚ÙˆÙ„ Ø§Ù„Ù…Ø·Ù„ÙˆØ¨Ø©', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if len(password) < 6:
            flash('ÙƒÙ„Ù…Ø© Ø§Ù„Ù…Ø±ÙˆØ± ÙŠØ¬Ø¨ Ø£Ù† ØªÙƒÙˆÙ† Ø¹Ù„Ù‰ Ø§Ù„Ø£Ù‚Ù„ 6 Ø£Ø­Ø±Ù', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if User.query.execution_options(tenant_skip=True).filter_by(username=username).first():
            flash('Ø§Ø³Ù… Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù… Ù…ÙˆØ¬ÙˆØ¯ Ø¨Ø§Ù„ÙØ¹Ù„', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if User.query.execution_options(tenant_skip=True).filter_by(email=email).first():
            flash('Ø§Ù„Ø¨Ø±ÙŠØ¯ Ø§Ù„Ø¥Ù„ÙƒØªØ±ÙˆÙ†ÙŠ Ù…Ø³ØªØ®Ø¯Ù… Ø¨Ø§Ù„ÙØ¹Ù„', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if is_account_mode:
            if not current_user.is_super_admin:
                flash('ÙÙ‚Ø· Ù…Ø³Ø¤ÙˆÙ„ Ø§Ù„Ù†Ø¸Ø§Ù… ÙŠØ³ØªØ·ÙŠØ¹ Ø¥Ù†Ø´Ø§Ø¡ Ø­Ø³Ø§Ø¨Ø§Øª Ø¹Ù…Ù„Ø§Ø¡ Ø¬Ø¯ÙŠØ¯Ø©', 'danger')
                return redirect(url_for('home.index'))

            if not account_name:
                flash('Ø§Ø³Ù… Ø§Ù„Ø­Ø³Ø§Ø¨ Ù…Ø·Ù„ÙˆØ¨', 'danger')
                return redirect(url_for('auth.register', mode='account'))

            if Account.query.execution_options(tenant_skip=True).filter_by(name=account_name).first():
                flash('Ø§Ø³Ù… Ø§Ù„Ø­Ø³Ø§Ø¨ Ù…ÙˆØ¬ÙˆØ¯ Ù…Ø³Ø¨Ù‚Ø§Ù‹ØŒ Ø§Ø®ØªØ± Ø§Ø³Ù…Ø§Ù‹ Ø¢Ø®Ø±', 'danger')
                return redirect(url_for('auth.register', mode='account'))

            account = Account(name=account_name, is_active=True)
            db.session.add(account)
            db.session.flush()

            owner_user = User(
                username=username,
                email=email,
                full_name=full_name,
                account_id=account.id,
            )
            _grant_full_permissions(owner_user)
            owner_user.set_password(password)

            try:
                db.session.add(owner_user)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('ØªØ¹Ø°Ø± Ø¥Ù†Ø´Ø§Ø¡ Ø§Ù„Ø­Ø³Ø§Ø¨ØŒ ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ù…Ø¯Ø®Ù„Ø©', 'danger')
                return redirect(url_for('auth.register', mode='account'))

            flash(
                f'ØªÙ… Ø¥Ù†Ø´Ø§Ø¡ Ø­Ø³Ø§Ø¨ Ø§Ù„Ø¹Ù…ÙŠÙ„ "{account.name}" Ù…Ø¹ Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù… "{username}" Ø¨Ù†Ø¬Ø§Ø­',
                'success',
            )
            return redirect(url_for('auth.register', mode='account'))

        if not current_user.account_id:
            flash('Ù„Ø§ ÙŠÙ…ÙƒÙ† Ø¥Ù†Ø´Ø§Ø¡ Ù…Ø³ØªØ®Ø¯Ù… Ø¨Ø¯ÙˆÙ† Ø­Ø³Ø§Ø¨ Ù…Ø±ØªØ¨Ø·', 'danger')
            return redirect(url_for('settings.users'))

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            account_id=current_user.account_id,
            is_active=True,
            is_admin=False,
        )
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('ØªØ¹Ø°Ø± Ø¥Ù†Ø´Ø§Ø¡ Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…ØŒ ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ù…Ø¯Ø®Ù„Ø©', 'danger')
            return redirect(url_for('auth.register', mode='user'))

        flash(f'ØªÙ… Ø¥Ù†Ø´Ø§Ø¡ Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù… "{full_name}" Ø¨Ù†Ø¬Ø§Ø­', 'success')
        return redirect(url_for('settings.users'))

    return render_template(
        'auth/register.html',
        is_account_mode=is_account_mode,
        is_super_admin=current_user.is_super_admin,
    )

