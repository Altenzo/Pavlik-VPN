import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from apps.db.models.user import User
from apps.db.models.transaction import Transaction
from apps.db.models.promo_code import PromoCode
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.keyboards.subscriptions import get_subscriptions_keyboard, get_payment_methods_keyboard
from bot.keyboards.common import get_back_keyboard, get_back_to_profile_keyboard
from bot.keyboards.profile_kb import get_profile_keyboard
from bot.keyboards.trial_kb import get_trial_confirmation_keyboard
from bot.keyboards.referral_kb import get_referral_keyboard
from bot.keyboards.payment_kb import get_payment_keyboard
from apps.services.payment.platega_service import PlategaService
from apps.services.payment.heleket_service import HeleketService
from apps.services.vpn.remnawave_service import RemnawaveService, format_bytes
from apps.db.repositories.transaction import (
    create_transaction,
    get_transaction,
    get_pending_transaction,
    update_transaction_id,
    update_transaction_status,
)
from apps.db.repositories.promo_code import (
    get_promo_by_code,
    has_user_used_promo,
    record_promo_usage,
)
from config import config

import logging
logger = logging.getLogger(__name__)

menu_router = Router()

_payment_locks: dict[int, asyncio.Lock] = {}

platega = PlategaService(config.PLATEGA_MERCHANT_ID, config.PLATEGA_SECRET)
heleket = HeleketService(config.HELEKET_MERCHANT_ID, config.HELEKET_API_KEY)
remnawave = RemnawaveService(
    panel_url=config.PANEL_URL,
    api_token=config.PANEL_API_TOKEN,
    inbound_uuid=config.PANEL_INBOUND_UUID,
    internal_squad_uuids=config.INTERNAL_SQUAD_UUIDS,
    external_squad_uuid=config.EXTERNAL_SQUAD_UUID,
)

TARIFF_DAYS = {
    "month_1": 30,
    "month_3": 90,
    "month_6": 180,
    "month_12": 365,
}

MAIN_TEXT = (
    "<tg-emoji emoji-id=\"5258152182150077732\">⚡</tg-emoji> <b>Blago VPN — Ваш персональный ключ к свободе.</b>\n\n"
    "Забудьте о границах в интернете. Мы обеспечиваем сверхбыстрое соединение, абсолютную анонимность и доступ к любому контенту в один клик.\n\n"
    "<tg-emoji emoji-id=\"5260221883940347555\">🚀</tg-emoji> <b>Наши преимущества:</b>\n"
    "  •  <b>Скорость:</b> До 1 Гбит/с без задержек.\n"
    "  •  <b>Приватность:</b> Мы уважаем твое право на частную жизнь и не храним историю твоих действий.\n"
    "  •  <b>Простота:</b> Настройка за 30 секунд прямо в Telegram.\n\n"
    "<i>Ваша безопасность — наша работа. Подключайтесь и летайте!</i>"
)

MAIN_TEXT_EN = (
    "<tg-emoji emoji-id=\"5258152182150077732\">⚡</tg-emoji> <b>Blago VPN — Your Personal Key to Freedom.</b>\n\n"
    "Forget about internet restrictions. We provide ultra-fast connection, complete anonymity and access to any content in one click.\n\n"
    "<tg-emoji emoji-id=\"5260221883940347555\">🚀</tg-emoji> <b>Our advantages:</b>\n"
    "  •  <b>Speed:</b> Up to 1 Gbit/s without delays.\n"
    "  •  <b>Privacy:</b> We respect your right to privacy and don't store your activity history.\n"
    "  •  <b>Simplicity:</b> Setup in 30 seconds directly in Telegram.\n\n"
    "<i>Your security is our job. Connect and fly!</i>"
)


def _main_text(language: str) -> str:
    return MAIN_TEXT_EN if language == "en" else MAIN_TEXT


# ─── FSM: активация промокода пользователем ──────────────────────
class PromoActivation(StatesGroup):
    enter_code = State()


# ──────────────────────────────────────────────
# Профиль
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258011929993026890\">👤</tg-emoji> <b>Привет, {user.full_name}!</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n",
        reply_markup=get_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "history_tx")
