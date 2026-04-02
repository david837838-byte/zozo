from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app import db
from app.models.worker import Worker, WorkLog, MotorLog, Attendance, MonthlyAttendance
from app.models.accounting import (
    ClosedWorkerAccount,
    ExpenseCategory,
    EXPENSE_TRANSACTION_TYPE_ALIASES,
    Transaction,
    WORKER_REFERENCE_TYPE_ALIASES,
    is_expense_transaction,
)
from datetime import datetime, date
from calendar import monthrange

bp = Blueprint('workers', __name__, url_prefix='/workers')

WORKER_PAYMENT_KIND_LABELS = {
    'loan': 'سلفة',
    'advance': 'دفعة على الحساب',
}


def _safe_float(value, default=0.0):
    """Convert a form value to float with safe fallback."""
    try:
        if value is None:
            return default
        raw = str(value).strip()
        if raw == '':
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _safe_date(value, default=None):
    """Convert date string (YYYY-MM-DD) safely."""
    default_date = default or date.today()
    try:
        raw = str(value).strip()
        if not raw:
            return default_date
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default_date


def _get_or_create_worker_payment_category():
    """Ensure a dedicated accounting category for worker loans/advances."""
    category_name = 'دفعات وسلف العمال'
    category = ExpenseCategory.query.filter_by(name=category_name).first()
    if category:
        return category

    category = ExpenseCategory(
        name=category_name,
        description='قيود السلف والدفعات على الحساب المرتبطة بقسم العمال'
    )
    db.session.add(category)
    db.session.flush()
    return category


def _detect_worker_payment_kind(transaction):
    """Detect worker payment kind from stored marker/description."""
    notes = transaction.notes or ''
    description = transaction.description or ''

    if 'worker_payment_kind=loan' in notes:
        return 'loan'
    if 'worker_payment_kind=advance' in notes:
        return 'advance'

    if 'سلفة' in description:
        return 'loan'
    if 'دفعة' in description or 'على الحساب' in description:
        return 'advance'
    return 'other'


