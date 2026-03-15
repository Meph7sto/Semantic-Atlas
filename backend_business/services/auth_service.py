"""
认证服务：处理用户登录、JWT Token 生成和验证
"""

import bcrypt
import datetime
import hashlib
import secrets
from typing import Dict, Optional, Tuple

import jwt


class AuthService:
    """认证服务类，处理登录、JWT 生成和验证"""

    def __init__(self, secret_key: str):
        """
        初始化认证服务

        Args:
            secret_key: JWT 签名密钥
        """
        self.secret_key = secret_key
        self.algorithm = "HS256"
        self.token_expiry_hours = 24  # Token 有效期（小时）

    def hash_password(self, password: str) -> str:
        """
        对密码进行哈希处理

        Args:
            password: 明文密码

        Returns:
            哈希后的密码
        """
        # 使用 bcrypt 进行密码哈希
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def verify_password(self, password: str, password_hash: str) -> bool:
        """
        验证密码是否匹配

        Args:
            password: 明文密码
            password_hash: 存储的哈希密码

        Returns:
            密码是否匹配
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False

    def generate_user_id(self) -> str:
        """生成用户 ID"""
        # 使用时间戳 + 随机数生成唯一 ID
        timestamp = str(int(datetime.datetime.now().timestamp()))
        random_str = secrets.token_hex(4)
        return f"user-{timestamp}-{random_str}"

    def generate_token(self, user_id: str, username: str, role: str, external_type: Optional[str] = None) -> str:
        """
        生成 JWT Token

        Args:
            user_id: 用户 ID
            username: 用户名
            role: 用户角色
            external_type: 外部身份类型

        Returns:
            JWT Token 字符串
        """
        now = datetime.datetime.utcnow()
        expiry = now + datetime.timedelta(hours=self.token_expiry_hours)

        payload = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "external_type": external_type,
            "iat": now,
            "exp": expiry,
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict]:
        """
        验证 JWT Token

        Args:
            token: JWT Token 字符串

        Returns:
            解码后的 payload，验证失败返回 None
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            # Token 已过期
            return None
        except jwt.InvalidTokenError:
            # Token 无效
            return None
        except Exception:
            return None

    def get_token_expiry(self) -> datetime.datetime:
        """
        获取 Token 过期时间（从现在开始计算）

        Returns:
            过期时间
        """
        return datetime.datetime.utcnow() + datetime.timedelta(hours=self.token_expiry_hours)


# 内置测试用户密码哈希（test）
# 生成方式：bcrypt.hashpw('test'.encode(), bcrypt.gensalt())
TEST_PASSWORD_HASH = "$2b$12$6m.Xy3YEOvHNSXvq79T/meEpiTFFOOYVaR2aEp8pbFlfqsr/XkLki"


# 全局认证服务实例
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """获取全局认证服务实例"""
    global _auth_service
    if _auth_service is None:
        # 从配置获取密钥
        from backend_business.config import settings
        _auth_service = AuthService(settings.JWT_SECRET_KEY)
    return _auth_service


def set_auth_service(service: AuthService) -> None:
    """设置全局认证服务实例（主要用于测试）"""
    global _auth_service
    _auth_service = service
