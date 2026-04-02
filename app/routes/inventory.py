from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models.inventory import InventoryItem, InventoryTransaction, InventoryPurchase
from app.models.box import BoxType, BoxUsage, BoxPurchase
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

bp = Blueprint('inventory', __name__, url_prefix='/inventory')

def _record_inventory_transaction(item_id, transaction_type, quantity, notes=''):
    """Store inventory movement for auditability."""
    tx = InventoryTransaction(
        item_id=item_id,
        transaction_type=transaction_type,
        quantity=quantity,
        notes=notes
    )
    db.session.add(tx)


@bp.route('/')
@login_required
def index():
    """قائمة المخزون"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    items = InventoryItem.query.all()
    return render_template('inventory/index.html', items=items)

@bp.route('/nofath')
@login_required
def out_of_stock():
    """قسم الأدوية التي نفذت من المخزون"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    # جلب جميع العناصر التي نفذت (quantity <= 0)
    out_of_stock_items = InventoryItem.query.filter(InventoryItem.quantity <= 0).all()
    return render_template('inventory/nofath.html', items=out_of_stock_items)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_item():
    """إضافة عنصر مخزون"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('inventory.index'))
    
    if request.method == 'POST':
        item = InventoryItem(
            name=request.form.get('name'),
            category=request.form.get('category'),
            quantity=float(request.form.get('quantity')),
            unit=request.form.get('unit'),
            purchase_price=float(request.form.get('purchase_price')),
            supplier=request.form.get('supplier'),
            expiry_date=datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d').date() if request.form.get('expiry_date') else None,
            notes=request.form.get('notes')
        )
        
        db.session.add(item)
        db.session.commit()
        
        flash(f'تم إضافة {item.name} إلى المخزون', 'success')
        return redirect(url_for('inventory.index'))
    
    return render_template('inventory/add.html')

@bp.route('/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    """تعديل عنصر مخزون"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('inventory.index'))
    
    item = InventoryItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        item.name = request.form.get('name')
        item.category = request.form.get('category')
        item.quantity = float(request.form.get('quantity'))
        item.unit = request.form.get('unit')
        item.purchase_price = float(request.form.get('purchase_price'))
        item.supplier = request.form.get('supplier')
        
        if request.form.get('expiry_date'):
            item.expiry_date = datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d').date()
        
        item.notes = request.form.get('notes')
        
        db.session.commit()
        flash(f'تم تحديث {item.name}', 'success')
        return redirect(url_for('inventory.index'))
    
    return render_template('inventory/edit.html', item=item)

@bp.route('/<int:item_id>/transaction', methods=['GET', 'POST'])
@login_required
def add_transaction(item_id):
    """تسجيل حركة مخزون"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('inventory.index'))
    
    item = InventoryItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        transaction_type = request.form.get('transaction_type')
        quantity = float(request.form.get('quantity'))
        
        # Update inventory quantity
        if transaction_type == 'دخول':
            item.quantity += quantity
        elif transaction_type == 'خروج':
            if item.quantity < quantity:
                flash('الكمية المتوفرة غير كافية', 'danger')
                return redirect(url_for('inventory.add_transaction', item_id=item_id))
            item.quantity -= quantity
        
        # Create transaction record
        transaction = InventoryTransaction(
            item_id=item_id,
            transaction_type=transaction_type,
            quantity=quantity,
            notes=request.form.get('notes')
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        flash(f'تم تسجيل حركة {transaction_type} للمخزون', 'success')
        return redirect(url_for('inventory.index'))
    
    return render_template('inventory/transaction.html', item=item)

@bp.route('/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    """حذف عنصر مخزون"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('inventory.index'))
    
    item = InventoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    
    flash(f'تم حذف {item.name}', 'success')
    return redirect(url_for('inventory.index'))

# Box Management Routes - قسم الشراحات والكراتين

