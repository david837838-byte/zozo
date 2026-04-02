from datetime import datetime

from app import db


class AppSetting(db.Model):
    """Simple key/value settings stored in the database."""
    __tablename__ = 'app_settings'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_value(cls, key, default=None):
        setting = cls.query.get(key)
        if not setting or setting.value is None or str(setting.value).strip() == "":
            return default
        return setting.value

    @classmethod
    def set_value(cls, key, value):
        setting = cls.query.get(key)
        if not setting:
            setting = cls(key=key, value=value)
            db.session.add(setting)
        else:
            setting.value = value
        db.session.commit()
        return setting
