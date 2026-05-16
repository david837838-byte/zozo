import os
from datetime import timedelta

DEFAULT_INSECURE_SECRET_KEY = 'dev-secret-key-change-in-production'


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or DEFAULT_INSECURE_SECRET_KEY
    SQLALCHEMY_DATABASE_URI = 'sqlite:///farm_management.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GEMINI_API_KEY = (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or '').strip()
    GEMINI_MODEL = (os.environ.get('GEMINI_MODEL') or 'gemini-2.5-flash').strip()
    OPENAI_API_KEY = (os.environ.get('OPENAI_API_KEY') or '').strip()
    OPENAI_MODEL = (os.environ.get('OPENAI_MODEL') or 'gpt-5.4-mini').strip()
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    TRUST_PROXY_HEADERS = str(os.environ.get('TRUST_PROXY_HEADERS', 'false')).strip().lower() in {
        '1', 'true', 'yes', 'on'
    }

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
