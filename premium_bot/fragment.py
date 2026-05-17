from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


class FragmentError(RuntimeError):
    """Raised when Fragment returns an unexpected response."""


@dataclass(frozen=True)
class PremiumOrder:
    username: str
    months: int
    recipient: str
    request_id: str
    amount_ton: Decimal
    destination: str | None
    ref: str
    comment: str
    expires_at: datetime


class FragmentClient:
    def __init__(
        self,
        *,
        fragment_hash: str,
        cookie: str,
        timeout: float = 20,
        base_url: str = "https://fragment.com",
    ) -> None:
        self.api_url = f"{base_url.rstrip('/')}/api/v1/{fragment_hash}"
        self.raw_request_url = f"{base_url.rstrip('/')}/tonkeeper/rawRequest"
        self.cookie = cookie
        self.timeout = timeout

    async def create_premium_order(
        self,
        *,
        username: str,
        months: int,
        show_sender: bool,
    ) -> PremiumOrder:
        normalized_username = normalize_username(username)
        recipient = await self.search_recipient(normalized_username, months)
        request_id = await self.init_gift_request(recipient, months)
        expires_at = await self.confirm_order(request_id, show_sender=show_sender)
        payment = await self.get_raw_request(request_id)

        return PremiumOrder(
            username=normalized_username,
            months=months,
            recipient=recipient,
            request_id=request_id,
            amount_ton=payment["amount_ton"],
            destination=payment["destination"],
            ref=payment["ref"],
            comment=f"Telegram Premium for {months} months Ref#{payment['ref']}",
            expires_at=expires_at,
        )

    async def search_recipient(self, username: str, months: int) -> str:
        data = await self._post(
            method="searchPremiumGiftRecipient",
            query=username,
            months=months,
        )
        found = _as_dict(data.get("found"), "found")
        recipient = found.get("recipient")
        if not isinstance(recipient, str) or not recipient:
            raise FragmentError("Fragment did not return a recipient for this username")
        return recipient

    async def init_gift_request(self, recipient: str, months: int) -> str:
        data = await self._post(
            method="initGiftPremiumRequest",
            recipient=recipient,
            months=months,
        )
        request_id = data.get("req_id")
        if not isinstance(request_id, str) or not request_id:
            raise FragmentError("Fragment did not return req_id")
        return request_id

    async def confirm_order(self, request_id: str, *, show_sender: bool) -> datetime:
        data = await self._post(
            method="getGiftPremiumLink",
            id=request_id,
            show_sender=1 if show_sender else 0,
        )
        expire_after = data.get("expire_after", 300)
        try:
            seconds = int(float(expire_after))
        except (TypeError, ValueError) as exc:
            raise FragmentError("Fragment returned an invalid expire_after value") from exc
        return datetime.now(timezone.utc) + timedelta(seconds=max(seconds, 1))

    async def get_raw_request(self, request_id: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    self.raw_request_url,
                    params={"id": request_id},
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise FragmentError(f"Fragment rawRequest failed: {exc}") from exc
        except ValueError as exc:
            raise FragmentError("Fragment rawRequest returned invalid JSON") from exc

        body = _as_dict(data.get("body"), "body")
        params = _as_dict(body.get("params"), "body.params")
        messages = params.get("messages")
        if not isinstance(messages, list) or not messages:
            raise FragmentError("Fragment rawRequest did not include payment messages")

        first_message = _as_dict(messages[0], "body.params.messages[0]")
        amount_ton = _nano_to_ton(first_message.get("amount"))
        payload = first_message.get("payload")
        if not isinstance(payload, str) or not payload:
            raise FragmentError("Fragment rawRequest did not include a payload")

        destination = first_message.get("address") or first_message.get("destination")
        if destination is not None and not isinstance(destination, str):
            raise FragmentError("Fragment rawRequest destination is not a string")

        decoded_payload = decode_fragment_payload(payload)
        ref = extract_ref(decoded_payload)
        if not ref:
            raise FragmentError("Could not extract Ref# from Fragment payment payload")

        return {
            "amount_ton": amount_ton,
            "destination": destination,
            "ref": ref,
        }

    async def _post(self, *, method: str, **fields: Any) -> dict[str, Any]:
        payload = {"method": method}
        payload.update({key: value for key, value in fields.items() if value is not None})

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                response = await client.post(self.api_url, data=payload, headers=self._headers())
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                raise FragmentError(f"Fragment API request failed: {exc}") from exc
            except ValueError as exc:
                raise FragmentError("Fragment API returned invalid JSON") from exc

        if isinstance(data, dict) and data.get("ok") is False:
            message = data.get("error") or data.get("message") or "Fragment request failed"
            raise FragmentError(str(message))
        if not isinstance(data, dict):
            raise FragmentError("Fragment returned a non-object response")
        return data

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": self.cookie,
            "User-Agent": "FragmentPremiumGiftBot/0.1",
            "Accept": "application/json, text/plain, */*",
        }


def normalize_username(username: str) -> str:
    username = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise FragmentError("Username must be a valid Telegram username, e.g. @example_user")
    return username


def decode_fragment_payload(payload: str) -> str:
    padded = payload + ("=" * (-len(payload) % 4))
    try:
        decoded = base64.b64decode(padded)
    except Exception:
        decoded = base64.urlsafe_b64decode(padded)
    return decoded.decode("utf-8", errors="ignore")


def extract_ref(decoded_payload: str) -> str | None:
    match = re.search(r"#([A-Za-z0-9]{8})", decoded_payload)
    if match:
        return match.group(1)
    hash_index = decoded_payload.find("#")
    if hash_index == -1:
        return None

    chars: list[str] = []
    for char in decoded_payload[hash_index + 1 :]:
        if char.isalnum():
            chars.append(char)
        if len(chars) == 8:
            return "".join(chars)
    return None


def _as_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FragmentError(f"Fragment response field {field_name} is invalid")
    return value


def _nano_to_ton(value: Any) -> Decimal:
    if value is None:
        raise FragmentError("Fragment rawRequest did not include an amount")
    try:
        nano = Decimal(str(value))
    except InvalidOperation as exc:
        raise FragmentError("Fragment rawRequest amount is invalid") from exc
    amount = nano / Decimal("1000000000")
    if amount <= 0:
        raise FragmentError("Fragment rawRequest amount must be greater than zero")
    return amount
