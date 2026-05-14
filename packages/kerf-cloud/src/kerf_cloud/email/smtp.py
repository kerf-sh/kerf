import asyncio
import random
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Self

from .service import (
    Credentials,
    Message,
    Provider,
    ProviderSMTP,
    ErrInvalidCredentials,
)


def _random_boundary() -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(16))


def _strip_tags(html: str) -> str:
    in_tag = False
    result = []
    for char in html:
        if char == "<":
            in_tag = True
        elif char == ">":
            in_tag = False
        elif not in_tag:
            result.append(char)
    return "".join(result)


def _send_sync(smtp_host: str, smtp_port: int, user: str, password: str, from_addr: str, msg: MIMEMultipart) -> None:
    addr = f"{smtp_host}:{smtp_port}"
    sender = from_addr

    with smtplib.SMTP(addr) as s:
        s.starttls()
        if user:
            s.login(user, password)
        s.sendmail(sender, [msg["To"]], msg.as_bytes())


class SMTPProvider(Provider):
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_addr

    @classmethod
    def from_credentials(cls, creds: Credentials) -> Self:
        if not creds.smtp_host or not creds.smtp_port:
            raise ErrInvalidCredentials("smtp: host+port required")
        if not creds.from_email:
            raise ErrInvalidCredentials("smtp: from_email required")

        from_addr = creds.from_email
        if creds.from_name:
            from_addr = f"{creds.from_name} <{creds.from_email}>"

        return cls(
            host=creds.smtp_host,
            port=creds.smtp_port,
            user=creds.smtp_username,
            password=creds.smtp_password,
            from_addr=from_addr,
        )

    def name(self) -> str:
        return ProviderSMTP

    def _from_addr(self, from_str: str) -> str:
        if "<" in from_str:
            start = from_str.find("<")
            end = from_str.find(">", start)
            if end > start:
                return from_str[start + 1 : end].strip()
        return from_str.strip()

    def send(self, msg: Message) -> bool:
        from_addr = msg.From or self._from
        if not msg.To:
            raise ValueError("smtp: empty recipient")

        msg_obj = MIMEMultipart("alternative")
        msg_obj["From"] = from_addr
        msg_obj["To"] = msg.To
        if msg.ReplyTo:
            msg_obj["Reply-To"] = msg.ReplyTo
        msg_obj["Subject"] = msg.Subject

        text_body = msg.Text
        if not text_body:
            text_body = _strip_tags(msg.HTML)

        part1 = MIMEText(text_body, "plain", "utf-8")
        msg_obj.attach(part1)

        if msg.HTML:
            part2 = MIMEText(msg.HTML, "html", "utf-8")
            msg_obj.attach(part2)

        sender = self._from_addr(from_addr)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            None,
            _send_sync,
            self._host,
            self._port,
            self._user,
            self._password,
            sender,
            msg_obj,
        )

        return True
