from collections import defaultdict
from datetime import datetime
from uuid import uuid4

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.crop import Crop, Production, Sales
from app.security import get_submitted_csrf_token, validate_csrf_token

bp = Blueprint('sales', __name__, url_prefix='/sales')

QUALITY_LEVELS = ('ممتازة', 'جيدة', 'متوسطة', 'منخفضة')
QUALITY_ALIASES = {
    'ممتاز': 'ممتازة',
    'ممتازة': 'ممتازة',
    'جيد': 'جيدة',
    'جيدة': 'جيدة',
    'وسط': 'متوسطة',
    'متوسط': 'متوسطة',
    'متوسطة': 'متوسطة',
    'منخفض': 'منخفضة',
    'منخفضة': 'منخفضة',
}


def _can_access_sales():
    return bool(current_user.can_manage_sales or current_user.is_admin)


def _normalize_quality(value):
    text = (value or '').strip()
    if text in QUALITY_LEVELS:
        return text
    return QUALITY_ALIASES.get(text, 'متوسطة')


def _safe_float(value):
    return float(str(value).strip())


def _safe_optional_float(value, default=0.0):
    text = (str(value).strip() if value is not None else '')
    if not text:
        return float(default)
    return float(text)


def _build_stock_map(crop_id, exclude_sale_id=None):
    stock_map = defaultdict(lambda: {'produced': 0.0, 'sold': 0.0})

    productions = Production.query.filter_by(crop_id=crop_id).all()
    for production in productions:
        quality = _normalize_quality(production.quality)
        unit = (production.unit or '').strip()
        quantity = float(production.quantity or 0)
        if not unit or quantity <= 0:
            continue
        stock_map[(quality, unit)]['produced'] += quantity

    sales_query = Sales.query.filter_by(crop_id=crop_id)
    if exclude_sale_id is not None:
        sales_query = sales_query.filter(Sales.id != exclude_sale_id)

    for sale in sales_query.all():
        quality = _normalize_quality(getattr(sale, 'quality', None))
        unit = (sale.unit or '').strip()
        quantity = float(sale.quantity or 0)
        if not unit or quantity <= 0:
            continue
        stock_map[(quality, unit)]['sold'] += quantity

    return stock_map


def _available_quantity(crop_id, quality, unit, exclude_sale_id=None):
    stock_map = _build_stock_map(crop_id, exclude_sale_id=exclude_sale_id)
    data = stock_map.get((_normalize_quality(quality), (unit or '').strip()))
    if not data:
        return 0.0
    return round((data['produced'] - data['sold']), 4)


def _stock_payload(crop_id, exclude_sale_id=None):
    stock_map = _build_stock_map(crop_id, exclude_sale_id=exclude_sale_id)

    quality_totals = {level: 0.0 for level in QUALITY_LEVELS}
    stock_entries = []

    for (quality, unit), values in stock_map.items():
        produced = round(values['produced'], 4)
        sold = round(values['sold'], 4)
        available = round(produced - sold, 4)
        quality_totals.setdefault(quality, 0.0)
        quality_totals[quality] += available
        stock_entries.append(
            {
                'quality': quality,
                'unit': unit,
                'produced': produced,
                'sold': sold,
                'available': available,
            }
        )

    stock_entries.sort(key=lambda row: (QUALITY_LEVELS.index(row['quality']) if row['quality'] in QUALITY_LEVELS else 999, row['unit']))

    quality_rows = [
        {'quality': quality, 'available': round(quality_totals.get(quality, 0.0), 4)}
        for quality in QUALITY_LEVELS
    ]

    return {
        'quality_totals': quality_rows,
        'stock_entries': stock_entries,
    }


def _build_invoice_group_key():
    return f"INVGRP-{uuid4().hex[:20]}"


def _load_invoice_sales(anchor_sale):
    if not anchor_sale.invoice_group_key:
        return [anchor_sale]
    return (
        Sales.query.filter_by(invoice_group_key=anchor_sale.invoice_group_key)
        .order_by(Sales.id.asc())
        .all()
    )


def _invoice_totals(invoice_sales):
    subtotal = sum(float(item.subtotal()) for item in invoice_sales)
    carrier = next(
        (
            item for item in invoice_sales
            if float(item.discount_percent or 0) > 0
            or float(item.discount_amount or 0) > 0
            or float(item.transport_cost or 0) > 0
        ),
        invoice_sales[0] if invoice_sales else None,
    )
    discount_percent = float(getattr(carrier, 'discount_percent', 0) or 0)
    discount_amount = float(getattr(carrier, 'discount_amount', 0) or 0)
    transport_cost = float(getattr(carrier, 'transport_cost', 0) or 0)
    net_total = subtotal - discount_amount - transport_cost
    return {
        'subtotal': subtotal,
        'discount_percent': discount_percent,
        'discount_amount': discount_amount,
        'transport_cost': transport_cost,
        'net_total': net_total,
        'carrier_id': getattr(carrier, 'id', None),
    }


