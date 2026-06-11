import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/email", tags=["email"])


class EmailRequest(BaseModel):
    recipients: List[str]
    subject: str
    html_content: str


@router.post("/send")
async def send_email(request: EmailRequest):
    email_from = getattr(settings, 'EMAIL_FROM', None)
    email_pass = getattr(settings, 'EMAIL_PASSWORD', None)

    if not email_from or not email_pass:
        raise HTTPException(
            status_code=503,
            detail="Email not configured. Add EMAIL_FROM and EMAIL_PASSWORD to your .env file."
        )

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = request.subject
        msg['From'] = f"FinEdge Intelligence <{email_from}>"
        msg['To'] = ', '.join(request.recipients)
        msg.attach(MIMEText(request.html_content, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(email_from, email_pass)
            server.sendmail(email_from, request.recipients, msg.as_string())

        logger.info(f"Email sent to {len(request.recipients)} recipients")
        return {"success": True, "sent_to": len(request.recipients)}

    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=401, detail="Gmail auth failed. Make sure you are using a Gmail App Password, not your regular password.")
    except Exception as exc:
        logger.error(f"Email send failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to send: {str(exc)}")
