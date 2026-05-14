import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from .service import (
    Credentials,
    Message,
    Provider,
    ProviderResend,
    ProviderSES,
    ProviderSMTP,
    provider_order,
    DRAIN_INTERVAL,
    DRAIN_BATCH,
    MAX_ATTEMPTS,
    LOW_BALANCE_WINDOW,
    ErrInvalidCredentials,
)
from .templates import renderer, TEMPLATES, template_subjects
from .resend import ResendProvider
from .ses import SESProvider
from .smtp import SMTPProvider

logger = logging.getLogger(__name__)

payloads: dict[str, bytes] = {}
payloads_mu = threading.Lock()


def _backoff_for(attempt: int) -> float:
    if attempt == 1:
        return 30.0
    elif attempt == 2:
        return 120.0
    else:
        return 480.0


def _parse_attempts(err_msg: str) -> int:
    prefix = "attempts="
    if not err_msg.startswith(prefix):
        return 0
    rest = err_msg[len(prefix) :]
    end = 0
    while end < len(rest) and rest[end].isdigit():
        end += 1
    if end == 0:
        return 0
    try:
        return int(rest[:end])
    except ValueError:
        return 0


def _build_provider(name: str, creds: Credentials) -> Provider:
    if name == ProviderResend:
        return ResendProvider.from_credentials(creds)
    elif name == ProviderSES:
        return SESProvider.from_credentials(creds)
    elif name == ProviderSMTP:
        return SMTPProvider.from_credentials(creds)
    else:
        raise ValueError(f"unknown provider: {name}")


class Mailer:
    def __init__(self, pool, cfg):
        self._pool = pool
        self._cfg = cfg
        self._providers: dict[str, Provider] = {}
        self._notify = asyncio.Queue(maxsize=1)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def boot(self):
        await self.reload()

        async def run_drain():
            while True:
                try:
                    await asyncio.sleep(DRAIN_INTERVAL)
                    await self._drain_once()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception(f"email: drain error: {e}")

        self._running = True
        self._task = asyncio.create_task(run_drain())

    async def shutdown(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def reload(self):
        if self._pool is None:
            return

        rows = await self._pool.fetch(
            "select provider, enabled, secret_encrypted from cloud_email_credentials"
        )

        next_providers: dict[str, Provider] = {}
        for row in rows:
            name = row["provider"]
            enabled = row["enabled"]
            ciphertext = row["secret_encrypted"]

            if not enabled or not ciphertext:
                continue

            try:
                plain = self._decrypt_secret(ciphertext)
                creds = Credentials.from_dict(json.loads(plain))
            except Exception as e:
                logger.warning(f"email: decrypt {name}: {e} (skipping)")
                continue

            try:
                p = _build_provider(name, creds)
                next_providers[name] = p
            except Exception as e:
                logger.warning(f"email: build {name}: {e} (skipping)")
                continue

        self._providers = next_providers

    def _decrypt_secret(self, ciphertext: bytes) -> str:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        import hashlib

        secret = self._cfg.jwt_secret
        key = hashlib.sha256(f"cloud:email-credentials:{secret}".encode()).digest()
        iv = ciphertext[:16]
        encrypted = ciphertext[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()
        padding = padded[-1]
        plaintext = padded[:-padding]
        return plaintext.decode("utf-8")

    def _active_provider(self) -> Optional[Provider]:
        for name in provider_order:
            if name in self._providers:
                return self._providers[name]
        return None

    async def send_template(
        self,
        template_name: str,
        recipient: str,
        user_id: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> None:
        if not recipient:
            raise ValueError("email: recipient is empty")

        if template_name not in TEMPLATES:
            raise ValueError(f"email: unknown template: {template_name}")

        if data is None:
            data = {}
        if "Email" not in data:
            data["Email"] = recipient

        renderer.render(template_name, recipient, data)

        payload = json.dumps(data).encode()

        row_id = await self._pool.fetchval(
            "insert into cloud_email_log (user_id, template, to_email, status) "
            "values ($1, $2, $3, 'queued') returning id",
            user_id or None,
            template_name,
            recipient,
        )

        with payloads_mu:
            payloads[row_id] = payload

        try:
            self._notify.put_nowait(True)
        except asyncio.QueueFull:
            pass

    def _recall_payload(self, row_id: str) -> bytes:
        with payloads_mu:
            return payloads.get(row_id, b"")

    def _forget_payload(self, row_id: str) -> None:
        with payloads_mu:
            payloads.pop(row_id, None)

    async def _drain_once(self) -> None:
        provider = self._active_provider()
        if provider is None:
            return

        rows = await self._pool.fetch(
            "select id, template, to_email from cloud_email_log "
            "where status = 'queued' order by created_at asc limit $1",
            DRAIN_BATCH,
        )

        for row in rows:
            await self._dispatch(provider, row["id"], row["template"], row["to_email"])

    async def _dispatch(
        self, provider: Provider, id: str, template: str, to: str
    ) -> None:
        raw = self._recall_payload(id)
        data = {}
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                pass

        if not data:
            data = {"Email": to}

        msg = renderer.render(template, to, data)

        try:
            provider.send(msg)

            await self._pool.execute(
                "update cloud_email_log set status = 'sent', provider = $2, "
                "sent_at = now(), error = null where id = $1",
                id,
                provider.name(),
            )

            await self._pool.execute(
                "update cloud_email_credentials set last_used_at = now(), "
                "updated_at = now() where provider = $1",
                provider.name(),
            )
        except Exception as e:
            await self._maybe_retry(id, provider.name(), str(e))

        self._forget_payload(id)

    async def _maybe_retry(self, id: str, provider_name: str, send_err: str) -> None:
        row = await self._pool.fetchrow(
            "select coalesce(error, '') as err from cloud_email_log where id = $1",
            id,
        )
        prev_err = row["err"] if row else ""
        attempts = _parse_attempts(prev_err) + 1

        if attempts >= MAX_ATTEMPTS:
            await self._mark_failed(id, f"attempts={attempts}|provider={provider_name}|{send_err}")
            self._forget_payload(id)
            return

        backoff = _backoff_for(attempts)

        await self._pool.execute(
            "update cloud_email_log set status = 'queued', provider = $2, "
            "error = $3, created_at = now() + interval '1 second' * $4 "
            "where id = $1",
            id,
            provider_name,
            f"attempts={attempts}|{send_err}",
            int(backoff),
        )

    async def _mark_failed(self, id: str, err_msg: str) -> None:
        await self._pool.execute(
            "update cloud_email_log set status = 'failed', error = $2 where id = $1",
            id,
            err_msg,
        )

    async def eligible_for_low_balance(self, user_id: str) -> bool:
        if not user_id:
            return False

        row = await self._pool.fetchrow(
            "select max(created_at) as last_at from cloud_email_log "
            "where user_id = $1 and template = 'low_balance' and status in ('queued', 'sent')",
            user_id,
        )

        last_at = row["last_at"] if row else None
        if last_at is None:
            return True

        now = datetime.now(timezone.utc)
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)

        elapsed = (now - last_at).total_seconds()
        return elapsed >= LOW_BALANCE_WINDOW
