import os
import shutil
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models.user import User
from app.models.box import BoxType, BoxUsage
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog

bp = Blueprint('settings', __name__, url_prefix='/settings')


def _backup_dir():
    backup_path = os.path.join(current_app.instance_path, 'backups')
    os.makedirs(backup_path, exist_ok=True)
    return backup_path


def _resolve_database_path():
    db_path = db.engine.url.database
    if not db_path:
        return None
    if os.path.isabs(db_path):
        return db_path
    return os.path.abspath(os.path.join(current_app.instance_path, db_path))


def _create_database_backup(prefix='backup'):
    db_path = _resolve_database_path()
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError('Database file is not available')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'{prefix}_{timestamp}.db'
    backup_path = os.path.join(_backup_dir(), backup_name)
    shutil.copy2(db_path, backup_path)
    return backup_path


def _list_backups(limit=12):
    items = []
    for file_name in os.listdir(_backup_dir()):
        if not file_name.lower().endswith('.db'):
            continue
        full_path = os.path.join(_backup_dir(), file_name)
        if not os.path.isfile(full_path):
            continue
        stats = os.stat(full_path)
        items.append(
            {
                'name': file_name,
                'path': full_path,
                'size': stats.st_size,
                'created_at': datetime.fromtimestamp(stats.st_mtime),
            }
        )

    items.sort(key=lambda row: row['created_at'], reverse=True)
    return items[:limit]


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except Exception:
        return None


def _run_auto_backup_if_due(backup_frequency):
    if backup_frequency not in {'daily', 'weekly'}:
        return

    now = datetime.now()
    last_auto_backup = _parse_iso_datetime(AppSetting.get_value('last_auto_backup_at'))
    required_interval = timedelta(days=1 if backup_frequency == 'daily' else 7)

    if last_auto_backup and now - last_auto_backup < required_interval:
        return

    backup_path = _create_database_backup(prefix='auto_backup')
    AppSetting.set_value('last_auto_backup_at', now.isoformat())
    AppSetting.set_value('last_backup_file', os.path.basename(backup_path))
    AppSetting.set_value('last_backup_at', now.isoformat())


