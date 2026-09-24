"""Notification delivery.

Rows are written wherever the event happens; sending is a separate step, so a
slow or misconfigured mail server never blocks somebody saving a test result.
With no SMTP host configured the app still works -- everything lands in the
in-app list and is marked "skipped" rather than failing.
"""
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Notification, NotificationPreference, User

# the events worth telling somebody about; anything noisier trains people to
# ignore the lot
KINDS = {
    "test_assigned": "Size test atandı",
    "run_completed": "Koşum tamamlandı",
    "milestone_due": "Milestone tarihi yaklaşıyor",
    "case_changed": "İzlediğiniz case değişti",
    "result_failed": "Atandığınız test başarısız oldu",
}


def wants(session: Session, user_id: int, kind: str) -> tuple[bool, bool]:
    """(in_app, email) for this user and event, with sensible defaults."""
    pref = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.kind == kind))
    if pref is None:
        return True, False
    return pref.in_app, pref.email


def notify(session: Session, user_id: int, kind: str, subject: str,
           body: str, link: str | None = None) -> Notification | None:
    """Queue a notification. Caller commits."""
    in_app, by_email = wants(session, user_id, kind)
    if not in_app and not by_email:
        return None
    row = Notification(
        user_id=user_id, kind=kind, subject=subject, body=body, link=link,
        email_status="pending" if by_email else "skipped",
    )
    session.add(row)
    return row


def send_pending(session: Session, limit: int = 50) -> dict:
    """Deliver queued e-mail. Safe to call repeatedly; failures stay queued
    with the reason attached."""
    settings = get_settings()
    if not settings.smtp_host:
        return {"sent": 0, "failed": 0, "skipped": 0,
                "detail": "SMTP yapılandırılmamış"}

    rows = session.scalars(
        select(Notification).where(Notification.email_status == "pending")
        .order_by(Notification.id).limit(limit)).all()
    if not rows:
        return {"sent": 0, "failed": 0, "skipped": 0}

    sent = failed = 0
    try:
        server = (smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port)
                  if settings.smtp_ssl
                  else smtplib.SMTP(settings.smtp_host, settings.smtp_port))
        with server:
            if settings.smtp_starttls and not settings.smtp_ssl:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            for row in rows:
                user = session.get(User, row.user_id)
                if user is None or not user.email:
                    row.email_status = "skipped"
                    continue
                message = EmailMessage()
                message["Subject"] = row.subject
                message["From"] = settings.smtp_from
                message["To"] = user.email
                link = f"\n\n{settings.public_url}{row.link}" if row.link else ""
                message.set_content(row.body + link)
                try:
                    server.send_message(message)
                    row.email_status = "sent"
                    row.sent_at = datetime.now(timezone.utc)
                    sent += 1
                except Exception as exc:  # one bad address must not stop the batch
                    row.email_status = "failed"
                    row.email_error = str(exc)[:400]
                    failed += 1
    except Exception as exc:
        for row in rows:
            row.email_error = str(exc)[:400]
        session.commit()
        return {"sent": 0, "failed": len(rows), "skipped": 0,
                "detail": f"SMTP baglanti hatasi: {str(exc)[:200]}"}

    session.commit()
    return {"sent": sent, "failed": failed, "skipped": len(rows) - sent - failed}
