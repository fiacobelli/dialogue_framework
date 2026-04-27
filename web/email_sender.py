"""Send SDOH screening classification report via email after each visit."""
import logging
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_report(visit_id: str, result: dict, patient_id: str, cfg: dict):
    """Dispatch email on a daemon thread — never blocks the HTTP response."""
    threading.Thread(
        target=_send,
        args=(visit_id, result, patient_id, cfg),
        daemon=True,
    ).start()


def _send(visit_id, result, patient_id, cfg):
    if not cfg.get('enabled'):
        return

    recipients = [r.strip() for r in cfg.get('recipients', '').split(',') if r.strip()]
    if not recipients or not cfg.get('sender') or not cfg.get('password'):
        logger.warning("Email report skipped — missing sender, password, or recipients in config")
        return

    subject = (
        f"SDOH Screening Report — "
        f"{patient_id or 'Anonymous'} — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = cfg['sender']
    msg['To']      = ', '.join(recipients)
    msg.attach(MIMEText(_build_html(visit_id, result, patient_id), 'html'))

    try:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg['sender'], cfg['password'])
            server.sendmail(cfg['sender'], recipients, msg.as_string())
        logger.info("Screening report emailed for visit %s to %s", visit_id, recipients)
    except Exception as e:
        logger.error("Failed to send screening report for visit %s: %s", visit_id, e)


def _build_html(visit_id, result, patient_id):
    rows = [
        ('Social Worker',      result.get('social_worker',      '—')),
        ('Dietitian',          result.get('dietitian',          '—')),
        ('Nephrologist',       result.get('nephrologist',       '—')),
        ('Nurse Practitioner', result.get('nurse_practitioner', '—')),
    ]
    rows_html = ''.join(
        f"<tr>"
        f"<td style='padding:8px 14px;font-weight:600;color:#555;width:180px;"
        f"border-bottom:1px solid #eee'>{label}</td>"
        f"<td style='padding:8px 14px;color:#222;border-bottom:1px solid #eee'>{value}</td>"
        f"</tr>"
        for label, value in rows
    )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;color:#333">
      <h2 style="color:#E86F2C;margin-bottom:4px">SDOH Screening Report</h2>
      <p style="color:#888;font-size:13px;margin-top:0">
        Patient: <strong>{patient_id or 'Anonymous'}</strong> &nbsp;|&nbsp;
        Visit ID: <strong>{visit_id or '—'}</strong> &nbsp;|&nbsp;
        {datetime.now().strftime('%B %d, %Y at %H:%M')}
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:16px 0">
      <h3 style="color:#333;margin-bottom:8px">Care Team Notes</h3>
      <table style="border-collapse:collapse;width:100%;background:#f9f9f9;border-radius:8px;overflow:hidden">
        {rows_html}
      </table>
      <h3 style="color:#333;margin-top:24px;margin-bottom:8px">Verbal Summary</h3>
      <p style="background:#fff8f2;border-left:4px solid #E86F2C;padding:12px 16px;
                color:#333;line-height:1.6;margin:0">
        {result.get('verbal_summary', '—')}
      </p>
      <p style="font-size:11px;color:#bbb;margin-top:24px">
        Sent automatically by the SDOH Screening System.
        This message may contain protected health information — handle per your institution's data policies.
      </p>
    </div>
    """
