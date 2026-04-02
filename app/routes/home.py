from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models.accounting import EXPENSE_TRANSACTION_TYPE_ALIASES, Transaction
from app.models.worker import Worker
from app.models.crop import Crop, CropConsumption, Production, Sales
from app.models.inventory import GeneralConsumption, InventoryItem

bp = Blueprint('home', __name__)


@bp.route('/')
def index():
    """Landing page."""
    return render_template('index.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with real summary metrics."""
    def _resolve_dashboard_range(raw_value):
        today = date.today()
        value = (raw_value or 'month').strip().lower()

        if value == 'today':
            return value, today, today, 'اليوم'
        if value == 'quarter':
            start = today - timedelta(days=89)
            return value, start, today, 'آخر 3 أشهر'
        if value == 'year':
            start = date(today.year, 1, 1)
            return value, start, today, 'هذه السنة'
        if value == 'all':
            return value, None, None, 'كل الفترات'

        start = date(today.year, today.month, 1)
        return 'month', start, today, 'هذا الشهر'

    def _apply_date_range(query, column, from_date, to_date):
        if from_date:
            query = query.filter(column >= from_date)
        if to_date:
            query = query.filter(column <= to_date)
        return query

    def _build_consumption_chart_data(category_name, from_date, to_date, limit=10):
        chart_map = {}

        general_query = (
            db.session.query(
                InventoryItem.id.label('item_id'),
                InventoryItem.name.label('item_name'),
                func.coalesce(func.sum(GeneralConsumption.quantity_used), 0).label('used_qty'),
                func.coalesce(
                    func.sum(GeneralConsumption.quantity_used * InventoryItem.purchase_price), 0
                ).label('used_cost'),
            )
            .join(InventoryItem, InventoryItem.id == GeneralConsumption.inventory_item_id)
            .filter(InventoryItem.category == category_name)
        )
        general_query = _apply_date_range(
            general_query,
            GeneralConsumption.consumption_date,
            from_date,
            to_date,
        )
        general_rows = (
            general_query.group_by(InventoryItem.id, InventoryItem.name)
            .all()
        )

        crop_query = (
            db.session.query(
                InventoryItem.id.label('item_id'),
                InventoryItem.name.label('item_name'),
                func.coalesce(func.sum(CropConsumption.quantity_used), 0).label('used_qty'),
                func.coalesce(
                    func.sum(CropConsumption.quantity_used * InventoryItem.purchase_price), 0
                ).label('used_cost'),
            )
            .join(InventoryItem, InventoryItem.id == CropConsumption.inventory_item_id)
            .filter(InventoryItem.category == category_name)
        )
        crop_query = _apply_date_range(
            crop_query,
            CropConsumption.consumption_date,
            from_date,
            to_date,
        )
        crop_rows = (
            crop_query.group_by(InventoryItem.id, InventoryItem.name)
            .all()
        )

        for row in general_rows + crop_rows:
            item_payload = chart_map.setdefault(
                row.item_id,
                {
                    'item_name': row.item_name,
                    'used_qty': 0.0,
                    'used_cost': 0.0,
                },
            )
            item_payload['used_qty'] += float(row.used_qty or 0.0)
            item_payload['used_cost'] += float(row.used_cost or 0.0)

        ranked_items = sorted(
            chart_map.values(),
            key=lambda item: item['used_qty'],
            reverse=True,
        )[:limit]

        return (
            [item['item_name'] for item in ranked_items],
            [round(item['used_qty'], 2) for item in ranked_items],
            [round(item['used_cost'], 2) for item in ranked_items],
        )

    selected_range, from_date, to_date, date_range_label = _resolve_dashboard_range(
        request.args.get('range')
    )

    workers_count = Worker.query.filter_by(is_active=True).count()
    crops_count = Crop.query.filter_by(is_active=True).count()
    inventory_count = InventoryItem.query.count()

    sales_query = _apply_date_range(Sales.query, Sales.sale_date, from_date, to_date)
    production_query = _apply_date_range(Production.query, Production.production_date, from_date, to_date)
    expenses_query = _apply_date_range(
        Transaction.query.filter(Transaction.transaction_type.in_(EXPENSE_TRANSACTION_TYPE_ALIASES)),
        Transaction.transaction_date,
        from_date,
        to_date,
    )

    total_sales = (
        sales_query.with_entities(func.coalesce(func.sum(Sales.total_price), 0)).scalar() or 0
    )
    total_costs = (
        expenses_query.with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar() or 0
    )
    net_profit = float(total_sales or 0) - float(total_costs or 0)

    production_rows = (
        production_query.join(Crop, Crop.id == Production.crop_id).with_entities(
            Crop.name.label('crop_name'),
            func.coalesce(func.sum(Production.quantity), 0).label('total_quantity'),
        )
        .group_by(Crop.name)
        .order_by(func.coalesce(func.sum(Production.quantity), 0).desc())
        .limit(10)
        .all()
    )
    production_chart_labels = [row.crop_name for row in production_rows]
    production_chart_values = [float(row.total_quantity or 0) for row in production_rows]

    sales_rows = (
        sales_query.join(Crop, Crop.id == Sales.crop_id).with_entities(
            Crop.name.label('crop_name'),
            func.coalesce(func.sum(Sales.total_price), 0).label('total_sales'),
        )
        .group_by(Crop.name)
        .order_by(func.coalesce(func.sum(Sales.total_price), 0).desc())
        .limit(10)
        .all()
    )
    sales_chart_labels = [row.crop_name for row in sales_rows]
    sales_chart_values = [float(row.total_sales or 0) for row in sales_rows]

    (
        medicine_chart_labels,
        medicine_chart_qty_values,
        medicine_chart_cost_values,
    ) = _build_consumption_chart_data('أدوية', from_date, to_date)
    (
        fertilizer_chart_labels,
        fertilizer_chart_qty_values,
        fertilizer_chart_cost_values,
    ) = _build_consumption_chart_data('أسمدة', from_date, to_date)

    today = date.today()
    expiring_limit_date = today + timedelta(days=30)
    out_of_stock_count = InventoryItem.query.filter(InventoryItem.quantity <= 0).count()
    low_stock_count = InventoryItem.query.filter(
        InventoryItem.quantity > 0,
        InventoryItem.quantity <= 10,
    ).count()
    expiring_soon_count = InventoryItem.query.filter(
        InventoryItem.expiry_date.isnot(None),
        InventoryItem.expiry_date >= today,
        InventoryItem.expiry_date <= expiring_limit_date,
    ).count()

    out_of_stock_items = (
        InventoryItem.query.filter(InventoryItem.quantity <= 0)
        .order_by(InventoryItem.name.asc())
        .limit(8)
        .all()
    )
    low_stock_items = (
        InventoryItem.query.filter(
            InventoryItem.quantity > 0,
            InventoryItem.quantity <= 10,
        )
        .order_by(InventoryItem.quantity.asc(), InventoryItem.name.asc())
        .limit(8)
        .all()
    )
    expiring_soon_items = (
        InventoryItem.query.filter(
            InventoryItem.expiry_date.isnot(None),
            InventoryItem.expiry_date >= today,
            InventoryItem.expiry_date <= expiring_limit_date,
        )
        .order_by(InventoryItem.expiry_date.asc(), InventoryItem.name.asc())
        .limit(8)
        .all()
    )

    return render_template(
        'dashboard.html',
        workers_count=workers_count,
        crops_count=crops_count,
        inventory_count=inventory_count,
        total_sales=total_sales,
        total_costs=total_costs,
        net_profit=net_profit,
        selected_range=selected_range,
        date_range_label=date_range_label,
        production_chart_labels=production_chart_labels,
        production_chart_values=production_chart_values,
        sales_chart_labels=sales_chart_labels,
        sales_chart_values=sales_chart_values,
        medicine_chart_labels=medicine_chart_labels,
        medicine_chart_qty_values=medicine_chart_qty_values,
        medicine_chart_cost_values=medicine_chart_cost_values,
        fertilizer_chart_labels=fertilizer_chart_labels,
        fertilizer_chart_qty_values=fertilizer_chart_qty_values,
        fertilizer_chart_cost_values=fertilizer_chart_cost_values,
        out_of_stock_count=out_of_stock_count,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        out_of_stock_items=out_of_stock_items,
        low_stock_items=low_stock_items,
        expiring_soon_items=expiring_soon_items,
    )