@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """صفحة الإعدادات الرئيسية"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        action = (request.form.get('action') or 'update_site_name').strip()

        if action == 'update_backup_settings':
            backup_frequency = (request.form.get('backup_frequency') or 'daily').strip().lower()
            if backup_frequency not in {'none', 'daily', 'weekly'}:
                flash('قيمة تكرار النسخ الاحتياطي غير صحيحة', 'danger')
            else:
                AppSetting.set_value('backup_frequency', backup_frequency)
                flash('تم تحديث إعدادات النسخ الاحتياطي بنجاح', 'success')
        else:
            site_name = (request.form.get('site_name') or '').strip()
            if not site_name:
                flash('اسم الموقع مطلوب', 'danger')
            else:
                AppSetting.set_value('site_name', site_name)
                flash('تم تحديث اسم الموقع بنجاح', 'success')

        return redirect(url_for('settings.index'))

    site_name = AppSetting.get_value('site_name', 'نظام المزرعة')
    backup_frequency = AppSetting.get_value('backup_frequency', 'daily')

    try:
        _run_auto_backup_if_due(backup_frequency)
    except Exception:
        flash('تعذر تشغيل النسخ الاحتياطي التلقائي حالياً', 'warning')

    backups = _list_backups(limit=12)
    last_backup_at = _parse_iso_datetime(AppSetting.get_value('last_backup_at'))
    last_restore_at = _parse_iso_datetime(AppSetting.get_value('last_restore_at'))
    last_backup_file = AppSetting.get_value('last_backup_file')

    return render_template(
        'settings/index.html',
        site_name=site_name,
        backup_frequency=backup_frequency,
        backups=backups,
        last_backup_at=last_backup_at,
        last_restore_at=last_restore_at,
        last_backup_file=last_backup_file,
    )


@bp.route('/backup/create', methods=['POST'])
@login_required
def create_backup():
    """Create backup and send it as a downloadable file."""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية تنفيذ النسخ الاحتياطي', 'danger')
        return redirect(url_for('home.index'))

    try:
        backup_path = _create_database_backup(prefix='manual_backup')
        now = datetime.now()
        AppSetting.set_value('last_backup_at', now.isoformat())
        AppSetting.set_value('last_backup_file', os.path.basename(backup_path))

        return send_file(
            backup_path,
            as_attachment=True,
            download_name=os.path.basename(backup_path),
            mimetype='application/octet-stream',
        )
    except Exception:
        flash('حدث خطأ أثناء إنشاء النسخة الاحتياطية', 'danger')
        return redirect(url_for('settings.index'))


@bp.route('/backup/restore', methods=['POST'])
@login_required
def restore_backup():
    """Restore database from uploaded backup file."""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية استرجاع النسخة الاحتياطية', 'danger')
        return redirect(url_for('home.index'))

    uploaded_file = request.files.get('backup_file')
    if not uploaded_file or not uploaded_file.filename:
        flash('يرجى اختيار ملف نسخة احتياطية', 'warning')
        return redirect(url_for('settings.index'))

    extension = os.path.splitext(uploaded_file.filename)[1].lower()
    if extension not in {'.db', '.sqlite', '.sqlite3'}:
        flash('امتداد الملف غير مدعوم للاسترجاع', 'danger')
        return redirect(url_for('settings.index'))

    upload_temp_path = os.path.join(
        _backup_dir(),
        f"restore_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
    )

    try:
        uploaded_file.save(upload_temp_path)
        if os.path.getsize(upload_temp_path) <= 0:
            raise ValueError('Uploaded backup file is empty')

        db_path = _resolve_database_path()
        if not db_path:
            raise FileNotFoundError('Database path not found')

        db.session.remove()
        db.engine.dispose()
        shutil.copy2(upload_temp_path, db_path)

        AppSetting.set_value('last_restore_at', datetime.now().isoformat())
        flash('تم استرجاع النسخة الاحتياطية بنجاح', 'success')
    except Exception:
        flash('حدث خطأ أثناء استرجاع النسخة الاحتياطية', 'danger')
    finally:
        if os.path.exists(upload_temp_path):
            try:
                os.remove(upload_temp_path)
            except Exception:
                pass

    return redirect(url_for('settings.index'))


@bp.route('/audit-logs')
@login_required
def audit_logs():
    """Audit trail viewer."""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى سجل التدقيق', 'danger')
        return redirect(url_for('home.index'))

    page = max(request.args.get('page', 1, type=int), 1)
    selected_action = (request.args.get('action') or '').strip().lower()
    selected_entity = (request.args.get('entity_type') or '').strip()
    selected_username = (request.args.get('username') or '').strip()
    from_date_raw = (request.args.get('from_date') or '').strip()
    to_date_raw = (request.args.get('to_date') or '').strip()

    from_date = _parse_date(from_date_raw)
    to_date = _parse_date(to_date_raw)

    if from_date_raw and not from_date:
        flash('تنسيق تاريخ البداية غير صحيح', 'warning')
    if to_date_raw and not to_date:
        flash('تنسيق تاريخ النهاية غير صحيح', 'warning')

    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date

    query = AuditLog.query

    if selected_action in {'create', 'update', 'delete'}:
        query = query.filter(AuditLog.action == selected_action)

    if selected_entity:
        query = query.filter(AuditLog.entity_type == selected_entity)

    if selected_username:
        query = query.filter(func.lower(AuditLog.username).contains(selected_username.lower()))

    if from_date:
        query = query.filter(AuditLog.created_at >= datetime.combine(from_date, datetime.min.time()))

    if to_date:
        query = query.filter(
            AuditLog.created_at < datetime.combine(to_date + timedelta(days=1), datetime.min.time())
        )

    pagination = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(
        page=page,
        per_page=40,
        error_out=False,
    )

    entity_types = [
        row[0]
        for row in db.session.query(AuditLog.entity_type)
        .filter(AuditLog.entity_type.isnot(None))
        .distinct()
        .order_by(AuditLog.entity_type.asc())
        .all()
    ]

    return render_template(
        'settings/audit_logs.html',
        logs=pagination.items,
        pagination=pagination,
        selected_action=selected_action,
        selected_entity=selected_entity,
        selected_username=selected_username,
        from_date=from_date.strftime('%Y-%m-%d') if from_date else '',
        to_date=to_date.strftime('%Y-%m-%d') if to_date else '',
        entity_types=entity_types,
    )

@bp.route('/users')
@login_required
def users():
    """إدارة المستخدمين"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    users = User.query.all()
    return render_template('settings/users.html', users=users)

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """تعديل بيانات المستخدم والصلاحيات"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('settings.users'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.email = request.form.get('email')
        user.is_active = request.form.get('is_active') == 'on'
        user.is_admin = request.form.get('is_admin') == 'on'
        
        # إذا كان إدميناً، سيكون لديه كامل الصلاحيات
        if user.is_admin:
            user.can_manage_workers = True
            user.can_manage_inventory = True
            user.can_manage_production = True
            user.can_manage_sales = True
            user.can_manage_accounting = True
            user.can_manage_reports = True
            user.can_delete = True
            user.can_edit = True
        else:
            # إذا لم يكن إدميناً، اقرأ الصلاحيات من النموذج
            user.can_manage_workers = request.form.get('can_manage_workers') == 'on'
            user.can_manage_inventory = request.form.get('can_manage_inventory') == 'on'
            user.can_manage_production = request.form.get('can_manage_production') == 'on'
            user.can_manage_sales = request.form.get('can_manage_sales') == 'on'
            user.can_manage_accounting = request.form.get('can_manage_accounting') == 'on'
            user.can_manage_reports = request.form.get('can_manage_reports') == 'on'
            user.can_delete = request.form.get('can_delete') == 'on'
            user.can_edit = request.form.get('can_edit') == 'on'
            
            # الصلاحيات المتقدمة للإنتاج
            user.can_manage_crop_health = request.form.get('can_manage_crop_health') == 'on'
            user.can_manage_production_batches = request.form.get('can_manage_production_batches') == 'on'
            user.can_manage_production_costs = request.form.get('can_manage_production_costs') == 'on'
            user.can_manage_production_stages = request.form.get('can_manage_production_stages') == 'on'
            user.can_view_analytics = request.form.get('can_view_analytics') == 'on'
        
        db.session.commit()
        flash(f'تم تحديث بيانات {user.full_name}', 'success')
        return redirect(url_for('settings.users'))
    
    return render_template('settings/edit_user.html', user=user)

@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """حذف مستخدم"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('settings.users'))
    
    if user_id == current_user.id:
        flash('لا يمكنك حذف حسابك الخاص', 'danger')
        return redirect(url_for('settings.users'))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    
    flash(f'تم حذف المستخدم {user.full_name}', 'success')
    return redirect(url_for('settings.users'))

