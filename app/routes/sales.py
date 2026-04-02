from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models.crop import Sales, Crop
from datetime import datetime

bp = Blueprint('sales', __name__, url_prefix='/sales')

@bp.route('/')
@login_required
def index():
    """قائمة المبيعات"""
    if not current_user.can_manage_sales and not current_user.is_admin:
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))
    
    sales_list = Sales.query.all()
    total_revenue = sum(sale.total_price for sale in sales_list)
    return render_template('sales/index.html', sales=sales_list, total_revenue=total_revenue)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_sale():
    """إضافة بيع جديد"""
    if not current_user.can_manage_sales and not current_user.is_admin:
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('sales.index'))
    
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        quantity = float(request.form.get('quantity'))
        price_per_unit = float(request.form.get('price_per_unit'))
        total_price = quantity * price_per_unit
        
        sale = Sales(
            crop_id=request.form.get('crop_id'),
            sale_date=datetime.strptime(request.form.get('sale_date'), '%Y-%m-%d').date(),
            quantity=quantity,
            unit=request.form.get('unit'),
            price_per_unit=price_per_unit,
            total_price=total_price,
            buyer_name=request.form.get('buyer_name'),
            buyer_phone=request.form.get('buyer_phone'),
            payment_status=request.form.get('payment_status'),
            notes=request.form.get('notes')
        )
        
        db.session.add(sale)
        db.session.commit()
        
        flash('تم تسجيل البيع بنجاح', 'success')
        return redirect(url_for('sales.index'))
    
    return render_template('sales/add.html', crops=crops)

@bp.route('/<int:sale_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_sale(sale_id):
    """تعديل بيع"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('sales.index'))
    
    sale = Sales.query.get_or_404(sale_id)
    crops = Crop.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        quantity = float(request.form.get('quantity'))
        price_per_unit = float(request.form.get('price_per_unit'))
        
        sale.crop_id = request.form.get('crop_id')
        sale.quantity = quantity
        sale.unit = request.form.get('unit')
        sale.price_per_unit = price_per_unit
        sale.total_price = quantity * price_per_unit
        sale.buyer_name = request.form.get('buyer_name')
        sale.buyer_phone = request.form.get('buyer_phone')
        sale.payment_status = request.form.get('payment_status')
        sale.notes = request.form.get('notes')
        
        db.session.commit()
        flash('تم تحديث البيع بنجاح', 'success')
        return redirect(url_for('sales.index'))
    
    return render_template('sales/edit.html', sale=sale, crops=crops)

@bp.route('/<int:sale_id>/delete', methods=['POST'])
@login_required
def delete_sale(sale_id):
    """حذف بيع"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('sales.index'))
    
    sale = Sales.query.get_or_404(sale_id)
    db.session.delete(sale)
    db.session.commit()
    
    flash('تم حذف البيع', 'success')
    return redirect(url_for('sales.index'))