def _month_bounds(year, month):
    """Return first/last date for a month."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start, end


def _worker_month_payment_totals(worker_id, year, month):
    """Sum worker payments (loans/advances) within selected month."""
    period_start, period_end = _month_bounds(year, month)

    transactions = (
        Transaction.query.filter(
            Transaction.reference_id == worker_id,
            Transaction.reference_type.in_(WORKER_REFERENCE_TYPE_ALIASES),
            Transaction.transaction_type.in_(EXPENSE_TRANSACTION_TYPE_ALIASES),
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
        )
        .order_by(Transaction.transaction_date.asc(), Transaction.id.asc())
        .all()
    )

    loans = 0.0
    advances = 0.0
    total = 0.0
    for transaction in transactions:
        amount = transaction.amount or 0.0
        total += amount
        payment_kind = _detect_worker_payment_kind(transaction)
        if payment_kind == 'loan':
            loans += amount
        elif payment_kind == 'advance':
            advances += amount

    return {
        'transactions': transactions,
        'loans': loans,
        'advances': advances,
        'total': total,
        'from_date': period_start,
        'to_date': period_end,
    }


@bp.route('/')
@login_required
def index():
    """قائمة العمال"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    workers = Worker.query.order_by(Worker.name.asc()).all()

    work_log_stats = (
        db.session.query(
            WorkLog.worker_id.label('worker_id'),
            func.coalesce(func.sum(WorkLog.hours), 0.0).label('total_hours'),
            func.count(func.distinct(WorkLog.work_date)).label('worked_days'),
        )
        .group_by(WorkLog.worker_id)
        .all()
    )
    work_log_map = {
        row.worker_id: {
            'total_hours': float(row.total_hours or 0.0),
            'worked_days': int(row.worked_days or 0),
        }
        for row in work_log_stats
    }

    attendance_stats = (
        db.session.query(
            Attendance.worker_id.label('worker_id'),
            func.coalesce(func.sum(Attendance.hours_worked), 0.0).label('total_hours'),
            func.count(func.distinct(Attendance.attendance_date)).label('worked_days'),
        )
        .filter(or_(Attendance.status == 'حاضر', Attendance.is_present.is_(True)))
        .group_by(Attendance.worker_id)
        .all()
    )
    attendance_map = {
        row.worker_id: {
            'total_hours': float(row.total_hours or 0.0),
            'worked_days': int(row.worked_days or 0),
        }
        for row in attendance_stats
    }

    worker_summaries = {}
    for worker in workers:
        summary = work_log_map.get(worker.id)
        if not summary:
            summary = attendance_map.get(worker.id, {'total_hours': 0.0, 'worked_days': 0})
        worker_summaries[worker.id] = summary

    return render_template(
        'workers/index.html',
        workers=workers,
        worker_summaries=worker_summaries,
    )

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_worker():
    """إضافة عامل جديد"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('workers.index'))
    
    if request.method == 'POST':
        is_monthly = request.form.get('is_monthly') == 'on'
        hourly_rate = _safe_float(request.form.get('hourly_rate', 0))
        monthly_salary = _safe_float(request.form.get('monthly_salary', 0))

        if is_monthly:
            hourly_rate = 0.0
        else:
            monthly_salary = 0.0

        worker = Worker(
            name=request.form.get('name'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            is_monthly=is_monthly,
            work_location=request.form.get('work_location'),
            hourly_rate=hourly_rate,
            monthly_salary=monthly_salary
        )
        
        db.session.add(worker)
        db.session.commit()
        
        flash(f'تم إضافة العامل {worker.name} بنجاح', 'success')
        return redirect(url_for('workers.index'))
    
    return render_template('workers/add.html')

@bp.route('/<int:worker_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_worker(worker_id):
    """تعديل بيانات العامل"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('workers.index'))
    
    worker = Worker.query.get_or_404(worker_id)
    
    if request.method == 'POST':
        is_monthly = request.form.get('is_monthly') == 'on'
        hourly_rate = _safe_float(request.form.get('hourly_rate', 0))
        monthly_salary = _safe_float(request.form.get('monthly_salary', 0))

        if is_monthly:
            hourly_rate = 0.0
        else:
            monthly_salary = 0.0

        worker.name = request.form.get('name')
        worker.phone = request.form.get('phone')
        worker.email = request.form.get('email')
        worker.is_monthly = is_monthly
        worker.work_location = request.form.get('work_location')
        worker.hourly_rate = hourly_rate
        worker.monthly_salary = monthly_salary
        
        db.session.commit()
        flash(f'تم تحديث بيانات {worker.name} بنجاح', 'success')
        return redirect(url_for('workers.index'))
    
    return render_template('workers/edit.html', worker=worker)

