from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.account import Account
from app.models.user import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


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


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """تسجيل الدخول."""
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('حسابك معطل. يرجى التواصل مع الإدارة.', 'danger')
                return redirect(url_for('auth.login'))

            if user.account and not user.account.is_active:
                flash('هذا الحساب متوقف حالياً، تواصل مع الإدارة.', 'danger')
                return redirect(url_for('auth.login'))

            login_user(user)
            session['account_id'] = user.account_id
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home.index'))

        flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')

    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    """تسجيل الخروج."""
    logout_user()
    session.pop('account_id', None)
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """تغيير كلمة المرور الشخصية."""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('كلمة المرور الحالية غير صحيحة', 'danger')
            return redirect(url_for('auth.change_password'))

        if new_password != confirm_password:
            flash('كلمة المرور الجديدة والتأكيد غير متطابقين', 'danger')
            return redirect(url_for('auth.change_password'))

        if len(new_password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('تم تغيير كلمة المرور بنجاح', 'success')
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
        flash('ليس لديك صلاحية لإنشاء حسابات أو مستخدمين', 'danger')
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
            flash('يرجى تعبئة كل الحقول المطلوبة', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if len(password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if User.query.execution_options(tenant_skip=True).filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if User.query.execution_options(tenant_skip=True).filter_by(email=email).first():
            flash('البريد الإلكتروني مستخدم بالفعل', 'danger')
            return redirect(url_for('auth.register', mode=mode))

        if is_account_mode:
            if not current_user.is_super_admin:
                flash('فقط مسؤول النظام يستطيع إنشاء حسابات عملاء جديدة', 'danger')
                return redirect(url_for('home.index'))

            if not account_name:
                flash('اسم الحساب مطلوب', 'danger')
                return redirect(url_for('auth.register', mode='account'))

            if Account.query.execution_options(tenant_skip=True).filter_by(name=account_name).first():
                flash('اسم الحساب موجود مسبقاً، اختر اسماً آخر', 'danger')
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
                flash('تعذر إنشاء الحساب، تحقق من البيانات المدخلة', 'danger')
                return redirect(url_for('auth.register', mode='account'))

            flash(
                f'تم إنشاء حساب العميل "{account.name}" مع المستخدم "{username}" بنجاح',
                'success',
            )
            return redirect(url_for('auth.register', mode='account'))

        if not current_user.account_id:
            flash('لا يمكن إنشاء مستخدم بدون حساب مرتبط', 'danger')
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
            flash('تعذر إنشاء المستخدم، تحقق من البيانات المدخلة', 'danger')
            return redirect(url_for('auth.register', mode='user'))

        flash(f'تم إنشاء المستخدم "{full_name}" بنجاح', 'success')
        return redirect(url_for('settings.users'))

    return render_template(
        'auth/register.html',
        is_account_mode=is_account_mode,
        is_super_admin=current_user.is_super_admin,
    )
