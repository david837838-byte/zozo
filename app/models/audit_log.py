import json
from datetime import datetime

from app import db


class AuditLog(db.Model):
    """Stores audited database mutations (create/update/delete)."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    username = db.Column(db.String(80), nullable=False, default="system", index=True)
    action = db.Column(db.String(20), nullable=False, index=True)  # create/update/delete
    entity_type = db.Column(db.String(120), nullable=False, index=True)
    entity_id = db.Column(db.String(120), nullable=True, index=True)
    summary = db.Column(db.String(255), nullable=True)
    changes = db.Column(db.Text, nullable=True)
    endpoint = db.Column(db.String(120), nullable=True, index=True)
    ip_address = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", lazy="joined")

    @property
    def changes_dict(self):
        """Return parsed change payload for rendering."""
        if not self.changes:
            return {}
        try:
            parsed = json.loads(self.changes)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except Exception:
            return {"value": self.changes}

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity_type}#{self.entity_id or '-'}>"
