from typing import Self

import boto3
from botocore.config import Config as BotoConfig

from .service import (
    Credentials,
    Message,
    Provider,
    ProviderSES,
    ErrInvalidCredentials,
)


class SESProvider(Provider):
    def __init__(self, client, from_addr: str, from_email: str, from_name: str = ""):
        self._client = client
        self._from = from_addr
        self._from_email = from_email
        self._from_name = from_name

    @classmethod
    def from_credentials(cls, creds: Credentials) -> Self:
        if not creds.from_email:
            raise ErrInvalidCredentials("ses: from_email is required")
        if not creds.region:
            raise ErrInvalidCredentials("ses: region is required")

        from_addr = creds.from_email
        if creds.from_name:
            from_addr = f"{creds.from_name} <{creds.from_email}>"

        session_kwargs = {"region_name": creds.region}
        client_kwargs = {"config": BotoConfig(retries={"mode": "standard"})}

        if creds.api_key and creds.smtp_password:
            session_kwargs["aws_access_key_id"] = creds.api_key
            session_kwargs["aws_secret_access_key"] = creds.smtp_password

        session = boto3.Session(**session_kwargs)
        client = session.client("sesv2", **client_kwargs)

        return cls(
            client=client,
            from_addr=from_addr,
            from_email=creds.from_email,
            from_name=creds.from_name,
        )

    def name(self) -> str:
        return ProviderSES

    def send(self, msg: Message) -> bool:
        from_addr = msg.From or self._from

        email_tags = []
        if msg.Tags:
            for k, v in msg.Tags.items():
                email_tags.append({"Name": k, "Value": v})

        content = {"Subject": {"Data": msg.Subject, "Charset": "UTF-8"}}

        body = {}
        if msg.HTML:
            body["Html"] = {"Data": msg.HTML, "Charset": "UTF-8"}
        if msg.Text:
            body["Text"] = {"Data": msg.Text, "Charset": "UTF-8"}

        if body:
            content["Body"] = body

        kwargs = {
            "FromEmailAddress": from_addr,
            "Destination": {"ToAddresses": [msg.To]},
            "Content": {"Simple": content},
        }

        if msg.ReplyTo:
            kwargs["ReplyToAddresses"] = [msg.ReplyTo]

        if email_tags:
            kwargs["EmailTags"] = email_tags

        self._client.send_email(**kwargs)
        return True
