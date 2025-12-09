from datetime import datetime
from . import db

class Requirement(db.Model):
    """需求模型"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 与追溯记录的关系
    trace_records = db.relationship('TraceRecord', backref='requirement', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class TraceRecord(db.Model):
    """追溯记录模型"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'), nullable=False)
    stage = db.Column(db.String(50), nullable=False)  # 阶段：需求、设计、开发、测试、部署
    stage_type = db.Column(db.String(20), default='info')  # 类型：success, warning, error, info
    description = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)  # 详细信息
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'stage': self.stage,
            'type': self.stage_type,
            'description': self.description,
            'details': self.details,
            'created_at': self.created_at.isoformat()
        }

class Risk(db.Model):
    """风险模型"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), default='info')  # low, medium, high, critical
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'title': self.title,
            'description': self.description,
            'level': self.level,
            'created_at': self.created_at.isoformat()
        }

class Suggestion(db.Model):
    """建议模型"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'content': self.content,
            'priority': self.priority,
            'created_at': self.created_at.isoformat()
        }
