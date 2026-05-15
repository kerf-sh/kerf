# Transactional email — provider configuration

Kerf supports three transactional email providers selected at deploy time via
environment variable.  The default is `smtp`, so existing deployments continue
working with no changes.

## Selecting a provider

Set `EMAIL_PROVIDER` to one of:

| Value    | Description                          | Required credentials            |
|----------|--------------------------------------|---------------------------------|
| `smtp`   | Any SMTP relay (default)             | `SMTP_HOST`, `SMTP_PORT`        |
| `resend` | Resend HTTP API                      | `RESEND_API_KEY`                |
| `ses`    | AWS SES v2 (requires `boto3`)        | `SES_REGION` (+ optional keys)  |

Always set `EMAIL_FROM` to the default "From" address, e.g.:

```
EMAIL_FROM=Kerf <noreply@kerf.app>
```

## Environment variables

```
# Provider selection (smtp | resend | ses)
EMAIL_PROVIDER=smtp

# Default From address
EMAIL_FROM=Kerf <noreply@kerf.app>

# Resend
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx

# AWS SES v2
SES_REGION=us-east-1
SES_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE        # omit when using an IAM role
SES_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# SMTP
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
```

## Using the dispatcher in code

```python
from kerf_cloud.email.providers import send_email
from kerf_core.config import get_settings

send_email(
    to="user@example.com",
    subject="Welcome to kerf",
    html="<p>Welcome!</p>",
    text="Welcome!",          # optional; omit to auto-strip HTML tags (smtp only)
    settings=get_settings(),
)
```

## SES and boto3

The SES path requires `boto3`.  It is an optional dependency — if `boto3` is not
installed, `send_email` raises a clear `ImportError` explaining how to install it.

```
pip install boto3
```

When running on AWS (EC2, ECS, Lambda) with an IAM role, leave
`SES_ACCESS_KEY_ID` and `SES_SECRET_ACCESS_KEY` unset; `boto3` will pick up the
instance credentials automatically.

## DB-backed multi-provider (cloud admin UI)

The `Mailer` class in `mailer.py` is a separate, higher-level system used by
the cloud admin panel.  It stores encrypted provider credentials in the
`cloud_email_credentials` Postgres table and supports run-time switching
without a redeploy.  `send_email` in `providers.py` is the simpler env-var
path designed for operator-controlled deployments.
