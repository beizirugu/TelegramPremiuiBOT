from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .config import Settings
from .fragment import FragmentClient, FragmentError, PremiumOrder
from .ton import TonPaymentClient, TonPaymentError

LOGGER = logging.getLogger(__name__)


@dataclass
class PendingOrder:
    order: PremiumOrder
    created_by: int
    expires_at: datetime
    paying: bool = False


class PremiumBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fragment = FragmentClient(
            fragment_hash=settings.fragment_hash,
            cookie=settings.fragment_cookie,
            timeout=settings.request_timeout,
        )
        self.ton = TonPaymentClient(
            mnemonic=settings.wallet_mnemonic,
            api_key=settings.toncenter_api_key,
            is_testnet=settings.ton_testnet,
            timeout=settings.request_timeout,
        )
        self.pending_orders: dict[str, PendingOrder] = {}

    def run(self) -> None:
        application = Application.builder().token(self.settings.telegram_bot_token).build()
        application.add_handler(CommandHandler(["start", "help"], self.help_command))
        application.add_handler(CommandHandler("open", self.open_command))
        application.add_handler(CommandHandler("wallet", self.wallet_command))
        application.add_handler(CommandHandler("config", self.config_command))
        application.add_handler(CallbackQueryHandler(self.callback_handler))

        LOGGER.info("Bot started. Dry run: %s", self.settings.payment_dry_run)
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return
        durations = ", ".join(str(item) for item in sorted(self.settings.allowed_durations))
        mode = "dry-run 模拟付款" if self.settings.payment_dry_run else "真实付款"
        text = (
            "Fragment Premium Gift Bot\n\n"
            f"当前模式：{mode}\n"
            f"支持月份：{durations}\n\n"
            "命令：\n"
            "/open @username 3 - 创建订单并等待确认\n"
            "/wallet - 查看付款钱包地址\n"
            "/config - 查看非敏感配置"
        )
        await update.effective_message.reply_text(text)

    async def open_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return
        if not update.effective_user or not update.effective_message:
            return

        if len(context.args) != 2:
            await update.effective_message.reply_text("用法：/open @username 3")
            return

        username = context.args[0]
        try:
            months = int(context.args[1])
        except ValueError:
            await update.effective_message.reply_text("月份必须是数字，例如：/open @username 3")
            return

        if months not in self.settings.allowed_durations:
            allowed = ", ".join(str(item) for item in sorted(self.settings.allowed_durations))
            await update.effective_message.reply_text(f"不支持这个月份，可用：{allowed}")
            return

        progress = await update.effective_message.reply_text("正在向 Fragment 创建订单，请稍等...")
        try:
            order = await self.fragment.create_premium_order(
                username=username,
                months=months,
                show_sender=self.settings.show_sender,
            )
            self._validate_order(order)
        except (FragmentError, ValueError) as exc:
            LOGGER.exception("Failed to create premium order")
            await progress.edit_text(f"创建订单失败：{exc}")
            return

        token = secrets.token_urlsafe(8)
        ttl_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.confirm_ttl_seconds
        )
        expires_at = min(order.expires_at, ttl_expires_at)
        self.pending_orders[token] = PendingOrder(
            order=order,
            created_by=update.effective_user.id,
            expires_at=expires_at,
        )

        mode = "模拟付款，不会转账" if self.settings.payment_dry_run else "真实付款，会发送 TON"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("确认付款", callback_data=f"pay:{token}"),
                    InlineKeyboardButton("取消", callback_data=f"cancel:{token}"),
                ]
            ]
        )
        await progress.edit_text(
            self._order_summary(order, mode=mode),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    async def wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return
        if not self.settings.wallet_mnemonic:
            await update.effective_message.reply_text(
                "当前未配置 WALLET_MNEMONIC。dry-run 可以不填，真实付款必须填写。"
            )
            return
        try:
            address = await self.ton.wallet_address()
        except TonPaymentError as exc:
            await update.effective_message.reply_text(f"读取钱包失败：{exc}")
            return
        await update.effective_message.reply_text(f"钱包地址：\n{address}")

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._ensure_admin(update):
            return
        durations = ", ".join(str(item) for item in sorted(self.settings.allowed_durations))
        text = (
            "当前配置：\n"
            f"PAYMENT_DRY_RUN={self.settings.payment_dry_run}\n"
            f"ALLOWED_DURATIONS={durations}\n"
            f"MAX_TON_AMOUNT={format_ton(self.settings.max_ton_amount)} TON\n"
            f"TON_TESTNET={self.settings.ton_testnet}\n"
            f"STRICT_FRAGMENT_WALLET={self.settings.strict_fragment_wallet}\n"
            f"SHOW_SENDER={self.settings.show_sender}"
        )
        await update.effective_message.reply_text(text)

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        if not await self._ensure_admin(update, callback=True):
            return

        data = query.data or ""
        action, _, token = data.partition(":")
        pending = self.pending_orders.get(token)
        if not pending:
            await query.edit_message_text("这个订单已经不存在或已处理。")
            return
        if pending.expires_at <= datetime.now(timezone.utc):
            self.pending_orders.pop(token, None)
            await query.edit_message_text("这个订单已经过期，请重新创建。")
            return

        if action == "cancel":
            self.pending_orders.pop(token, None)
            await query.edit_message_text("订单已取消。")
            return
        if action != "pay":
            await query.edit_message_text("未知操作。")
            return
        if pending.paying:
            await query.edit_message_text("这笔订单正在处理，请不要重复点击。")
            return

        pending.paying = True
        order = pending.order
        destination = order.destination or self.settings.fragment_wallet_address
        if self.settings.payment_dry_run:
            self.pending_orders.pop(token, None)
            await query.edit_message_text(
                "dry-run 完成，没有发送链上交易。\n\n" + self._plain_order_summary(order)
            )
            return

        try:
            result = await self.ton.transfer(
                destination=destination,
                amount=order.amount_ton,
                comment=order.comment,
            )
        except TonPaymentError as exc:
            pending.paying = False
            LOGGER.exception("TON transfer failed")
            await query.edit_message_text(f"付款失败：{exc}")
            return

        self.pending_orders.pop(token, None)
        await query.edit_message_text(
            "付款已发送。\n"
            f"交易 Hash：{result.tx_hash}\n"
            f"查看交易：{result.explorer_url}"
        )

    async def _ensure_admin(self, update: Update, *, callback: bool = False) -> bool:
        user = update.effective_user
        allowed = bool(user and user.id in self.settings.telegram_admin_ids)
        if allowed:
            return True

        target = update.callback_query.message if callback and update.callback_query else update.effective_message
        if target:
            await target.reply_text("你没有权限使用这个 bot。")
        return False

    def _validate_order(self, order: PremiumOrder) -> None:
        if order.amount_ton > self.settings.max_ton_amount:
            raise ValueError(
                f"订单金额 {format_ton(order.amount_ton)} TON 超过 MAX_TON_AMOUNT"
            )
        if self.settings.strict_fragment_wallet and order.destination:
            expected = self.settings.fragment_wallet_address
            if order.destination != expected:
                raise ValueError("Fragment 返回的收款地址与 FRAGMENT_WALLET_ADDRESS 不一致")

    def _order_summary(self, order: PremiumOrder, *, mode: str) -> str:
        destination = order.destination or self.settings.fragment_wallet_address
        return (
            "<b>订单已创建，等待确认</b>\n\n"
            f"用户：@{order.username}\n"
            f"月份：{order.months}\n"
            f"金额：{format_ton(order.amount_ton)} TON\n"
            f"收款地址：<code>{destination}</code>\n"
            f"付款备注：<code>{order.comment}</code>\n"
            f"模式：{mode}\n"
            f"过期时间：{order.expires_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def _plain_order_summary(self, order: PremiumOrder) -> str:
        destination = order.destination or self.settings.fragment_wallet_address
        return (
            f"用户：@{order.username}\n"
            f"月份：{order.months}\n"
            f"金额：{format_ton(order.amount_ton)} TON\n"
            f"收款地址：{destination}\n"
            f"付款备注：{order.comment}"
        )


def format_ton(amount: Decimal) -> str:
    normalized = amount.normalize()
    return format(normalized, "f")