@bp.route('/')
@login_required
def index():
    """قائمة المبيعات"""
    if not _can_access_sales():
        flash('ليس لديك صلاحية للوصول إلى هذا القسم', 'danger')
        return redirect(url_for('home.index'))

    sales_list = Sales.query.order_by(Sales.sale_date.desc(), Sales.id.desc()).all()
    total_revenue = sum(float(sale.net_total()) for sale in sales_list)
    return render_template('sales/index.html', sales=sales_list, total_revenue=total_revenue)


@bp.route('/stock/<int:crop_id>')
@login_required
def stock_by_crop(crop_id):
    """واجهة JSON لعرض المتاح من الإنتاج أثناء البيع."""
    if not _can_access_sales():
        return jsonify({'error': 'forbidden'}), 403

    payload = _stock_payload(crop_id)
    return jsonify(payload)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_sale():
    """إضافة بيع جديد"""
    if not _can_access_sales():
        flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
        return redirect(url_for('sales.index'))

    crops = Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()

    if request.method == 'POST':
        submitted_token = get_submitted_csrf_token()
        if not validate_csrf_token(submitted_token):
            flash('رمز الأمان غير صالح، يرجى إعادة المحاولة', 'danger')
            return redirect(url_for('sales.add_sale'))

        try:
            crop_id = request.form.get('crop_id', type=int)
            sale_date = datetime.strptime(request.form.get('sale_date'), '%Y-%m-%d').date()
            discount_percent = _safe_optional_float(request.form.get('discount_percent'), default=0.0)
            transport_cost = _safe_optional_float(request.form.get('transport_cost'), default=0.0)
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات بيع صحيحة', 'danger')
            return render_template('sales/add.html', crops=crops)

        if not crop_id:
            flash('يرجى اختيار الصنف', 'danger')
            return render_template('sales/add.html', crops=crops)

        if discount_percent < 0 or discount_percent > 100 or transport_cost < 0:
            flash('نسبة الخصم يجب أن تكون بين 0 و100، والنقل يجب أن يكون صفر أو أكبر', 'danger')
            return render_template('sales/add.html', crops=crops)

        qualities = request.form.getlist('line_quality[]')
        units = request.form.getlist('line_unit[]')
        quantities = request.form.getlist('line_quantity[]')
        prices = request.form.getlist('line_price_per_unit[]')

        line_count = max(len(qualities), len(units), len(quantities), len(prices))
        line_items = []
        requested_quantities_by_bucket = defaultdict(float)

        for index in range(line_count):
            quality_raw = (qualities[index] if index < len(qualities) else '').strip()
            unit = (units[index] if index < len(units) else '').strip()
            quantity_raw = (quantities[index] if index < len(quantities) else '').strip()
            price_raw = (prices[index] if index < len(prices) else '').strip()

            if not quality_raw and not unit and not quantity_raw and not price_raw:
                continue

            try:
                quantity = _safe_float(quantity_raw)
                price_per_unit = _safe_float(price_raw)
            except (TypeError, ValueError):
                flash(f'بيانات البند رقم {index + 1} غير صحيحة', 'danger')
                return render_template('sales/add.html', crops=crops)

            quality = _normalize_quality(quality_raw)

            if quantity <= 0 or price_per_unit < 0:
                flash(f'الكمية/السعر في البند رقم {index + 1} غير صالحين', 'danger')
                return render_template('sales/add.html', crops=crops)

            if not unit:
                flash(f'الوحدة مطلوبة في البند رقم {index + 1}', 'danger')
                return render_template('sales/add.html', crops=crops)

            subtotal = quantity * price_per_unit
            line_items.append(
                {
                    'quality': quality,
                    'unit': unit,
                    'quantity': quantity,
                    'price_per_unit': price_per_unit,
                    'subtotal': subtotal,
                }
            )
            requested_quantities_by_bucket[(quality, unit)] += quantity

        if not line_items:
            flash('أضف بند بيع واحد على الأقل', 'danger')
            return render_template('sales/add.html', crops=crops)

        stock_map = _build_stock_map(crop_id)
        for (quality, unit), requested_qty in requested_quantities_by_bucket.items():
            stock_data = stock_map.get((quality, unit), {'produced': 0.0, 'sold': 0.0})
            available_qty = float(stock_data.get('produced', 0.0) - stock_data.get('sold', 0.0))
            if requested_qty > available_qty:
                flash(
                    f'الكمية المطلوبة ({requested_qty} {unit}) للجودة {quality} أكبر من المتاح ({round(available_qty, 4)} {unit})',
                    'danger',
                )
                return render_template('sales/add.html', crops=crops)

        invoice_subtotal = sum(item['subtotal'] for item in line_items)
        discount_amount = invoice_subtotal * (discount_percent / 100.0)
        invoice_group_key = _build_invoice_group_key()

        buyer_name = (request.form.get('buyer_name') or '').strip() or None
        buyer_phone = (request.form.get('buyer_phone') or '').strip() or None
        payment_status = request.form.get('payment_status')
        notes = (request.form.get('notes') or '').strip() or None

        created_sales = []
        for item_index, item in enumerate(line_items):
            sale = Sales(
                crop_id=crop_id,
                sale_date=sale_date,
                quantity=item['quantity'],
                unit=item['unit'],
                quality=item['quality'],
                price_per_unit=item['price_per_unit'],
                total_price=item['subtotal'],
                discount_percent=discount_percent if item_index == 0 else 0.0,
                discount_amount=discount_amount if item_index == 0 else 0.0,
                transport_cost=transport_cost if item_index == 0 else 0.0,
                buyer_name=buyer_name,
                buyer_phone=buyer_phone,
                payment_status=payment_status,
                notes=notes,
                invoice_group_key=invoice_group_key,
            )
            db.session.add(sale)
            created_sales.append(sale)

        db.session.commit()

        flash('تم تسجيل البيع في فاتورة واحدة بنجاح', 'success')
        return redirect(url_for('sales.invoice', sale_id=created_sales[0].id))

    return render_template('sales/add.html', crops=crops)