@bp.route('/boxes')
@login_required
def boxes():
    """إدارة الشراحات والكراتين"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('inventory.index'))
    
    boxes = BoxType.query.all()
    return render_template('inventory/boxes.html', boxes=boxes)

@bp.route('/boxes/add', methods=['GET', 'POST'])
@login_required
def add_box():
    """إضافة نوع صندوق"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('inventory.boxes'))
    
    if request.method == 'POST':
        try:
            name = (request.form.get('name') or '').strip()
            box_type = (request.form.get('box_type') or '').strip()
            capacity_raw = (request.form.get('capacity') or '').strip()
            unit = (request.form.get('unit') or '').strip() or None
            supplier = (request.form.get('supplier') or '').strip() or None
            cost_per_box = float(request.form.get('cost_per_box') or 0)
            capacity = float(capacity_raw) if capacity_raw else None
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات صحيحة للصندوق', 'danger')
            return render_template('inventory/add_box.html')

        if not name:
            flash('اسم الصندوق مطلوب', 'danger')
            return render_template('inventory/add_box.html')

        if not box_type:
            flash('نوع الصندوق مطلوب', 'danger')
            return render_template('inventory/add_box.html')

        if cost_per_box <= 0:
            flash('تكلفة الصندوق يجب أن تكون أكبر من صفر', 'danger')
            return render_template('inventory/add_box.html')

        existing_box = BoxType.query.filter(
            func.lower(func.trim(BoxType.name)) == name.lower()
        ).first()
        if existing_box:
            flash(f'نوع الصندوق "{name}" موجود مسبقًا', 'warning')
            return render_template('inventory/add_box.html')

        box = BoxType(
            name=name,
            box_type=box_type,
            capacity=capacity,
            unit=unit,
            cost_per_box=cost_per_box,
            supplier=supplier
        )

        try:
            db.session.add(box)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f'نوع الصندوق "{name}" موجود مسبقًا', 'warning')
            return render_template('inventory/add_box.html')

        flash(f'تم إضافة النوع {box.name}', 'success')
        return redirect(url_for('inventory.boxes'))
    
    return render_template('inventory/add_box.html')

