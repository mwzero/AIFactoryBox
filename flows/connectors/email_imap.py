"""Zero-dependency IMAP/SMTP connector for enterprise mailboxes & Italian PEC."""
from dataclasses import dataclass, field
import email
from email.header import decode_header
from email.message import EmailMessage
import imaplib
import os
from pathlib import Path
import smtplib
import tempfile
import time
from typing import List, Optional


@dataclass
class IncomingEmail:
    uid: str
    subject: str
    sender: str
    body_text: str
    attachments: List[Path] = field(default_factory=list)


def _decode_mime_header(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(chunk))
    return "".join(decoded)


class EmailIMAPConnector:
    """Connettore standard IMAP/SMTP compatibile con PEC, OVH, Aruba, Gmail e Microsoft 365."""

    def __init__(
        self,
        imap_host: Optional[str] = None,
        imap_port: int = 993,
        smtp_host: Optional[str] = None,
        smtp_port: int = 465,
        username: Optional[str] = None,
        password: Optional[str] = None,
        drafts_folder: str = "Drafts",
    ):
        self.imap_host = imap_host or os.getenv("IMAP_HOST", "")
        self.imap_port = int(os.getenv("IMAP_PORT", str(imap_port)))
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", self.imap_host)
        self.smtp_port = int(os.getenv("SMTP_PORT", str(smtp_port)))
        self.username = username or os.getenv("EMAIL_USER", "")
        self.password = password or os.getenv("EMAIL_PASSWORD", "")
        self.drafts_folder = drafts_folder

    def fetch_unread_emails(
        self,
        mailbox: str = "INBOX",
        limit: int = 5,
        mark_seen: bool = False,
        download_dir: Optional[Path] = None,
    ) -> List[IncomingEmail]:
        if not self.imap_host or not self.username or not self.password:
            raise ValueError("IMAP_HOST, EMAIL_USER and EMAIL_PASSWORD must be configured.")

        target_dir = download_dir or Path(tempfile.mkdtemp(prefix="aifactory_mail_"))
        target_dir.mkdir(parents=True, exist_ok=True)
        results: List[IncomingEmail] = []

        with imaplib.IMAP4_SSL(self.imap_host, self.imap_port) as client:
            client.login(self.username, self.password)
            client.select(mailbox, readonly=not mark_seen)
            status, data = client.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return results

            uids = data[0].split()[-limit:]
            for raw_uid in uids:
                uid_str = raw_uid.decode("utf-8", errors="ignore")
                fetch_flag = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
                st, msg_data = client.fetch(raw_uid, fetch_flag)
                if st != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode_mime_header(msg.get("Subject"))
                sender = _decode_mime_header(msg.get("From"))
                body_parts: List[str] = []
                attachments: List[Path] = []

                if msg.is_multipart():
                    for part in msg.walk():
                        disp = str(part.get("Content-Disposition") or "")
                        ctype = part.get_content_type()
                        if "attachment" in disp.lower() or part.get_filename():
                            fname = _decode_mime_header(part.get_filename() or f"att_{uid_str}.bin")
                            safe_name = Path(fname).name
                            payload = part.get_payload(decode=True)
                            if payload:
                                att_path = target_dir / f"{uid_str}_{safe_name}"
                                att_path.write_bytes(payload)
                                attachments.append(att_path)
                        elif ctype == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body_parts.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))

                results.append(
                    IncomingEmail(
                        uid=uid_str,
                        subject=subject,
                        sender=sender,
                        body_text="\n".join(body_parts).strip(),
                        attachments=attachments,
                    )
                )
        return results

    def save_draft(self, to_addr: str, subject: str, body: str) -> None:
        """Salva una bozza nella cartella Drafts via IMAP APPEND (Human-in-the-loop)."""
        if not self.imap_host or not self.username or not self.password:
            raise ValueError("IMAP credentials not configured.")
        msg = EmailMessage()
        msg["From"] = self.username
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)

        with imaplib.IMAP4_SSL(self.imap_host, self.imap_port) as client:
            client.login(self.username, self.password)
            client.append(
                self.drafts_folder,
                "(\\Draft)",
                imaplib.Time2Internaldate(time.time()),
                msg.as_bytes(),
            )

    def send_email(self, to_addr: str, subject: str, body: str) -> None:
        """Invia una notifica o un report via SMTP SSL."""
        if not self.smtp_host or not self.username or not self.password:
            raise ValueError("SMTP credentials not configured.")
        msg = EmailMessage()
        msg["From"] = self.username
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
            server.login(self.username, self.password)
            server.send_message(msg)
