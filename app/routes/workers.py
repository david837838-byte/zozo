from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app import db
from app.models.worker import WorkerFamily, Worker, WorkLog, MotorLog, Attendance, MonthlyAttendance
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
FEMALE_GENDER_ALIASES = {'أنثى', 'انثى', 'بنت', 'female', 'f'}
MALE_GENDER_ALIASES = {'ذكر', 'شاب', 'male', 'm'}


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


def _safe_int(value, default=None):
    """Convert value to int with safe fallback."""
    try:
        if value is None:
            return default
        raw = str(value).strip()
        if raw == '':
            return default
        return int(raw)
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


def _family_rates_for_gender(family, gender):
    """Return hourly/monthly rates from family based on gender."""
    if not family:
        return 0.0, 0.0
    normalized_gender = _normalize_gender(gender)
    if normalized_gender == 'أنثى':
        return (family.female_hourly_rate or 0.0), (family.female_monthly_salary or 0.0)
    return (family.male_hourly_rate or 0.0), (family.male_monthly_salary or 0.0)


def _normalize_gender(value):
    """Normalize worker gender to canonical Arabic values."""
    raw = (value or '').strip().lower()
    if raw in FEMALE_GENDER_ALIASES:
        return 'أنثى'
    if raw in MALE_GENDER_ALIASES:
        return 'ذكر'
    return None


def _is_female_gender(value):
    """Check whether given gender value maps to female."""
    return _normalize_gender(value) == 'أنثى'


def _is_male_gender(value):
    """Check whether given gender value maps to male."""
    return _normalize_gender(value) == 'ذكر'


def _count_workers_by_gender(workers):
    """Count workers by normalized gender."""
    male_count = 0
    female_count = 0
    unknown_count = 0
    for worker in workers:
        if _is_female_gender(worker.gender):
            female_count += 1
        elif _is_male_gender(worker.gender):
            male_count += 1
        else:
            unknown_count += 1
    return male_count, female_count, unknown_count


ATTENDANCE_STATUS_CHOICES = ('حاضر', 'غياب', 'مرض', 'إجازة')
GROUP_DISTRIBUTION_METHODS = ('equal', 'by_hours', 'manual')


def _normalize_distribution_method(value):
    """Return normalized group distribution method."""
    method = (value or '').strip().lower()
    if method in GROUP_DISTRIBUTION_METHODS:
        return method
    return 'equal'


def _split_amount_evenly(total_amount, worker_ids):
    """Split amount equally and keep 2-decimal total consistent."""
    cleaned_total = max(0.0, round(float(total_amount or 0.0), 2))
    if not worker_ids:
        return {}
    base_amount = round(cleaned_total / len(worker_ids), 2)
    allocations = {worker_id: base_amount for worker_id in worker_ids}
    diff = round(cleaned_total - sum(allocations.values()), 2)
    if diff != 0:
        allocations[worker_ids[-1]] = round(allocations[worker_ids[-1]] + diff, 2)
    return allocations


def _split_amount_by_weights(total_amount, worker_ids, weights_map):
    """Split amount by weights and keep 2-decimal total consistent."""
    cleaned_total = max(0.0, round(float(total_amount or 0.0), 2))
    if not worker_ids:
        return {}

    weighted_rows = []
    for worker_id in worker_ids:
        weight = max(0.0, float(weights_map.get(worker_id, 0.0) or 0.0))
        weighted_rows.append((worker_id, weight))

    weight_sum = sum(weight for _, weight in weighted_rows)
    if weight_sum <= 0:
        return _split_amount_evenly(cleaned_total, worker_ids)

    allocations = {
        worker_id: round(cleaned_total * (weight / weight_sum), 2)
        for worker_id, weight in weighted_rows
    }
    diff = round(cleaned_total - sum(allocations.values()), 2)
    if diff != 0:
        target_worker_id = max(weighted_rows, key=lambda row: row[1])[0]
        allocations[target_worker_id] = round(allocations[target_worker_id] + diff, 2)
    return allocations


def _safe_optional_date(value):
    """Convert optional date string (YYYY-MM-DD) to date or None."""
    try:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _extract_marker_value(text, marker_key):
    """Extract marker value like [marker_key=value] from notes text."""
    if not text:
        return None
    raw_text = str(text)
    prefix = f'[{marker_key}='
    start = raw_text.find(prefix)
    if start < 0:
        return None
    value_start = start + len(prefix)
    value_end = raw_text.find(']', value_start)
    if value_end < 0:
        return None
    value = raw_text[value_start:value_end].strip()
    return value or None


