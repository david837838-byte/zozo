from app import db
from datetime import datetime

class InventoryItem(db.Model):
    """نموذج عنصر المخزون (الأدوية والأسمدة والمشتقات النفطية)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)  # اسم المنتج
    category = db.Column(db.String(50), nullable=False)  # أدوية أو أسمدة أو مشتقات نفطية
    quantity = db.Column(db.Float, nullable=False)  # الكمية
    unit = db.Column(db.String(50), nullable=False)  # الوحدة (كيس، لتر، إلخ)
    purchase_price = db.Column(db.Float, nullable=False)
    supplier = db.Column(db.String(120), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Relations
    transactions = db.relationship('InventoryTransaction', backref='item', lazy=True, cascade='all, delete-orphan')
    consumptions = db.relationship('CropConsumption', lazy=True, overlaps='inventory_item')
    general_consumptions = db.relationship('GeneralConsumption', lazy=True, cascade='all, delete-orphan', overlaps='inventory_item')
    purchases = db.relationship('InventoryPurchase', backref='item', lazy=True, cascade='all, delete-orphan')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<InventoryItem {self.name}>'

class InventoryTransaction(db.Model):
    """نموذج معاملات المخزون"""
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)  # دخول أو خروج
    quantity = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<InventoryTransaction {self.item.name} - {self.transaction_type}>'

class GeneralConsumption(db.Model):
    """نموذج استهلاك الأدوية والأسمدة والمشتقات النفطية"""
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    quantity_used = db.Column(db.Float, nullable=False)
    consumption_type = db.Column(db.String(50), nullable=False)  # نوع الاستهلاك
    consumption_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    
    # Relations
    inventory_item = db.relationship('InventoryItem', viewonly=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<GeneralConsumption {self.inventory_item.name}>'

class InventoryPurchase(db.Model):
    """نموذج شراء عناصر المخزون (الأدوية والأسمدة والمشتقات النفطية)"""
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)  # كمية الشراء
    unit_price = db.Column(db.Float, nullable=False)  # سعر الوحدة
    purchase_date = db.Column(db.Date, nullable=False)  # تاريخ الشراء
    supplier = db.Column(db.String(120), nullable=True)  # الموردة
    invoice_number = db.Column(db.String(50), nullable=True)  # رقم الفاتورة
    total_cost = db.Column(db.Float, default=0.0)  # التكلفة الإجمالية
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def calculate_total_cost(self):
        """حساب التكلفة الإجمالية"""
        self.total_cost = self.quantity * self.unit_price
        return self.total_cost
    
    def __repr__(self):
        return f'<InventoryPurchase {self.item.name} - {self.quantity}>'
