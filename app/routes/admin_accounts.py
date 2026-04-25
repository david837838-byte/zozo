"""
Route module for Super Admin account management.
Only users with is_super_admin=True can access these routes.
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.account import Account
from app.models.user import User
from app.routes.auth import _grant_full_permissions
from app.security import get_submitted_csrf_token, validate_csrf_token

bp = Blueprint('admin_accounts', __name__, url_prefix='/super-admin/accounts')


def _check_super_admin():
    """Check if current user is Super Admin."""
    if not current_user.is_authenticated:
        return False
    return getattr(current_user, 'is_super_admin', False)


def _users_query():
    """Return user query without tenant auto-filter for Super Admin routes."""
    return User.query.execution_options(tenant_skip=True)


@bp.before_request
def before_request():
    """Ensure only Super Admins can access these routes."""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.path))

    if not _check_super_admin():
        flash('ليس لديك صلاحيات كافية للوصول إلى هذه الصفحة', 'danger')
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        submitted_token = get_submitted_csrf_token()
        if not validate_csrf_token(submitted_token):
            flash('Invalid CSRF token. Please retry.', 'danger')
            return redirect(request.referrer or url_for('admin_accounts.list_accounts'))


@bp.route('/', methods=['GET'])
@login_required
def list_accounts():
    """List all accounts and their admins."""
    accounts = Account.query.all()
    
    account_data = []
    for account in accounts:
        admin_user = _users_query().filter_by(
            account_id=account.id,
            is_admin=True
        ).first()
        
        user_count = _users_query().filter_by(account_id=account.id).count()
        account_data.append({
            'account': account,
            'admin_user': admin_user,
            'user_count': user_count
        })
    
    return render_template('admin/accounts_list.html', account_data=account_data)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_account():
    """Create new account with first admin user."""
    if request.method == 'POST':
        account_name = request.form.get('account_name', '').strip()
        admin_username = request.form.get('admin_username', '').strip()
        admin_email = request.form.get('admin_email', '').strip()
        admin_password = request.form.get('admin_password', '')
        admin_full_name = request.form.get('admin_full_name', '').strip()
        
        # Validation
        if not account_name:
            flash('اسم الحساب مطلوب', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
        
        if not admin_username:
            flash('اسم المستخدم مطلوب', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
        
        if not admin_password or len(admin_password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
        
        if not admin_full_name:
            flash('الاسم الكامل مطلوب', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
        
        if not admin_email:
            flash('البريد الإلكتروني مطلوب', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
        
        try:
            # Create new account
            new_account = Account(name=account_name, is_active=True)
            db.session.add(new_account)
            db.session.flush()  # Get the ID
            
            # Create first admin user for this account
            admin_user = User(
                account_id=new_account.id,
                username=admin_username,
                email=admin_email,
                full_name=admin_full_name,
                is_active=True,
            )
            admin_user.set_password(admin_password)
            
            # Grant full permissions to first admin
            _grant_full_permissions(admin_user)
            
            db.session.add(admin_user)
            db.session.commit()
            
            flash(
                f'تم إنشاء الحساب "{account_name}" بنجاح مع مسؤول "{admin_username}"',
                'success'
            )
            return redirect(url_for('admin_accounts.list_accounts'))
        
        except IntegrityError:
            db.session.rollback()
            flash('اسم الحساب أو اسم المستخدم موجود بالفعل', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
            return redirect(url_for('admin_accounts.create_account'))
    
    return render_template('admin/create_account.html')


@bp.route('/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    """Edit account details."""
    account = Account.query.get_or_404(account_id)
    
    if request.method == 'POST':
        account_name = request.form.get('account_name', '').strip()
        is_active = request.form.get('is_active') == 'on'
        
        if not account_name:
            flash('اسم الحساب مطلوب', 'danger')
            return redirect(url_for('admin_accounts.edit_account', account_id=account_id))
        
        try:
            account.name = account_name
            account.is_active = is_active
            db.session.commit()
            
            flash('تم تحديث الحساب بنجاح', 'success')
            return redirect(url_for('admin_accounts.list_accounts'))
        
        except IntegrityError:
            db.session.rollback()
            flash('اسم الحساب موجود بالفعل', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    admin_user = _users_query().filter_by(
        account_id=account_id,
        is_admin=True
    ).first()
    
    return render_template('admin/edit_account.html', account=account, admin_user=admin_user)


@bp.route('/<int:account_id>/toggle-status', methods=['POST'])
@login_required
def toggle_account_status(account_id):
    """Toggle account active/inactive status."""
    account = Account.query.get_or_404(account_id)
    
    try:
        account.is_active = not account.is_active
        db.session.commit()
        
        status_text = 'مفعل' if account.is_active else 'معطل'
        flash(f'تم تغيير حالة الحساب إلى: {status_text}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('admin_accounts.list_accounts'))


@bp.route('/<int:account_id>/users', methods=['GET'])
@login_required
def account_users(account_id):
    """List all users in an account."""
    account = Account.query.get_or_404(account_id)
    users = _users_query().filter_by(account_id=account_id).all()
    
    return render_template('admin/account_users.html', account=account, users=users)


@bp.route('/<int:account_id>/users/create', methods=['GET', 'POST'])
@login_required
def create_account_user(account_id):
    """Create new user for an account (Super Admin only)."""
    account = Account.query.get_or_404(account_id)
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        
        if not username or not email or not password or not full_name:
            flash('جميع الحقول مطلوبة', 'danger')
            return redirect(url_for('admin_accounts.create_account_user', account_id=account_id))
        
        if len(password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
            return redirect(url_for('admin_accounts.create_account_user', account_id=account_id))
        
        try:
            new_user = User(
                account_id=account_id,
                username=username,
                email=email,
                full_name=full_name,
                is_active=True,
                is_admin=False,
                # Module permissions
                can_manage_workers=request.form.get('can_manage_workers') == 'on',
                can_manage_inventory=request.form.get('can_manage_inventory') == 'on',
                can_manage_production=request.form.get('can_manage_production') == 'on',
                can_manage_sales=request.form.get('can_manage_sales') == 'on',
                can_manage_accounting=request.form.get('can_manage_accounting') == 'on',
                can_manage_reports=request.form.get('can_manage_reports') == 'on',
                # Action permissions
                can_delete=request.form.get('can_delete') == 'on',
                can_edit=request.form.get('can_edit') == 'on',
                # Advanced production permissions
                can_manage_crop_health=request.form.get('can_manage_crop_health') == 'on',
                can_manage_production_batches=request.form.get('can_manage_production_batches') == 'on',
                can_manage_production_costs=request.form.get('can_manage_production_costs') == 'on',
                can_manage_production_stages=request.form.get('can_manage_production_stages') == 'on',
                can_view_analytics=request.form.get('can_view_analytics') == 'on',
            )
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash(f'تم إنشاء المستخدم "{username}" بنجاح', 'success')
            return redirect(url_for('admin_accounts.account_users', account_id=account_id))
        
        except IntegrityError:
            db.session.rollback()
            flash('اسم المستخدم أو البريد الإلكتروني موجود بالفعل', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('admin/create_account_user.html', account=account)


@bp.route('/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    """Delete an account and all its related data."""
    account = Account.query.get_or_404(account_id)
    
    try:
        # Delete all users in this account
        _users_query().filter_by(account_id=account_id).delete()
        
        # Delete the account
        db.session.delete(account)
        db.session.commit()
        
        flash(f'تم حذف الحساب "{account.name}" وجميع بيانات المستخدمين بنجاح', 'success')
        return redirect(url_for('admin_accounts.list_accounts'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء حذف الحساب: {str(e)}', 'danger')
        return redirect(url_for('admin_accounts.list_accounts'))


@bp.route('/<int:account_id>/users/<int:user_id>/change-password', methods=['GET', 'POST'])
@login_required
def change_user_password(account_id, user_id):
    """Change password for a user (Super Admin only)."""
    account = Account.query.get_or_404(account_id)
    user = _users_query().filter_by(id=user_id, account_id=account_id).first_or_404()
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or len(new_password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
            return redirect(url_for('admin_accounts.change_user_password', account_id=account_id, user_id=user_id))
        
        if new_password != confirm_password:
            flash('كلمة المرور والتأكيد غير متطابقة', 'danger')
            return redirect(url_for('admin_accounts.change_user_password', account_id=account_id, user_id=user_id))
        
        try:
            user.set_password(new_password)
            db.session.commit()
            
            flash(f'تم تغيير كلمة مرور "{user.username}" بنجاح', 'success')
            return redirect(url_for('admin_accounts.account_users', account_id=account_id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('admin/change_user_password.html', account=account, user=user)


@bp.route('/<int:account_id>/users/<int:user_id>/edit-permissions', methods=['GET', 'POST'])
@login_required
def edit_user_permissions(account_id, user_id):
    """Edit all permissions for a user."""
    account = Account.query.get_or_404(account_id)
    user = _users_query().filter_by(id=user_id, account_id=account_id).first_or_404()
    
    if request.method == 'POST':
        try:
            # Basic permissions
            user.is_active = request.form.get('is_active') == 'on'
            user.is_admin = request.form.get('is_admin') == 'on'
            
            # Module permissions
            user.can_manage_workers = request.form.get('can_manage_workers') == 'on'
            user.can_manage_inventory = request.form.get('can_manage_inventory') == 'on'
            user.can_manage_production = request.form.get('can_manage_production') == 'on'
            user.can_manage_sales = request.form.get('can_manage_sales') == 'on'
            user.can_manage_accounting = request.form.get('can_manage_accounting') == 'on'
            user.can_manage_reports = request.form.get('can_manage_reports') == 'on'
            
            # Action permissions
            user.can_delete = request.form.get('can_delete') == 'on'
            user.can_edit = request.form.get('can_edit') == 'on'
            
            # Advanced production permissions
            user.can_manage_crop_health = request.form.get('can_manage_crop_health') == 'on'
            user.can_manage_production_batches = request.form.get('can_manage_production_batches') == 'on'
            user.can_manage_production_costs = request.form.get('can_manage_production_costs') == 'on'
            user.can_manage_production_stages = request.form.get('can_manage_production_stages') == 'on'
            user.can_view_analytics = request.form.get('can_view_analytics') == 'on'
            
            db.session.commit()
            
            flash(f'تم تحديث صلاحيات "{user.username}" بنجاح', 'success')
            return redirect(url_for('admin_accounts.account_users', account_id=account_id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('admin/edit_user_permissions.html', account=account, user=user)


@bp.route('/<int:account_id>/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(account_id, user_id):
    """Delete a user from an account."""
    account = Account.query.get_or_404(account_id)
    user = _users_query().filter_by(id=user_id, account_id=account_id).first_or_404()
    
    # Prevent deleting the only admin in account
    admin_count = _users_query().filter_by(account_id=account_id, is_admin=True).count()
    if user.is_admin and admin_count == 1:
        flash('لا يمكن حذف المسؤول الوحيد من الحساب', 'danger')
        return redirect(url_for('admin_accounts.account_users', account_id=account_id))
    
    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        flash(f'تم حذف المستخدم "{username}" بنجاح', 'success')
        return redirect(url_for('admin_accounts.account_users', account_id=account_id))
    
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('admin_accounts.account_users', account_id=account_id))


@bp.route('/super-admin/permissions', methods=['GET', 'POST'])
@login_required
def super_admin_permissions():
    """Edit permissions for Super Admin."""
    if not _check_super_admin():
        flash('ليس لديك صلاحيات كافية', 'danger')
        return redirect(url_for('home.index'))
    
    super_admin = current_user
    
    if request.method == 'POST':
        try:
            # Module permissions
            super_admin.can_manage_workers = request.form.get('can_manage_workers') == 'on'
            super_admin.can_manage_inventory = request.form.get('can_manage_inventory') == 'on'
            super_admin.can_manage_production = request.form.get('can_manage_production') == 'on'
            super_admin.can_manage_sales = request.form.get('can_manage_sales') == 'on'
            super_admin.can_manage_accounting = request.form.get('can_manage_accounting') == 'on'
            super_admin.can_manage_reports = request.form.get('can_manage_reports') == 'on'
            
            # Action permissions
            super_admin.can_delete = request.form.get('can_delete') == 'on'
            super_admin.can_edit = request.form.get('can_edit') == 'on'
            
            # Advanced production permissions
            super_admin.can_manage_crop_health = request.form.get('can_manage_crop_health') == 'on'
            super_admin.can_manage_production_batches = request.form.get('can_manage_production_batches') == 'on'
            super_admin.can_manage_production_costs = request.form.get('can_manage_production_costs') == 'on'
            super_admin.can_manage_production_stages = request.form.get('can_manage_production_stages') == 'on'
            super_admin.can_view_analytics = request.form.get('can_view_analytics') == 'on'
            
            db.session.commit()
            
            flash('تم تحديث صلاحياتك بنجاح', 'success')
            return redirect(url_for('home.dashboard'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('admin/super_admin_permissions.html', user=super_admin)