@bp.route('/boxes')
@login_required
def boxes():
    """إدارة الشراحات والكراتين"""
    if not current_user.is_admin and not current_user.can_manage_production:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    boxes = BoxType.query.all()
    return render_template('settings/boxes.html', boxes=boxes)

@bp.route('/boxes/add', methods=['GET', 'POST'])
@login_required
def add_box():
    """إضافة نوع صندوق"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('settings.boxes'))
    
    if request.method == 'POST':
        box = BoxType(
            name=request.form.get('name'),
            box_type=request.form.get('box_type'),
            capacity=float(request.form.get('capacity')) if request.form.get('capacity') else None,
            unit=request.form.get('unit'),
            cost_per_box=float(request.form.get('cost_per_box')),
            supplier=request.form.get('supplier')
        )
        
        db.session.add(box)
        db.session.commit()
        
        flash(f'تم إضافة النوع {box.name}', 'success')
        return redirect(url_for('settings.boxes'))
    
    return render_template('settings/add_box.html')

@bp.route('/boxes/<int:box_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_box(box_id):
    """تعديل نوع صندوق"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('settings.boxes'))
    
    box = BoxType.query.get_or_404(box_id)
    
    if request.method == 'POST':
        box.name = request.form.get('name')
        box.box_type = request.form.get('box_type')
        box.capacity = float(request.form.get('capacity')) if request.form.get('capacity') else None
        box.unit = request.form.get('unit')
        box.cost_per_box = float(request.form.get('cost_per_box'))
        box.supplier = request.form.get('supplier')
        
        db.session.commit()
        flash(f'تم تحديث {box.name}', 'success')
        return redirect(url_for('settings.boxes'))
    
    return render_template('settings/edit_box.html', box=box)

@bp.route('/boxes/<int:box_id>/usage', methods=['GET', 'POST'])
@login_required
def add_box_usage(box_id):
    """تسجيل استخدام صندوق"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('settings.boxes'))
    
    box = BoxType.query.get_or_404(box_id)
    
    if request.method == 'POST':
        usage = BoxUsage(
            box_type_id=box_id,
            quantity_used=int(request.form.get('quantity_used')),
            usage_date=datetime.strptime(request.form.get('usage_date'), '%Y-%m-%d').date(),
            purpose=request.form.get('purpose'),
            notes=request.form.get('notes')
        )
        
        usage.calculate_cost()
        
        db.session.add(usage)
        db.session.commit()
        
        flash('تم تسجيل الاستخدام بنجاح', 'success')
        return redirect(url_for('settings.boxes'))
    
    return render_template('settings/add_box_usage.html', box=box)

@bp.route('/boxes/<int:box_id>/delete', methods=['POST'])
@login_required
def delete_box(box_id):
    """حذف نوع صندوق"""
    if not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('settings.boxes'))
    
    box = BoxType.query.get_or_404(box_id)
    db.session.delete(box)
    db.session.commit()
    
    flash(f'تم حذف النوع {box.name}', 'success')
    return redirect(url_for('settings.boxes'))

# ==================== إعدادات الحساب الشخصي ====================

@bp.route('/profile')
@login_required
def profile():
    """صفحة الملف الشخصي"""
    return render_template('settings/profile.html', user=current_user)

@bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """تعديل الملف الشخصي"""
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.email = request.form.get('email')
        
        db.session.commit()
        flash('تم تحديث ملفك الشخصي بنجاح', 'success')
        return redirect(url_for('settings.profile'))
    
    return render_template('settings/edit_profile.html', user=current_user)
