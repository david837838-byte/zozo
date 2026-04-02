"""
نموذج المحركات وتسجيل الاستخدام
Motors and Usage Tracking Models
"""

from datetime import datetime
from app import db


class Motor(db.Model):
    """
    نموذج المحرك
    موديل المحركات الرئيسية المستخدمة في المزرعة
    """
    __tablename__ = 'motors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)  # اسم المحرك
    motor_type = db.Column(db.String(50), nullable=False)  # نوع المحرك (ديزل، بنزين، كهربائي)
    model = db.Column(db.String(100))  # موديل المحرك
    serial_number = db.Column(db.String(100), unique=True)  # رقم المحرك التسلسلي
    purchase_date = db.Column(db.Date)  # تاريخ الشراء
    capacity = db.Column(db.Float)  # القوة (HP)
    description = db.Column(db.Text)  # وصف المحرك
    location = db.Column(db.String(100))  # موقع المحرك
    is_active = db.Column(db.Boolean, default=True, index=True)  # هل المحرك نشط
    
    # العلاقات
    usage_logs = db.relationship('MotorUsage', backref='motor', lazy='dynamic', cascade='all, delete-orphan')
    
    # الطوابع الزمنية
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Motor {self.name}>'
    
    def to_dict(self):
        """تحويل النموذج إلى قاموس"""
        return {
            'id': self.id,
            'name': self.name,
            'motor_type': self.motor_type,
            'model': self.model,
            'serial_number': self.serial_number,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'capacity': self.capacity,
            'description': self.description,
            'location': self.location,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class OperatorQuota(db.Model):
    """
    نموذج حصة ساعات المشغل السنوية
    تحديد الحد الأقصى من الساعات لكل مشغل في السنة
    """
    __tablename__ = 'operator_quotas'
    
    id = db.Column(db.Integer, primary_key=True)
    operator_name = db.Column(db.String(100), nullable=False, index=True)  # اسم المشغل
    year = db.Column(db.Integer, nullable=False, index=True)  # السنة
    allocated_hours = db.Column(db.Float, nullable=False, default=0)  # عدد الساعات المخصصة
    used_hours = db.Column(db.Float, default=0)  # عدد الساعات المستخدمة
    remaining_hours = db.Column(db.Float, default=0)  # الساعات المتبقية
    status = db.Column(db.String(20), default='نشط')  # الحالة (نشط، مجمد، معطل)
    notes = db.Column(db.Text)  # ملاحظات
    
    # الطوابع الزمنية
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('operator_name', 'year', name='uq_operator_year'),)
    
    def __repr__(self):
        return f'<OperatorQuota {self.operator_name} - {self.year}>'
    
    def update_remaining_hours(self):
        """تحديث الساعات المتبقية"""
        # التحقق من أن القيم ليست None
        allocated = self.allocated_hours if self.allocated_hours is not None else 0
        used = self.used_hours if self.used_hours is not None else 0
        
        self.remaining_hours = allocated - used
        if self.remaining_hours < 0:
            self.remaining_hours = 0
        return self.remaining_hours
    
    def to_dict(self):
        """تحويل النموذج إلى قاموس"""
        return {
            'id': self.id,
            'operator_name': self.operator_name,
            'year': self.year,
            'allocated_hours': self.allocated_hours,
            'used_hours': self.used_hours,
            'remaining_hours': self.remaining_hours,
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class MotorUsage(db.Model):
    """
    نموذج تسجيل استخدام المحرك
    تسجيل من يستخدم المحرك وكم ساعة
    """
    __tablename__ = 'motor_usages'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # العلاقات الخارجية
    motor_id = db.Column(db.Integer, db.ForeignKey('motors.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), index=True)  # مسؤول التسجيل
    
    # معلومات الاستخدام
    operator_name = db.Column(db.String(100), nullable=False)  # اسم الشخص الذي يستخدم المحرك
    operator_phone = db.Column(db.String(20))  # رقم هاتف المشغل
    
    # ساعات الاستخدام
    start_hours = db.Column(db.Float, nullable=False)  # ساعات البداية
    end_hours = db.Column(db.Float, nullable=False)  # ساعات النهاية
    total_hours = db.Column(db.Float)  # إجمالي الساعات (يتم حسابها تلقائياً)
    
    # التفاصيل
    usage_date = db.Column(db.Date, nullable=False, index=True, default=lambda: datetime.utcnow().date())
    usage_purpose = db.Column(db.String(200))  # الغرض من الاستخدام
    location = db.Column(db.String(100))  # مكان الاستخدام
    notes = db.Column(db.Text)  # ملاحظات إضافية
    
    # معلومات الوقود (إذا لزم الأمر)
    fuel_added = db.Column(db.Float)  # كمية الوقود المضافة (لتر)
    fuel_cost = db.Column(db.Float)  # تكلفة الوقود
    
    # الطوابع الزمنية
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.Index('idx_operator_motor_date', 'operator_name', 'motor_id', 'usage_date'),)
    
    def __repr__(self):
        return f'<MotorUsage {self.motor.name} - {self.operator_name}>'
    
    def calculate_total_hours(self):
        """حساب إجمالي الساعات"""
        if self.start_hours is not None and self.end_hours is not None:
            self.total_hours = self.end_hours - self.start_hours
            if self.total_hours < 0:
                self.total_hours = 0
        else:
            self.total_hours = 0
        return self.total_hours
    
    def to_dict(self):
        """تحويل النموذج إلى قاموس"""
        return {
            'id': self.id,
            'motor_id': self.motor_id,
            'motor_name': self.motor.name if self.motor else None,
            'operator_name': self.operator_name,
            'operator_phone': self.operator_phone,
            'start_hours': self.start_hours,
            'end_hours': self.end_hours,
            'total_hours': self.total_hours,
            'usage_date': self.usage_date.isoformat(),
            'usage_purpose': self.usage_purpose,
            'location': self.location,
            'fuel_added': self.fuel_added,
            'fuel_cost': self.fuel_cost,
            'notes': self.notes,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
class MotorCost(db.Model):
    """نموذج تتبع تكاليف المحركات (وقود وصيانة)"""
    __tablename__ = 'motor_costs'
    
    id = db.Column(db.Integer, primary_key=True)
    motor_id = db.Column(db.Integer, db.ForeignKey('motors.id', ondelete='CASCADE'), nullable=False, index=True)
    cost_type = db.Column(db.String(50), nullable=False)  # وقود أو صيانة
    quantity = db.Column(db.Float, nullable=False)  # كمية (لتر للوقود، وحدة للصيانة)
    unit_price = db.Column(db.Float, nullable=False)  # سعر الوحدة
    cost_date = db.Column(db.Date, nullable=False)  # تاريخ التكلفة
    supplier = db.Column(db.String(120), nullable=True)  # الموردة
    invoice_number = db.Column(db.String(50), nullable=True)  # رقم الفاتورة
    total_cost = db.Column(db.Float, default=0.0)  # التكلفة الإجمالية
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def calculate_total_cost(self):
        """حساب التكلفة الإجومالية"""
        self.total_cost = self.quantity * self.unit_price
        return self.total_cost
    
    def __repr__(self):
        return f'<MotorCost {self.motor.name if hasattr(self, "motor") else "Unknown"} - {self.cost_type}>'