async def show_history_tx(callback: types.CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.status == "CONFIRMED"
    ).order_by(Transaction.id.desc()).limit(10)
    result = await session.execute(stmt)
    transactions = result.scalars().all()

    history_text = "\n".join([
        f"• {tx.tariff_key}: {tx.amount}₽ ({tx.created_at.strftime('%d.%m.%Y')})"
        for tx in transactions
    ]) or "• История пока пуста"

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258419835922030550\">📜</tg-emoji> <b>История ваших транзакций</b>\n\n"
        f"{history_text}\n",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


def _my_subs_keyboard(can_refresh: bool) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_refresh:
        builder.row(InlineKeyboardButton(text="🔄 Обновить ссылку", callback_data="refresh_link"))
    builder.row(InlineKeyboardButton(
        text="Назад", callback_data="profile",
        icon_custom_emoji_id="5258236805890710909", style="danger"
    ))
    return builder.as_markup()


def _format_sub_status(user: User) -> str:
    now = datetime.now()
    if user.subscription_end and user.subscription_end > now:
        days_left = (user.subscription_end - now).days
        return (
            f"✅ Активна\n"
            f"Истекает: <b>{user.subscription_end.strftime('%d.%m.%Y %H:%M')}</b> (осталось {days_left} д.)"
        )
    if user.subscription_end:
        return "⚠️ Истекла"
    return "❌ Не активна"


async def _build_my_subs_text(user: User) -> str:
    sub_status = _format_sub_status(user)

    traffic_text = ""
    devices_text = ""
    if user.vpn_uuid:
        vpn_info = await remnawave.get_user(user.vpn_uuid)
        if vpn_info:
            used = format_bytes(vpn_info.used_traffic_bytes)
            limit = (
                format_bytes(vpn_info.traffic_limit_bytes)
                if vpn_info.traffic_limit_bytes > 0 else "∞"
            )
            traffic_text = f"\n\n📊 <b>Трафик:</b> {used} / {limit}"

        devices = await remnawave.get_user_devices(user.vpn_uuid)
        if devices:
            lines = []
            for i, dev in enumerate(devices, 1):
                label = dev.device_model or dev.platform or "Устройство"
                meta = []
                if dev.platform and dev.device_model:
                    meta.append(dev.platform)
                if dev.created_at:
                    meta.append(f"подкл. {dev.created_at.strftime('%d.%m.%Y')}")
                meta_text = f" ({', '.join(meta)})" if meta else ""
                lines.append(f"  {i}. {label}{meta_text}")
            devices_text = (
                f"\n\n📱 <b>Устройства ({len(devices)}):</b>\n" + "\n".join(lines)
            )
        else:
            devices_text = "\n\n📱 <b>Устройства:</b> пока не подключались"

    vless_text = ""
    if user.vless_link and user.is_active:
        vless_text = f"\n\n<b>Ссылка для подключения:</b>\n<code>{user.vless_link}</code>"

    return (
        f"<b>Ваши подписки</b>\n\n"
        f"Статус: {sub_status}"
        f"{traffic_text}"
        f"{devices_text}"
        f"{vless_text}"
    )


