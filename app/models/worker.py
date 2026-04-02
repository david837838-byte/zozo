from app import db
from datetime import datetime

class Worker(db.Model):
    """نموذج العامل"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    is_monthly = db.Column(db.Boolean, default=False)  # عامل شهري
    work_location = db.Column(db.String(50), nullable=True)  # جبل أو سهل
    hourly_rate = db.Column(db.Float, default=0.0)  # السعر بالساعة
    monthly_salary = db.Column(db.Float, default=0.0)  # الراتب الشهري
    is_active = db.Column(db.Boolean, default=True)
    
    # Relations
    shifts = db.relationship('Shift', backref='worker', lazy=True, cascade='all, delete-orphan')
    work_logs = db.relationship('WorkLog', backref='worker', lazy=True, cascade='all, delete-orphan')
    motor_logs = db.relationship('MotorLog', backref='worker', lazy=True, cascade='all, delete-orphan')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Worker {self.name}>'

class Shift(db.Model):
    """نموذج الوردية"""
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    shift_type = db.Column(db.String(50), nullable=False)  # صباحي أو بعد ظهر
    work_date = db.Column(db.Date, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Shift {self.worker} - {self.shift_type}>'

class WorkLog(db.Model):
    """نموذج تسجيل ساعات العمل"""
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    work_date = db.Column(db.Date, nullable=False)
    hours = db.Column(db.Float, nullable=False)  # عدد الساعات
    shift_type = db.Column(db.String(50), nullable=True)  # صباحي أو بعد ظهر
    location = db.Column(db.String(50), nullable=True)  # جبل أو سهل
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<WorkLog {self.worker.name} - {self.hours} ساعات>'

class MotorLog(db.Model):
    """نموذج تسجيل ساعات المحرك"""
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    motor_name = db.Column(db.String(120), nullable=False)  # اسم المحرك
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    total_hours = db.Column(db.Float, default=0.0)  # إجمالي الساعات
    
    # حساب المازوت
    diesel_price_per_hour = db.Column(db.Float, default=0.0)  # سعر الصرف بالساعة
    diesel_price_per_liter = db.Column(db.Float, default=0.0)  # سعر اللتر
    total_diesel_cost = db.Column(db.Float, default=0.0)  # إجمالي مصروف المازوت
    
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def calculate_diesel_cost(self):
        """حساب إجمالي مصروف المازوت"""
        if self.end_date:
            hours = (self.end_date - self.start_date).total_seconds() / 3600
            self.total_hours = hours
            self.total_diesel_cost = hours * self.diesel_price_per_hour * self.diesel_price_per_liter
            return self.total_diesel_cost
        return 0
    
    def __repr__(self):
        return f'<MotorLog {self.motor_name} - {self.total_hours} ساعات>'


class Attendance(db.Model):
    """نموذج الحضور اليومي"""
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    is_present = db.Column(db.Boolean, default=True)  # حاضر أم غائب
    status = db.Column(db.String(50), nullable=False)  # حاضر، غياب، إجازة، مرض
    hours_worked = db.Column(db.Float, default=8.0)  # عدد الساعات المعملة
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    worker = db.relationship('Worker', backref=db.backref('attendances', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<Attendance {self.worker.name} - {self.attendance_date}>'


class MonthlyAttendance(db.Model):
    """نموذج ملخص الحضور الشهري"""
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    
    # بيانات الحضور
    total_days = db.Column(db.Integer, default=0)  # إجمالي أيام الشهر
    present_days = db.Column(db.Integer, default=0)  # أيام الحضور
    absent_days = db.Column(db.Integer, default=0)  # أيام الغياب
    sick_days = db.Column(db.Integer, default=0)  # أيام المرض
    vacation_days = db.Column(db.Integer, default=0)  # أيام الإجازة
    total_hours = db.Column(db.Float, default=0.0)  # إجمالي الساعات
    
    # حسابات الراتب
    base_salary = db.Column(db.Float, default=0.0)  # الراتب الأساسي
    hourly_rate = db.Column(db.Float, default=0.0)  # سعر الساعة الإضافية
    overtime_hours = db.Column(db.Float, default=0.0)  # ساعات إضافية
    overtime_pay = db.Column(db.Float, default=0.0)  # أجر الساعات الإضافية
    deductions = db.Column(db.Float, default=0.0)  # الخصومات (غياب، مرض، إلخ)
    bonuses = db.Column(db.Float, default=0.0)  # المكافآت
    
    # الصافي
    net_salary = db.Column(db.Float, default=0.0)  # الراتب الصافي (base + overtime + bonuses - deductions)
    
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    worker = db.relationship('Worker', backref=db.backref('monthly_attendances', lazy=True, cascade='all, delete-orphan'))
    
    def calculate_net_salary(self):
        """حساب الراتب الصافي"""
        # التأكد من أن جميع القيم ليست None
        overtime_hours = self.overtime_hours or 0.0
        hourly_rate = self.hourly_rate or 0.0
        bonuses = self.bonuses or 0.0
        deductions = self.deductions or 0.0
        base_salary = self.base_salary or 0.0
        
        self.overtime_pay = overtime_hours * hourly_rate
        self.net_salary = base_salary + self.overtime_pay + bonuses - deductions
        return self.net_salary
    
    def __repr__(self):
        return f'<MonthlyAttendance {self.worker.name} - {self.year}/{self.month}>'
