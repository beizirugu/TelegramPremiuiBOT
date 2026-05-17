from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from urllib.parse import quote


class TonPaymentError(RuntimeError):
    """Raised when TON payment cannot be sent."""


@dataclass(frozen=True)
class PaymentResult:
    tx_hash: str
    explorer_url: str


class TonPaymentClient:
    def __init__(
        self,
        *,
        mnemonic: str,
        api_key: str | None,
        is_testnet: bool,
        timeout: float = 20,
    ) -> None:
        self.mnemonic = mnemonic
        self.api_key = api_key
        self.is_testnet = is_testnet
        self.timeout = timeout

    async def wallet_address(self) -> str:
        client, wallet = self._wallet()
        try:
            return wallet.address.to_str()
        finally:
            await client.close()

    async def transfer(self, *, destination: str, amount: Decimal, comment: str) -> PaymentResult:
        if not self.mnemonic:
            raise TonPaymentError("WALLET_MNEMONIC is required for real payments")

        client, wallet = self._wallet()
        try:
            external_message = await wallet.transfer(
                destination=destination,
                amount=to_nanotons(amount),
                body=comment,
            )
        except Exception as exc:  # pragma: no cover - depends on external TON provider.
            raise TonPaymentError(str(exc)) from exc
        finally:
            await client.close()

        tx_hash_text = str(external_message.normalized_hash)
        return PaymentResult(
            tx_hash=tx_hash_text,
            explorer_url=f"https://tonscan.org/tx/{quote(tx_hash_text, safe='')}",
        )

    def _wallet(self):
        try:
            from ton_core.contrib.types import NetworkGlobalID
            from tonutils.clients.http import ToncenterClient
            from tonutils.contracts.wallet import WalletV4R2
        except ImportError as exc:  # pragma: no cover - only triggered without dependencies.
            raise TonPaymentError(
                "Missing tonutils dependency. Install requirements.txt before running real payments."
            ) from exc

        network = NetworkGlobalID.TESTNET if self.is_testnet else NetworkGlobalID.MAINNET
        client = ToncenterClient(
            network,
            api_key=self.api_key,
            timeout=self.timeout,
            rps_limit=1,
        )
        wallet, _public_key, _private_key, _mnemonic = WalletV4R2.from_mnemonic(
            client,
            self.mnemonic,
        )
        return client, wallet


def to_nanotons(amount: Decimal) -> int:
    nanotons = (amount * Decimal("1000000000")).to_integral_value(rounding=ROUND_DOWN)
    value = int(nanotons)
    if value <= 0:
        raise TonPaymentError("TON amount is too small")
    return value
