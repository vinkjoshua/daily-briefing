"""Send email over SMTP (implicit TLS on 465, STARTTLS otherwise)."""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any


@dataclass(frozen=True)
class SmtpSettings:
    """SMTP connection settings."""

    host: str
    port: int
    user: str
    password: str


def factory_for(port: int) -> type[smtplib.SMTP]:
    """Pick the smtplib class for a port.

    Args:
        port: SMTP port.

    Returns:
        smtplib.SMTP_SSL for 465, smtplib.SMTP otherwise.
    """
    return smtplib.SMTP_SSL if port == 465 else smtplib.SMTP


def build_message(*, subject: str, text: str, html: str, sender: str, to: str) -> EmailMessage:
    """Build a multipart/alternative email.

    Args:
        subject: Subject line.
        text: Plain-text body (the Markdown).
        html: HTML body.
        sender: From address.
        to: To address.

    Returns:
        The message.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send(
    message: EmailMessage,
    settings: SmtpSettings,
    smtp_factory: Callable[..., Any] | None = None,
) -> None:
    """Send a message.

    Args:
        message: The email.
        settings: Connection settings; spaces in the password are removed (Gmail shows them).
        smtp_factory: Override for tests; defaults to factory_for(settings.port).
    """
    factory = smtp_factory or factory_for(settings.port)
    ctx = ssl.create_default_context()
    # smtplib.SMTP (STARTTLS) takes no context at construction; SMTP_SSL does.
    kwargs: dict[str, Any] = {"context": ctx} if settings.port == 465 else {}
    with factory(settings.host, settings.port, timeout=60, **kwargs) as smtp:
        if settings.port != 465:
            smtp.starttls(context=ctx)
        smtp.login(settings.user, settings.password.replace(" ", ""))
        smtp.send_message(message)