@menu_router.callback_query(F.data == "my_subs")
async def show_my_subs(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.")
        return

    can_refresh = bool(user.vless_link and user.is_active and user.vpn_uuid)
    text = await _build_my_subs_text(user)

    await callback.message.edit_text(
        text,
        reply_markup=_my_subs_keyboard(can_refresh),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "refresh_link")
async def refresh_link(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    if not (user.vpn_uuid and user.is_active and user.subscription_end):
        await callback.answer("❌ Активная подписка не найдена.", show_alert=True)
        return

    if user.subscription_end <= datetime.now():
        await callback.answer("❌ Подписка истекла, продлите её.", show_alert=True)
        return

    await callback.answer("⏳ Генерируем новую ссылку...")

    # Сначала синхронизируем срок действия в панели — иначе после revoke
    # клиент может получить "expired", если в Remnawave expireAt отстал от БД.
    extended = await remnawave.extend_user(user.vpn_uuid, new_expire_dt=user.subscription_end)
    if not extended:
        logger.warning(f"refresh_link: extend_user failed для user={user.id}")

    vpn_user = await remnawave.revoke_subscription(user.vpn_uuid)
    if not vpn_user:
        await callback.answer("❌ Не удалось обновить ссылку. Попробуйте позже.", show_alert=True)
        return

    # Повторно фиксируем срок и активируем пользователя — на случай,
    # если revoke сбросил expireAt или статус.
    await remnawave.extend_user(user.vpn_uuid, new_expire_dt=user.subscription_end)
    await remnawave.enable_user(user.vpn_uuid)

    user.vless_link = vpn_user.subscription_url
    await session.commit()

    text = await _build_my_subs_text(user)
    await callback.message.edit_text(
        text,
        reply_markup=_my_subs_keyboard(can_refresh=True),
        parse_mode="HTML"
    )


@menu_router.callback_query(F.data == "user_agreement")
async def show_user_agreement(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📄 Пользовательское соглашение", url="https://telegra.ph/POLZOVATELSKOE-SOGLASHENIE-03-30-18")
    )
    builder.row(
        InlineKeyboardButton(text="🔒 Политика конфиденциальности", url="https://telegra.ph/Politika-konfidencialnosti-04-03-41")
    )
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data="profile", icon_custom_emoji_id="5258236805890710909", style="danger")
    )

    await callback.message.edit_text(
        "<b>📄 Документы</b>\n\nНажмите на нужный документ чтобы ознакомиться:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ──────────────────────────────────────────────
# Рефералы
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "referrals")
async def show_referrals(callback: types.CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return

    stmt1 = select(func.count(User.id)).where(User.referred_by == user_id)
    lvl1_count = (await session.execute(stmt1)).scalar() or 0

    bot_username = (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    await callback.message.edit_text(
        f"<b>👥 Реферальная система</b>\n\n"
        f"Приглашайте друзей и получайте <b>{int(config.REFERRAL_COMMISSION_RATE * 100)}%</b> с их покупок!\n\n"
        f"Ваша ссылка: <code>{ref_link}</code>\n\n"
        f"Рефералов: <b>{lvl1_count}</b>\n"
        f"Заработано всего: <b>{user.total_earned:.2f} ₽</b>\n"
        f"Доступно для вывода: <b>{user.referral_balance:.2f} ₽</b>\n\n"
        f"Для вывода обратитесь в поддержку.",
        reply_markup=get_referral_keyboard(ref_link),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "withdraw_referral")
async def withdraw_referral(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return
    if user.referral_balance < 1000:
        await callback.answer(
            f"❌ Минимальная сумма вывода — 1000 ₽\nВаш баланс: {user.referral_balance:.2f} ₽",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        f"<b>💰 Вывод средств</b>\n\n"
        f"Ваш баланс: <b>{user.referral_balance:.2f} ₽</b>\n\n"
        f"Для выплаты на USDT TRC-20 свяжитесь с поддержкой, укажите ваш ID: <code>{user.id}</code>.\n\n"
        f"Поддержка: {config.SUPPORT_USERNAME}",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ──────────────────────────────────────────────
# Покупка подписки
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "buy_subscription")
async def select_subscription(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    promo_note = ""
    if user and user.active_promo_code_id:
        promo = await session.get(PromoCode, user.active_promo_code_id)
        if promo and promo.is_active and (not promo.expires_at or promo.expires_at > datetime.now()):
            promo_note = f"\n\n🎟 Активен промокод <b>{promo.code}</b> — скидка <b>{promo.discount}%</b>"

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258123337149717894\">📦</tg-emoji> <b>Выберите срок подписки:</b>{promo_note}",
        reply_markup=get_subscriptions_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data.startswith("select_sub:"))
async def process_select_sub(callback: types.CallbackQuery):
    _, tariff_key, amount = callback.data.split(":")
    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5409048419211682843\">💲</tg-emoji> <b>Шаг 2: Способ оплаты</b>\n\n"
        f"Тариф: <b>{tariff_key}</b>\nК оплате: <b>{amount} ₽</b>",
        reply_markup=get_payment_methods_keyboard(tariff_key, amount),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data.startswith("buy:"))
async def process_buy_tariff(callback: types.CallbackQuery, session: AsyncSession):
    data = callback.data.split(":")
    tariff_key, amount, method = data[1], data[2], data[3]
    amount = float(amount)
    base_amount = amount  # сохраняем исходную цену до скидки

    if method == "crypto" and not (config.HELEKET_MERCHANT_ID and config.HELEKET_API_KEY):
        await callback.answer(
            "🛑 Криптовалюта временно недоступна. Используйте СБП.",
            show_alert=True
        )
        return

    # Загружаем пользователя
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: пользователь не найден.", show_alert=True)
        return

    # Проверяем активный промокод
    promo = None
    discount_text = ""

    if user.active_promo_code_id:
        promo = await session.get(PromoCode, user.active_promo_code_id)
        if promo and promo.is_active and (not promo.expires_at or promo.expires_at > datetime.now()):
            original_amount = amount
            amount = round(amount * (1 - promo.discount / 100), 2)
            saved = round(original_amount - amount, 2)
            discount_text = f"\n🎟 Промокод <b>{promo.code}</b>: -{promo.discount}% (-{saved:.0f} ₽)"
        else:
            # Промокод просрочен или неактивен — убираем
            user.active_promo_code_id = None
            await session.commit()
            promo = None

    await callback.message.edit_text("⏳ <b>Формируем счет...</b>", parse_mode="HTML")

    # Проверяем существующий незавершённый платёж
    existing_tx = await get_pending_transaction(session, callback.from_user.id)
    if existing_tx:
        if existing_tx.external_id and existing_tx.redirect_url:
            # Реальный незавершённый платёж — показываем кнопку возврата
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text="💳 Вернуться к оплате",
                url=existing_tx.redirect_url
            ))
            builder.row(InlineKeyboardButton(
                text="🔄 Отменить и создать новый",
                callback_data=f"cancel_pending:{existing_tx.id}:{tariff_key}:{base_amount}:{method}"
            ))
            builder.row(InlineKeyboardButton(
                text="◀️ Назад", callback_data="back_to_main",
                icon_custom_emoji_id="5258236805890710909", style="danger"
            ))
            await callback.message.edit_text(
                f"<b>У вас есть незавершённый платёж.</b>\n\n"
                f"Тариф: <b>{existing_tx.tariff_key}</b>\n"
                f"Сумма: <b>{existing_tx.amount} ₽</b>\n\n"
                f"Вернитесь к оплате или отмените и создайте новый:",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        else:
            # Мёртвая транзакция (провайдер не ответил) — отменяем автоматически
            await update_transaction_status(session, existing_tx.id, "EXPIRED")

    await _create_invoice_and_show(callback, session, tariff_key, amount, method, discount_text)


async def _create_invoice_and_show(
    callback: types.CallbackQuery,
    session: AsyncSession,
    tariff_key: str,
    amount: float,
    method: str,
    discount_text: str,
):
    """
    Создаёт транзакцию у выбранного провайдера (СБП → Platega, крипта → Heleket),
    сохраняет external_id, ставит задачу авто-подтверждения и показывает счёт.
    """
    tx = await create_transaction(
        session, callback.from_user.id, amount, tariff_key, payment_method=method
    )

    if method == "crypto":
        payment_data = await heleket.create_transaction(
            amount=amount,
            description=f"VPN: {tariff_key}",
            order_id=str(tx.id),
            callback_url=config.HELEKET_CALLBACK_URL,
        )
        external_id = payment_data.get("uuid") if payment_data else None
        pay_url = payment_data.get("url") if payment_data else None
        method_label = "Криптовалюта"
    else:
        payment_data = await platega.create_transaction(
            amount, f"VPN: {tariff_key}", str(tx.id)
        )
        external_id = payment_data.get("transactionId") if payment_data else None
        pay_url = payment_data.get("redirect") if payment_data else None
        method_label = "СБП"

    if not payment_data or not external_id or not pay_url:
        await update_transaction_status(session, tx.id, "EXPIRED")
        await callback.message.edit_text(
            "<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> <b>Ошибка при создании счета.</b>\n"
            "Попробуйте позже или выберите другой способ.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        return

    await update_transaction_id(session, tx.id, external_id, redirect_url=pay_url)

    from apps.db.database import async_session as _async_session
    asyncio.create_task(
        _auto_confirm_payment(callback.message, tx.id, external_id, _async_session, method)
    )

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258477770735885832\">📄</tg-emoji> <b>Счет сформирован!</b>\n\n"
        f"Сумма: <b>{amount} ₽</b> | Метод: <b>{method_label}</b>{discount_text}\n\n"
        f"Нажмите кнопку ниже чтобы оплатить.",
        reply_markup=get_payment_keyboard(pay_url, str(tx.id)),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data.startswith("cancel_pending:"))
async def cancel_pending_and_create(callback: types.CallbackQuery, session: AsyncSession):
    """Отменяет текущий незавершённый платёж и сразу создаёт новый."""
    parts = callback.data.split(":")
    old_tx_id = int(parts[1])
    tariff_key = parts[2]
    amount = float(parts[3])
    method = parts[4]

    await update_transaction_status(session, old_tx_id, "CANCELED")

    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: пользователь не найден.", show_alert=True)
        return

    # Применяем промокод если есть
    promo = None
    discount_text = ""
    if user.active_promo_code_id:
        promo = await session.get(PromoCode, user.active_promo_code_id)
        if promo and promo.is_active and (not promo.expires_at or promo.expires_at > datetime.now()):
            original_amount = amount
            amount = round(amount * (1 - promo.discount / 100), 2)
            saved = round(original_amount - amount, 2)
            discount_text = f"\n🎟 Промокод <b>{promo.code}</b>: -{promo.discount}% (-{saved:.0f} ₽)"
        else:
            user.active_promo_code_id = None
            await session.commit()
            promo = None

    await callback.message.edit_text("⏳ <b>Формируем счет...</b>", parse_mode="HTML")
    await _create_invoice_and_show(callback, session, tariff_key, amount, method, discount_text)


async def _auto_confirm_payment(
    message: types.Message,
    tx_id: int,
    external_id: str,
    session_maker,
    method: str = "sbp",
):
    provider = heleket if method == "crypto" else platega
    # 90 раз по 20 сек = 30 минут
    for _ in range(90):
        await asyncio.sleep(20)
        try:
            status = await provider.check_status(external_id)
        except Exception as e:
            logger.error(f"check_status error tx={tx_id}: {e}")
            continue

        if status == "CONFIRMED":
            async with session_maker() as session:
                await _activate_subscription_after_payment(session, tx_id)
            try:
                await message.edit_text(
                    "<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> <b>Оплата подтверждена!</b>\nВаша подписка активирована. Ссылку ищите в Профиле → Мои подписки.",
                    reply_markup=get_back_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                try:
                    await message.answer(
                        "<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> <b>Оплата подтверждена!</b>\nВаша подписка активирована. Ссылку ищите в Профиле → Мои подписки.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            return

        if status in ("CANCELED", "FAILED"):
            async with session_maker() as session:
                await update_transaction_status(session, tx_id, status)
            try:
                await message.edit_text(
                    f"<b>Платёж отклонён.</b> Статус: <b>{status}</b>",
                    reply_markup=get_back_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

    async with session_maker() as session:
        await update_transaction_status(session, tx_id, "EXPIRED")
    try:
        await message.edit_text(
            f"⏰ <b>Время ожидания оплаты истекло.</b>\n\nЕсли вы оплатили — обратитесь в поддержку: {config.SUPPORT_USERNAME}",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        pass


async def _activate_subscription_after_payment(session: AsyncSession, tx_id: int):
    lock = _payment_locks.setdefault(tx_id, asyncio.Lock())
    try:
        async with lock:
            await _activate_subscription_inner(session, tx_id)
    finally:
        _payment_locks.pop(tx_id, None)


async def _activate_subscription_inner(session: AsyncSession, tx_id: int):
    tx = await get_transaction(session, tx_id)
    if not tx or tx.status == "CONFIRMED":
        return

    await update_transaction_status(session, tx_id, "CONFIRMED")

    user = await session.get(User, tx.user_id)
    if not user:
        return

    days = TARIFF_DAYS.get(tx.tariff_key, 30)
    now = datetime.now()

    if user.vpn_uuid:
        current_end = user.subscription_end if (user.subscription_end and user.subscription_end > now) else now
        new_end = current_end + timedelta(days=days)
        user.subscription_end = new_end
        user.is_active = True
        ok = await remnawave.extend_user(user.vpn_uuid, new_expire_dt=new_end)
        if not ok:
            logger.warning(f"Remnawave extend_user failed для user={user.id}, подписка обновлена только в БД")
    else:
        new_end = now + timedelta(days=days)
        user.subscription_end = new_end
        user.is_active = True
        vpn_user = await remnawave.create_user(telegram_id=user.id, days=days)
        if vpn_user:
            user.vpn_uuid = vpn_user.uuid
            user.vless_link = vpn_user.subscription_url
        else:
            logger.warning(f"Remnawave create_user failed для user={user.id}, подписка обновлена только в БД")

    # Фиксируем использование промокода
    if user.active_promo_code_id:
        await record_promo_usage(session, user.active_promo_code_id, user.id)
        user.active_promo_code_id = None

    await session.commit()


# ──────────────────────────────────────────────
# Промокод (активация пользователем)
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "promo_code")
async def show_promo_code(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PromoActivation.enter_code)
    await callback.message.edit_text(
        "<tg-emoji emoji-id=\"5359719332542718652\">🎟</tg-emoji> <b>Активация промокода</b>\n\n"
        "Введите промокод в ответном сообщении:",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.message(StateFilter(PromoActivation.enter_code))
async def activate_promo_code(message: types.Message, state: FSMContext, session: AsyncSession):
    code = (message.text or "").strip().upper()

    if not code:
        await message.answer("❌ Введите название промокода.")
        return

    user = await session.get(User, message.from_user.id)
    if not user:
        await state.clear()
        return

    promo = await get_promo_by_code(session, code)

    if not promo or not promo.is_active:
        await message.answer(
            "❌ <b>Промокод не найден</b> или недействителен.\n\nПроверьте правильность ввода.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    now = datetime.now()
    if promo.expires_at and promo.expires_at < now:
        await message.answer(
            "❌ <b>Срок действия промокода истёк.</b>",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    if promo.max_activations is not None and promo.current_activations >= promo.max_activations:
        await message.answer(
            "❌ <b>Промокод исчерпан</b> — все активации уже использованы.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    already_used = await has_user_used_promo(session, promo.id, user.id)
    if already_used:
        await message.answer(
            "❌ Вы уже использовали этот промокод.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Все проверки пройдены — сохраняем промокод и сбрасываем состояние
    user.active_promo_code_id = promo.id
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ <b>Промокод активирован!</b>\n\n"
        f"🎟 Код: <code>{promo.code}</code>\n"
        f"💰 Скидка: <b>{promo.discount}%</b>\n\n"
        f"Скидка будет применена при следующей покупке.\nВыберите тариф:",
        reply_markup=get_subscriptions_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
# Язык
# ──────────────────────────────────────────────

@menu_router.message(Command("lang"))
async def cmd_lang(message: types.Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        return
    await _show_lang_selection(message, user, edit=False)


@menu_router.callback_query(F.data == "select_lang")
async def show_lang_selection_cb(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer()
        return
    await _show_lang_selection(callback.message, user, edit=True)
    await callback.answer()


async def _show_lang_selection(msg: types.Message, user: User, edit: bool):
    lang = getattr(user, "language", "ru")
    if lang == "en":
        current = "🇬🇧 English"
        title = "🌐 <b>Interface language</b>"
        current_label = "Current language"
        choose_label = "Choose language:"
        back_label = "◀️ Back"
    else:
        current = "🇷🇺 Русский"
        title = "🌐 <b>Язык интерфейса</b>"
        current_label = "Текущий язык"
        choose_label = "Выберите язык:"
        back_label = "◀️ Назад"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en"),
    )
    builder.row(InlineKeyboardButton(
        text=back_label, callback_data="back_to_main",
        icon_custom_emoji_id="5258236805890710909", style="danger"
    ))
    text = f"{title}\n\n{current_label}: <b>{current}</b>\n\n{choose_label}"
    if edit:
        await msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@menu_router.callback_query(F.data.startswith("set_lang:"))
async def set_language(callback: types.CallbackQuery, session: AsyncSession):
    lang = callback.data.split(":")[1]
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer()
        return

    user.language = lang
    await session.commit()

    if lang == "en":
        alert_text = "✅ Language changed: 🇬🇧 English"
    else:
        alert_text = "✅ Язык изменён: 🇷🇺 Русский"

    await callback.answer(alert_text, show_alert=True)

    await callback.message.edit_text(
        _main_text(lang),
        reply_markup=get_main_menu_keyboard(user, language=lang),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
# Триал
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "confirm_trial_request")
async def show_trial_confirmation(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return
    if user.trial_used:
        await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
        return

    end_date = (datetime.now() + timedelta(days=config.TRIAL_DAYS)).strftime("%d.%m.%Y %H:%M")
    await callback.message.edit_text(
        f"<b>Активация пробного периода</b>\n\n"
        f"Бесплатный доступ на <b>{config.TRIAL_DAYS} дн.</b> до <b>{end_date}</b>.\n\n"
        f"Активировать можно только <b>один раз</b>.",
        reply_markup=get_trial_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "claim_trial")
async def claim_trial(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return

    if user.trial_used:
        await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
        return

    await callback.message.edit_text("⏳ <b>Активируем доступ...</b>", parse_mode="HTML")

    vpn_user = await remnawave.create_user(telegram_id=user.id, days=config.TRIAL_DAYS)

    now = datetime.now()
    new_end = now + timedelta(days=config.TRIAL_DAYS)

    if vpn_user:
        user.vpn_uuid = vpn_user.uuid
        user.vless_link = vpn_user.subscription_url
        user.is_active = True
        link_text = f"\n\n<b>Ссылка для подключения:</b>\n<code>{vpn_user.subscription_url}</code>"
        extra_msg = "\nСкопируйте ссылку и импортируйте в <b>v2rayNG</b> (Android) или <b>FoXray</b> (iOS)."
    else:
        link_text = ""
        extra_msg = "\n\nСсылку для подключения мы выдадим в течение нескольких минут — следите за уведомлениями."

    if user.subscription_end and user.subscription_end > now:
        user.subscription_end += timedelta(days=config.TRIAL_DAYS)
    else:
        user.subscription_end = new_end

    user.trial_used = True
    await session.commit()

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> <b>Пробный период активирован!</b>\n\n"
        f"Доступ выдан на <b>{config.TRIAL_DAYS} дн.</b> до <b>{user.subscription_end.strftime('%d.%m.%Y %H:%M')}</b>."
        f"{link_text}{extra_msg}",
        reply_markup=get_main_menu_keyboard(user, language=getattr(user, "language", "ru")),
        parse_mode="HTML"
    )
    await callback.answer("✅ Подписка активирована!", show_alert=True)


# ──────────────────────────────────────────────
# Инструкции
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "instructions")
async def show_instructions(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Android", callback_data="instr:android", icon_custom_emoji_id="5359575107540892257"),
        InlineKeyboardButton(text="iOS", callback_data="instr:ios", icon_custom_emoji_id="5359840360426126173")
    )
    builder.row(
        InlineKeyboardButton(text="Windows", callback_data="instr:windows", icon_custom_emoji_id="5359700310132536945"),
        InlineKeyboardButton(text="macOS", callback_data="instr:macos", icon_custom_emoji_id="5359661453563414473")
    )
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5258236805890710909", style="danger")
    )

    await callback.message.edit_text(
        "<b>Инструкция по подключению</b>\n\nВыберите вашу платформу:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data.startswith("instr:"))
async def show_platform_apps(callback: types.CallbackQuery):
    platform = callback.data.split(":")[1]
    platform_names = {
        "android": "Android",
        "ios": "iOS",
        "windows": "Windows",
        "macos": "macOS",
    }

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Happ", callback_data=f"app:{platform}:happ"),
        InlineKeyboardButton(text="V2RayTun", callback_data=f"app:{platform}:v2raytun")
    )
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data="instructions", icon_custom_emoji_id="5258236805890710909", style="danger")
    )

    await callback.message.edit_text(
        f"<b>{platform_names.get(platform, platform)}</b>\n\nВыберите приложение:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


ANDROID_INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-podklyucheniya-servisa-Blago-Vpn-04-22"
IOS_INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-podklyucheniyu-Blago-VPN-04-22"
WINDOWS_INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-podklyucheniyu-Blago-VPN-04-22-2"
MACOS_INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-podklyucheniyu-Blago-VPN-04-22-3"

_INSTRUCTION_URLS = {
    "android": ANDROID_INSTRUCTION_URL,
    "ios": IOS_INSTRUCTION_URL,
    "windows": WINDOWS_INSTRUCTION_URL,
    "macos": MACOS_INSTRUCTION_URL,
}

_PLATFORM_LABELS = {
    "android": "Android",
    "ios": "iOS",
    "windows": "Windows",
    "macos": "macOS",
}


@menu_router.callback_query(F.data.startswith("app:"))
async def show_app_wip(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    platform = parts[1]
    app = parts[2] if len(parts) > 2 else ""

    builder = InlineKeyboardBuilder()
    instruction_url = _INSTRUCTION_URLS.get(platform)

    if instruction_url:
        app_names = {"happ": "Happ", "v2raytun": "V2RayTun"}
        app_title = app_names.get(app, _PLATFORM_LABELS.get(platform, platform))
        platform_label = _PLATFORM_LABELS.get(platform, platform)

        builder.row(InlineKeyboardButton(
            text="📖 Открыть инструкцию",
            url=instruction_url,
        ))
        builder.row(InlineKeyboardButton(
            text="Назад",
            callback_data=f"instr:{platform}",
            icon_custom_emoji_id="5258236805890710909",
            style="danger",
        ))

        await callback.message.edit_text(
            f"<b>Инструкция по подключению — {platform_label} ({app_title})</b>\n\n"
            f"Нажмите кнопку ниже, чтобы открыть пошаговую инструкцию по подключению "
            f"сервиса <b>Blago VPN</b> на устройстве {platform_label}.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    else:
        builder.row(InlineKeyboardButton(
            text="Назад",
            callback_data=f"instr:{platform}",
            icon_custom_emoji_id="5258236805890710909",
            style="danger",
        ))

        await callback.message.edit_text(
            "🚧 <b>Пока в разработке</b>\n\nИнструкция скоро появится. Следите за обновлениями в @blago_vpn_news",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )

    await callback.answer()


@menu_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return
    lang = getattr(user, "language", "ru")
    await callback.message.edit_text(
        _main_text(lang),
        reply_markup=get_main_menu_keyboard(user, language=lang),
        parse_mode="HTML"
    )
    await callback.answer()


# ─── Глобальный обработчик ошибок ────────────────────────────────
from aiogram.types import ErrorEvent

@menu_router.errors()
async def global_error_handler(event: ErrorEvent):
    logger.error(f"Необработанная ошибка: {event.exception}", exc_info=True)

    try:
        update = event.update
        if update.callback_query:
            await update.callback_query.answer(
                "⚙️ Технические работы, попробуйте позже.", show_alert=True
            )
        elif update.message:
            await update.message.answer("⚙️ Технические работы, попробуйте позже.")
    except Exception:
        pass

    try:
        from main import notify_admins
        err_text = (
            f"<b>Ошибка в хендлере</b>\n\n"
            f"<code>{type(event.exception).__name__}: {event.exception}</code>"
        )
        bot = event.update.bot if hasattr(event.update, 'bot') else None
        if bot:
            await notify_admins(bot, err_text)
    except Exception:
        pass
