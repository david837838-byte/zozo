from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.crop import (Crop, CropConsumption, Production, Sales, CropHealth, 
                             ProductionBatch, ProductionCost, ProductionStage, ProductionInventory)
from app.models.inventory import InventoryItem, InventoryTransaction, GeneralConsumption
from datetime import datetime, timedelta
from sqlalchemy import func

bp = Blueprint('production', __name__, url_prefix='/production')

@bp.route('/')
@login_required
def index():
    """قائمة الأصناف والإنتاج"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    crops = Crop.query.filter_by(is_active=True).all()

    # Aggregate productions per crop by quality
    aggregated_productions = []
    for crop in crops:
        prods = Production.query.filter_by(crop_id=crop.id).all()
        by_quality = {
            'ممتازة': 0.0,
            'جيدة': 0.0,
            'متوسطة': 0.0,
            'منخفضة': 0.0,
        }
        total = 0.0
        for p in prods:
            qty = p.quantity or 0.0
            q = p.quality or ''
            if q in by_quality:
                by_quality[q] += qty
            else:
                by_quality.setdefault(q, 0.0)
                by_quality[q] += qty
            total += qty

        aggregated_productions.append({
            'crop': crop,
            'by_quality': by_quality,
            'total': total,
            'records': prods
        })

    return render_template('production/index.html', crops=crops, aggregated_productions=aggregated_productions)


@bp.route('/crops')
@login_required
def crops():
    """إدارة الأصناف"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    crops = Crop.query.all()
    return render_template('production/crops.html', crops=crops)

@bp.route('/crops/add', methods=['GET', 'POST'])
@login_required
def add_crop():
    """إضافة صنف جديد"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.crops'))
    
    if request.method == 'POST':
        crop = Crop(
            name=request.form.get('name'),
            category=request.form.get('category'),
            variety=request.form.get('variety'),
            planting_date=datetime.strptime(request.form.get('planting_date'), '%Y-%m-%d').date() if request.form.get('planting_date') else None,
            expected_harvest_date=datetime.strptime(request.form.get('expected_harvest_date'), '%Y-%m-%d').date() if request.form.get('expected_harvest_date') else None,
            location=request.form.get('location'),
            area=float(request.form.get('area')) if request.form.get('area') else None
        )
        
        db.session.add(crop)
        db.session.commit()
        
        flash(f'تم إضافة الصنف {crop.name}', 'success')
        return redirect(url_for('production.crops'))
    
    return render_template('production/add_crop.html')

@bp.route('/crops/<int:crop_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_crop(crop_id):
    """تعديل صنف"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('production.crops'))
    
    crop = Crop.query.get_or_404(crop_id)
    
    if request.method == 'POST':
        crop.name = request.form.get('name')
        crop.category = request.form.get('category')
        crop.variety = request.form.get('variety')
        crop.location = request.form.get('location')
        
        if request.form.get('planting_date'):
            crop.planting_date = datetime.strptime(request.form.get('planting_date'), '%Y-%m-%d').date()
        if request.form.get('expected_harvest_date'):
            crop.expected_harvest_date = datetime.strptime(request.form.get('expected_harvest_date'), '%Y-%m-%d').date()
        if request.form.get('area'):
            crop.area = float(request.form.get('area'))
        
        db.session.commit()
        flash(f'تم تحديث الصنف {crop.name}', 'success')
        return redirect(url_for('production.crops'))
    
    return render_template('production/edit_crop.html', crop=crop)