def _get_or_create_worker_payment_category():
    """Ensure a dedicated accounting category for worker loans/advances."""
    category_name = 'دفعات وسلف العمال'
    account_id = current_user.account_id if current_user else None
    
    if not account_id:
        return None
    
    # البحث عن فئة موجودة لنفس الحساب والاسم
    category = ExpenseCategory.query.filter_by(
        account_id=account_id,
        name=category_name
    ).first()
    
    if category:
        return category
    
    # محاولة إنشاء فئة جديدة
    try:
        category = ExpenseCategory(
            account_id=account_id,
            name=category_name,
            description='قيود السلف والدفعات على الحساب المرتبطة بقسم العمال'
        )
        db.session.add(category)
        db.session.flush()
        return category
    except Exception:
        # في حالة الفشل، ابحث مجدداً
        db.session.rollback()
        category = ExpenseCategory.query.filter_by(
            account_id=account_id,
            name=category_name
        ).first()
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
    
    families = WorkerFamily.query.filter_by(is_active=True).order_by(WorkerFamily.family_name.asc()).all()

    if request.method == 'POST':
        is_monthly = request.form.get('is_monthly') == 'on'
        hourly_rate = _safe_float(request.form.get('hourly_rate', 0))
        monthly_salary = _safe_float(request.form.get('monthly_salary', 0))
        family_id = _safe_int(request.form.get('family_id'))
        gender = _normalize_gender(request.form.get('gender'))
        use_family_rates = request.form.get('use_family_rates') == 'on'
        family = WorkerFamily.query.get(family_id) if family_id else None

        if use_family_rates:
            if not family:
                flash('يرجى اختيار العائلة لتفعيل تسعير العائلة', 'warning')
                return render_template('workers/add.html', families=families)
            if gender not in ('ذكر', 'أنثى'):
                flash('يرجى اختيار الجنس لتطبيق تسعير العائلة', 'warning')
                return render_template('workers/add.html', families=families)
            family_hourly, family_monthly = _family_rates_for_gender(family, gender)
            if is_monthly:
                hourly_rate = 0.0
                monthly_salary = family_monthly
            else:
                hourly_rate = family_hourly
                monthly_salary = 0.0
        else:
            if is_monthly:
                hourly_rate = 0.0
            else:
                monthly_salary = 0.0

        worker = Worker(
            name=request.form.get('name'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            family_id=family.id if family else None,
            gender=gender,
            is_monthly=is_monthly,
            use_family_rates=use_family_rates,
            work_location=request.form.get('work_location'),
            hourly_rate=hourly_rate,
            monthly_salary=monthly_salary
        )
        
        db.session.add(worker)
        db.session.commit()
        
        flash(f'تم إضافة العامل {worker.name} بنجاح', 'success')
        return redirect(url_for('workers.index'))
    
    return render_template('workers/add.html', families=families)

@bp.route('/<int:worker_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_worker(worker_id):
    """تعديل بيانات العامل"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('workers.index'))
    
    worker = Worker.query.get_or_404(worker_id)
    families = WorkerFamily.query.order_by(WorkerFamily.family_name.asc()).all()
    
    if request.method == 'POST':
        is_monthly = request.form.get('is_monthly') == 'on'
        hourly_rate = _safe_float(request.form.get('hourly_rate', 0))
        monthly_salary = _safe_float(request.form.get('monthly_salary', 0))
        family_id = _safe_int(request.form.get('family_id'))
        gender = _normalize_gender(request.form.get('gender'))
        use_family_rates = request.form.get('use_family_rates') == 'on'
        family = WorkerFamily.query.get(family_id) if family_id else None

        if use_family_rates:
            if not family:
                flash('يرجى اختيار العائلة لتفعيل تسعير العائلة', 'warning')
                return render_template('workers/edit.html', worker=worker, families=families)
            if gender not in ('ذكر', 'أنثى'):
                flash('يرجى اختيار الجنس لتطبيق تسعير العائلة', 'warning')
                return render_template('workers/edit.html', worker=worker, families=families)
            family_hourly, family_monthly = _family_rates_for_gender(family, gender)
            if is_monthly:
                hourly_rate = 0.0
                monthly_salary = family_monthly
            else:
                hourly_rate = family_hourly
                monthly_salary = 0.0
        else:
            if is_monthly:
                hourly_rate = 0.0
            else:
                monthly_salary = 0.0

        worker.name = request.form.get('name')
        worker.phone = request.form.get('phone')
        worker.email = request.form.get('email')
        worker.family_id = family.id if family else None
        worker.gender = gender
        worker.is_monthly = is_monthly
        worker.use_family_rates = use_family_rates
        worker.work_location = request.form.get('work_location')
        worker.hourly_rate = hourly_rate
        worker.monthly_salary = monthly_salary
        
        db.session.commit()
        flash(f'تم تحديث بيانات {worker.name} بنجاح', 'success')
        return redirect(url_for('workers.index'))
    
    return render_template('workers/edit.html', worker=worker, families=families)

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
            account_id=current_user.account_id,
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


@bp.route('/group-section')
@login_required
def group_section():
    """واجهة القسم الجماعي للعمال."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    families_count = WorkerFamily.query.count()
    linked_workers_count = Worker.query.filter(Worker.family_id.isnot(None)).count()
    return render_template(
        'workers/group_section.html',
        families_count=families_count,
        linked_workers_count=linked_workers_count,
    )


@bp.route('/group-section/families')
@login_required
def group_families():
    """قائمة عائلات العمال."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    families = WorkerFamily.query.order_by(WorkerFamily.family_name.asc()).all()
    family_worker_counts = {
        row.family_id: int(row.workers_count or 0)
        for row in db.session.query(
            Worker.family_id.label('family_id'),
            func.count(Worker.id).label('workers_count'),
        )
        .filter(Worker.family_id.isnot(None))
        .group_by(Worker.family_id)
        .all()
    }
    return render_template(
        'workers/group_families.html',
        families=families,
        family_worker_counts=family_worker_counts,
    )


@bp.route('/group-section/families/add', methods=['GET', 'POST'])
@login_required
def add_family():
    """إضافة عائلة عمال جديدة."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('workers.group_families'))

    if request.method == 'POST':
        family_name = (request.form.get('family_name') or '').strip()
        if not family_name:
            flash('اسم العائلة مطلوب', 'warning')
            return render_template('workers/add_family.html')

        existing = WorkerFamily.query.filter_by(family_name=family_name).first()
        if existing:
            flash('هذه العائلة موجودة مسبقًا', 'warning')
            return render_template('workers/add_family.html')

        family = WorkerFamily(
            family_name=family_name,
            contact_name=(request.form.get('contact_name') or '').strip() or None,
            phone=(request.form.get('phone') or '').strip() or None,
            notes=(request.form.get('notes') or '').strip() or None,
            is_active=request.form.get('is_active') == 'on',
            male_hourly_rate=_safe_float(request.form.get('male_hourly_rate'), 0.0),
            female_hourly_rate=_safe_float(request.form.get('female_hourly_rate'), 0.0),
            male_monthly_salary=_safe_float(request.form.get('male_monthly_salary'), 0.0),
            female_monthly_salary=_safe_float(request.form.get('female_monthly_salary'), 0.0),
        )
        db.session.add(family)
        db.session.commit()
        flash(f'تمت إضافة عائلة {family.family_name} بنجاح', 'success')
        return redirect(url_for('workers.group_families'))

    return render_template('workers/add_family.html')


@bp.route('/group-section/families/<int:family_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_family(family_id):
    """تعديل بيانات عائلة العمال."""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('workers.group_families'))

    family = WorkerFamily.query.get_or_404(family_id)

    if request.method == 'POST':
        family_name = (request.form.get('family_name') or '').strip()
        if not family_name:
            flash('اسم العائلة مطلوب', 'warning')
            return render_template('workers/edit_family.html', family=family)

        existing = WorkerFamily.query.filter_by(family_name=family_name).first()
        if existing and existing.id != family.id:
            flash('اسم العائلة مستخدم بالفعل', 'warning')
            return render_template('workers/edit_family.html', family=family)

        family.family_name = family_name
        family.contact_name = (request.form.get('contact_name') or '').strip() or None
        family.phone = (request.form.get('phone') or '').strip() or None
        family.notes = (request.form.get('notes') or '').strip() or None
        family.is_active = request.form.get('is_active') == 'on'
        family.male_hourly_rate = _safe_float(request.form.get('male_hourly_rate'), 0.0)
        family.female_hourly_rate = _safe_float(request.form.get('female_hourly_rate'), 0.0)
        family.male_monthly_salary = _safe_float(request.form.get('male_monthly_salary'), 0.0)
        family.female_monthly_salary = _safe_float(request.form.get('female_monthly_salary'), 0.0)

        db.session.commit()
        flash(f'تم تحديث عائلة {family.family_name} بنجاح', 'success')
        return redirect(url_for('workers.group_families'))

    return render_template('workers/edit_family.html', family=family)


@bp.route('/group-section/families/<int:family_id>/delete', methods=['POST'])
@login_required
def delete_family(family_id):
    """حذف عائلة عمال."""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('workers.group_families'))

    family = WorkerFamily.query.get_or_404(family_id)
    linked_workers_count = Worker.query.filter_by(family_id=family.id).count()
    if linked_workers_count > 0:
        flash('لا يمكن حذف العائلة لأنها مرتبطة بعمال. قم بفك الربط أولًا.', 'warning')
        return redirect(url_for('workers.group_families'))

    family_name = family.family_name
    db.session.delete(family)
    db.session.commit()
    flash(f'تم حذف عائلة {family_name}', 'success')
    return redirect(url_for('workers.group_families'))


@bp.route('/group-section/attendance', methods=['GET', 'POST'])
@login_required
def group_attendance():
    """تسجيل حضور جماعي لعائلة كاملة في صفحة واحدة."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    families = WorkerFamily.query.filter_by(is_active=True).order_by(WorkerFamily.family_name.asc()).all()

    selected_family_id = _safe_int(request.values.get('family_id'))
    selected_date = _safe_date(request.values.get('date'), default=date.today())
    male_default_hours = max(0.0, _safe_float(request.values.get('male_hours'), 8.0))
    female_default_hours = max(0.0, _safe_float(request.values.get('female_hours'), 8.0))

    selected_family = WorkerFamily.query.get(selected_family_id) if selected_family_id else None
    family_workers = []
    existing_attendances = {}
    female_worker_ids = set()
    male_worker_ids = set()

    if selected_family:
        family_workers = (
            Worker.query.filter_by(family_id=selected_family.id, is_active=True)
            .order_by(Worker.name.asc())
            .all()
        )
        female_worker_ids = {worker.id for worker in family_workers if _is_female_gender(worker.gender)}
        male_worker_ids = {worker.id for worker in family_workers if _is_male_gender(worker.gender)}
        worker_ids = [worker.id for worker in family_workers]
        if worker_ids:
            existing_rows = (
                Attendance.query.filter(
                    Attendance.worker_id.in_(worker_ids),
                    Attendance.attendance_date == selected_date,
                )
                .order_by(Attendance.id.asc())
                .all()
            )
            existing_attendances = {row.worker_id: row for row in existing_rows}

    if request.method == 'POST':
        if not selected_family:
            flash('يرجى اختيار العائلة أولًا', 'warning')
            return redirect(url_for('workers.group_attendance'))

        if not family_workers:
            flash('لا يوجد عمال نشطون ضمن هذه العائلة', 'warning')
            return redirect(
                url_for(
                    'workers.group_attendance',
                    family_id=selected_family.id,
                    date=selected_date.strftime('%Y-%m-%d'),
                    male_hours=male_default_hours,
                    female_hours=female_default_hours,
                )
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        global_notes = (request.form.get('notes') or '').strip()

        for worker in family_workers:
            include_worker = request.form.get(f'include_{worker.id}') == 'on'
            if not include_worker:
                skipped_count += 1
                continue

            submitted_gender = _normalize_gender(request.form.get(f'gender_{worker.id}'))
            if submitted_gender and worker.gender != submitted_gender:
                worker.gender = submitted_gender
            if submitted_gender == 'أنثى':
                female_worker_ids.add(worker.id)
                male_worker_ids.discard(worker.id)
            elif submitted_gender == 'ذكر':
                male_worker_ids.add(worker.id)
                female_worker_ids.discard(worker.id)

            status = (request.form.get(f'status_{worker.id}') or 'حاضر').strip()
            if status not in ATTENDANCE_STATUS_CHOICES:
                status = 'حاضر'

            raw_hours = request.form.get(f'hours_{worker.id}')
            if raw_hours is None or str(raw_hours).strip() == '':
                default_hours = female_default_hours if _is_female_gender(worker.gender) else male_default_hours
                hours_worked = default_hours if status == 'حاضر' else 0.0
            else:
                hours_worked = max(0.0, _safe_float(raw_hours, 0.0))

            row_notes = (request.form.get(f'notes_{worker.id}') or '').strip()
            final_notes = row_notes or global_notes or None
            is_present = status == 'حاضر'

            existing = existing_attendances.get(worker.id)
            if existing:
                existing.status = status
                existing.is_present = is_present
                existing.hours_worked = hours_worked
                existing.notes = final_notes
                updated_count += 1
            else:
                db.session.add(
                    Attendance(
                        worker_id=worker.id,
                        attendance_date=selected_date,
                        is_present=is_present,
                        status=status,
                        hours_worked=hours_worked,
                        notes=final_notes,
                    )
                )
                created_count += 1

        db.session.commit()
        flash(
            f'تم حفظ الحضور الجماعي: جديد {created_count}، محدث {updated_count}، متروك {skipped_count}',
            'success',
        )
        return redirect(
            url_for(
                'workers.group_attendance',
                family_id=selected_family.id,
                date=selected_date.strftime('%Y-%m-%d'),
                male_hours=male_default_hours,
                female_hours=female_default_hours,
            )
        )

    return render_template(
        'workers/group_attendance.html',
        families=families,
        selected_family=selected_family,
        selected_date=selected_date,
        male_default_hours=male_default_hours,
        female_default_hours=female_default_hours,
        family_workers=family_workers,
        existing_attendances=existing_attendances,
        female_worker_ids=female_worker_ids,
        male_worker_ids=male_worker_ids,
        status_choices=ATTENDANCE_STATUS_CHOICES,
    )


@bp.route('/group-section/attendance/receipt')
@login_required
def group_attendance_receipt():
    """إيصال حضور جماعي مختصر."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    family_id = _safe_int(request.args.get('family_id'))
    receipt_date = _safe_date(request.args.get('date'), default=date.today())
    if not family_id:
        flash('يرجى اختيار العائلة أولًا', 'warning')
        return redirect(url_for('workers.group_attendance'))

    family = WorkerFamily.query.get_or_404(family_id)
    family_workers = (
        Worker.query.filter_by(family_id=family.id, is_active=True)
        .order_by(Worker.name.asc())
        .all()
    )
    worker_ids = [worker.id for worker in family_workers]

    attendance_rows = []
    if worker_ids:
        attendance_rows = (
            Attendance.query.filter(
                Attendance.worker_id.in_(worker_ids),
                Attendance.attendance_date == receipt_date,
            )
            .order_by(Attendance.id.asc())
            .all()
        )
    day_payment_total = 0.0
    if worker_ids:
        day_payment_total = sum(
            (tx.amount or 0.0)
            for tx in Transaction.query.filter(
                Transaction.reference_id.in_(worker_ids),
                Transaction.reference_type.in_(WORKER_REFERENCE_TYPE_ALIASES),
                Transaction.transaction_type.in_(EXPENSE_TRANSACTION_TYPE_ALIASES),
                Transaction.transaction_date == receipt_date,
            ).all()
        )

    male_count, female_count, _unknown_count = _count_workers_by_gender(family_workers)
    total_hours = sum((row.hours_worked or 0.0) for row in attendance_rows)

    receipt_number = f"GAT-{receipt_date.strftime('%Y%m%d')}-{family.id:04d}"
    return render_template(
        'workers/group_attendance_receipt.html',
        family=family,
        receipt_date=receipt_date,
        receipt_number=receipt_number,
        male_count=male_count,
        female_count=female_count,
        total_hours=total_hours,
        day_payment_total=day_payment_total,
        printed_at=datetime.now(),
    )


@bp.route('/group-section/payments', methods=['GET', 'POST'])
@login_required
def group_payments():
    """تسجيل دفعات جماعية للعائلة وتوزيعها على العمال."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))
    
    # التحقق من أن المستخدم لديه حساب مرتبط
    if not current_user.account_id:
        flash('لا يمكن تسجيل الدفعات بدون حساب مرتبط', 'danger')
        return redirect(url_for('workers.index'))

    families = WorkerFamily.query.filter_by(account_id=current_user.account_id, is_active=True).order_by(WorkerFamily.family_name.asc()).all()

    # جمع البيانات من النموذج والـ URL (query string)
    if request.method == 'POST':
        source_values = request.form.to_dict()
        # إضافة query string values إذا كانت موجودة
        source_values.update(request.args.to_dict())
    else:
        source_values = request.args.to_dict()
    
    selected_family_id = _safe_int(source_values.get('family_id'))
    selected_date = _safe_date(source_values.get('date'), default=date.today())
    payment_kind = (source_values.get('payment_kind') or 'loan').strip()
    distribution_method = _normalize_distribution_method(source_values.get('distribution_method'))
    total_amount = max(0.0, _safe_float(source_values.get('total_amount'), 0.0))
    user_description = (source_values.get('description') or '').strip()
    user_notes = (source_values.get('notes') or '').strip()
    history_family_id = _safe_int(source_values.get('history_family_id'), default=selected_family_id)
    history_date = _safe_optional_date(source_values.get('history_date'))

    selected_family = WorkerFamily.query.filter_by(id=selected_family_id, account_id=current_user.account_id).first() if selected_family_id else None
    family_workers = []
    attendance_map = {}
    preview_amounts = {}

    if selected_family:
        family_workers = (
            Worker.query.filter_by(family_id=selected_family.id, account_id=current_user.account_id, is_active=True)
            .order_by(Worker.name.asc())
            .all()
        )
        worker_ids = [worker.id for worker in family_workers]
        if worker_ids:
            attendance_rows = (
                Attendance.query.filter(
                    Attendance.account_id == current_user.account_id,
                    Attendance.worker_id.in_(worker_ids),
                    Attendance.attendance_date == selected_date,
                )
                .order_by(Attendance.id.asc())
                .all()
            )
            attendance_map = {row.worker_id: row for row in attendance_rows}

            weights_map = {
                worker_id: (
                    attendance_map[worker_id].hours_worked
                    if worker_id in attendance_map and attendance_map[worker_id].status == 'حاضر'
                    else 0.0
                )
                for worker_id in worker_ids
            }
            if distribution_method == 'by_hours':
                preview_amounts = _split_amount_by_weights(total_amount, worker_ids, weights_map)
            else:
                preview_amounts = _split_amount_evenly(total_amount, worker_ids)

    if request.method == 'POST':
        if payment_kind not in WORKER_PAYMENT_KIND_LABELS:
            flash('نوع الدفعة غير صحيح', 'warning')
            return redirect(url_for('workers.group_payments'))

        if not selected_family:
            flash('يرجى اختيار العائلة أولًا', 'warning')
            return redirect(url_for('workers.group_payments'))

        if not family_workers:
            flash('لا يوجد عمال نشطون ضمن هذه العائلة', 'warning')
            return redirect(
                url_for(
                    'workers.group_payments',
                    family_id=selected_family.id,
                    date=selected_date.strftime('%Y-%m-%d'),
                )
            )

        selected_worker_ids = []
        manual_amounts = {}
        
        # إذا لم يتم توفير include_* fields، نقوم بتحديد جميع العمال افتراضياً
        has_include_fields = any(f'include_{worker.id}' in request.form or f'include_{worker.id}' in request.args for worker in family_workers)
        
        for worker in family_workers:
            # البحث عن include_* في form والـ query string
            include_value = request.form.get(f'include_{worker.id}') or request.args.get(f'include_{worker.id}')
            
            # إذا لم تكن هناك include fields على الإطلاق، نختار جميع العمال افتراضياً
            if not has_include_fields or include_value == 'on' or include_value == 'true':
                selected_worker_ids.append(worker.id)
                amount_value = request.form.get(f'amount_{worker.id}') or request.args.get(f'amount_{worker.id}')
                manual_amounts[worker.id] = max(0.0, _safe_float(amount_value, 0.0))

        if not selected_worker_ids:
            flash('يرجى اختيار عامل واحد على الأقل', 'warning')
            return redirect(
                url_for(
                    'workers.group_payments',
                    family_id=selected_family.id,
                    date=selected_date.strftime('%Y-%m-%d'),
                    payment_kind=payment_kind,
                    distribution_method=distribution_method,
                    total_amount=total_amount,
                )
            )

        if distribution_method == 'manual':
            allocations = {
                worker_id: round(amount, 2)
                for worker_id, amount in manual_amounts.items()
                if worker_id in selected_worker_ids and amount > 0
            }
            if not allocations:
                flash('في التوزيع اليدوي يجب إدخال مبلغ أكبر من صفر لعامل واحد على الأقل', 'warning')
                return redirect(
                    url_for(
                        'workers.group_payments',
                        family_id=selected_family.id,
                        date=selected_date.strftime('%Y-%m-%d'),
                        payment_kind=payment_kind,
                        distribution_method=distribution_method,
                        total_amount=total_amount,
                    )
                )
            total_allocated_amount = round(sum(allocations.values()), 2)
        else:
            if total_amount <= 0:
                flash('يرجى إدخال مبلغ إجمالي صحيح أكبر من صفر', 'warning')
                return redirect(
                    url_for(
                        'workers.group_payments',
                        family_id=selected_family.id,
                        date=selected_date.strftime('%Y-%m-%d'),
                        payment_kind=payment_kind,
                        distribution_method=distribution_method,
                        total_amount=total_amount,
                    )
                )
            if distribution_method == 'by_hours':
                weights_map = {}
                for worker_id in selected_worker_ids:
                    attendance = attendance_map.get(worker_id)
                    if attendance and attendance.status == 'حاضر':
                        weights_map[worker_id] = attendance.hours_worked or 0.0
                    else:
                        weights_map[worker_id] = 0.0
                allocations = _split_amount_by_weights(total_amount, selected_worker_ids, weights_map)
            else:
                allocations = _split_amount_evenly(total_amount, selected_worker_ids)
            total_allocated_amount = round(sum(allocations.values()), 2)

        try:
            category = _get_or_create_worker_payment_category()
            created_count = 0

            for worker in family_workers:
                if worker.id not in allocations:
                    continue
                worker_amount = round(allocations.get(worker.id, 0.0), 2)
                if worker_amount <= 0:
                    continue

                description = (
                    user_description
                    or f"{WORKER_PAYMENT_KIND_LABELS[payment_kind]} جماعية - {selected_family.family_name} - {worker.name}"
                )
                marker = f"[worker_payment_kind={payment_kind}]"
                group_marker = (
                    f"[group_family_id={selected_family.id}]"
                    f"[group_distribution={distribution_method}]"
                    f"[group_date={selected_date.strftime('%Y-%m-%d')}]"
                )
                full_notes = f"{marker} {group_marker} {user_notes}".strip()

                transaction = Transaction(
                    account_id=current_user.account_id,
                    category_id=category.id if category else None,
                    transaction_type='مصروف',
                    description=description,
                    amount=worker_amount,
                    transaction_date=selected_date,
                    reference_type='عامل',
                    reference_id=worker.id,
                    notes=full_notes,
                )
                db.session.add(transaction)
                created_count += 1

            db.session.commit()
            flash(
                f'تم تسجيل دفعة جماعية بنجاح: {created_count} قيود بإجمالي {total_allocated_amount:.2f}',
                'success',
            )
            return redirect(
                url_for(
                    'workers.group_payments',
                    family_id=selected_family.id,
                    date=selected_date.strftime('%Y-%m-%d'),
                    payment_kind=payment_kind,
                    distribution_method=distribution_method,
                    total_amount=total_allocated_amount,
                    history_family_id=history_family_id or selected_family.id,
                    history_date=history_date.strftime('%Y-%m-%d') if history_date else '',
                )
            )
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            flash(f'حدث خطأ أثناء تسجيل الدفعات الجماعية: {str(e)}', 'danger')

    history_query = (
        Transaction.query.filter(
            Transaction.account_id == current_user.account_id,
            Transaction.reference_type.in_(WORKER_REFERENCE_TYPE_ALIASES),
            Transaction.transaction_type.in_(EXPENSE_TRANSACTION_TYPE_ALIASES),
            Transaction.notes.isnot(None),
            Transaction.notes.contains('[group_family_id='),
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    if history_family_id:
        history_query = history_query.filter(
            Transaction.notes.contains(f'[group_family_id={history_family_id}]')
        )
    if history_date:
        history_query = history_query.filter(
            Transaction.notes.contains(f'[group_date={history_date.strftime("%Y-%m-%d")}]')
        )

    history_transactions = history_query.limit(250).all()
    worker_ids = sorted({tx.reference_id for tx in history_transactions if tx.reference_id is not None})
    workers_map = {}
    if worker_ids:
        workers_map = {
            worker.id: worker.name
            for worker in Worker.query.filter(
                Worker.account_id == current_user.account_id,
                Worker.id.in_(worker_ids)
            ).all()
        }

    families_map = {
        family.id: family.family_name
        for family in WorkerFamily.query.filter_by(account_id=current_user.account_id).order_by(WorkerFamily.family_name.asc()).all()
    }
    distribution_labels = {
        'equal': 'بالتساوي',
        'by_hours': 'حسب الساعات',
        'manual': 'يدوي',
    }

    history_rows = []
    daily_totals_map = {}
    for tx in history_transactions:
        notes = tx.notes or ''
        group_family_raw = _extract_marker_value(notes, 'group_family_id')
        group_distribution = _extract_marker_value(notes, 'group_distribution') or '-'
        group_date = _extract_marker_value(notes, 'group_date')
        if not group_date:
            group_date = tx.transaction_date.strftime('%Y-%m-%d') if tx.transaction_date else '-'

        group_family_id_value = _safe_int(group_family_raw)
        family_name = families_map.get(group_family_id_value, '-') if group_family_id_value else '-'
        worker_name = workers_map.get(tx.reference_id, f'عامل #{tx.reference_id}')
        payment_kind_detected = _detect_worker_payment_kind(tx)
        payment_kind_label = WORKER_PAYMENT_KIND_LABELS.get(payment_kind_detected, 'دفعة مرتبطة')

        amount_value = float(tx.amount or 0.0)
        daily_totals_map[group_date] = round(daily_totals_map.get(group_date, 0.0) + amount_value, 2)

        history_rows.append(
            {
                'transaction': tx,
                'worker_name': worker_name,
                'family_name': family_name,
                'payment_kind_label': payment_kind_label,
                'distribution_label': distribution_labels.get(group_distribution, group_distribution),
                'group_date': group_date,
                'amount': amount_value,
            }
        )

    history_daily_totals = [
        {'date': day, 'total': total}
        for day, total in sorted(daily_totals_map.items(), key=lambda item: item[0], reverse=True)
    ]

    return render_template(
        'workers/group_payments.html',
        families=families,
        selected_family=selected_family,
        selected_date=selected_date,
        payment_kind=payment_kind,
        distribution_method=distribution_method,
        total_amount=total_amount,
        family_workers=family_workers,
        attendance_map=attendance_map,
        preview_amounts=preview_amounts,
        user_description=user_description,
        user_notes=user_notes,
        distribution_methods=GROUP_DISTRIBUTION_METHODS,
        history_family_id=history_family_id,
        history_date=history_date,
        history_rows=history_rows,
        history_daily_totals=history_daily_totals,
    )


@bp.route('/group-section/payments/receipt')
@login_required
def group_payments_receipt():
    """إيصال دفعات جماعية يتضمن عدد الشباب والبنات."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    family_id = _safe_int(request.args.get('family_id'))
    receipt_date = _safe_date(request.args.get('date'), default=date.today())
    payment_kind = (request.args.get('payment_kind') or '').strip().lower()
    if not family_id:
        flash('يرجى اختيار العائلة أولًا', 'warning')
        return redirect(url_for('workers.group_payments'))

    family = WorkerFamily.query.get_or_404(family_id)

    transactions_query = (
        Transaction.query.filter(
            Transaction.reference_type.in_(WORKER_REFERENCE_TYPE_ALIASES),
            Transaction.transaction_type.in_(EXPENSE_TRANSACTION_TYPE_ALIASES),
            Transaction.notes.isnot(None),
            Transaction.notes.contains(f'[group_family_id={family.id}]'),
            Transaction.notes.contains(f'[group_date={receipt_date.strftime("%Y-%m-%d")}]'),
        )
        .order_by(Transaction.id.asc())
    )
    if payment_kind in WORKER_PAYMENT_KIND_LABELS:
        transactions_query = transactions_query.filter(
            Transaction.notes.contains(f'[worker_payment_kind={payment_kind}]')
        )
    transactions = transactions_query.all()

    worker_ids = sorted({tx.reference_id for tx in transactions if tx.reference_id is not None})
    workers = []
    workers_map = {}
    if worker_ids:
        workers = Worker.query.filter(Worker.id.in_(worker_ids)).order_by(Worker.name.asc()).all()
        workers_map = {worker.id: worker for worker in workers}

    male_count, female_count, unknown_count = _count_workers_by_gender(workers)

    loans_total = 0.0
    advances_total = 0.0
    total_amount = 0.0
    for tx in transactions:
        amount = float(tx.amount or 0.0)
        total_amount += amount
        kind = _detect_worker_payment_kind(tx)
        if kind == 'loan':
            loans_total += amount
        elif kind == 'advance':
            advances_total += amount

    transaction_rows = []
    for tx in transactions:
        worker_obj = workers_map.get(tx.reference_id)
        worker_name = worker_obj.name if worker_obj else f'عامل #{tx.reference_id}'
        transaction_rows.append(
            {
                'transaction': tx,
                'worker_name': worker_name,
                'kind_label': WORKER_PAYMENT_KIND_LABELS.get(_detect_worker_payment_kind(tx), 'دفعة مرتبطة'),
            }
        )

    receipt_number = f"GPP-{receipt_date.strftime('%Y%m%d')}-{family.id:04d}"
    return render_template(
        'workers/group_payments_receipt.html',
        family=family,
        receipt_date=receipt_date,
        receipt_number=receipt_number,
        payment_kind=payment_kind,
        transaction_rows=transaction_rows,
        transactions_count=len(transactions),
        workers_count=len(workers),
        male_count=male_count,
        female_count=female_count,
        unknown_count=unknown_count,
        loans_total=loans_total,
        advances_total=advances_total,
        total_amount=total_amount,
        printed_at=datetime.now(),
    )


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


@bp.route('/attendance/<int:attendance_id>/receipt')
@login_required
def attendance_receipt(attendance_id):
    """عرض إيصال حضور قابل للطباعة بمقاس 50x50."""
    if not current_user.can_manage_workers and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('workers.index'))

    attendance = Attendance.query.get_or_404(attendance_id)
    receipt_number = f"AT-{attendance.attendance_date.strftime('%Y%m%d')}-{attendance.id:06d}"

    day_transactions = (
        Transaction.query.filter(
            Transaction.reference_id == attendance.worker_id,
            Transaction.reference_type.in_(WORKER_REFERENCE_TYPE_ALIASES),
            Transaction.transaction_type.in_(EXPENSE_TRANSACTION_TYPE_ALIASES),
            Transaction.transaction_date == attendance.attendance_date,
        )
        .order_by(Transaction.id.asc())
        .all()
    )

    day_payment_total = 0.0
    day_loans = 0.0
    day_advances = 0.0
    for transaction in day_transactions:
        amount = transaction.amount or 0.0
        day_payment_total += amount
        payment_kind = _detect_worker_payment_kind(transaction)
        if payment_kind == 'loan':
            day_loans += amount
        elif payment_kind == 'advance':
            day_advances += amount

    return render_template(
        'workers/attendance_receipt.html',
        attendance=attendance,
        receipt_number=receipt_number,
        day_payment_total=day_payment_total,
        day_loans=day_loans,
        day_advances=day_advances,
        printed_at=datetime.now(),
    )


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
    total_worker_loans = sum(getattr(m, 'worker_loans', 0.0) for m in monthly_data)
    total_worker_advances = sum(getattr(m, 'worker_advances', 0.0) for m in monthly_data)

    return render_template(
        'workers/monthly_attendance.html',
        monthly_data=monthly_data,
        year=year,
        month=month,
        total_present=total_present,
        total_salary_before_payments=total_salary_before_payments,
        total_worker_payments=total_worker_payments,
        total_worker_loans=total_worker_loans,
        total_worker_advances=total_worker_advances,
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
