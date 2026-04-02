from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.accounting import (
    ExpenseCategory,
    Transaction,
    is_expense_transaction,
    is_income_transaction,
    is_worker_reference_type,
    normalize_reference_type,
    normalize_transaction_type,
)
from app.models.worker import Worker
from app.security import get_submitted_csrf_token, validate_csrf_token
from datetime import datetime

bp = Blueprint('accounting', __name__, url_prefix='/accounting')

ALLOWED_REFERENCE_TYPES = {'عامل', 'مخزون', 'بيع', 'إنتاج'}
ALLOWED_TRANSACTION_TYPES = {'دخل', 'مصروف'}


def _safe_float(value):
    """Convert a form value to float with fallback None."""
    try:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    """Convert a form value to integer with fallback None."""
    try:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        return int(raw)
    except (TypeError, ValueError):
        return None


def _safe_date(value):
    """Parse YYYY-MM-DD date string safely."""
    try:
        raw = str(value or '').strip()
        if not raw:
            return None
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _clean_optional_text(value):
    """Trim text and return None when empty."""
    raw = str(value or '').strip()
    return raw or None


def _require_csrf(redirect_endpoint, **kwargs):
    """Validate CSRF token for create/edit forms."""
    submitted_token = get_submitted_csrf_token()
    if validate_csrf_token(submitted_token):
        return None

    flash('رمز الأمان غير صالح، يرجى إعادة المحاولة', 'danger')
    return redirect(url_for(redirect_endpoint, **kwargs))


def _read_transaction_form_data():
    """Validate and normalize transaction payload from form."""
    transaction_type = normalize_transaction_type(request.form.get('transaction_type'))
    if transaction_type not in ALLOWED_TRANSACTION_TYPES:
        flash('يرجى اختيار نوع معاملة صحيح', 'warning')
        return None

    description = _clean_optional_text(request.form.get('description'))
    if not description:
        flash('يرجى إدخال البيان', 'warning')
        return None

    amount = _safe_float(request.form.get('amount'))
    if amount is None or amount <= 0:
        flash('يرجى إدخال مبلغ صحيح أكبر من صفر', 'warning')
        return None

    transaction_date = _safe_date(request.form.get('transaction_date'))
    if not transaction_date:
        flash('يرجى إدخال تاريخ صحيح', 'warning')
        return None

    category_id = _safe_int(request.form.get('category_id'))
    if category_id is not None and not ExpenseCategory.query.get(category_id):
        flash('الفئة المختارة غير موجودة', 'warning')
        return None

    if transaction_type == 'دخل':
        category_id = None

    reference_type = normalize_reference_type(request.form.get('reference_type')) or None
    reference_id = _safe_int(request.form.get('reference_id'))

    if reference_type and reference_type not in ALLOWED_REFERENCE_TYPES:
        flash('نوع المرجع غير صالح', 'warning')
        return None

    if reference_type == 'عامل':
        if reference_id is None:
            flash('يرجى إدخال رقم العامل عند اختيار مرجع عامل', 'warning')
            return None
        if not Worker.query.get(reference_id):
            flash('رقم العامل غير موجود', 'warning')
            return None

    return {
        'category_id': category_id,
        'transaction_type': transaction_type,
        'description': description,
        'amount': amount,
        'transaction_date': transaction_date,
        'reference_type': reference_type,
        'reference_id': reference_id,
        'notes': _clean_optional_text(request.form.get('notes')),
    }


@bp.route('/')
@login_required
def index():
    """لوحة المحاسبة"""
    if not current_user.can_manage_accounting and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    transactions = Transaction.query.order_by(
        Transaction.transaction_date.desc(),
        Transaction.id.desc()
    ).all()

    for transaction in transactions:
        transaction.display_transaction_type = normalize_transaction_type(transaction.transaction_type)
        transaction.display_reference_type = normalize_reference_type(transaction.reference_type)

    total_income = sum((t.amount or 0) for t in transactions if is_income_transaction(t.transaction_type))
    total_expenses = sum((t.amount or 0) for t in transactions if is_expense_transaction(t.transaction_type))
    net = total_income - total_expenses

    worker_ids = sorted({
        t.reference_id
        for t in transactions
        if is_worker_reference_type(t.reference_type) and t.reference_id
    })
    worker_lookup = {}
    if worker_ids:
        worker_rows = (
            Worker.query.with_entities(Worker.id, Worker.name)
            .filter(Worker.id.in_(worker_ids))
            .all()
        )
        worker_lookup = {worker_id: name for worker_id, name in worker_rows}

    return render_template('accounting/index.html',
                         transactions=transactions,
                         total_income=total_income,
                         total_expenses=total_expenses,
                         net=net,
                         worker_lookup=worker_lookup)

@bp.route('/categories')
@login_required
def categories():
    """إدارة فئات المصروفات"""
    if not current_user.can_manage_accounting and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('accounting.index'))
    
    categories = ExpenseCategory.query.all()
    return render_template('accounting/categories.html', categories=categories)