@bp.route('/<int:worker_id>/add_hours', methods=['GET', 'POST'])
@login_required
def add_work_hours(worker_id):
    """إضافة ساعات عمل"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('workers.index'))
    
    worker = Worker.query.get_or_404(worker_id)
    
    if request.method == 'POST':
        work_log = WorkLog(
            worker_id=worker_id,
            work_date=datetime.strptime(request.form.get('work_date'), '%Y-%m-%d').date(),
            hours=float(request.form.get('hours')),
            shift_type=request.form.get('shift_type'),
            location=request.form.get('location'),
            notes=request.form.get('notes')
        )
        
        db.session.add(work_log)
        db.session.commit()
        
        flash(f'تم إضافة {work_log.hours} ساعات لـ {worker.name}', 'success')
        return redirect(url_for('workers.view_worker', worker_id=worker_id))
    
    return render_template('workers/add_hours.html', worker=worker)

@bp.route('/<int:worker_id>')
@login_required
def view_worker(worker_id):
    """عرض بيانات العامل وساعاته."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))

    worker = Worker.query.get_or_404(worker_id)
    work_logs = WorkLog.query.filter_by(worker_id=worker_id).all()
    motor_logs = MotorLog.query.filter_by(worker_id=worker_id).all()
    worker_transactions = (
        Transaction.query.filter(
            Transaction.reference_id == worker_id,
            Transaction.reference_type.in_(WORKER_REFERENCE_TYPE_ALIASES),
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .all()
    )

    total_hours = sum(log.hours for log in work_logs)

    payment_rows = []
    total_worker_loans = 0.0
    total_worker_advances = 0.0
    total_worker_payments = 0.0

    for transaction in worker_transactions:
        kind = _detect_worker_payment_kind(transaction)
        amount = transaction.amount or 0.0
        if is_expense_transaction(transaction.transaction_type):
            total_worker_payments += amount
            if kind == 'loan':
                total_worker_loans += amount
            elif kind == 'advance':
                total_worker_advances += amount

        payment_rows.append(
            {
                'transaction': transaction,
                'kind': kind,
                'kind_label': WORKER_PAYMENT_KIND_LABELS.get(kind, 'قيد مرتبط بالعامل'),
            }
        )

    return render_template(
        'workers/view.html',
        worker=worker,
        work_logs=work_logs,
        motor_logs=motor_logs,
        total_hours=total_hours,
        payment_rows=payment_rows,
        total_worker_loans=total_worker_loans,
        total_worker_advances=total_worker_advances,
        total_worker_payments=total_worker_payments,
        today_date=date.today().strftime('%Y-%m-%d'),
    )


@bp.route('/<int:worker_id>/add-payment', methods=['POST'])
@login_required
def add_worker_payment(worker_id):
    """Register worker loan/advance and mirror it in accounting."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('workers.view_worker', worker_id=worker_id))

    worker = Worker.query.get_or_404(worker_id)
    payment_kind = (request.form.get('payment_kind') or '').strip()
    amount = _safe_float(request.form.get('amount'), default=0.0)

    if payment_kind not in WORKER_PAYMENT_KIND_LABELS:
        flash('نوع الدفعة غير صحيح', 'warning')
        return redirect(url_for('workers.view_worker', worker_id=worker_id))

    if amount <= 0:
        flash('يرجى إدخال مبلغ صحيح أكبر من صفر', 'warning')
        return redirect(url_for('workers.view_worker', worker_id=worker_id))

    transaction_date = _safe_date(request.form.get('transaction_date'), default=date.today())
    user_description = (request.form.get('description') or '').strip()
    notes = (request.form.get('notes') or '').strip()

    description = user_description or f"{WORKER_PAYMENT_KIND_LABELS[payment_kind]} للعامل {worker.name}"
    marker = f"[worker_payment_kind={payment_kind}]"
    full_notes = f"{marker} {notes}".strip()

    try:
        category = _get_or_create_worker_payment_category()
        transaction = Transaction(
            category_id=category.id if category else None,
            transaction_type='مصروف',
            description=description,
            amount=amount,
            transaction_date=transaction_date,
            reference_type='عامل',
            reference_id=worker.id,
            notes=full_notes,
        )
        db.session.add(transaction)
        db.session.commit()
        flash(
            f"تم تسجيل {WORKER_PAYMENT_KIND_LABELS[payment_kind]} للعامل {worker.name} وربطها بالمحاسبة",
            'success',
        )
    except Exception:
        db.session.rollback()
        flash('حدث خطأ أثناء تسجيل الدفعة وربطها بالمحاسبة', 'danger')

    return redirect(url_for('workers.view_worker', worker_id=worker_id))

@bp.route('/<int:worker_id>/add_motor', methods=['GET', 'POST'])
@login_required
def add_motor_log(worker_id):
    """إضافة تسجيل ساعات محرك"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('workers.index'))
    
    worker = Worker.query.get_or_404(worker_id)
    
    if request.method == 'POST':
        motor_log = MotorLog(
            worker_id=worker_id,
            motor_name=request.form.get('motor_name'),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d %H:%M'),
            diesel_price_per_hour=float(request.form.get('diesel_price_per_hour', 0)),
            diesel_price_per_liter=float(request.form.get('diesel_price_per_liter', 0)),
            notes=request.form.get('notes')
        )
        
        db.session.add(motor_log)
        db.session.commit()
        
        flash(f'تم إضافة تسجيل المحرك {motor_log.motor_name}', 'success')
        return redirect(url_for('workers.view_worker', worker_id=worker_id))
    
    return render_template('workers/add_motor.html', worker=worker)

@bp.route('/<int:worker_id>/delete', methods=['POST'])
@login_required
def delete_worker(worker_id):
    """حذف عامل"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('workers.index'))
    
    worker = Worker.query.get_or_404(worker_id)
    db.session.delete(worker)
    db.session.commit()
    
    flash(f'تم حذف العامل {worker.name}', 'success')
    return redirect(url_for('workers.index'))


@bp.route('/<int:worker_id>/close', methods=['GET', 'POST'])
@login_required
def close_worker_account(worker_id):
    """تسكير حساب العامل"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية تسكير الحساب', 'danger')
        return redirect(url_for('workers.index'))
    
    worker = Worker.query.get_or_404(worker_id)

    if not worker.is_active:
        flash('حساب العامل مسكر بالفعل', 'warning')
        return redirect(url_for('workers.closed_accounts'))

    if request.method == 'POST':
        # إنشاء سجل حساب مسكر
        closed_account = ClosedWorkerAccount(
            worker_id=worker.id,
            worker_name=worker.name,
            phone=worker.phone,
            email=worker.email,
            is_monthly=worker.is_monthly,
            work_location=worker.work_location,
            hourly_rate=worker.hourly_rate,
            monthly_salary=worker.monthly_salary,
            closure_date=datetime.now().date(),
            closure_reason=request.form.get('closure_reason'),
            final_balance=float(request.form.get('final_balance', 0)),
            notes=request.form.get('notes')
        )

        db.session.add(closed_account)

        # تسكير حساب العامل (تعديل الحالة بدلاً من الحذف)
        worker.is_active = False
        db.session.commit()

        flash(f'تم تسكير حساب العامل {worker.name} بنجاح', 'success')
        return redirect(url_for('workers.index'))

    return render_template('workers/close_account.html', worker=worker)


@bp.route('/<int:worker_id>/reopen', methods=['POST'])
@login_required
def reopen_worker_account(worker_id):
    """إعادة فتح حساب العامل المسكر."""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية إعادة فتح الحساب', 'danger')
        return redirect(url_for('workers.closed_accounts'))

    worker = Worker.query.get(worker_id)
    if not worker:
        flash('تعذر العثور على العامل المرتبط بالحساب المسكر', 'danger')
        return redirect(url_for('workers.closed_accounts'))

    if worker.is_active:
        # تنظيف أي سجلات تسكير متبقية إن وجدت.
        stale_closed_accounts = ClosedWorkerAccount.query.filter_by(worker_id=worker.id).all()
        for account in stale_closed_accounts:
            db.session.delete(account)
        db.session.commit()

        flash('حساب العامل مفتوح بالفعل وتم تنظيف السجلات القديمة', 'info')
        return redirect(url_for('workers.index'))

    worker.is_active = True

    # إزالة سجلات التسكير للعامل حتى لا يبقى في قائمة الحسابات المسكرة.
    closed_accounts = ClosedWorkerAccount.query.filter_by(worker_id=worker.id).all()
    for account in closed_accounts:
        db.session.delete(account)

    db.session.commit()
    flash(f'تمت إعادة فتح حساب العامل {worker.name} بنجاح', 'success')
    return redirect(url_for('workers.index'))


@bp.route('/closed-accounts')
@login_required
def closed_accounts():
    """عرض قائمة الحسابات المسكرة للعمال"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    closed_accounts_list = ClosedWorkerAccount.query.order_by(ClosedWorkerAccount.closure_date.desc()).all()
    total_final_balance = sum(account.final_balance for account in closed_accounts_list)
    
    return render_template('workers/closed_accounts.html', 
                         closed_accounts=closed_accounts_list,
                         total_final_balance=total_final_balance)


# ==================== الحضور والغياب ====================

@bp.route('/attendance')
@login_required
def attendance():
    """قائمة الحضور"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))
    
    # الحصول على التاريخ المختار أو اليوم الحالي
    selected_date = request.args.get('date')
    if selected_date:
        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    # جلب الحضور ليوم معين
    attendances = Attendance.query.filter_by(attendance_date=selected_date).all()
    
    # جلب جميع العمال النشطين
    all_workers = Worker.query.filter_by(is_active=True).all()
    
    # العمال الذين لم يتم تسجيل حضورهم
    attended_worker_ids = {a.worker_id for a in attendances}
    unattended_workers = [w for w in all_workers if w.id not in attended_worker_ids]
    
    return render_template('workers/attendance.html',
                         attendances=attendances,
                         unattended_workers=unattended_workers,
                         selected_date=selected_date)

@bp.route('/attendance/<int:worker_id>/add', methods=['GET', 'POST'])
@login_required
def add_attendance(worker_id):
    """إضافة حضور للعامل"""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('workers.attendance'))
    
    worker = Worker.query.get_or_404(worker_id)
    
    if request.method == 'POST':
        attendance_date = datetime.strptime(request.form.get('attendance_date'), '%Y-%m-%d').date()
        
        # التحقق من عدم تكرار تسجيل نفس التاريخ
        existing = Attendance.query.filter_by(
            worker_id=worker_id,
            attendance_date=attendance_date
        ).first()
        
        if existing:
            flash('تم تسجيل الحضور لهذا التاريخ بالفعل', 'warning')
            return redirect(url_for('workers.add_attendance', worker_id=worker_id))
        
        attendance = Attendance(
            worker_id=worker_id,
            attendance_date=attendance_date,
            is_present=request.form.get('is_present') == 'on',
            status=request.form.get('status'),
            hours_worked=float(request.form.get('hours_worked', 8)),
            notes=request.form.get('notes')
        )
        
        db.session.add(attendance)
        db.session.commit()
        
        flash(f'تم تسجيل حضور {worker.name}', 'success')
        return redirect(url_for('workers.attendance'))
    
    return render_template('workers/add_attendance.html', worker=worker)