@bp.route('/<int:sale_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_sale(sale_id):
    """تعديل بيع"""
    if not current_user.can_edit and not current_user.is_admin:
        flash('ليس لديك صلاحية التعديل', 'danger')
        return redirect(url_for('sales.index'))

    sale = Sales.query.get_or_404(sale_id)
    crops = Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()

    if request.method == 'POST':
        submitted_token = get_submitted_csrf_token()
        if not validate_csrf_token(submitted_token):
            flash('رمز الأمان غير صالح، يرجى إعادة المحاولة', 'danger')
            return redirect(url_for('sales.edit_sale', sale_id=sale.id))

        try:
            crop_id = request.form.get('crop_id', type=int)
            sale_date = datetime.strptime(request.form.get('sale_date'), '%Y-%m-%d').date()
            quantity = _safe_float(request.form.get('quantity'))
            price_per_unit = _safe_float(request.form.get('price_per_unit'))
            discount_percent = _safe_optional_float(request.form.get('discount_percent'), default=0.0)
            transport_cost = _safe_optional_float(request.form.get('transport_cost'), default=0.0)
            unit = (request.form.get('unit') or '').strip()
            quality = _normalize_quality(request.form.get('quality'))
        except (TypeError, ValueError):
            flash('يرجى إدخال بيانات بيع صحيحة', 'danger')
            return render_template('sales/edit.html', sale=sale, crops=crops)

        if not crop_id:
            flash('يرجى اختيار الصنف', 'danger')
            return render_template('sales/edit.html', sale=sale, crops=crops)

        if quantity <= 0 or price_per_unit < 0:
            flash('الكمية والسعر يجب أن يكونا صالحين', 'danger')
            return render_template('sales/edit.html', sale=sale, crops=crops)

        if not unit:
            flash('الوحدة مطلوبة', 'danger')
            return render_template('sales/edit.html', sale=sale, crops=crops)

        if discount_percent < 0 or discount_percent > 100 or transport_cost < 0:
            flash('نسبة الخصم يجب أن تكون بين 0 و100، والنقل يجب أن يكون صفر أو أكبر', 'danger')
            return render_template('sales/edit.html', sale=sale, crops=crops)

        available_qty = _available_quantity(crop_id, quality, unit, exclude_sale_id=sale.id)
        old_same_bucket = (
            sale.crop_id == crop_id
            and (sale.unit or '').strip() == unit
            and _normalize_quality(getattr(sale, 'quality', None)) == quality
        )
        allowed_qty = available_qty + (float(sale.quantity or 0) if old_same_bucket else 0.0)
        if quantity > allowed_qty:
            flash(
                f'الكمية المطلوبة أكبر من المتاح لهذه الجودة بعد التعديل. المتاح: {allowed_qty} {unit}',
                'danger',
            )
            return render_template('sales/edit.html', sale=sale, crops=crops)

        subtotal = quantity * price_per_unit
        buyer_name = (request.form.get('buyer_name') or '').strip() or None
        buyer_phone = (request.form.get('buyer_phone') or '').strip() or None
        payment_status = request.form.get('payment_status')
        notes = (request.form.get('notes') or '').strip() or None

        group_sales = _load_invoice_sales(sale)
        is_grouped_invoice = bool(sale.invoice_group_key and len(group_sales) > 1)

        sale.crop_id = crop_id
        sale.sale_date = sale_date
        sale.quantity = quantity
        sale.unit = unit
        sale.quality = quality
        sale.price_per_unit = price_per_unit
        sale.total_price = subtotal

        if is_grouped_invoice:
            carrier = next(
                (
                    row for row in group_sales
                    if float(row.discount_percent or 0) > 0
                    or float(row.discount_amount or 0) > 0
                    or float(row.transport_cost or 0) > 0
                ),
                group_sales[0],
            )

            carrier_discount_percent = (
                discount_percent if carrier.id == sale.id else float(carrier.discount_percent or 0)
            )
            carrier_transport_cost = (
                transport_cost if carrier.id == sale.id else float(carrier.transport_cost or 0)
            )

            invoice_subtotal = sum(
                float((subtotal if row.id == sale.id else row.total_price) or 0.0)
                for row in group_sales
            )
            carrier_discount_amount = invoice_subtotal * (carrier_discount_percent / 100.0)

            for row in group_sales:
                row.buyer_name = buyer_name
                row.buyer_phone = buyer_phone
                row.payment_status = payment_status
                row.notes = notes
                if row.id == carrier.id:
                    row.discount_percent = carrier_discount_percent
                    row.discount_amount = carrier_discount_amount
                    row.transport_cost = carrier_transport_cost
                else:
                    row.discount_percent = 0.0
                    row.discount_amount = 0.0
                    row.transport_cost = 0.0
        else:
            discount_amount = subtotal * (discount_percent / 100.0)
            sale.discount_percent = discount_percent
            sale.discount_amount = discount_amount
            sale.transport_cost = transport_cost
            sale.buyer_name = buyer_name
            sale.buyer_phone = buyer_phone
            sale.payment_status = payment_status
            sale.notes = notes

        db.session.commit()
        flash('تم تحديث البيع بنجاح', 'success')
        return redirect(url_for('sales.index'))

    return render_template('sales/edit.html', sale=sale, crops=crops)


@bp.route('/<int:sale_id>/invoice')
@login_required
def invoice(sale_id):
    """عرض فاتورة البيع."""
    if not _can_access_sales() and not current_user.can_manage_reports:
        flash('ليس لديك صلاحية عرض الفاتورة', 'danger')
        return redirect(url_for('home.index'))

    sale = Sales.query.get_or_404(sale_id)
    invoice_sales = _load_invoice_sales(sale)
    anchor_sale = invoice_sales[0] if invoice_sales else sale
    invoice_number = f'INV-{anchor_sale.id:06d}'
    totals = _invoice_totals(invoice_sales)
    return render_template(
        'sales/invoice.html',
        sale=anchor_sale,
        invoice_sales=invoice_sales,
        invoice_number=invoice_number,
        invoice_totals=totals,
    )


@bp.route('/<int:sale_id>/delete', methods=['POST'])
@login_required
def delete_sale(sale_id):
    """حذف بيع"""
    if not current_user.can_delete and not current_user.is_admin:
        flash('ليس لديك صلاحية الحذف', 'danger')
        return redirect(url_for('sales.index'))

    sale = Sales.query.get_or_404(sale_id)
    grouped_rows = _load_invoice_sales(sale)

    if sale.invoice_group_key and len(grouped_rows) > 1:
        carries_invoice_adjustments = bool(
            float(sale.discount_percent or 0) > 0
            or float(sale.discount_amount or 0) > 0
            or float(sale.transport_cost or 0) > 0
        )
        if carries_invoice_adjustments:
            replacement = next((row for row in grouped_rows if row.id != sale.id), None)
            if replacement:
                replacement.discount_percent = float(sale.discount_percent or 0.0)
                replacement.discount_amount = float(sale.discount_amount or 0.0)
                replacement.transport_cost = float(sale.transport_cost or 0.0)

    db.session.delete(sale)
    db.session.commit()

    flash('تم حذف البيع', 'success')
    return redirect(url_for('sales.index'))
