"""
مسارات إدارة المحركات
Motors Management Routes
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.motor import Motor, MotorUsage, OperatorQuota, MotorCost
from datetime import datetime, timedelta
from sqlalchemy import func

motors_bp = Blueprint('motors', __name__, url_prefix='/motors')


def _can_access_motors():
    """Centralized access rule for motors module."""
    return current_user.is_admin or current_user.can_manage_inventory


@motors_bp.before_request
def enforce_motor_permissions():
    """Protect all motors routes with a consistent permission check."""
    if not current_user.is_authenticated:
        return None

    if not _can_access_motors():
        flash('ليس لديك صلاحية للوصول إلى قسم المحركات', 'danger')
        return redirect(url_for('home.index'))
    return None


# ==================== المحركات ====================

@motors_bp.route('/', methods=['GET'])
@login_required
def index():
    """عرض قائمة المحركات"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Motor.query
    if search:
        query = query.filter(
            (Motor.name.contains(search)) |
            (Motor.motor_type.contains(search)) |
            (Motor.location.contains(search))
        )
    
    motors = query.paginate(page=page, per_page=10)
    
    return render_template('motors/index.html', motors=motors, search=search)


@motors_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_motor():
    """إضافة محرك جديد"""
    if request.method == 'POST':
        try:
            motor = Motor(
                name=request.form.get('name').strip(),
                motor_type=request.form.get('motor_type'),
                model=request.form.get('model', '').strip(),
                serial_number=request.form.get('serial_number', '').strip() or None,
                capacity=float(request.form.get('capacity', 0)) if request.form.get('capacity') else None,
                description=request.form.get('description', '').strip(),
                location=request.form.get('location', '').strip(),
                is_active=request.form.get('is_active') == 'on'
            )
            
            if request.form.get('purchase_date'):
                motor.purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
            
            db.session.add(motor)
            db.session.commit()
            
            flash(f'تم إضافة المحرك "{motor.name}" بنجاح', 'success')
            return redirect(url_for('motors.index'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('motors/add.html')


@motors_bp.route('/<int:motor_id>/view')
@login_required
def view_motor(motor_id):
    """عرض تفاصيل المحرك مع ساعات التشغيل"""
    motor = Motor.query.get_or_404(motor_id)
    
    # حساب إحصائيات الاستخدام الإجمالية
    total_hours = db.session.query(func.sum(MotorUsage.total_hours)).filter_by(motor_id=motor_id).scalar() or 0
    usage_count = MotorUsage.query.filter_by(motor_id=motor_id).count()
    total_fuel_cost = db.session.query(func.sum(MotorUsage.fuel_cost)).filter_by(motor_id=motor_id).scalar() or 0
    
    # حساب ساعات التشغيل لكل شخص (مجموع الساعات)
    operator_stats = db.session.query(
        MotorUsage.operator_name,
        func.sum(MotorUsage.total_hours).label('total_hours'),
        func.count(MotorUsage.id).label('usage_count'),
        func.sum(MotorUsage.fuel_cost).label('total_fuel_cost')
    ).filter_by(motor_id=motor_id).group_by(MotorUsage.operator_name).order_by(
        func.sum(MotorUsage.total_hours).desc()
    ).all()
    
    # آخر 10 استخدامات
    recent_usages = MotorUsage.query.filter_by(motor_id=motor_id).order_by(
        MotorUsage.usage_date.desc(),
        MotorUsage.created_at.desc()
    ).limit(10).all()
    
    return render_template('motors/view.html',
                         motor=motor,
                         total_hours=total_hours,
                         usage_count=usage_count,
                         total_fuel_cost=total_fuel_cost,
                         operator_stats=operator_stats,
                         recent_usages=recent_usages)


@motors_bp.route('/<int:motor_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_motor(motor_id):
    """تعديل المحرك"""
    motor = Motor.query.get_or_404(motor_id)
    
    if request.method == 'POST':
        try:
            motor.name = request.form.get('name').strip()
            motor.motor_type = request.form.get('motor_type')
            motor.model = request.form.get('model', '').strip()
            motor.serial_number = request.form.get('serial_number', '').strip() or None
            motor.capacity = float(request.form.get('capacity', 0)) if request.form.get('capacity') else None
            motor.description = request.form.get('description', '').strip()
            motor.location = request.form.get('location', '').strip()
            motor.is_active = request.form.get('is_active') == 'on'
            
            if request.form.get('purchase_date'):
                motor.purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
            
            db.session.commit()
            flash(f'تم تحديث المحرك "{motor.name}" بنجاح', 'success')
            return redirect(url_for('motors.index'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # حساب ساعات التشغيل لكل شخص
    operator_stats = db.session.query(
        MotorUsage.operator_name,
        func.sum(MotorUsage.total_hours).label('total_hours'),
        func.count(MotorUsage.id).label('usage_count'),
        func.sum(MotorUsage.fuel_cost).label('total_fuel_cost')
    ).filter_by(motor_id=motor_id).group_by(MotorUsage.operator_name).order_by(
        func.sum(MotorUsage.total_hours).desc()
    ).all()
    
    # إجمالي الساعات والإحصائيات
    total_hours = db.session.query(func.sum(MotorUsage.total_hours)).filter_by(motor_id=motor_id).scalar() or 0
    usage_count = MotorUsage.query.filter_by(motor_id=motor_id).count()
    
    return render_template('motors/edit.html',
                         motor=motor,
                         operator_stats=operator_stats,
                         total_hours=total_hours,
                         usage_count=usage_count)


@motors_bp.route('/<int:motor_id>/delete', methods=['POST'])
@login_required
def delete_motor(motor_id):
    """حذف المحرك"""
    motor = Motor.query.get_or_404(motor_id)
    
    try:
        motor_name = motor.name
        db.session.delete(motor)
        db.session.commit()
        flash(f'تم حذف المحرك "{motor_name}" بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('motors.index'))


# ==================== تسجيل استخدام المحركات ====================

@motors_bp.route('/usage', methods=['GET'])
@login_required
def usage_logs():
    """عرض سجل الاستخدام"""
    page = request.args.get('page', 1, type=int)
    motor_id = request.args.get('motor_id', type=int)
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    query = MotorUsage.query.order_by(MotorUsage.usage_date.desc(), MotorUsage.created_at.desc())
    
    if motor_id:
        query = query.filter_by(motor_id=motor_id)
    
    if from_date:
        try:
            from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
            query = query.filter(MotorUsage.usage_date >= from_date_obj)
        except ValueError:
            flash('تنسيق تاريخ البداية غير صحيح', 'warning')
            from_date = None
    
    if to_date:
        try:
            to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
            query = query.filter(MotorUsage.usage_date <= to_date_obj)
        except ValueError:
            flash('تنسيق تاريخ النهاية غير صحيح', 'warning')
            to_date = None
    
    usages = query.paginate(page=page, per_page=15)
    motors = Motor.query.filter_by(is_active=True).order_by(Motor.name).all()
    
    # حساب إحصائيات
    total_hours = db.session.query(func.sum(MotorUsage.total_hours)).scalar() or 0
    total_fuel_cost = db.session.query(func.sum(MotorUsage.fuel_cost)).scalar() or 0
    total_fuel = db.session.query(func.sum(MotorUsage.fuel_added)).scalar() or 0
    
    return render_template('motors/usage.html',
                         usages=usages,
                         motors=motors,
                         motor_id=motor_id,
                         from_date=from_date,
                         to_date=to_date,
                         total_hours=total_hours,
                         total_fuel_cost=total_fuel_cost,
                         total_fuel=total_fuel)


@motors_bp.route('/usage/add', methods=['GET', 'POST'])
@login_required
def add_usage():
    """تسجيل استخدام جديد"""
    if request.method == 'POST':
        try:
            motor_id = request.form.get('motor_id', type=int)
            motor = Motor.query.get_or_404(motor_id)
            operator_name = request.form.get('operator_name').strip()
            
            # التحقق من القيم المدخلة
            start_hours_str = request.form.get('start_hours', '').strip()
            end_hours_str = request.form.get('end_hours', '').strip()
            
            if not start_hours_str or not end_hours_str:
                flash('الرجاء إدخال ساعات البداية والنهاية', 'danger')
                return redirect(url_for('motors.add_usage'))
            
            try:
                start_hours = float(start_hours_str)
                end_hours = float(end_hours_str)
            except ValueError:
                flash('الرجاء إدخال أرقام صحيحة للساعات', 'danger')
                return redirect(url_for('motors.add_usage'))
            
            total_hours = end_hours - start_hours
            
            if request.form.get('usage_date'):
                usage_date = datetime.strptime(request.form.get('usage_date'), '%Y-%m-%d').date()
            else:
                usage_date = datetime.utcnow().date()
            
            # فحص منع التكرار: نفس المشغل والمحرك في نفس اليوم
            existing_usage = MotorUsage.query.filter_by(
                operator_name=operator_name,
                motor_id=motor_id,
                usage_date=usage_date
            ).first()
            
            if existing_usage:
                # تحديث السجل الموجود بدلاً من الإضافة الجديدة
                existing_usage.end_hours = end_hours
                existing_usage.start_hours = start_hours
                existing_usage.calculate_total_hours()
                existing_usage.usage_purpose = request.form.get('usage_purpose', '').strip()
                existing_usage.location = request.form.get('location', '').strip()
                existing_usage.notes = request.form.get('notes', '').strip()
                existing_usage.operator_phone = request.form.get('operator_phone', '').strip()
                existing_usage.fuel_added = float(request.form.get('fuel_added', 0)) if request.form.get('fuel_added') else None
                existing_usage.fuel_cost = float(request.form.get('fuel_cost', 0)) if request.form.get('fuel_cost') else None
                
                db.session.commit()
                flash(f'تم تحديث استخدام "{operator_name}" للمحرك "{motor.name}" بنجاح', 'success')
                return redirect(url_for('motors.usage_logs'))
            
            # فحص حصة الساعات السنوية للمشغل
            current_year = usage_date.year
            quota = OperatorQuota.query.filter_by(
                operator_name=operator_name,
                year=current_year
            ).first()
            
            # إذا لم توجد حصة للسنة الحالية، أنشئها
            if not quota:
                quota = OperatorQuota(
                    operator_name=operator_name,
                    year=current_year,
                    allocated_hours=0,  # سيتم تحديثها من قبل المسؤول
                    used_hours=0
                )
                db.session.add(quota)
                db.session.flush()
            
            # إذا كانت هناك حصة محددة، تحقق من الساعات المتبقية
            if quota.allocated_hours > 0:
                if quota.status != 'نشط':
                    flash(f'حساب "{operator_name}" معطل أو مجمد', 'warning')
                    return redirect(url_for('motors.add_usage'))
                
                potential_used = quota.used_hours + total_hours
                if potential_used > quota.allocated_hours:
                    remaining = quota.allocated_hours - quota.used_hours
                    flash(f'لا توجد ساعات كافية لـ "{operator_name}". الساعات المتبقية: {remaining:.2f} ساعة', 'danger')
                    return redirect(url_for('motors.add_usage'))
            
            # إنشاء السجل الجديد
            usage = MotorUsage(
                motor_id=motor_id,
                user_id=current_user.id,
                operator_name=operator_name,
                operator_phone=request.form.get('operator_phone', '').strip(),
                start_hours=start_hours,
                end_hours=end_hours,
                usage_purpose=request.form.get('usage_purpose', '').strip(),
                location=request.form.get('location', '').strip(),
                notes=request.form.get('notes', '').strip(),
                fuel_added=float(request.form.get('fuel_added', 0)) if request.form.get('fuel_added') else None,
                fuel_cost=float(request.form.get('fuel_cost', 0)) if request.form.get('fuel_cost') else None,
                usage_date=usage_date
            )
            
            usage.calculate_total_hours()
            
            # تحديث ساعات الحصة
            if quota.used_hours is None:
                quota.used_hours = 0
            if usage.total_hours is None:
                usage.total_hours = 0
            quota.used_hours += usage.total_hours
            quota.update_remaining_hours()
            
            db.session.add(usage)
            db.session.commit()
            
            flash(f'تم تسجيل استخدام المحرك "{motor.name}" بنجاح', 'success')
            return redirect(url_for('motors.usage_logs'))
        
        except ValueError as e:
            db.session.rollback()
            flash('الرجاء التحقق من الأرقام المدخلة', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الحصول على قائمة أسماء المشغلين الفريدة من جدول الحصص والاستخدام
    quota_operators = db.session.query(OperatorQuota.operator_name).distinct().order_by(OperatorQuota.operator_name).all()
    usage_operators = db.session.query(MotorUsage.operator_name).distinct().order_by(MotorUsage.operator_name).all()
    
    # دمج الأسماء من كلا الجدولين وإزالة التكرارات
    all_names = set()
    all_names.update([op[0] for op in quota_operators if op[0]])
    all_names.update([op[0] for op in usage_operators if op[0]])
    operator_names = sorted(list(all_names))
    
    motors = Motor.query.filter_by(is_active=True).order_by(Motor.name).all()
    return render_template('motors/add_usage.html', motors=motors, operator_names=operator_names)


@motors_bp.route('/usage/<int:usage_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_usage(usage_id):
    """تعديل تسجيل الاستخدام"""
    usage = MotorUsage.query.get_or_404(usage_id)
    
    if request.method == 'POST':
        try:
            usage.motor_id = request.form.get('motor_id', type=int)
            usage.operator_name = request.form.get('operator_name').strip()
            usage.operator_phone = request.form.get('operator_phone', '').strip()
            
            # التحقق من القيم المدخلة
            start_hours_str = request.form.get('start_hours', '').strip()
            end_hours_str = request.form.get('end_hours', '').strip()
            
            if not start_hours_str or not end_hours_str:
                flash('الرجاء إدخال ساعات البداية والنهاية', 'danger')
                return redirect(url_for('motors.edit_usage', usage_id=usage_id))
            
            try:
                usage.start_hours = float(start_hours_str)
                usage.end_hours = float(end_hours_str)
            except ValueError:
                flash('الرجاء إدخال أرقام صحيحة للساعات', 'danger')
                return redirect(url_for('motors.edit_usage', usage_id=usage_id))
            
            usage.usage_purpose = request.form.get('usage_purpose', '').strip()
            usage.location = request.form.get('location', '').strip()
            usage.notes = request.form.get('notes', '').strip()
            usage.fuel_added = float(request.form.get('fuel_added', 0)) if request.form.get('fuel_added') else None
            usage.fuel_cost = float(request.form.get('fuel_cost', 0)) if request.form.get('fuel_cost') else None
            
            if request.form.get('usage_date'):
                usage.usage_date = datetime.strptime(request.form.get('usage_date'), '%Y-%m-%d').date()
            
            usage.calculate_total_hours()
            
            db.session.commit()
            flash('تم تحديث التسجيل بنجاح', 'success')
            return redirect(url_for('motors.usage_logs'))
        
        except ValueError:
            db.session.rollback()
            flash('الرجاء التحقق من الأرقام المدخلة', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    motors = Motor.query.filter_by(is_active=True).order_by(Motor.name).all()
    
    # الحصول على قائمة أسماء المشغلين الفريدة من جدول الحصص والاستخدام
    quota_operators = db.session.query(OperatorQuota.operator_name).distinct().order_by(OperatorQuota.operator_name).all()
    usage_operators = db.session.query(MotorUsage.operator_name).distinct().order_by(MotorUsage.operator_name).all()
    
    # دمج الأسماء من كلا الجدولين وإزالة التكرارات
    all_names = set()
    all_names.update([op[0] for op in quota_operators if op[0]])
    all_names.update([op[0] for op in usage_operators if op[0]])
    operator_names = sorted(list(all_names))
    
    return render_template('motors/edit_usage.html', usage=usage, motors=motors, operator_names=operator_names)


@motors_bp.route('/usage/<int:usage_id>/delete', methods=['POST'])
@login_required
def delete_usage(usage_id):
    """حذف تسجيل الاستخدام"""
    usage = MotorUsage.query.get_or_404(usage_id)
    
    try:
        db.session.delete(usage)
        db.session.commit()
        flash('تم حذف التسجيل بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('motors.usage_logs'))


# ==================== إدارة حصص الساعات السنوية ====================

@motors_bp.route('/quotas', methods=['GET'])
@login_required
def operator_quotas():
    """عرض حصص الساعات السنوية للمشغلين"""
    from app.models.motor import OperatorQuota
    
    page = request.args.get('page', 1, type=int)
    year = request.args.get('year', type=int)
    search = request.args.get('search', '')
    
    if not year:
        year = datetime.now().year
    
    query = OperatorQuota.query.filter_by(year=year)
    
    if search:
        query = query.filter(OperatorQuota.operator_name.contains(search))
    
    quotas = query.order_by(OperatorQuota.operator_name).paginate(page=page, per_page=15)
    
    # الحصول على السنوات المتاحة
    available_years = db.session.query(OperatorQuota.year).distinct().order_by(OperatorQuota.year.desc()).all()
    years = [y[0] for y in available_years]
    if year not in years:
        years.insert(0, year)
    
    return render_template('motors/quotas.html',
                         quotas=quotas,
                         year=year,
                         years=sorted(years, reverse=True),
                         search=search)


@motors_bp.route('/quotas/add', methods=['GET', 'POST'])
@login_required
def add_quota():
    """إضافة حصة ساعات جديدة"""
    if request.method == 'POST':
        try:
            operator_name = request.form.get('operator_name').strip()
            year = int(request.form.get('year'))
            allocated_hours = float(request.form.get('allocated_hours'))
            status = request.form.get('status', 'نشط')
            notes = request.form.get('notes', '').strip()
            
            # فحص الوجود
            existing = OperatorQuota.query.filter_by(
                operator_name=operator_name,
                year=year
            ).first()
            
            if existing:
                flash(f'الحصة موجودة بالفعل لـ "{operator_name}" في عام {year}', 'warning')
                return redirect(url_for('motors.operator_quotas', year=year))
            
            quota = OperatorQuota(
                operator_name=operator_name,
                year=year,
                allocated_hours=allocated_hours,
                status=status,
                notes=notes
            )
            quota.update_remaining_hours()
            
            db.session.add(quota)
            db.session.commit()
            
            flash(f'تم إضافة حصة "{operator_name}" ({allocated_hours} ساعة) بنجاح', 'success')
            return redirect(url_for('motors.operator_quotas', year=year))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('motors/add_quota.html')


@motors_bp.route('/quotas/<int:quota_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_quota(quota_id):
    """تعديل حصة الساعات"""

    quota = OperatorQuota.query.get_or_404(quota_id)
    
    if request.method == 'POST':
        try:
            quota.allocated_hours = float(request.form.get('allocated_hours'))
            quota.status = request.form.get('status', 'نشط')
            quota.notes = request.form.get('notes', '').strip()
            quota.update_remaining_hours()
            
            db.session.commit()
            flash(f'تم تحديث حصة "{quota.operator_name}" بنجاح', 'success')
            return redirect(url_for('motors.operator_quotas', year=quota.year))
        
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('motors/edit_quota.html', quota=quota)


@motors_bp.route('/quotas/<int:quota_id>/delete', methods=['POST'])
@login_required
def delete_quota(quota_id):
    """حذف حصة الساعات"""

    quota = OperatorQuota.query.get_or_404(quota_id)
    year = quota.year
    
    try:
        operator_name = quota.operator_name
        db.session.delete(quota)
        db.session.commit()
        flash(f'تم حذف حصة "{operator_name}" بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('motors.operator_quotas', year=year))


@motors_bp.route('/report/operators', methods=['GET'])
@login_required
def operators_annual_report():
    """تقرير سنوي لساعات المشغلين"""
    year = request.args.get('year', type=int)
    if not year:
        year = datetime.now().year
    
    # الحصول على جميع المشغلين والحصص في السنة
    quotas = OperatorQuota.query.filter_by(year=year).order_by(OperatorQuota.operator_name).all()
    
    # حساب الساعات الفعلية المستخدمة من قاعدة البيانات
    for quota in quotas:
        # استخدام التاريخ لحساب الساعات من السنة المطلوبة
        from datetime import date as date_type
        year_start = date_type(year, 1, 1)
        year_end = date_type(year, 12, 31)
        
        used_from_db = db.session.query(func.sum(MotorUsage.total_hours)).filter(
            MotorUsage.operator_name == quota.operator_name,
            MotorUsage.usage_date >= year_start,
            MotorUsage.usage_date <= year_end
        ).scalar() or 0
        
        # تحديث من قاعدة البيانات إذا اختلفت
        if abs(quota.used_hours - used_from_db) > 0.01:
            quota.used_hours = used_from_db
            quota.update_remaining_hours()
    
    # حفظ التحديثات
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    # البيانات الإجمالية
    total_allocated = sum((q.allocated_hours if q.allocated_hours else 0) for q in quotas)
    total_used = sum((q.used_hours if q.used_hours else 0) for q in quotas)
    total_remaining = sum((q.remaining_hours if q.remaining_hours else 0) for q in quotas)
    
    # السنوات المتاحة
    available_years = db.session.query(
        func.extract('year', MotorUsage.usage_date).label('year')
    ).distinct().order_by(func.extract('year', MotorUsage.usage_date).desc()).all()
    years = [int(y[0]) for y in available_years if y[0]]
    
    return render_template('motors/operators_report.html',
                         quotas=quotas,
                         year=year,
                         years=sorted(years, reverse=True),
                         total_allocated=total_allocated,
                         total_used=total_used,
                         total_remaining=total_remaining)


# ==================== API والتقارير ====================

@motors_bp.route('/api/motor-stats/<int:motor_id>')
@login_required
def motor_stats(motor_id):
    """إحصائيات المحرك"""
    motor = Motor.query.get_or_404(motor_id)
    
    # إجمالي الساعات
    total_hours = db.session.query(func.sum(MotorUsage.total_hours)).filter_by(motor_id=motor_id).scalar() or 0
    
    # عدد مرات الاستخدام
    usage_count = MotorUsage.query.filter_by(motor_id=motor_id).count()
    
    # إجمالي تكاليف الوقود
    total_fuel_cost = db.session.query(func.sum(MotorUsage.fuel_cost)).filter_by(motor_id=motor_id).scalar() or 0
    
    # إجمالي الوقود المستخدم
    total_fuel = db.session.query(func.sum(MotorUsage.fuel_added)).filter_by(motor_id=motor_id).scalar() or 0
    
    # آخر استخدام
    last_usage = MotorUsage.query.filter_by(motor_id=motor_id).order_by(MotorUsage.usage_date.desc()).first()
    
    return jsonify({
        'total_hours': float(total_hours),
        'usage_count': usage_count,
        'total_fuel_cost': float(total_fuel_cost),
        'total_fuel': float(total_fuel),
        'last_usage_date': last_usage.usage_date.isoformat() if last_usage else None,
        'last_operator': last_usage.operator_name if last_usage else None
    })


@motors_bp.route('/report')
@login_required
def report():
    """تقرير فترة زمنية"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    motor_id = request.args.get('motor_id', type=int)
    
    query = MotorUsage.query
    
    if motor_id:
        query = query.filter_by(motor_id=motor_id)
    
    if from_date:
        try:
            from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
            query = query.filter(MotorUsage.usage_date >= from_date_obj)
        except ValueError:
            flash('تنسيق تاريخ البداية غير صحيح', 'warning')
            from_date = None
    else:
        from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
        query = query.filter(MotorUsage.usage_date >= from_date_obj)
    
    if to_date:
        try:
            to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
            query = query.filter(MotorUsage.usage_date <= to_date_obj)
        except ValueError:
            flash('تنسيق تاريخ النهاية غير صحيح', 'warning')
            to_date = None
    else:
        to_date = datetime.now().strftime('%Y-%m-%d')
    
    usages = query.order_by(MotorUsage.usage_date.desc()).all()
    motors = Motor.query.filter_by(is_active=True).order_by(Motor.name).all()
    
    # حساب الإحصائيات
    summary = {
        'total_hours': sum(u.total_hours or 0 for u in usages),
        'total_fuel_cost': sum(u.fuel_cost or 0 for u in usages),
        'total_fuel': sum(u.fuel_added or 0 for u in usages),
        'usage_count': len(usages)
    }
    
    return render_template('motors/report.html',
                         usages=usages,
                         motors=motors,
                         motor_id=motor_id,
                         from_date=from_date,
                         to_date=to_date,
                         summary=summary)

# ==================== Motor Costs ====================

@motors_bp.route('/costs/list')
@login_required
def motor_costs():
    """قائمة تكاليف المحركات"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('motors.index'))
    
    costs = MotorCost.query.order_by(MotorCost.cost_date.desc()).all()
    total_cost = sum(c.total_cost for c in costs)
    
    # Group by cost type
    by_type = {}
    for cost in costs:
        cost_type = cost.cost_type
        if cost_type not in by_type:
            by_type[cost_type] = {
                'quantity': 0,
                'total_cost': 0,
                'costs': []
            }
        by_type[cost_type]['quantity'] += cost.quantity
        by_type[cost_type]['total_cost'] += cost.total_cost
        by_type[cost_type]['costs'].append(cost)
    
    return render_template('motors/motor_costs.html', 
                         costs=costs, 
                         total_cost=total_cost,
                         by_type=by_type)

@motors_bp.route('/<int:motor_id>/cost/add', methods=['GET', 'POST'])
@login_required
def add_motor_cost(motor_id):
    """إضافة تكلفة محرك"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('motors.motor_costs'))
    
    motor = Motor.query.get_or_404(motor_id)
    
    if request.method == 'POST':
        cost = MotorCost(
            motor_id=motor_id,
            cost_type=request.form.get('cost_type'),
            quantity=float(request.form.get('quantity')),
            unit_price=float(request.form.get('unit_price')),
            cost_date=datetime.strptime(request.form.get('cost_date'), '%Y-%m-%d').date(),
            supplier=request.form.get('supplier'),
            invoice_number=request.form.get('invoice_number'),
            notes=request.form.get('notes')
        )
        
        cost.calculate_total_cost()
        
        db.session.add(cost)
        db.session.commit()
        
        flash('تم تسجيل التكلفة بنجاح', 'success')
        return redirect(url_for('motors.motor_costs'))
    
    return render_template('motors/add_motor_cost.html', motor=motor)

@motors_bp.route('/cost/<int:cost_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_motor_cost(cost_id):
    """تعديل تكلفة محرك"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('motors.motor_costs'))
    
    cost = MotorCost.query.get_or_404(cost_id)
    
    if request.method == 'POST':
        cost.cost_type = request.form.get('cost_type')
        cost.quantity = float(request.form.get('quantity'))
        cost.unit_price = float(request.form.get('unit_price'))
        cost.cost_date = datetime.strptime(request.form.get('cost_date'), '%Y-%m-%d').date()
        cost.supplier = request.form.get('supplier')
        cost.invoice_number = request.form.get('invoice_number')
        cost.notes = request.form.get('notes')
        
        cost.calculate_total_cost()
        
        db.session.commit()
        flash('تم تحديث التكلفة بنجاح', 'success')
        return redirect(url_for('motors.motor_costs'))
    
    return render_template('motors/edit_motor_cost.html', cost=cost)

@motors_bp.route('/cost/<int:cost_id>/delete', methods=['POST'])
@login_required
def delete_motor_cost(cost_id):
    """حذف تكلفة محرك"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('motors.motor_costs'))
    
    cost = MotorCost.query.get_or_404(cost_id)
    db.session.delete(cost)
    db.session.commit()
    
    flash('تم حذف التكلفة بنجاح', 'success')
    return redirect(url_for('motors.motor_costs'))

@motors_bp.route('/costs/report')
@login_required
def motor_costs_report():
    """تقرير تكاليف المحركات السنوي"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('motors.index'))
    
    # تحديد السنة الحالية
    current_year = datetime.now().year
    year_start = datetime(current_year, 1, 1).date()
    year_end = datetime(current_year, 12, 31).date()
    
    # جلب جميع التكاليف للسنة الحالية
    costs = MotorCost.query.filter(
        MotorCost.cost_date >= year_start,
        MotorCost.cost_date <= year_end
    ).order_by(MotorCost.cost_date.desc()).all()
    
    # حساب الإحصائيات
    total_cost = sum(c.total_cost for c in costs)
    total_quantity = sum(c.quantity for c in costs)
    
    # تجميع حسب نوع التكلفة والمحرك
    by_type_and_motor = {}
    for cost in costs:
        key = (cost.cost_type, cost.motor.name)
        if key not in by_type_and_motor:
            by_type_and_motor[key] = {
                'quantity': 0,
                'total_cost': 0,
                'costs': []
            }
        by_type_and_motor[key]['quantity'] += cost.quantity
        by_type_and_motor[key]['total_cost'] += cost.total_cost
        by_type_and_motor[key]['costs'].append(cost)
    
    return render_template('motors/motor_costs_report.html',
                         costs=costs,
                         total_cost=total_cost,
                         total_quantity=total_quantity,
                         by_type_and_motor=by_type_and_motor,
                         year=current_year)