@bp.route('/crops/<int:crop_id>/delete', methods=['POST'])
@login_required
def delete_crop(crop_id):
    """حذف صنف"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.crops'))
    
    crop = Crop.query.get_or_404(crop_id)
    crop_name = crop.name
    
    try:
        # حذف السجلات المرتبطة بالصنف
        Production.query.filter_by(crop_id=crop_id).delete()
        CropConsumption.query.filter_by(crop_id=crop_id).delete()
        
        # حذف الصنف نفسه
        db.session.delete(crop)
        db.session.commit()
        
        flash(f'تم حذف الصنف "{crop_name}" وجميع سجلاته بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء الحذف: {str(e)}', 'danger')
    
    return redirect(url_for('production.crops'))

@bp.route('/crops/<int:crop_id>/consumption', methods=['GET', 'POST'])
@login_required
def add_consumption(crop_id):
    """إضافة استهلاك مخزون لصنف معين مع خصمه من المخزون."""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية إضافة استهلاك للإنتاج', 'danger')
        return redirect(url_for('production.crops'))

    crop = Crop.query.get_or_404(crop_id)
    inventory_items = InventoryItem.query.order_by(InventoryItem.name).all()

    if request.method == 'POST':
        try:
            item_id = request.form.get('inventory_item_id', type=int)
            quantity_used = float(request.form.get('quantity_used', 0))
            consumption_date = datetime.strptime(request.form.get('consumption_date'), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات استهلاك صحيحة', 'danger')
            return render_template('production/add_consumption.html', crop=crop, inventory_items=inventory_items, consumptions=CropConsumption.query.filter_by(crop_id=crop_id).all())

        inventory_item = InventoryItem.query.get_or_404(item_id)

        if quantity_used <= 0:
            flash('الكمية يجب أن تكون أكبر من صفر', 'danger')
            return render_template('production/add_consumption.html', crop=crop, inventory_items=inventory_items, consumptions=CropConsumption.query.filter_by(crop_id=crop_id).all())

        if inventory_item.quantity < quantity_used:
            flash('الكمية المتوفرة في المخزون غير كافية', 'danger')
            return render_template('production/add_consumption.html', crop=crop, inventory_items=inventory_items, consumptions=CropConsumption.query.filter_by(crop_id=crop_id).all())

        consumption = CropConsumption(
            crop_id=crop_id,
            inventory_item_id=item_id,
            quantity_used=quantity_used,
            consumption_date=consumption_date,
            notes=request.form.get('notes')
        )

        inventory_item.quantity -= quantity_used

        stock_tx = InventoryTransaction(
            item_id=item_id,
            transaction_type='خروج',
            quantity=quantity_used,
            notes=f'استهلاك للصنف: {crop.name}'
        )

        db.session.add(consumption)
        db.session.add(stock_tx)
        db.session.commit()

        flash(f'تم تسجيل استهلاك لصنف "{crop.name}" وتحديث كمية المخزون', 'success')
        return redirect(url_for('production.crop_consumptions', crop_id=crop_id))

    consumptions = CropConsumption.query.filter_by(crop_id=crop_id).order_by(CropConsumption.consumption_date.desc()).all()
    return render_template('production/add_consumption.html', crop=crop, inventory_items=inventory_items, consumptions=consumptions)


@bp.route('/crops/<int:crop_id>/consumptions')
@login_required
def crop_consumptions(crop_id):
    """عرض سجل استهلاك الصنف"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('production.crops'))
    
    crop = Crop.query.get_or_404(crop_id)
    consumptions = CropConsumption.query.filter_by(crop_id=crop_id).order_by(CropConsumption.consumption_date.desc()).all()
    
    return render_template('production/crop_consumptions.html', crop=crop, consumptions=consumptions)

