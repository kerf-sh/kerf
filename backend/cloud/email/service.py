SECRET_DOMAIN = "cloud:email-credentials"

PROVIDER_RESEND = "resend"
PROVIDER_SES = "ses"
PROVIDER_SMTP = "smtp"

ProviderResend = PROVIDER_RESEND
ProviderSES = PROVIDER_SES
ProviderSMTP = PROVIDER_SMTP

provider_order = [PROVIDER_RESEND, PROVIDER_SES, PROVIDER_SMTP]

DRAIN_INTERVAL = 5
DRAIN_BATCH = 50
MAX_ATTEMPTS = 3

LOW_BALANCE_WINDOW = 24 * 3600


class Message:
    def __init__(
        self,
        to: str = "",
        from_addr: str = "",
        reply_to: str = "",
        subject: str = "",
        html: str = "",
        text: str = "",
        tags: dict | None = None,
    ):
        self.To = to
        self.From = from_addr
        self.ReplyTo = reply_to
        self.Subject = subject
        self.HTML = html
        self.Text = text
        self.Tags = tags or {}


class Credentials:
    def __init__(
        self,
        api_key: str = "",
        from_email: str = "",
        from_name: str = "",
        region: str = "",
        smtp_host: str = "",
        smtp_port: int = 0,
        smtp_username: str = "",
        smtp_password: str = "",
    ):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.region = region
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password

    @classmethod
    def from_dict(cls, d: dict) -> "Credentials":
        return cls(
            api_key=d.get("api_key", ""),
            from_email=d.get("from_email", ""),
            from_name=d.get("from_name", ""),
            region=d.get("region", ""),
            smtp_host=d.get("smtp_host", ""),
            smtp_port=d.get("smtp_port", 0),
            smtp_username=d.get("smtp_username", ""),
            smtp_password=d.get("smtp_password", ""),
        )


class Provider:
    def name(self) -> str:
        raise NotImplementedError

    def send(self, msg: Message) -> bool:
        raise NotImplementedError


class ErrNoProvider(Exception):
    pass


class ErrInvalidCredentials(Exception):
    pass


def validate_credentials(provider: str, creds: Credentials) -> None:
    if not creds.from_email:
        raise ValueError("from_email is required")

    if provider == PROVIDER_RESEND:
        if not creds.api_key:
            raise ValueError("resend: api_key is required")
    elif provider == PROVIDER_SES:
        if not creds.region:
            raise ValueError("ses: region is required")
    elif provider == PROVIDER_SMTP:
        if not creds.smtp_host:
            raise ValueError("smtp: smtp_host is required")
        if not creds.smtp_port:
            raise ValueError("smtp: smtp_port is required")
    else:
        raise ValueError(f"unknown provider: {provider}")
