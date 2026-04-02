from app import db
from datetime import datetime

class BoxType(db.Model):
    """نموذج أنواع الشراحات والكراتين"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    box_type = db.Column(db.String(50), nullable=False)  # كبير، صغير، نصفي، فريز، قرقوز
    capacity = db.Column(db.Float, nullable=True)  # سعة الصندوق
    unit = db.Column(db.String(50), nullable=True)
    cost_per_box = db.Column(db.Float, nullable=False)
    supplier = db.Column(db.String(120), nullable=True)
    
    # Relations
    usages = db.relationship('BoxUsage', backref='box_type', lazy=True, cascade='all, delete-orphan')
    purchases = db.relationship('BoxPurchase', backref='box_type', lazy=True, cascade='all, delete-orphan')
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<BoxType {self.name}>'

class BoxUsage(db.Model):
    """نموذج استخدام الشراحات والكراتين"""
    id = db.Column(db.Integer, primary_key=True)
    box_type_id = db.Column(db.Integer, db.ForeignKey('box_type.id'), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False)
    usage_date = db.Column(db.Date, nullable=False)
    purpose = db.Column(db.Text, nullable=True)  # الغرض من الاستخدام
    
    # Cost calculation
    total_cost = db.Column(db.Float, default=0.0)
    
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def calculate_cost(self):
        """حساب التكلفة الإجمالية"""
        self.total_cost = self.quantity_used * self.box_type.cost_per_box
        return self.total_cost
    
    def __repr__(self):
        return f'<BoxUsage {self.box_type.name}>'

class BoxPurchase(db.Model):
    """نموذج شراء الشراحات والكراتين"""
    id = db.Column(db.Integer, primary_key=True)
    box_type_id = db.Column(db.Integer, db.ForeignKey('box_type.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)  # عدد الوحدات المشتراة
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
        return f'<BoxPurchase {self.box_type.name} - {self.quantity}>'