@bp.route('/crop-consumption/<int:consumption_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_crop_consumption(consumption_id):
    """تعديل استهلاك صنف مع مزامنة المخزون."""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية تعديل الاستهلاك', 'danger')
        return redirect(url_for('production.crops'))

    consumption = CropConsumption.query.get_or_404(consumption_id)
    crop = consumption.crop
    inventory_items = InventoryItem.query.order_by(InventoryItem.name).all()

    if request.method == 'POST':
        old_item = consumption.inventory_item
        old_quantity = consumption.quantity_used

        try:
            new_item_id = request.form.get('inventory_item_id', type=int)
            new_quantity = float(request.form.get('quantity_used', 0))
            new_date = datetime.strptime(request.form.get('consumption_date'), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات استهلاك صحيحة', 'danger')
            return render_template('production/edit_consumption.html', consumption=consumption, crop=crop, inventory_items=inventory_items)

        new_item = InventoryItem.query.get_or_404(new_item_id)

        if new_quantity <= 0:
            flash('الكمية يجب أن تكون أكبر من صفر', 'danger')
            return render_template('production/edit_consumption.html', consumption=consumption, crop=crop, inventory_items=inventory_items)

        # إعادة الكمية القديمة إلى المخزون
        old_item.quantity += old_quantity

        # التأكد من توفر الكمية المطلوبة بعد التعديل
        if new_item.quantity < new_quantity:
            old_item.quantity -= old_quantity
            flash('الكمية المتوفرة في المخزون غير كافية بعد التعديل', 'danger')
            return render_template('production/edit_consumption.html', consumption=consumption, crop=crop, inventory_items=inventory_items)

        new_item.quantity -= new_quantity

        consumption.inventory_item_id = new_item_id
        consumption.quantity_used = new_quantity
        consumption.consumption_date = new_date
        consumption.notes = request.form.get('notes')

        db.session.add(InventoryTransaction(
            item_id=old_item.id,
            transaction_type='دخول',
            quantity=old_quantity,
            notes=f'إرجاع كمية قديمة عند تعديل استهلاك الصنف: {crop.name}'
        ))
        db.session.add(InventoryTransaction(
            item_id=new_item.id,
            transaction_type='خروج',
            quantity=new_quantity,
            notes=f'تسجيل استهلاك بعد التعديل: {crop.name}'
        ))

        db.session.commit()
        flash('تم تحديث استهلاك الصنف بنجاح', 'success')
        return redirect(url_for('production.crop_consumptions', crop_id=crop.id))

    return render_template('production/edit_consumption.html', consumption=consumption, crop=crop, inventory_items=inventory_items)


@bp.route('/crop-consumption/<int:consumption_id>/delete', methods=['POST'])
@login_required
def delete_crop_consumption(consumption_id):
    """حذف استهلاك صنف وإرجاع الكمية إلى المخزون."""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية حذف الاستهلاك', 'danger')
        return redirect(url_for('production.crops'))

    consumption = CropConsumption.query.get_or_404(consumption_id)
    crop_id = consumption.crop_id

    consumption.inventory_item.quantity += consumption.quantity_used

    db.session.add(InventoryTransaction(
        item_id=consumption.inventory_item_id,
        transaction_type='دخول',
        quantity=consumption.quantity_used,
        notes=f'إرجاع كمية بعد حذف استهلاك الصنف: {consumption.crop.name}'
    ))

    db.session.delete(consumption)
    db.session.commit()

    flash('تم حذف استهلاك الصنف وإرجاع الكمية إلى المخزون', 'success')
    return redirect(url_for('production.crop_consumptions', crop_id=crop_id))


@bp.route('/crops/<int:crop_id>/productions')
@login_required
def crop_productions(crop_id):
    """عرض سجل الإنتاج للصنف"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('production.crops'))
    
    crop = Crop.query.get_or_404(crop_id)
    crop_productions = Production.query.filter_by(crop_id=crop_id).order_by(Production.production_date.desc()).all()
    
    return render_template('production/crop_productions.html', crop=crop, crop_productions=crop_productions)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_production():
    """إضافة إنتاج"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.index'))
    
    crops = Crop.query.filter_by(is_active=True).all()
    productions = Production.query.all()
    
    if request.method == 'POST':
        production = Production(
            crop_id=request.form.get('crop_id'),
            production_date=datetime.strptime(request.form.get('production_date'), '%Y-%m-%d').date(),
            quantity=float(request.form.get('quantity')),
            unit=request.form.get('unit'),
            quality=request.form.get('quality'),
            notes=request.form.get('notes')
        )
        
        db.session.add(production)
        db.session.commit()
        
        flash('تم تسجيل الإنتاج بنجاح', 'success')
        return redirect(url_for('production.index'))
    
    return render_template('production/add_production.html', crops=crops)


@bp.route('/<int:production_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_production(production_id):
    """تعديل سجل إنتاج"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.index'))

    production = Production.query.get_or_404(production_id)
    crops = Crop.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        production.crop_id = int(request.form.get('crop_id'))
        production.production_date = datetime.strptime(request.form.get('production_date'), '%Y-%m-%d').date()
        production.quantity = float(request.form.get('quantity'))
        production.unit = request.form.get('unit')
        production.quality = request.form.get('quality') if request.form.get('quality') else None
        production.notes = request.form.get('notes')

        db.session.commit()
        flash('تم تحديث سجل الإنتاج بنجاح', 'success')
        return redirect(url_for('production.index'))

    return render_template('production/edit_production.html', production=production, crops=crops)


@bp.route('/<int:production_id>/delete', methods=['POST'])
@login_required
def delete_production(production_id):
    """حذف إنتاج"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.index'))
    
    production = Production.query.get_or_404(production_id)
    db.session.delete(production)
    db.session.commit()
    
    flash('تم حذف الإنتاج بنجاح', 'success')
    return redirect(url_for('production.index'))

# Routes for General Consumption (أدوية، أسمدة، مشتقات نفطية)

@bp.route('/consumptions')
@login_required
def general_consumptions():
    """قائمة استهلاكات الأدوية والأسمدة والمشتقات النفطية"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    consumptions = GeneralConsumption.query.order_by(GeneralConsumption.consumption_date.desc()).all()
    return render_template('production/consumptions.html', consumptions=consumptions)

@bp.route('/consumptions/add', methods=['GET', 'POST'])
@login_required
def add_general_consumption():
    """إضافة استهلاك عام"""
    if not current_user.can_manage_production and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.general_consumptions'))
    
    inventory_items = InventoryItem.query.all()
    
    if request.method == 'POST':
        item_id = request.form.get('inventory_item_id')
        inventory_item = InventoryItem.query.get_or_404(item_id)
        quantity_used = float(request.form.get('quantity_used'))
        
        # Check stock availability
        if inventory_item.quantity < quantity_used:
            flash('الكمية المتوفرة غير كافية', 'danger')
            return render_template('production/add_general_consumption.html', inventory_items=inventory_items)
        
        consumption = GeneralConsumption(
            inventory_item_id=item_id,
            quantity_used=quantity_used,
            consumption_type=request.form.get('consumption_type'),
            consumption_date=datetime.strptime(request.form.get('consumption_date'), '%Y-%m-%d').date(),
            notes=request.form.get('notes')
        )
        
        # Update inventory quantity
        inventory_item.quantity -= quantity_used
        
        db.session.add(consumption)
        db.session.commit()
        
        flash('تم تسجيل الاستهلاك بنجاح', 'success')
        return redirect(url_for('production.general_consumptions'))
    
    return render_template('production/add_general_consumption.html', inventory_items=inventory_items)

@bp.route('/consumptions/<int:consumption_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_general_consumption(consumption_id):
    """تعديل استهلاك عام"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('production.general_consumptions'))
    
    consumption = GeneralConsumption.query.get_or_404(consumption_id)
    inventory_items = InventoryItem.query.all()
    
    if request.method == 'POST':
        old_quantity = consumption.quantity_used
        new_quantity = float(request.form.get('quantity_used'))
        
        # Adjust inventory
        if old_quantity != new_quantity:
            difference = old_quantity - new_quantity
            consumption.inventory_item.quantity += difference
            
            # Check if stock is sufficient
            if consumption.inventory_item.quantity < 0:
                flash('الكمية المتوفرة غير كافية', 'danger')
                consumption.inventory_item.quantity -= difference
                return render_template('production/edit_general_consumption.html', 
                                     consumption=consumption, inventory_items=inventory_items)
        
        consumption.inventory_item_id = request.form.get('inventory_item_id')
        consumption.quantity_used = new_quantity
        consumption.consumption_type = request.form.get('consumption_type')
        consumption.consumption_date = datetime.strptime(request.form.get('consumption_date'), '%Y-%m-%d').date()
        consumption.notes = request.form.get('notes')
        
        db.session.commit()
        flash('تم تحديث الاستهلاك بنجاح', 'success')
        return redirect(url_for('production.general_consumptions'))
    
    return render_template('production/edit_general_consumption.html', 
                         consumption=consumption, inventory_items=inventory_items)

@bp.route('/consumptions/<int:consumption_id>/delete', methods=['POST'])
@login_required
def delete_general_consumption(consumption_id):
    """حذف استهلاك عام"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.general_consumptions'))
    
    consumption = GeneralConsumption.query.get_or_404(consumption_id)
    
    # Return quantity to inventory
    consumption.inventory_item.quantity += consumption.quantity_used
    
    db.session.delete(consumption)
    db.session.commit()
    
    flash('تم حذف الاستهلاك بنجاح', 'success')
    return redirect(url_for('production.general_consumptions'))

# ========== مسارات جديدة متقدمة ==========

# مسارات صحة المحاصيل
@bp.route('/health')
@login_required
def health_records():
    """قائمة سجلات صحة المحاصيل"""
    if not (current_user.can_manage_crop_health or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    health_records = CropHealth.query.order_by(CropHealth.health_date.desc()).all()
    critical_issues = [h for h in health_records if h.health_status == 'حرجة']
    
    return render_template('production/health_records.html', 
                         health_records=health_records, 
                         critical_issues=critical_issues)

@bp.route('/health/add', methods=['GET', 'POST'])
@login_required
def add_health_record():
    """إضافة سجل صحة للمحصول"""
    if not (current_user.can_manage_crop_health or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.health_records'))
    
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        severity_str = request.form.get('severity_percentage', '0').strip()
        severity_percentage = float(severity_str) if severity_str else 0
        
        recovery_str = request.form.get('recovery_estimated_days', '').strip()
        recovery_estimated_days = int(recovery_str) if recovery_str else None
        
        health_record = CropHealth(
            crop_id=request.form.get('crop_id'),
            health_date=datetime.strptime(request.form.get('health_date'), '%Y-%m-%d').date(),
            health_status=request.form.get('health_status'),
            disease_name=request.form.get('disease_name'),
            pest_name=request.form.get('pest_name'),
            treatment_applied=request.form.get('treatment_applied'),
            severity_percentage=severity_percentage,
            recovery_estimated_days=recovery_estimated_days,
            notes=request.form.get('notes')
        )
        
        db.session.add(health_record)
        db.session.commit()
        
        flash('تم تسجيل حالة الصحة بنجاح', 'success')
        return redirect(url_for('production.health_records'))
    
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('production/add_health_record.html', crops=crops, today=today)

@bp.route('/health/<int:health_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_health_record(health_id):
    """تعديل سجل صحة المحصول"""
    if not (current_user.can_edit or current_user.is_admin):
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('production.health_records'))
    
    health_record = CropHealth.query.get_or_404(health_id)
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        health_record.crop_id = request.form.get('crop_id')
        health_record.health_date = datetime.strptime(request.form.get('health_date'), '%Y-%m-%d').date()
        health_record.health_status = request.form.get('health_status')
        health_record.disease_name = request.form.get('disease_name')
        health_record.pest_name = request.form.get('pest_name')
        health_record.treatment_applied = request.form.get('treatment_applied')
        
        severity_str = request.form.get('severity_percentage', '0').strip()
        health_record.severity_percentage = float(severity_str) if severity_str else 0
        
        recovery_str = request.form.get('recovery_estimated_days', '').strip()
        health_record.recovery_estimated_days = int(recovery_str) if recovery_str else None
        health_record.notes = request.form.get('notes')
        
        db.session.commit()
        flash('تم تحديث سجل الصحة بنجاح', 'success')
        return redirect(url_for('production.health_records'))
    
    return render_template('production/edit_health_record.html', health_record=health_record, crops=crops)

@bp.route('/health/<int:health_id>/delete', methods=['POST'])
@login_required
def delete_health_record(health_id):
    """حذف سجل صحة المحصول"""
    if not (current_user.can_delete or current_user.is_admin):
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.health_records'))
    
    health_record = CropHealth.query.get_or_404(health_id)
    db.session.delete(health_record)
    db.session.commit()
    
    flash('تم حذف سجل الصحة بنجاح', 'success')
    return redirect(url_for('production.health_records'))

# مسارات دفعات الإنتاج
@bp.route('/batches')
@login_required
def production_batches():
    """قائمة دفعات الإنتاج"""
    if not (current_user.can_manage_production_batches or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    batches = ProductionBatch.query.order_by(ProductionBatch.planting_date.desc()).all()
    total_costs = sum([batch.get_total_costs() for batch in batches])
    
    return render_template('production/batches.html', batches=batches, total_costs=total_costs)

@bp.route('/batches/add', methods=['GET', 'POST'])
@login_required
def add_production_batch():
    """إضافة دفعة إنتاج جديدة"""
    if not (current_user.can_manage_production_batches or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.production_batches'))
    
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        batch_number = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Parse numeric fields safely
        area_used_str = request.form.get('area_used', '').strip()
        area_used = float(area_used_str) if area_used_str else None
        
        soil_prep_str = request.form.get('soil_preparation_cost', '0').strip()
        soil_prep = float(soil_prep_str) if soil_prep_str else 0
        
        seeds_str = request.form.get('seeds_cost', '0').strip()
        seeds = float(seeds_str) if seeds_str else 0
        
        fertilizers_str = request.form.get('fertilizers_cost', '0').strip()
        fertilizers = float(fertilizers_str) if fertilizers_str else 0
        
        pesticides_str = request.form.get('pesticides_cost', '0').strip()
        pesticides = float(pesticides_str) if pesticides_str else 0
        
        labor_str = request.form.get('labor_cost', '0').strip()
        labor = float(labor_str) if labor_str else 0
        
        watering_str = request.form.get('watering_cost', '0').strip()
        watering = float(watering_str) if watering_str else 0
        
        other_str = request.form.get('other_costs', '0').strip()
        other = float(other_str) if other_str else 0
        
        batch = ProductionBatch(
            crop_id=request.form.get('crop_id'),
            batch_number=batch_number,
            planting_date=datetime.strptime(request.form.get('planting_date'), '%Y-%m-%d').date(),
            expected_harvest_date=datetime.strptime(request.form.get('expected_harvest_date'), '%Y-%m-%d').date() if request.form.get('expected_harvest_date') else None,
            area_used=area_used,
            soil_preparation_cost=soil_prep,
            seeds_cost=seeds,
            fertilizers_cost=fertilizers,
            pesticides_cost=pesticides,
            labor_cost=labor,
            watering_cost=watering,
            other_costs=other,
            notes=request.form.get('notes')
        )
        
        db.session.add(batch)
        db.session.commit()
        
        flash(f'تم إنشاء دفعة إنتاج جديدة {batch_number}', 'success')
        return redirect(url_for('production.production_batches'))
    
    return render_template('production/add_batch.html', crops=crops)

@bp.route('/batches/<int:batch_id>')
@login_required
def view_batch(batch_id):
    """عرض تفاصيل دفعة الإنتاج"""
    if not (current_user.can_manage_production_batches or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('home.index'))
    
    batch = ProductionBatch.query.get_or_404(batch_id)
    stages = ProductionStage.query.filter_by(crop_id=batch.crop_id).order_by(ProductionStage.stage_order).all()
    
    return render_template('production/view_batch.html', batch=batch, stages=stages)

@bp.route('/batches/<int:batch_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_production_batch(batch_id):
    """تعديل دفعة إنتاج"""
    if not (current_user.can_manage_production_batches or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.production_batches'))
    
    batch = ProductionBatch.query.get_or_404(batch_id)
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        batch.crop_id = request.form.get('crop_id')
        batch.planting_date = datetime.strptime(request.form.get('planting_date'), '%Y-%m-%d').date()
        
        if request.form.get('expected_harvest_date'):
            batch.expected_harvest_date = datetime.strptime(request.form.get('expected_harvest_date'), '%Y-%m-%d').date()
        
        # Parse numeric fields safely
        area_used_str = request.form.get('area_used', '').strip()
        batch.area_used = float(area_used_str) if area_used_str else None
        
        soil_prep_str = request.form.get('soil_preparation_cost', '0').strip()
        batch.soil_preparation_cost = float(soil_prep_str) if soil_prep_str else 0
        
        seeds_str = request.form.get('seeds_cost', '0').strip()
        batch.seeds_cost = float(seeds_str) if seeds_str else 0
        
        fertilizers_str = request.form.get('fertilizers_cost', '0').strip()
        batch.fertilizers_cost = float(fertilizers_str) if fertilizers_str else 0
        
        pesticides_str = request.form.get('pesticides_cost', '0').strip()
        batch.pesticides_cost = float(pesticides_str) if pesticides_str else 0
        
        labor_str = request.form.get('labor_cost', '0').strip()
        batch.labor_cost = float(labor_str) if labor_str else 0
        
        watering_str = request.form.get('watering_cost', '0').strip()
        batch.watering_cost = float(watering_str) if watering_str else 0
        
        other_str = request.form.get('other_costs', '0').strip()
        batch.other_costs = float(other_str) if other_str else 0
        
        batch.notes = request.form.get('notes')
        
        db.session.commit()
        flash(f'تم تحديث دفعة الإنتاج {batch.batch_number} بنجاح', 'success')
        return redirect(url_for('production.production_batches'))
    
    return render_template('production/edit_batch.html', batch=batch, crops=crops)

@bp.route('/batches/<int:batch_id>/delete', methods=['POST'])
@login_required
def delete_production_batch(batch_id):
    """حذف دفعة إنتاج"""
    if not (current_user.can_delete or current_user.is_admin):
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.production_batches'))
    
    batch = ProductionBatch.query.get_or_404(batch_id)
    batch_number = batch.batch_number
    
    db.session.delete(batch)
    db.session.commit()
    
    flash(f'تم حذف دفعة الإنتاج {batch_number} بنجاح', 'success')
    return redirect(url_for('production.production_batches'))

# مسارات تكاليف الإنتاج
@bp.route('/costs')
@login_required
def production_costs():
    """قائمة تكاليف الإنتاج"""
    if not (current_user.can_manage_production_costs or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    costs = ProductionCost.query.order_by(ProductionCost.cost_date.desc()).all()
    total_costs = db.session.query(func.sum(ProductionCost.total_cost)).scalar() or 0
    costs_by_type = db.session.query(
        ProductionCost.cost_type, 
        func.sum(ProductionCost.total_cost)
    ).group_by(ProductionCost.cost_type).all()
    
    return render_template('production/costs.html', 
                         costs=costs, 
                         total_costs=total_costs,
                         costs_by_type=costs_by_type)

@bp.route('/costs/add', methods=['GET', 'POST'])
@login_required
def add_production_cost():
    """إضافة تكلفة إنتاج"""
    if not (current_user.can_manage_production_costs or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.production_costs'))
    
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        quantity_str = request.form.get('quantity', '').strip()
        quantity = float(quantity_str) if quantity_str else None
        
        unit_cost_str = request.form.get('unit_cost', '0').strip()
        unit_cost = float(unit_cost_str) if unit_cost_str else 0
        
        total_cost_str = request.form.get('total_cost', '0').strip()
        total_cost = float(total_cost_str) if total_cost_str else 0
        
        cost = ProductionCost(
            crop_id=request.form.get('crop_id'),
            cost_date=datetime.strptime(request.form.get('cost_date'), '%Y-%m-%d').date(),
            cost_type=request.form.get('cost_type'),
            cost_category=request.form.get('cost_category'),
            description=request.form.get('description'),
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            reference_number=request.form.get('reference_number'),
            notes=request.form.get('notes')
        )
        
        db.session.add(cost)
        db.session.commit()
        
        flash('تم تسجيل التكلفة بنجاح', 'success')
        return redirect(url_for('production.production_costs'))
    
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('production/add_cost.html', crops=crops, today=today)

@bp.route('/costs/<int:cost_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_production_cost(cost_id):
    """تعديل تكلفة إنتاج"""
    if not (current_user.can_manage_production_costs or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.production_costs'))
    
    cost = ProductionCost.query.get_or_404(cost_id)
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        cost.crop_id = request.form.get('crop_id')
        cost.cost_date = datetime.strptime(request.form.get('cost_date'), '%Y-%m-%d').date()
        cost.cost_type = request.form.get('cost_type')
        cost.cost_category = request.form.get('cost_category')
        cost.description = request.form.get('description')
        
        quantity_str = request.form.get('quantity', '').strip()
        cost.quantity = float(quantity_str) if quantity_str else None
        
        unit_cost_str = request.form.get('unit_cost', '0').strip()
        cost.unit_cost = float(unit_cost_str) if unit_cost_str else 0
        
        total_cost_str = request.form.get('total_cost', '0').strip()
        cost.total_cost = float(total_cost_str) if total_cost_str else 0
        
        cost.reference_number = request.form.get('reference_number')
        cost.notes = request.form.get('notes')
        
        db.session.commit()
        flash('تم تحديث التكلفة بنجاح', 'success')
        return redirect(url_for('production.production_costs'))
    
    return render_template('production/edit_cost.html', cost=cost, crops=crops)

@bp.route('/costs/<int:cost_id>/delete', methods=['POST'])
@login_required
def delete_production_cost(cost_id):
    """حذف تكلفة إنتاج"""
    if not (current_user.can_delete or current_user.is_admin):
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.production_costs'))
    
    cost = ProductionCost.query.get_or_404(cost_id)
    db.session.delete(cost)
    db.session.commit()
    
    flash('تم حذف التكلفة بنجاح', 'success')
    return redirect(url_for('production.production_costs'))

# مسارات مراحل الإنتاج
@bp.route('/stages/<int:crop_id>')
@login_required
def production_stages(crop_id):
    """قائمة مراحل الإنتاج للصنف"""
    if not (current_user.can_manage_production_stages or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('home.index'))
    
    crop = Crop.query.get_or_404(crop_id)
    stages = ProductionStage.query.filter_by(crop_id=crop_id).order_by(ProductionStage.stage_order).all()
    
    return render_template('production/stages.html', crop=crop, stages=stages)

@bp.route('/stages/<int:crop_id>/add', methods=['GET', 'POST'])
@login_required
def add_production_stage(crop_id):
    """إضافة مرحلة إنتاج"""
    if not (current_user.can_manage_production_stages or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.production_stages', crop_id=crop_id))
    
    crop = Crop.query.get_or_404(crop_id)
    
    if request.method == 'POST':
        stage = ProductionStage(
            crop_id=crop_id,
            stage_name=request.form.get('stage_name'),
            stage_order=int(request.form.get('stage_order')),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else None,
            expected_duration_days=int(request.form.get('expected_duration_days', 0)) or None,
            description=request.form.get('description'),
            required_actions=request.form.get('required_actions'),
            completion_notes=request.form.get('completion_notes')
        )
        
        db.session.add(stage)
        db.session.commit()
        
        flash('تم إضافة مرحلة الإنتاج بنجاح', 'success')
        return redirect(url_for('production.production_stages', crop_id=crop_id))
    
    return render_template('production/add_stage.html', crop=crop)

@bp.route('/stages/<int:stage_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_production_stage(stage_id):
    """تعديل مرحلة إنتاج"""
    if not (current_user.can_manage_production_stages or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('production.index'))
    
    stage = ProductionStage.query.get_or_404(stage_id)
    crop = stage.crop
    
    if request.method == 'POST':
        stage.stage_name = request.form.get('stage_name')
        stage.stage_order = int(request.form.get('stage_order'))
        stage.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        
        if request.form.get('end_date'):
            stage.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        
        duration_str = request.form.get('expected_duration_days', '').strip()
        stage.expected_duration_days = int(duration_str) if duration_str else None
        
        stage.description = request.form.get('description')
        stage.required_actions = request.form.get('required_actions')
        stage.completion_notes = request.form.get('completion_notes')
        
        db.session.commit()
        flash('تم تحديث مرحلة الإنتاج بنجاح', 'success')
        return redirect(url_for('production.production_stages', crop_id=stage.crop_id))
    
    return render_template('production/edit_stage.html', stage=stage, crop=crop)

@bp.route('/stages/<int:stage_id>/delete', methods=['POST'])
@login_required
def delete_production_stage(stage_id):
    """حذف مرحلة إنتاج"""
    if not (current_user.can_delete or current_user.is_admin):
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('production.index'))
    
    stage = ProductionStage.query.get_or_404(stage_id)
    crop_id = stage.crop_id
    
    db.session.delete(stage)
    db.session.commit()
    
    flash('تم حذف مرحلة الإنتاج بنجاح', 'success')
    return redirect(url_for('production.production_stages', crop_id=crop_id))

# مسارات تحليلات الإنتاج
@bp.route('/analytics')
@login_required
def production_analytics():
    """تحليلات الإنتاج والأداء"""
    if not (current_user.can_view_analytics or current_user.can_manage_production or current_user.is_admin):
        flash('ليس لديك صلاحية للوصول', 'danger')
        return redirect(url_for('home.index'))
    
    # إجمالي الإنتاج
    total_production = db.session.query(func.sum(Production.quantity)).scalar() or 0
    
    # إجمالي المبيعات
    total_sales = db.session.query(func.sum(Sales.total_price)).scalar() or 0
    
    # إجمالي التكاليف
    total_costs = db.session.query(func.sum(ProductionCost.total_cost)).scalar() or 0
    
    # الربحية
    profitability = total_sales - total_costs
    
    # الأصناف الأكثر إنتاجية
    top_crops = db.session.query(
        Crop.name, 
        func.sum(Production.quantity).label('total_qty'),
        func.sum(Sales.total_price).label('total_sales')
    ).outerjoin(Production).outerjoin(Sales).group_by(Crop.id).order_by(
        func.sum(Production.quantity).desc()
    ).limit(10).all()
    
    # الأصناف الأكثر ربحية
    crops = Crop.query.all()
    crop_profitability = []
    for crop in crops:
        profit = crop.get_profitability()
        if profit != 0:
            crop_profitability.append({'name': crop.name, 'profitability': profit})
    crop_profitability.sort(key=lambda x: x['profitability'], reverse=True)
    
    # الأصناف الحرجة (صحة)
    critical_crops = db.session.query(Crop).filter(Crop.health_status == 'حرجة').all()
    
    return render_template('production/analytics.html',
                         total_production=total_production,
                         total_sales=total_sales,
                         total_costs=total_costs,
                         profitability=profitability,
                         top_crops=top_crops,
                         crop_profitability=crop_profitability[:5],
                         critical_crops=critical_crops)

@bp.route('/report')
@login_required
def production_report():
    """تقرير الإنتاج الشامل"""
    if not (current_user.can_view_analytics or current_user.can_manage_reports or current_user.is_admin):
        flash('ليس لديك صلاحية الوصول', 'danger')
        return redirect(url_for('home.index'))
    
    crops = Crop.query.all()
    crop_data = []
    
    for crop in crops:
        crop_data.append({
            'crop': crop,
            'total_production': crop.get_total_production(),
            'total_sales': crop.get_total_sales(),
            'total_costs': crop.get_total_costs(),
            'profitability': crop.get_profitability(),
            'productivity': crop.get_productivity(),
            'batches': len(crop.production_batches),
            'health_status': crop.health_status
        })
    
    return render_template('production/report.html', crop_data=crop_data)
