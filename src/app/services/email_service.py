"""Email delivery service for transactional messages."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from urllib.parse import urlencode

import structlog

from ..core.config import settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class VerificationEmailPayload:
    to_email: str
    to_name: str | None
    verification_link: str


class EmailService:
    """Send transactional emails over SMTP."""

    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.EMAIL_FROM_ADDRESS)

    def build_verification_link(self, request_origin: str, token: str) -> str:
        base_url = request_origin.rstrip("/")
        query = urlencode({"token": token})
        return f"{base_url}/api/v1/verify-email?{query}"

    async def send_verification_email(self, payload: VerificationEmailPayload) -> None:
        if not self.is_configured():
            logger.warning(
                "Email service is not configured; skipping verification email",
                recipient=payload.to_email,
            )
            return

        message = self._build_verification_email_message(payload)
        try:
            await asyncio.to_thread(self._send_via_smtp, message)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to send verification email",
                recipient=payload.to_email,
                error=str(exc),
            )
            if settings.ENVIRONMENT != "production":
                raise

    def _build_verification_email_message(self, payload: VerificationEmailPayload) -> EmailMessage:
        recipient_name = payload.to_name.strip() if payload.to_name else "there"
        escaped_name = escape(recipient_name)
        escaped_link = escape(payload.verification_link, quote=True)

        subject = "Please verify your email"

        plain_text = (
            f"Hi {recipient_name},\n\n"
            "Welcome to Poets Crew.\n"
            "Please verify your email address by opening the link below:\n\n"
            f"{payload.verification_link}\n\n"
            f"This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_DAYS} days.\n"
            "If you did not create this account, you can ignore this email."
        )

        html_text = f"""
<!doctype html>
<html lang="en">
  <body
    style="margin:0;padding:0;background:#f8f9fb;color:#111827;font-family:Arial,sans-serif;line-height:1.5;"
  >
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 12px;">
      <tr>
        <td align="center">
          <table
            role="presentation"
            width="100%"
            cellspacing="0"
            cellpadding="0"
            style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:28px;"
          >
            <tr>
              <td>
                <h1 style="margin:0 0 16px;font-size:24px;color:#111827;">Verify Your Email</h1>
                <p style="margin:0 0 12px;font-size:16px;">Hi {escaped_name},</p>
                <p style="margin:0 0 16px;font-size:16px;">
                  Welcome to Poets Crew. Please verify your email address to complete your registration.
                </p>
                <p style="margin:0 0 20px;">
                  <a
                    href="{escaped_link}"
                    style="display:inline-block;background:#111827;color:#ffffff;text-decoration:none;"
                  >
                    Verify Email
                  </a>
                </p>
                <p style="margin:0 0 10px;font-size:14px;color:#4b5563;">
                  Or copy and paste this link into your browser:
                </p>
                <p style="margin:0 0 18px;font-size:14px;word-break:break-all;">
                  <a href="{escaped_link}" style="color:#2563eb;">{escaped_link}</a>
                </p>
                <p style="margin:0 0 10px;font-size:14px;color:#4b5563;">
                  This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_DAYS} days.
                </p>
                <p style="margin:0;font-size:14px;color:#4b5563;">
                  If you did not create this account, you can ignore this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.EMAIL_FROM_NAME, str(settings.EMAIL_FROM_ADDRESS)))
        message["To"] = payload.to_email
        if settings.EMAIL_REPLY_TO:
            message["Reply-To"] = settings.EMAIL_REPLY_TO

        message.set_content(plain_text)
        message.add_alternative(html_text, subtype="html")

        return message

    def _send_via_smtp(self, message: EmailMessage) -> None:
        if not settings.SMTP_HOST or not settings.EMAIL_FROM_ADDRESS:
            return

        smtp_password = settings.SMTP_PASSWORD.get_secret_value() if settings.SMTP_PASSWORD else None

        if settings.SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
                context=context,
            ) as server:
                if settings.SMTP_USERNAME and smtp_password:
                    server.login(settings.SMTP_USERNAME, smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS) as server:
            if settings.SMTP_USE_STARTTLS:
                context = ssl.create_default_context()
                server.starttls(context=context)
            if settings.SMTP_USERNAME and smtp_password:
                server.login(settings.SMTP_USERNAME, smtp_password)
            server.send_message(message)


email_service = EmailService()
