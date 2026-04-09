import asyncio
from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from apps.db.models.user import User
from apps.db.models.transaction import Transaction
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.keyboards.subscriptions import get_subscriptions_keyboard, get_payment_methods_keyboard
from bot.keyboards.common import get_back_keyboard, get_back_to_profile_keyboard
from bot.keyboards.profile_kb import get_profile_keyboard
from bot.keyboards.trial_kb import get_trial_confirmation_keyboard
from bot.keyboards.referral_kb import get_referral_keyboard
from bot.keyboards.payment_kb import get_payment_keyboard
from apps.services.payment.platega_service import PlategaService
from apps.services.vpn.remnawave_service import RemnawaveService
from apps.db.repositories.transaction import (
    create_transaction,
    get_transaction,
    get_pending_transaction,
    update_transaction_id,
    update_transaction_status,
    count_pending_transactions,
)
from config import config

import logging
logger = logging.getLogger(__name__)

menu_router = Router()

platega = PlategaService(config.PLATEGA_MERCHANT_ID, config.PLATEGA_SECRET)
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


@menu_router.callback_query(F.data == "my_subs")
async def show_my_subs(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден.")
        return

    now = datetime.now()
    if user.subscription_end and user.subscription_end > now:
        days_left = (user.subscription_end - now).days
        sub_status = (
            f"✅ Активна\n"
            f"Истекает: <b>{user.subscription_end.strftime('%d.%m.%Y %H:%M')}</b> (осталось {days_left} д.)"
        )
    elif user.subscription_end:
        sub_status = "⚠️ Истекла"
    else:
        sub_status = "❌ Не активна"

    vless_text = ""
    if user.vless_link and user.is_active:
        vless_text = f"\n\n<b>Ссылка для подключения:</b>\n<code>{user.vless_link}</code>"

    await callback.message.edit_text(
        f"<b>Ваши подписки</b>\n\n"
        f"Статус: {sub_status}{vless_text}",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "user_agreement")
async def show_user_agreement(callback: types.CallbackQuery):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

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
        f"Поддержка: @blago_vpn_manager",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ──────────────────────────────────────────────
# Покупка подписки
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "buy_subscription")
async def select_subscription(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<tg-emoji emoji-id=\"5258123337149717894\">📦</tg-emoji> <b>Выберите срок подписки:</b>",
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

    if method == "crypto":
        await callback.answer(
            "🛑 Криптовалюта пока недоступна. Используйте СБП.",
            show_alert=True
        )
        return

    await callback.message.edit_text("⏳ <b>Формируем счет...</b>", parse_mode="HTML")

    pending_count = await count_pending_transactions(session, callback.from_user.id)
    if pending_count >= 1:
        await callback.message.edit_text(
            "<b>У вас уже есть незавершённый платёж.</b>\n\n"
            "Завершите или дождитесь его истечения, прежде чем создавать новый.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        return

    tx = await create_transaction(session, callback.from_user.id, amount, tariff_key, payment_method=method)

    amount_to_pay = round(amount / 1.13, 2)
    payment_data = await platega.create_transaction(amount_to_pay, f"VPN: {tariff_key}", str(tx.id))

    if not payment_data or "redirect" not in payment_data:
        await callback.message.edit_text(
            "<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> <b>Ошибка при создании счета.</b>\n"
            "Попробуйте позже или выберите другой способ.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        return

    await update_transaction_id(session, tx.id, payment_data["transactionId"])

    from apps.db.database import async_session
    asyncio.create_task(
        _auto_confirm_payment(callback.message, tx.id, payment_data["transactionId"], async_session)
    )

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258477770735885832\">📄</tg-emoji> <b>Счет сформирован!</b>\n\n"
        f"Сумма: <b>{amount} ₽</b> | Метод: <b>СБП</b>\n\n"
        f"Нажмите кнопку ниже чтобы оплатить.",
        reply_markup=get_payment_keyboard(payment_data["redirect"], str(tx.id)),
        parse_mode="HTML"
    )
    await callback.answer()


async def _auto_confirm_payment(message: types.Message, tx_id: int, external_id: str, session_maker):
    # 90 раз по 20 сек = 30 минут
    for _ in range(90):
        await asyncio.sleep(20)
        try:
            status = await platega.check_status(external_id)
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
            "⏰ <b>Время ожидания оплаты истекло.</b>\n\nЕсли вы оплатили — обратитесь в поддержку: @blago_vpn_manager",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        pass


async def _activate_subscription_after_payment(session: AsyncSession, tx_id: int):
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

    await session.commit()


# ──────────────────────────────────────────────
# Промокод
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "promo_code")
async def show_promo_code(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<tg-emoji emoji-id=\"5359719332542718652\">🎟</tg-emoji> <b>Активация промокода</b>\n\n"
        "Введите промокод в ответном сообщении или обратитесь в поддержку:\n"
        "@blago_vpn_manager",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ──────────────────────────────────────────────
# Триал
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "confirm_trial_request")
async def show_trial_confirmation(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    if user.trial_used:
        await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
        return

    end_date = (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y %H:%M")
    await callback.message.edit_text(
        f"<b>Активация пробного периода</b>\n\n"
        f"Бесплатный доступ на <b>3 дня</b> до <b>{end_date}</b>.\n\n"
        f"Активировать можно только <b>один раз</b>.",
        reply_markup=get_trial_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "claim_trial")
async def claim_trial(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)

    if user.trial_used:
        await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)
        return

    await callback.message.edit_text("⏳ <b>Активируем доступ...</b>", parse_mode="HTML")

    vpn_user = await remnawave.create_user(telegram_id=user.id, days=3)

    now = datetime.now()
    new_end = now + timedelta(days=3)

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
        user.subscription_end += timedelta(days=3)
    else:
        user.subscription_end = new_end

    user.trial_used = True
    await session.commit()

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> <b>Пробный период активирован!</b>\n\n"
        f"Доступ выдан на <b>3 дня</b> до <b>{user.subscription_end.strftime('%d.%m.%Y %H:%M')}</b>."
        f"{link_text}{extra_msg}",
        reply_markup=get_main_menu_keyboard(user),
        parse_mode="HTML"
    )
    await callback.answer("✅ Подписка активирована!", show_alert=True)


# ──────────────────────────────────────────────
# Инструкции
# ──────────────────────────────────────────────

@menu_router.callback_query(F.data == "instructions")
async def show_instructions(callback: types.CallbackQuery):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 Android", callback_data="instr:android"),
        InlineKeyboardButton(text="🍎 iOS", callback_data="instr:ios")
    )
    builder.row(
        InlineKeyboardButton(text="💻 Windows", callback_data="instr:windows"),
        InlineKeyboardButton(text="🖥 macOS", callback_data="instr:macos")
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
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    platform = callback.data.split(":")[1]
    platform_names = {
        "android": "📱 Android",
        "ios": "🍎 iOS",
        "windows": "💻 Windows",
        "macos": "🖥 macOS",
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


@menu_router.callback_query(F.data.startswith("app:"))
async def show_app_wip(callback: types.CallbackQuery):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    platform = callback.data.split(":")[1]

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Назад", callback_data=f"instr:{platform}", icon_custom_emoji_id="5258236805890710909", style="danger")
    )

    await callback.message.edit_text(
        "🚧 <b>Пока в разработке</b>\n\nИнструкция скоро появится. Следите за обновлениями в @blago_vpn_news",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@menu_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, session: AsyncSession):
    user = await session.get(User, callback.from_user.id)
    await callback.message.edit_text(
        "<tg-emoji emoji-id=\"5258152182150077732\">⚡</tg-emoji> <b>Blago VPN — Ваш персональный ключ к свободе.</b>\n\n"
        "Забудьте о границах в интернете. Мы обеспечиваем сверхбыстрое соединение, абсолютную анонимность и доступ к любому контенту в один клик.\n\n"
        "<tg-emoji emoji-id=\"5260221883940347555\">🚀</tg-emoji> <b>Наши преимущества:</b>\n"
        "  •  <b>Скорость:</b> До 1 Гбит/с без задержек.\n"
        "  •  <b>Приватность:</b> Мы уважаем твое право на частную жизнь и не храним историю твоих действий.\n"
        "  •  <b>Простота:</b> Настройка за 30 секунд прямо в Telegram.\n\n"
        "<i>Ваша безопасность — наша работа. Подключайтесь и летайте!</i>",
        reply_markup=get_main_menu_keyboard(user),
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