@bp.route('/attendance/<int:attendance_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_attendance(attendance_id):
    """تعديل الحضور"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('workers.attendance'))
    
    attendance = Attendance.query.get_or_404(attendance_id)
    
    if request.method == 'POST':
        attendance.is_present = request.form.get('is_present') == 'on'
        attendance.status = request.form.get('status')
        attendance.hours_worked = float(request.form.get('hours_worked', 8))
        attendance.notes = request.form.get('notes')
        
        db.session.commit()
        flash('تم تحديث الحضور بنجاح', 'success')
        return redirect(url_for('workers.attendance'))
    
    return render_template('workers/edit_attendance.html', attendance=attendance)

@bp.route('/attendance/<int:attendance_id>/delete', methods=['POST'])
@login_required
def delete_attendance(attendance_id):
    """حذف سجل الحضور"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('workers.attendance'))
    
    attendance = Attendance.query.get_or_404(attendance_id)
    worker_name = attendance.worker.name
    db.session.delete(attendance)
    db.session.commit()
    
    flash(f'تم حذف سجل الحضور لـ {worker_name}', 'success')
    return redirect(url_for('workers.attendance'))


def _build_or_refresh_monthly_summary(worker, year, month, persist=False):
    """Build monthly summary from daily attendance and optionally persist it."""
    attendances = Attendance.query.filter(
        Attendance.worker_id == worker.id
    ).filter(
        db.extract('year', Attendance.attendance_date) == year,
        db.extract('month', Attendance.attendance_date) == month
    ).all()

    if attendances:
        present_days = sum(1 for a in attendances if a.status == 'حاضر')
        absent_days = sum(1 for a in attendances if a.status == 'غياب')
        sick_days = sum(1 for a in attendances if a.status == 'مرض')
        vacation_days = sum(1 for a in attendances if a.status == 'إجازة')
        total_hours = sum(a.hours_worked for a in attendances)
    elif worker.is_monthly:
        present_days = 22
        absent_days = 0
        sick_days = 0
        vacation_days = 0
        total_hours = 22 * 8
    else:
        present_days = 0
        absent_days = 0
        sick_days = 0
        vacation_days = 0
        total_hours = 0

    monthly = MonthlyAttendance.query.filter_by(
        worker_id=worker.id,
        year=year,
        month=month
    ).first()

    if not monthly:
        monthly = MonthlyAttendance(worker_id=worker.id, year=year, month=month)
        if persist:
            db.session.add(monthly)

    hourly_rate = worker.hourly_rate or 0
    if worker.is_monthly:
        base_salary = worker.monthly_salary or 0
        absence_deductions = (absent_days * (base_salary / 30)) if base_salary > 0 else 0.0
    else:
        # Hourly workers should be paid by worked hours within the selected month.
        base_salary = (total_hours or 0) * hourly_rate
        absence_deductions = 0.0

    monthly.total_days = monthrange(year, month)[1]
    monthly.present_days = present_days
    monthly.absent_days = absent_days
    monthly.sick_days = sick_days
    monthly.vacation_days = vacation_days
    monthly.total_hours = total_hours
    monthly.base_salary = base_salary
    monthly.hourly_rate = hourly_rate
    monthly.overtime_hours = monthly.overtime_hours or 0.0
    monthly.bonuses = monthly.bonuses or 0.0
    monthly.deductions = absence_deductions
    monthly.calculate_net_salary()

    # Salary after base rules (attendance, overtime, bonuses, absence deductions)
    salary_before_worker_payments = monthly.net_salary or 0.0

    # Worker-linked payments for the selected month (loan / advance / any worker expense)
    month_payments = _worker_month_payment_totals(worker.id, year, month)
    worker_payment_deductions = month_payments['total'] or 0.0
    remaining_salary = salary_before_worker_payments - worker_payment_deductions

    # Runtime-only fields for reports/templates (no schema change)
    monthly.absence_deductions = absence_deductions
    monthly.salary_before_worker_payments = salary_before_worker_payments
    monthly.worker_payment_deductions = worker_payment_deductions
    monthly.net_salary_after_worker_payments = remaining_salary
    monthly.remaining_salary = remaining_salary
    monthly.worker_loans = month_payments['loans'] or 0.0
    monthly.worker_advances = month_payments['advances'] or 0.0

    return monthly, attendances


@bp.route('/monthly-attendance')
@login_required
def monthly_attendance():
    """تقرير حضور شهري."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)

    monthly_data = []
    workers = Worker.query.filter_by(is_active=True).order_by(Worker.name.asc()).all()

    for worker in workers:
        monthly, _ = _build_or_refresh_monthly_summary(worker, year, month, persist=True)
        monthly.worker = worker
        monthly_data.append(monthly)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('حدث خطأ أثناء حفظ الملخص الشهري', 'danger')

    total_present = sum(m.present_days for m in monthly_data)
    total_salary_before_payments = sum(
        getattr(m, 'salary_before_worker_payments', m.net_salary or 0.0) for m in monthly_data
    )
    total_salary = sum(getattr(m, 'remaining_salary', m.net_salary or 0.0) for m in monthly_data)
    total_worker_payments = sum(getattr(m, 'worker_payment_deductions', 0.0) for m in monthly_data)

    return render_template(
        'workers/monthly_attendance.html',
        monthly_data=monthly_data,
        year=year,
        month=month,
        total_present=total_present,
        total_salary_before_payments=total_salary_before_payments,
        total_worker_payments=total_worker_payments,
        total_salary=total_salary,
    )


@bp.route('/worker/<int:worker_id>/salary-report')
@login_required
def worker_salary_report(worker_id):
    """تقرير راتب العامل الشهري."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    worker = Worker.query.get_or_404(worker_id)

    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)

    monthly_summary, daily_attendances = _build_or_refresh_monthly_summary(
        worker, year, month, persist=True
    )
    month_payment_data = _worker_month_payment_totals(worker.id, year, month)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('حدث خطأ أثناء حفظ الملخص الشهري', 'danger')

    month_name = {
        1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
        5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
        9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
    }

    return render_template(
        'workers/worker_salary_report.html',
        worker=worker,
        daily_attendances=daily_attendances,
        monthly_summary=monthly_summary,
        month_payment_transactions=month_payment_data['transactions'],
        month_payment_total=month_payment_data['total'],
        month_payment_loans=month_payment_data['loans'],
        month_payment_advances=month_payment_data['advances'],
        year=year,
        month=month,
        month_name=month_name.get(month, ''),
    )
