"""邮件发送模块

基于 fastapi-mail 实现异步邮件发送。
SMTP 未配置时仅打印日志（开发模式）。
"""
import logging

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

from .config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

logger = logging.getLogger(__name__)


def create_mailer() -> FastMail:
    """创建 FastMail 实例，SMTP 未配置时返回 None 占位"""
    if not SMTP_HOST or not SMTP_USER:
        logger.info("SMTP 未配置，邮件仅在日志输出（开发模式）")
        return None
    conf = ConnectionConfig(
        MAIL_USERNAME=SMTP_USER,
        MAIL_PASSWORD=SMTP_PASSWORD,
        MAIL_FROM=SMTP_FROM or SMTP_USER,
        MAIL_PORT=SMTP_PORT,
        MAIL_SERVER=SMTP_HOST,
        MAIL_STARTTLS=False,
        MAIL_SSL_TLS=True,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )
    return FastMail(conf)


async def send_verification_email(mailer: FastMail, to_email: str, code: str) -> bool:
    """发送邮箱验证码。SMTP 未配置时仅打印日志。"""
    body = f"""您好，

您的 MockMate 邮箱验证码是：{code}

验证码 5 分钟内有效，请勿泄露给他人。

如果这不是您本人的操作，请忽略此邮件。"""

    if mailer is None:
        logger.info(f"[DEV] 发送验证码到 {to_email}: {code}")
        return False

    try:
        message = MessageSchema(
            subject="MockMate 邮箱验证码",
            recipients=[to_email],
            body=body,
            subtype="plain",
        )
        await mailer.send_message(message)
        logger.info(f"验证码邮件发送成功: {to_email}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False
