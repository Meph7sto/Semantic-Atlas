import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///requirement_trace.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # API配置
    API_TITLE = "需求追溯系统"
    API_VERSION = "1.0.0"
    
    # CORS配置
    CORS_ORIGINS = ["http://localhost:8080", "http://127.0.0.1:8080"]

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
