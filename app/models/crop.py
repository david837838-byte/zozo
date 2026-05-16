from app import db
from datetime import datetime
from sqlalchemy import UniqueConstraint

class Crop(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ Ø§Ù„ØµÙ†Ù (ÙÙˆØ§ÙƒÙ‡ ÙˆØ®Ø¶Ø±ÙˆØ§Øª)"""
    __table_args__ = (
        UniqueConstraint('name', 'variety', name='uix_crop_name_variety'),
    )
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # ÙÙˆØ§ÙƒÙ‡ Ø£Ùˆ Ø®Ø¶Ø±ÙˆØ§Øª
    variety = db.Column(db.String(120), nullable=True)  # Ø§Ù„ØµÙ†Ù
    planting_date = db.Column(db.Date, nullable=True)
    expected_harvest_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(120), nullable=True)  # Ù…ÙˆÙ‚Ø¹ Ø§Ù„Ø²Ø±Ø§Ø¹Ø©
    area = db.Column(db.Float, nullable=True)  # Ø§Ù„Ù…Ø³Ø§Ø­Ø©
    unit = db.Column(db.String(50), default='Ù…ØªØ± Ù…Ø±Ø¨Ø¹')
    
    # Ù…ØªÙ‚Ø¯Ù… - Ù…Ø¹Ù„ÙˆÙ…Ø§Øª Ø§Ù„ØµØ­Ø© ÙˆØ§Ù„Ø¥Ù†ØªØ§Ø¬ÙŠØ©
    health_status = db.Column(db.String(50), default='Ø¬ÙŠØ¯Ø©')  # Ø¬ÙŠØ¯Ø©ØŒ Ù…ØªÙˆØ³Ø·Ø©ØŒ Ø­Ø±Ø¬Ø©
    irrigation_frequency = db.Column(db.String(50), nullable=True)  # ÙŠÙˆÙ…ÙŠØŒ ÙƒÙ„ ÙŠÙˆÙ…ÙŠÙ†ØŒ Ø¥Ù„Ø®
    soil_type = db.Column(db.String(50), nullable=True)  # Ù†ÙˆØ¹ Ø§Ù„ØªØ±Ø¨Ø©
    expected_yield = db.Column(db.Float, nullable=True)  # Ø§Ù„Ø¥Ù†ØªØ§Ø¬ Ø§Ù„Ù…ØªÙˆÙ‚Ø¹
    estimated_market_price = db.Column(db.Float, nullable=True)  # Ø§Ù„Ø³Ø¹Ø± Ø§Ù„Ù…ØªÙˆÙ‚Ø¹
    
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
        """Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø¥Ù†ØªØ§Ø¬"""
        return sum([p.quantity or 0 for p in self.productions])
    
    def get_total_sales(self):
        """Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ù…Ø¨ÙŠØ¹Ø§Øª"""
        return sum([s.total_price or 0 for s in self.sales])
    
    def get_total_costs(self):
        """Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„ØªÙƒØ§Ù„ÙŠÙ"""
        return sum([c.total_cost or 0 for c in self.production_costs])
    
    def get_profitability(self):
        """Ø§Ù„Ø±Ø¨Ø­ÙŠØ©"""
        return self.get_total_sales() - self.get_total_costs()
    
    def get_productivity(self):
        """Ø§Ù„Ø¥Ù†ØªØ§Ø¬ÙŠØ© (Ø§Ù„Ø¥Ù†ØªØ§Ø¬ Ø¨Ø§Ù„Ù†Ø³Ø¨Ø© Ù„Ù„Ù…Ø³Ø§Ø­Ø©)"""
        if self.area and self.area > 0:
            return self.get_total_production() / self.area
        return 0
    
    def __repr__(self):
        return f'<Crop {self.name}>'

class CropConsumption(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ Ø§Ø³ØªÙ‡Ù„Ø§Ùƒ Ø§Ù„Ø£Ø¯ÙˆÙŠØ© ÙˆØ§Ù„Ø£Ø³Ù…Ø¯Ø© Ø¹Ù„Ù‰ Ø§Ù„Ø£ØµÙ†Ø§Ù"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
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
    """Ù†Ù…ÙˆØ°Ø¬ Ø§Ù„Ø¥Ù†ØªØ§Ø¬"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    production_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)  # ÙƒÙŠØ³ØŒ ØµÙ†Ø¯ÙˆÙ‚ØŒ Ù„ØªØ±ØŒ Ø¥Ù„Ø®
    quality = db.Column(db.String(50), nullable=True)  # Ø¬ÙˆØ¯Ø© Ø§Ù„Ø¥Ù†ØªØ§Ø¬
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Production {self.crop.name}>'

class Sales(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ Ø§Ù„Ù…Ø¨ÙŠØ¹Ø§Øª"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    sale_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    quality = db.Column(db.String(50), nullable=False, default='Ù…ØªÙˆØ³Ø·Ø©')
    invoice_group_key = db.Column(db.String(64), nullable=True, index=True)
    price_per_unit = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)  # Subtotal before discount/transport
    discount_percent = db.Column(db.Float, nullable=False, default=0.0)
    discount_amount = db.Column(db.Float, nullable=False, default=0.0)
    transport_cost = db.Column(db.Float, nullable=False, default=0.0)
    buyer_name = db.Column(db.String(120), nullable=True)
    buyer_phone = db.Column(db.String(20), nullable=True)
    payment_status = db.Column(db.String(50), default='Ù…Ø¯ÙÙˆØ¹')  # Ù…Ø¯ÙÙˆØ¹ Ø£Ùˆ ØºÙŠØ± Ù…Ø¯ÙÙˆØ¹
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def subtotal(self):
        return float(self.total_price or 0.0)

    def net_total(self):
        return float(self.subtotal() - float(self.discount_amount or 0.0) - float(self.transport_cost or 0.0))

    def __repr__(self):
        return f'<Sales {self.crop.name}>'

class CropHealth(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ ØªØªØ¨Ø¹ ØµØ­Ø© Ø§Ù„ØµÙ†Ù ÙˆØ§Ù„Ø£Ù…Ø±Ø§Ø¶"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    health_date = db.Column(db.Date, nullable=False)
    health_status = db.Column(db.String(50), nullable=False)  # Ø¬ÙŠØ¯Ø©ØŒ Ù…ØªÙˆØ³Ø·Ø©ØŒ Ø­Ø±Ø¬Ø©
    disease_name = db.Column(db.String(120), nullable=True)  # Ø§Ø³Ù… Ø§Ù„Ù…Ø±Ø¶ Ø¥Ù† ÙˆØ¬Ø¯
    pest_name = db.Column(db.String(120), nullable=True)  # Ø§Ø³Ù… Ø§Ù„Ø¢ÙØ© Ø¥Ù† ÙˆØ¬Ø¯Øª
    treatment_applied = db.Column(db.Text, nullable=True)  # Ø§Ù„Ø¹Ù„Ø§Ø¬ Ø§Ù„Ù…Ø·Ø¨Ù‚
    severity_percentage = db.Column(db.Float, default=0.0)  # Ù†Ø³Ø¨Ø© Ø§Ù„Ø¥ØµØ§Ø¨Ø©
    recovery_estimated_days = db.Column(db.Integer, nullable=True)  # Ø£ÙŠØ§Ù… Ø§Ù„Ø´ÙØ§Ø¡ Ø§Ù„Ù…ØªÙˆÙ‚Ø¹Ø©
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<CropHealth {self.crop.name}>'

class ProductionBatch(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ Ø¯ÙØ¹Ø§Øª Ø§Ù„Ø¥Ù†ØªØ§Ø¬ (Ø§Ù„Ù…Ø­Ø§ØµÙŠÙ„)"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
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
    batch_status = db.Column(db.String(50), default='Ø¬Ø§Ø±ÙŠØ©')  # Ø¬Ø§Ø±ÙŠØ©ØŒ Ù…Ø­ØµÙˆØ¯Ø©ØŒ Ù…ÙƒØªÙ…Ù„Ø©
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_total_costs(self):
        """Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„ØªÙƒØ§Ù„ÙŠÙ"""
        return (self.soil_preparation_cost + self.seeds_cost + self.fertilizers_cost + 
                self.pesticides_cost + self.labor_cost + self.watering_cost + self.other_costs)
    
    def get_cost_per_area(self):
        """Ø§Ù„ØªÙƒÙ„ÙØ© Ø¨Ø§Ù„Ù†Ø³Ø¨Ø© Ù„Ù„Ù…Ø³Ø§Ø­Ø©"""
        if self.area_used and self.area_used > 0:
            return self.get_total_costs() / self.area_used
        return 0
    
    def __repr__(self):
        return f'<ProductionBatch {self.batch_number}>'

class ProductionCost(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ ØªØªØ¨Ø¹ ØªÙƒØ§Ù„ÙŠÙ Ø§Ù„Ø¥Ù†ØªØ§Ø¬"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    cost_date = db.Column(db.Date, nullable=False)
    cost_type = db.Column(db.String(50), nullable=False)  # ØªØ¬Ù‡ÙŠØ² Ø§Ù„ØªØ±Ø¨Ø©ØŒ Ø¨Ø°ÙˆØ±ØŒ Ø£Ø³Ù…Ø¯Ø©ØŒ Ù…Ø¨ÙŠØ¯Ø§ØªØŒ Ø¹Ù…Ø§Ù„Ø©ØŒ ÙƒÙ‡Ø±Ø¨Ø§Ø¡/Ù…Ø§Ø¡ØŒ Ø£Ø®Ø±Ù‰
    cost_category = db.Column(db.String(50), nullable=False)  # ØªØµÙ†ÙŠÙ Ø§Ù„ØªÙƒÙ„ÙØ©
    description = db.Column(db.String(200), nullable=True)
    quantity = db.Column(db.Float, nullable=True)
    unit_cost = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    reference_number = db.Column(db.String(50), nullable=True)  # Ø±Ù‚Ù… Ø§Ù„ÙØ§ØªÙˆØ±Ø© Ø£Ùˆ Ø§Ù„Ù…Ø±Ø¬Ø¹
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProductionCost {self.cost_type}>'

class ProductionStage(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ Ù…Ø±Ø§Ø­Ù„ Ø§Ù„Ø¥Ù†ØªØ§Ø¬ ÙˆØ§Ù„Ù†Ù…Ùˆ"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    stage_name = db.Column(db.String(120), nullable=False)  # Ø§Ù„ØªØ´Ø±ÙŠÙ‚ØŒ Ø§Ù„Ù†Ù…Ùˆ Ø§Ù„Ø®Ø¶Ø±ÙŠØŒ Ø§Ù„ØªØ²Ù‡ÙŠØ±ØŒ Ø§Ù„Ø¹Ù‚Ø¯ØŒ Ø§Ù„Ù†Ø¶Ø¬
    stage_order = db.Column(db.Integer, nullable=False)  # ØªØ±ØªÙŠØ¨ Ø§Ù„Ù…Ø±Ø­Ù„Ø©
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    expected_duration_days = db.Column(db.Integer, nullable=True)  # Ø§Ù„Ù…Ø¯Ø© Ø§Ù„Ù…ØªÙˆÙ‚Ø¹Ø© Ø¨Ø§Ù„Ø£ÙŠØ§Ù…
    description = db.Column(db.Text, nullable=True)
    required_actions = db.Column(db.Text, nullable=True)  # Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª Ø§Ù„Ù…Ø·Ù„ÙˆØ¨Ø©
    is_completed = db.Column(db.Boolean, default=False)
    completion_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_duration(self):
        """Ø§Ù„Ù…Ø¯Ø© Ø§Ù„ÙØ¹Ù„ÙŠØ©"""
        if self.end_date:
            return (self.end_date - self.start_date).days
        return (datetime.utcnow().date() - self.start_date).days
    
    def __repr__(self):
        return f'<ProductionStage {self.stage_name}>'

class ProductionInventory(db.Model):
    """Ù†Ù…ÙˆØ°Ø¬ Ù…Ø®Ø²Ù† Ø§Ù„Ø¥Ù†ØªØ§Ø¬ (Ø§Ù„Ù…Ù†ØªØ¬Ø§Øª Ø§Ù„Ù…Ø®Ø²Ù†Ø©)"""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True, index=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    production_id = db.Column(db.Integer, db.ForeignKey('production.id'), nullable=True)
    storage_location = db.Column(db.String(120), nullable=True)  # Ù…ÙˆÙ‚Ø¹ Ø§Ù„ØªØ®Ø²ÙŠÙ†
    quantity = db.Column(db.Float, nullable=False)  # Ø§Ù„ÙƒÙ…ÙŠØ© Ø§Ù„Ù…ØªØ¨Ù‚ÙŠØ©
    unit = db.Column(db.String(50), nullable=False)
    quality = db.Column(db.String(50), nullable=True)
    packaging_type = db.Column(db.String(50), nullable=True)  # Ù†ÙˆØ¹ Ø§Ù„ØªØ¹Ø¨Ø¦Ø©
    storage_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    temperature = db.Column(db.Float, nullable=True)  # Ø¯Ø±Ø¬Ø© Ø§Ù„Ø­Ø±Ø§Ø±Ø© Ø§Ù„Ù…Ø·Ù„ÙˆØ¨Ø©
    humidity_level = db.Column(db.Float, nullable=True)  # Ù†Ø³Ø¨Ø© Ø§Ù„Ø±Ø·ÙˆØ¨Ø© Ø§Ù„Ù…Ø·Ù„ÙˆØ¨Ø©
    storage_cost = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='Ù…ØªØ§Ø­')  # Ù…ØªØ§Ø­ØŒ Ù…Ø¨Ø§Ø¹ØŒ ØªØ§Ù„ÙØŒ Ù…Ù†ØªÙ‡ÙŠ Ø§Ù„ØµÙ„Ø§Ø­ÙŠØ©
    notes = db.Column(db.Text, nullable=True)
    
    # Relation
    production = db.relationship('Production')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProductionInventory {self.crop.name}>'
