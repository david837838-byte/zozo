from app import db
from datetime import datetime

INCOME_TRANSACTION_TYPE_ALIASES = ("دخل", "???")
EXPENSE_TRANSACTION_TYPE_ALIASES = ("مصروف", "?????")
WORKER_REFERENCE_TYPE_ALIASES = ("عامل", "????")


def _clean_text(value):
    """Return stripped text or empty string."""
    if value is None:
        return ""
    return str(value).strip()


def normalize_transaction_type(value):
    """Normalize legacy transaction types to canonical Arabic values."""
    raw = _clean_text(value)
    if raw in INCOME_TRANSACTION_TYPE_ALIASES:
        return "دخل"
    if raw in EXPENSE_TRANSACTION_TYPE_ALIASES:
        return "مصروف"
    return raw


def normalize_reference_type(value):
    """Normalize legacy reference types."""
    raw = _clean_text(value)
    if raw in WORKER_REFERENCE_TYPE_ALIASES:
        return "عامل"
    return raw


def is_income_transaction(value):
    """Check whether value maps to income transaction."""
    return normalize_transaction_type(value) == "دخل"


def is_expense_transaction(value):
    """Check whether value maps to expense transaction."""
    return normalize_transaction_type(value) == "مصروف"


def is_worker_reference_type(value):
    """Check whether value maps to worker reference type."""
    return normalize_reference_type(value) == "عامل"


class ExpenseCategory(db.Model):
    """نموذج فئات المصروفات"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    
    # Relations
    transactions = db.relationship('Transaction', backref='category', lazy=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'

class Transaction(db.Model):
    """نموذج المعاملات المحاسبية"""
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'), nullable=True)
    transaction_type = db.Column(db.String(50), nullable=False)  # دخل أو مصروف
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    reference_type = db.Column(db.String(50), nullable=True)  # نوع المرجع (عامل، مخزون، بيع، إلخ)
    reference_id = db.Column(db.Integer, nullable=True)  # معرف المرجع
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.description}>'


class ClosedWorkerAccount(db.Model):
    """نموذج حسابات العمال المسكرة"""
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, nullable=False)  # معرف العامل (الأصلي)
    worker_name = db.Column(db.String(120), nullable=False)  # اسم العامل
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    is_monthly = db.Column(db.Boolean, default=False)  # هل كان عامل شهري
    work_location = db.Column(db.String(50), nullable=True)
    hourly_rate = db.Column(db.Float, default=0.0)
    monthly_salary = db.Column(db.Float, default=0.0)
    
    # معلومات التسكير
    closure_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)  # تاريخ التسكير
    closure_reason = db.Column(db.Text, nullable=True)  # سبب التسكير
    final_balance = db.Column(db.Float, default=0.0)  # الرصيد النهائي
    notes = db.Column(db.Text, nullable=True)  # ملاحظات عامة
    
    # تاريخ الإنشاء
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ClosedWorkerAccount {self.worker_name}>'
