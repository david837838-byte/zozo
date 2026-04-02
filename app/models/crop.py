from app import db
from datetime import datetime
from sqlalchemy import UniqueConstraint

class Crop(db.Model):
    """نموذج الصنف (فواكه وخضروات)"""
    __table_args__ = (
        UniqueConstraint('name', 'variety', name='uix_crop_name_variety'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # فواكه أو خضروات
    variety = db.Column(db.String(120), nullable=True)  # الصنف
    planting_date = db.Column(db.Date, nullable=True)
    expected_harvest_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(120), nullable=True)  # موقع الزراعة
    area = db.Column(db.Float, nullable=True)  # المساحة
    unit = db.Column(db.String(50), default='متر مربع')
    
    # متقدم - معلومات الصحة والإنتاجية
    health_status = db.Column(db.String(50), default='جيدة')  # جيدة، متوسطة، حرجة
    irrigation_frequency = db.Column(db.String(50), nullable=True)  # يومي، كل يومين، إلخ
    soil_type = db.Column(db.String(50), nullable=True)  # نوع التربة
    expected_yield = db.Column(db.Float, nullable=True)  # الإنتاج المتوقع
    estimated_market_price = db.Column(db.Float, nullable=True)  # السعر المتوقع
    
    # Relations
    consumptions = db.relationship('CropConsumption', backref='crop', lazy=True, cascade='all, delete-orphan')
    productions = db.relationship('Production', backref='crop', lazy=True, cascade='all, delete-orphan')
    sales = db.relationship('Sales', backref='crop', lazy=True, cascade='all, delete-orphan')
    health_records = db.relationship('CropHealth', backref='crop', lazy=True, cascade='all, delete-orphan')
    production_batches = db.relationship('ProductionBatch', backref='crop', lazy=True, cascade='all, delete-orphan')
    production_costs = db.relationship('ProductionCost', backref='crop', lazy=True, cascade='all, delete-orphan')
    production_stages = db.relationship('ProductionStage', backref='crop', lazy=True, cascade='all, delete-orphan')
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_total_production(self):
        """إجمالي الإنتاج"""
        return sum([p.quantity or 0 for p in self.productions])
    
    def get_total_sales(self):
        """إجمالي المبيعات"""
        return sum([s.total_price or 0 for s in self.sales])
    
    def get_total_costs(self):
        """إجمالي التكاليف"""
        return sum([c.total_cost or 0 for c in self.production_costs])
    
    def get_profitability(self):
        """الربحية"""
        return self.get_total_sales() - self.get_total_costs()
    
    def get_productivity(self):
        """الإنتاجية (الإنتاج بالنسبة للمساحة)"""
        if self.area and self.area > 0:
            return self.get_total_production() / self.area
        return 0
    
    def __repr__(self):
        return f'<Crop {self.name}>'

class CropConsumption(db.Model):
    """نموذج استهلاك الأدوية والأسمدة على الأصناف"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    quantity_used = db.Column(db.Float, nullable=False)
    consumption_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    
    # Relations
    inventory_item = db.relationship('InventoryItem', viewonly=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CropConsumption {self.crop.name}>'

class Production(db.Model):
    """نموذج الإنتاج"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    production_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)  # كيس، صندوق، لتر، إلخ
    quality = db.Column(db.String(50), nullable=True)  # جودة الإنتاج
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Production {self.crop.name}>'

class Sales(db.Model):
    """نموذج المبيعات"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    sale_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    buyer_name = db.Column(db.String(120), nullable=True)
    buyer_phone = db.Column(db.String(20), nullable=True)
    payment_status = db.Column(db.String(50), default='مدفوع')  # مدفوع أو غير مدفوع
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Sales {self.crop.name}>'

class CropHealth(db.Model):
    """نموذج تتبع صحة الصنف والأمراض"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    health_date = db.Column(db.Date, nullable=False)
    health_status = db.Column(db.String(50), nullable=False)  # جيدة، متوسطة، حرجة
    disease_name = db.Column(db.String(120), nullable=True)  # اسم المرض إن وجد
    pest_name = db.Column(db.String(120), nullable=True)  # اسم الآفة إن وجدت
    treatment_applied = db.Column(db.Text, nullable=True)  # العلاج المطبق
    severity_percentage = db.Column(db.Float, default=0.0)  # نسبة الإصابة
    recovery_estimated_days = db.Column(db.Integer, nullable=True)  # أيام الشفاء المتوقعة
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<CropHealth {self.crop.name}>'

class ProductionBatch(db.Model):
    """نموذج دفعات الإنتاج (المحاصيل)"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    batch_number = db.Column(db.String(50), nullable=False, unique=True)
    planting_date = db.Column(db.Date, nullable=False)
    expected_harvest_date = db.Column(db.Date, nullable=True)
    actual_harvest_date = db.Column(db.Date, nullable=True)
    area_used = db.Column(db.Float, nullable=True)
    soil_preparation_cost = db.Column(db.Float, default=0.0)
    seeds_cost = db.Column(db.Float, default=0.0)
    fertilizers_cost = db.Column(db.Float, default=0.0)
    pesticides_cost = db.Column(db.Float, default=0.0)
    labor_cost = db.Column(db.Float, default=0.0)
    watering_cost = db.Column(db.Float, default=0.0)
    other_costs = db.Column(db.Float, default=0.0)
    batch_status = db.Column(db.String(50), default='جارية')  # جارية، محصودة، مكتملة
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_total_costs(self):
        """إجمالي التكاليف"""
        return (self.soil_preparation_cost + self.seeds_cost + self.fertilizers_cost + 
                self.pesticides_cost + self.labor_cost + self.watering_cost + self.other_costs)
    
    def get_cost_per_area(self):
        """التكلفة بالنسبة للمساحة"""
        if self.area_used and self.area_used > 0:
            return self.get_total_costs() / self.area_used
        return 0
    
    def __repr__(self):
        return f'<ProductionBatch {self.batch_number}>'

class ProductionCost(db.Model):
    """نموذج تتبع تكاليف الإنتاج"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    cost_date = db.Column(db.Date, nullable=False)
    cost_type = db.Column(db.String(50), nullable=False)  # تجهيز التربة، بذور، أسمدة، مبيدات، عمالة، كهرباء/ماء، أخرى
    cost_category = db.Column(db.String(50), nullable=False)  # تصنيف التكلفة
    description = db.Column(db.String(200), nullable=True)
    quantity = db.Column(db.Float, nullable=True)
    unit_cost = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    reference_number = db.Column(db.String(50), nullable=True)  # رقم الفاتورة أو المرجع
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProductionCost {self.cost_type}>'

class ProductionStage(db.Model):
    """نموذج مراحل الإنتاج والنمو"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    stage_name = db.Column(db.String(120), nullable=False)  # التشريق، النمو الخضري، التزهير، العقد، النضج
    stage_order = db.Column(db.Integer, nullable=False)  # ترتيب المرحلة
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    expected_duration_days = db.Column(db.Integer, nullable=True)  # المدة المتوقعة بالأيام
    description = db.Column(db.Text, nullable=True)
    required_actions = db.Column(db.Text, nullable=True)  # الإجراءات المطلوبة
    is_completed = db.Column(db.Boolean, default=False)
    completion_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_duration(self):
        """المدة الفعلية"""
        if self.end_date:
            return (self.end_date - self.start_date).days
        return (datetime.utcnow().date() - self.start_date).days
    
    def __repr__(self):
        return f'<ProductionStage {self.stage_name}>'

class ProductionInventory(db.Model):
    """نموذج مخزن الإنتاج (المنتجات المخزنة)"""
    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    production_id = db.Column(db.Integer, db.ForeignKey('production.id'), nullable=True)
    storage_location = db.Column(db.String(120), nullable=True)  # موقع التخزين
    quantity = db.Column(db.Float, nullable=False)  # الكمية المتبقية
    unit = db.Column(db.String(50), nullable=False)
    quality = db.Column(db.String(50), nullable=True)
    packaging_type = db.Column(db.String(50), nullable=True)  # نوع التعبئة
    storage_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    temperature = db.Column(db.Float, nullable=True)  # درجة الحرارة المطلوبة
    humidity_level = db.Column(db.Float, nullable=True)  # نسبة الرطوبة المطلوبة
    storage_cost = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='متاح')  # متاح، مباع، تالف، منتهي الصلاحية
    notes = db.Column(db.Text, nullable=True)
    
    # Relation
    production = db.relationship('Production')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProductionInventory {self.crop.name}>'