@bp.route('/categories/add', methods=['GET', 'POST'])
@login_required
def add_category():
    """إضافة فئة مصروفات"""
    if not current_user.can_manage_accounting and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('accounting.categories'))
    
    if request.method == 'POST':
        csrf_error = _require_csrf('accounting.add_category')
        if csrf_error:
            return csrf_error

        category_name = _clean_optional_text(request.form.get('name'))
        if not category_name:
            flash('اسم الفئة مطلوب', 'warning')
            return redirect(url_for('accounting.add_category'))

        category = ExpenseCategory(
            name=category_name,
            description=_clean_optional_text(request.form.get('description'))
        )

        try:
            db.session.add(category)
            db.session.commit()
            flash(f'تم إضافة الفئة {category.name}', 'success')
            return redirect(url_for('accounting.categories'))
        except IntegrityError:
            db.session.rollback()
            flash('اسم الفئة موجود مسبقًا', 'warning')
            return redirect(url_for('accounting.add_category'))
    
    return render_template('accounting/add_category.html')

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    """إضافة معاملة محاسبية"""
    if not current_user.can_manage_accounting and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('accounting.index'))
    
    categories = ExpenseCategory.query.all()
    
    if request.method == 'POST':
        csrf_error = _require_csrf('accounting.add_transaction')
        if csrf_error:
            return csrf_error

        form_data = _read_transaction_form_data()
        if not form_data:
            return redirect(url_for('accounting.add_transaction'))

        transaction = Transaction(**form_data)

        try:
            db.session.add(transaction)
            db.session.commit()
            flash('تم تسجيل المعاملة بنجاح', 'success')
            return redirect(url_for('accounting.index'))
        except Exception:
            db.session.rollback()
            flash('حدث خطأ أثناء تسجيل المعاملة', 'danger')
            return redirect(url_for('accounting.add_transaction'))
    
    return render_template('accounting/add_transaction.html', categories=categories)

@bp.route('/<int:transaction_id>/delete', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    """حذف معاملة"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('accounting.index'))
    
    transaction = Transaction.query.get_or_404(transaction_id)
    db.session.delete(transaction)
    db.session.commit()
    
    flash('تم حذف المعاملة', 'success')
    return redirect(url_for('accounting.index'))


@bp.route('/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    """تعديل معاملة محاسبية"""
    if not current_user.can_manage_accounting and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('accounting.index'))
    
    transaction = Transaction.query.get_or_404(transaction_id)
    categories = ExpenseCategory.query.all()
    
    if request.method == 'POST':
        csrf_error = _require_csrf('accounting.edit_transaction', transaction_id=transaction_id)
        if csrf_error:
            return csrf_error

        form_data = _read_transaction_form_data()
        if not form_data:
            return redirect(url_for('accounting.edit_transaction', transaction_id=transaction_id))

        transaction.category_id = form_data['category_id']
        transaction.transaction_type = form_data['transaction_type']
        transaction.description = form_data['description']
        transaction.amount = form_data['amount']
        transaction.transaction_date = form_data['transaction_date']
        transaction.reference_type = form_data['reference_type']
        transaction.reference_id = form_data['reference_id']
        transaction.notes = form_data['notes']

        try:
            db.session.commit()
            flash('تم تحديث المعاملة بنجاح', 'success')
            return redirect(url_for('accounting.index'))
        except Exception:
            db.session.rollback()
            flash('حدث خطأ أثناء تحديث المعاملة', 'danger')
            return redirect(url_for('accounting.edit_transaction', transaction_id=transaction_id))
    
    return render_template('accounting/edit_transaction.html', 
                         transaction=transaction, 
                         categories=categories)


@bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(category_id):
    """تعديل فئة مصروفات"""
    if not current_user.can_manage_accounting and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('accounting.categories'))
    
    category = ExpenseCategory.query.get_or_404(category_id)
    
    if request.method == 'POST':
        csrf_error = _require_csrf('accounting.edit_category', category_id=category_id)
        if csrf_error:
            return csrf_error

        category_name = _clean_optional_text(request.form.get('name'))
        if not category_name:
            flash('اسم الفئة مطلوب', 'warning')
            return redirect(url_for('accounting.edit_category', category_id=category_id))

        category.name = category_name
        category.description = _clean_optional_text(request.form.get('description'))

        try:
            db.session.commit()
            flash(f'تم تحديث الفئة {category.name} بنجاح', 'success')
            return redirect(url_for('accounting.categories'))
        except IntegrityError:
            db.session.rollback()
            flash('اسم الفئة مستخدم لفئة أخرى', 'warning')
            return redirect(url_for('accounting.edit_category', category_id=category_id))
    
    return render_template('accounting/edit_category.html', category=category)


@bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    """حذف فئة مصروفات"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('accounting.categories'))
    
    category = ExpenseCategory.query.get_or_404(category_id)
    
    # التحقق من وجود معاملات مرتبطة
    if category.transactions:
        flash(f'لا يمكن حذف الفئة {category.name} لأن بها معاملات مرتبطة', 'warning')
        return redirect(url_for('accounting.categories'))
    
    db.session.delete(category)
    db.session.commit()
    
    flash(f'تم حذف الفئة {category.name}', 'success')
    return redirect(url_for('accounting.categories'))