@bp.route('/boxes/<int:box_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_box(box_id):
    """تعديل نوع صندوق"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('inventory.boxes'))
    
    box = BoxType.query.get_or_404(box_id)
    
    if request.method == 'POST':
        try:
            name = (request.form.get('name') or '').strip()
            box_type = (request.form.get('box_type') or '').strip()
            capacity_raw = (request.form.get('capacity') or '').strip()
            unit = (request.form.get('unit') or '').strip() or None
            supplier = (request.form.get('supplier') or '').strip() or None
            cost_per_box = float(request.form.get('cost_per_box') or 0)
            capacity = float(capacity_raw) if capacity_raw else None
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات صحيحة للصندوق', 'danger')
            return render_template('inventory/edit_box.html', box=box)

        if not name:
            flash('اسم الصندوق مطلوب', 'danger')
            return render_template('inventory/edit_box.html', box=box)

        if not box_type:
            flash('نوع الصندوق مطلوب', 'danger')
            return render_template('inventory/edit_box.html', box=box)

        if cost_per_box <= 0:
            flash('تكلفة الصندوق يجب أن تكون أكبر من صفر', 'danger')
            return render_template('inventory/edit_box.html', box=box)

        existing_box = BoxType.query.filter(
            func.lower(func.trim(BoxType.name)) == name.lower(),
            BoxType.id != box.id
        ).first()
        if existing_box:
            flash(f'نوع الصندوق "{name}" موجود مسبقًا', 'warning')
            return render_template('inventory/edit_box.html', box=box)

        box.name = name
        box.box_type = box_type
        box.capacity = capacity
        box.unit = unit
        box.cost_per_box = cost_per_box
        box.supplier = supplier

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(f'نوع الصندوق "{name}" موجود مسبقًا', 'warning')
            return render_template('inventory/edit_box.html', box=box)

        flash(f'تم تحديث {box.name}', 'success')
        return redirect(url_for('inventory.boxes'))
    
    return render_template('inventory/edit_box.html', box=box)

@bp.route('/boxes/<int:box_id>/usage', methods=['GET', 'POST'])
@login_required
def add_box_usage(box_id):
    """تسجيل استخدام صندوق"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('inventory.boxes'))
    
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
        return redirect(url_for('inventory.boxes'))
    
    return render_template('inventory/add_box_usage.html', box=box)

@bp.route('/boxes/<int:box_id>/delete', methods=['POST'])
@login_required
def delete_box(box_id):
    """حذف نوع صندوق"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('inventory.boxes'))
    
    box = BoxType.query.get_or_404(box_id)
    db.session.delete(box)
    db.session.commit()
    
    flash(f'تم حذف النوع {box.name}', 'success')
    return redirect(url_for('inventory.boxes'))

# Box Purchase Routes - قسم شراء الشراحات والكراتين

@bp.route('/boxes/purchases/list')
@login_required
def box_purchases():
    """قائمة عمليات شراء الشراحات والكراتين"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('inventory.boxes'))
    
    purchases = BoxPurchase.query.order_by(BoxPurchase.purchase_date.desc()).all()
    total_cost = sum(p.total_cost for p in purchases)
    
    return render_template('inventory/box_purchases.html', purchases=purchases, total_cost=total_cost)

@bp.route('/boxes/<int:box_id>/purchase/add', methods=['GET', 'POST'])
@login_required
def add_box_purchase(box_id):
    """إضافة عملية شراء"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية القيام بهذا الإجراء', 'danger')
        return redirect(url_for('inventory.box_purchases'))
    
    box = BoxType.query.get_or_404(box_id)
    
    if request.method == 'POST':
        purchase = BoxPurchase(
            box_type_id=box_id,
            quantity=int(request.form.get('quantity')),
            unit_price=float(request.form.get('unit_price')),
            purchase_date=datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date(),
            supplier=request.form.get('supplier'),
            invoice_number=request.form.get('invoice_number'),
            notes=request.form.get('notes')
        )
        
        purchase.calculate_total_cost()
        
        db.session.add(purchase)
        db.session.commit()
        
        flash('تم تسجيل الشراء بنجاح', 'success')
        return redirect(url_for('inventory.box_purchases'))
    
    return render_template('inventory/add_box_purchase.html', box=box)

@bp.route('/box-purchase/<int:purchase_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_box_purchase(purchase_id):
    """تعديل عملية شراء"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('inventory.box_purchases'))
    
    purchase = BoxPurchase.query.get_or_404(purchase_id)
    
    if request.method == 'POST':
        purchase.quantity = int(request.form.get('quantity'))
        purchase.unit_price = float(request.form.get('unit_price'))
        purchase.purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        purchase.supplier = request.form.get('supplier')
        purchase.invoice_number = request.form.get('invoice_number')
        purchase.notes = request.form.get('notes')
        
        purchase.calculate_total_cost()
        
        db.session.commit()
        flash('تم تحديث الشراء بنجاح', 'success')
        return redirect(url_for('inventory.box_purchases'))
    
    return render_template('inventory/edit_box_purchase.html', purchase=purchase)

@bp.route('/box-purchase/<int:purchase_id>/delete', methods=['POST'])
@login_required
def delete_box_purchase(purchase_id):
    """حذف عملية شراء"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('inventory.box_purchases'))
    
    purchase = BoxPurchase.query.get_or_404(purchase_id)
    db.session.delete(purchase)
    db.session.commit()
    
    flash('تم حذف الشراء بنجاح', 'success')
    return redirect(url_for('inventory.box_purchases'))

@bp.route('/boxes/purchases/report')
@login_required
def box_purchases_report():
    """تقرير عمليات شراء الشراحات والكراتين السنوي"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('inventory.boxes'))
    
    # تحديد السنة الحالية
    current_year = datetime.now().year
    year_start = datetime(current_year, 1, 1).date()
    year_end = datetime(current_year, 12, 31).date()
    
    # جلب جميع عمليات الشراء للسنة الحالية
    purchases = BoxPurchase.query.filter(
        BoxPurchase.purchase_date >= year_start,
        BoxPurchase.purchase_date <= year_end
    ).order_by(BoxPurchase.purchase_date.desc()).all()
    
    # حساب الإحصائيات
    total_cost = sum(p.total_cost for p in purchases)
    total_quantity = sum(p.quantity for p in purchases)
    
    # تجميع حسب نوع الصندوق
    by_type = {}
    for purchase in purchases:
        box_name = purchase.box_type.name
        if box_name not in by_type:
            by_type[box_name] = {
                'quantity': 0,
                'total_cost': 0,
                'purchases': []
            }
        by_type[box_name]['quantity'] += purchase.quantity
        by_type[box_name]['total_cost'] += purchase.total_cost
        by_type[box_name]['purchases'].append(purchase)
    
    return render_template('inventory/box_purchases_report.html',
                         purchases=purchases,
                         total_cost=total_cost,
                         total_quantity=total_quantity,
                         by_type=by_type,
                         year=current_year)

# Inventory Item Purchase Routes - قسم شراء عناصر المخزون

@bp.route('/purchases/list')
@login_required
def inventory_purchases():
    """قائمة عمليات شراء المخزون"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('inventory.index'))
    
    purchases = InventoryPurchase.query.order_by(InventoryPurchase.purchase_date.desc()).all()
    total_cost = sum(p.total_cost for p in purchases)
    
    return render_template('inventory/inventory_purchases.html', purchases=purchases, total_cost=total_cost)

@bp.route('/<int:item_id>/purchase/add', methods=['GET', 'POST'])
@login_required
def add_inventory_purchase(item_id):
    """إضافة عملية شراء جديدة لعنصر مخزون."""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية إضافة عملية شراء للمخزون', 'danger')
        return redirect(url_for('inventory.inventory_purchases'))

    item = InventoryItem.query.get_or_404(item_id)

    if request.method == 'POST':
        try:
            quantity = float(request.form.get('quantity', 0))
            unit_price = float(request.form.get('unit_price', 0))
            purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات شراء صحيحة', 'danger')
            return render_template('inventory/add_inventory_purchase.html', item=item)

        if quantity <= 0:
            flash('الكمية يجب أن تكون أكبر من صفر', 'danger')
            return render_template('inventory/add_inventory_purchase.html', item=item)

        purchase = InventoryPurchase(
            item_id=item_id,
            quantity=quantity,
            unit_price=unit_price,
            purchase_date=purchase_date,
            supplier=request.form.get('supplier'),
            invoice_number=request.form.get('invoice_number'),
            notes=request.form.get('notes')
        )

        purchase.calculate_total_cost()

        # تحديث المخزون: عملية شراء تعني إضافة كمية
        item.quantity += quantity
        _record_inventory_transaction(
            item_id=item_id,
            transaction_type='دخول',
            quantity=quantity,
            notes=f'شراء مخزون - فاتورة: {purchase.invoice_number or "بدون رقم"}'
        )

        db.session.add(purchase)
        db.session.commit()

        flash('تم تسجيل عملية شراء المخزون وتحديث الكمية بنجاح', 'success')
        return redirect(url_for('inventory.inventory_purchases'))

    return render_template('inventory/add_inventory_purchase.html', item=item)


@bp.route('/purchase/<int:purchase_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_inventory_purchase(purchase_id):
    """تعديل عملية شراء للمخزون مع مزامنة الكمية."""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية تعديل عمليات الشراء', 'danger')
        return redirect(url_for('inventory.inventory_purchases'))

    purchase = InventoryPurchase.query.get_or_404(purchase_id)

    if request.method == 'POST':
        old_quantity = purchase.quantity
        try:
            new_quantity = float(request.form.get('quantity', 0))
            unit_price = float(request.form.get('unit_price', 0))
            purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات شراء صحيحة', 'danger')
            return render_template('inventory/edit_inventory_purchase.html', purchase=purchase)

        if new_quantity <= 0:
            flash('الكمية يجب أن تكون أكبر من صفر', 'danger')
            return render_template('inventory/edit_inventory_purchase.html', purchase=purchase)

        delta = new_quantity - old_quantity
        if delta < 0 and purchase.item.quantity < abs(delta):
            flash('لا يمكن تقليل كمية الشراء لأن المخزون الحالي لا يكفي', 'danger')
            return render_template('inventory/edit_inventory_purchase.html', purchase=purchase)

        purchase.quantity = new_quantity
        purchase.unit_price = unit_price
        purchase.purchase_date = purchase_date
        purchase.supplier = request.form.get('supplier')
        purchase.invoice_number = request.form.get('invoice_number')
        purchase.notes = request.form.get('notes')

        purchase.calculate_total_cost()

        if delta != 0:
            purchase.item.quantity += delta
            tx_type = 'دخول' if delta > 0 else 'خروج'
            _record_inventory_transaction(
                item_id=purchase.item_id,
                transaction_type=tx_type,
                quantity=abs(delta),
                notes=f'تعديل شراء المخزون رقم {purchase.id}'
            )

        db.session.commit()
        flash('تم تحديث عملية شراء المخزون بنجاح', 'success')
        return redirect(url_for('inventory.inventory_purchases'))

    return render_template('inventory/edit_inventory_purchase.html', purchase=purchase)


@bp.route('/purchase/<int:purchase_id>/delete', methods=['POST'])
@login_required
def delete_inventory_purchase(purchase_id):
    """حذف عملية شراء مخزون مع عكس أثرها على الكمية."""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية حذف عمليات الشراء', 'danger')
        return redirect(url_for('inventory.inventory_purchases'))

    purchase = InventoryPurchase.query.get_or_404(purchase_id)

    # قبل حذف الشراء: يجب أن يكون المخزون الحالي كافيا لعكس الكمية
    if purchase.item.quantity < purchase.quantity:
        flash('لا يمكن حذف عملية الشراء لأن الكمية الحالية في المخزون أقل من الكمية المسجلة', 'danger')
        return redirect(url_for('inventory.inventory_purchases'))

    purchase.item.quantity -= purchase.quantity
    _record_inventory_transaction(
        item_id=purchase.item_id,
        transaction_type='خروج',
        quantity=purchase.quantity,
        notes=f'حذف شراء المخزون رقم {purchase.id}'
    )

    db.session.delete(purchase)
    db.session.commit()

    flash('تم حذف عملية شراء المخزون وتحديث الكمية بنجاح', 'success')
    return redirect(url_for('inventory.inventory_purchases'))


@bp.route('/purchases/report')
@login_required
def inventory_purchases_report():
    """تقرير عمليات شراء المخزون السنوي"""
    if not current_user.can_manage_inventory and not current_user.is_admin:
        flash('ليس لديك صلاحية الوصول إلى هذا القسم', 'danger')
        return redirect(url_for('inventory.index'))
    
    # تحديد السنة الحالية
    current_year = datetime.now().year
    year_start = datetime(current_year, 1, 1).date()
    year_end = datetime(current_year, 12, 31).date()
    
    # جلب جميع عمليات الشراء للسنة الحالية
    purchases = InventoryPurchase.query.filter(
        InventoryPurchase.purchase_date >= year_start,
        InventoryPurchase.purchase_date <= year_end
    ).order_by(InventoryPurchase.purchase_date.desc()).all()
    
    # حساب الإحصائيات
    total_cost = sum(p.total_cost for p in purchases)
    total_quantity = sum(p.quantity for p in purchases)
    
    # تجميع حسب نوع العنصر
    by_category = {}
    for purchase in purchases:
        category = purchase.item.category
        if category not in by_category:
            by_category[category] = {
                'quantity': 0,
                'total_cost': 0,
                'purchases': []
            }
        by_category[category]['quantity'] += purchase.quantity
        by_category[category]['total_cost'] += purchase.total_cost
        by_category[category]['purchases'].append(purchase)
    
    return render_template('inventory/inventory_purchases_report.html',
                         purchases=purchases,
                         total_cost=total_cost,
                         total_quantity=total_quantity,
                         by_category=by_category,
                         year=current_year)
