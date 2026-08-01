"""用户设置中 API Key 的加密与掩码工具

Key 落库前用 Fernet 加密（密钥由 SECRET_KEY 派生），
接口对外只返回掩码，绝不返回明文。
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import SECRET_KEY


def _fernet() -> Fernet:
    """由 SECRET_KEY 派生稳定的 Fernet 密钥"""
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_key(plaintext: str) -> str:
    """加密 API Key，返回密文字符串；空值原样返回"""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_key(token: str) -> str:
    """解密 API Key；解密失败（如密钥变更）返回空串"""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def mask_key(value: str) -> str:
    """生成掩码展示：sk-****abcd；超短 Key 只保留前 2 位"""
    if not value:
        return ""
    if len(value) <= 8:
        return value[:2] + "****"
    return value[:3] + "****" + value[-4:]
