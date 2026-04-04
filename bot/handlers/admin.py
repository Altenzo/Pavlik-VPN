import asyncio
import logging
import logging.handlers
import os
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.db.models.user import User
from apps.db.models.transaction import Transaction
from apps.services.vpn.remnawave_service import RemnawaveService
from config import config

admin_router = Router()
logger = logging.getLogger(__name__)

# ─── Лог действий админов ───────────────────────────────────────
os.makedirs("logs", exist_ok=True)
_action_handler = logging.handlers.RotatingFileHandler(
    "logs/admin_actions.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8"
)
_action_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
admin_logger = logging.getLogger("admin_actions")
admin_logger.addHandler(_action_handler)
admin_logger.setLevel(logging.INFO)

remnawave = RemnawaveService(
    panel_url=config.PANEL_URL,
    api_token=config.PANEL_API_TOKEN,
    inbound_uuid=config.PANEL_INBOUND_UUID,
)


def log_action(admin_id: int, action: str):
    admin_logger.info(f"admin={admin_id} | {action}")


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ─── Фильтр: только для админов ─────────────────────────────────
def admin_only(message: types.Message) -> bool:
    return is_admin(message.from_user.id)


# ─── /users_stats ────────────────────────────────────────────────
@admin_router.message(Command("users_stats"), F.func(admin_only))
async def cmd_users_stats(message: types.Message, session: AsyncSession):
    log_action(message.from_user.id, "/users_stats")
    try:
        now = datetime.now()

        total = (await session.execute(select(func.count(User.id)))).scalar() or 0

        active = (await session.execute(
            select(func.count(User.id)).where(
                User.is_active == True,
                User.subscription_end > now
            )
        )).scalar() or 0

        trial = (await session.execute(
            select(func.count(User.id)).where(User.trial_used == True)
        )).scalar() or 0

        # Выручка (CONFIRMED транзакции)
        revenue = (await session.execute(
            select(func.sum(Transaction.amount)).where(Transaction.status == "CONFIRMED")
        )).scalar() or 0.0

        # Новые за сегодня
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        new_today = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= today_start)
        )).scalar() or 0

        await message.answer(
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{total}</b>\n"
            f"✅ Активных подписок: <b>{active}</b>\n"
            f"🎁 Использовали триал: <b>{trial}</b>\n"
            f"🆕 Новых сегодня: <b>{new_today}</b>\n"
            f"💰 Общая выручка: <b>{revenue:.2f} ₽</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"users_stats error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка БД: <code>{e}</code>", parse_mode="HTML")


# ─── /give_sub [user_id] [days] ─────────────────────────────────
@admin_router.message(Command("give_sub"), F.func(admin_only))
async def cmd_give_sub(message: types.Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /give_sub <user_id> <days>")
        return

    try:
        target_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("❌ user_id и days должны быть числами")
        return

    log_action(message.from_user.id, f"/give_sub user={target_id} days={days}")

    try:
        user = await session.get(User, target_id)
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден в БД")
            return

        now = datetime.now()
        from datetime import timedelta

        # Продлеваем в Remnawave
        if user.vpn_uuid:
            current_end = user.subscription_end if (user.subscription_end and user.subscription_end > now) else now
            new_end = current_end + timedelta(days=days)
            ok = await remnawave.extend_user(user.vpn_uuid, new_expire_dt=new_end)
            if not ok:
                await message.answer("⚠️ Обновлено в БД, но Remnawave вернул ошибку — проверь панель.")
        else:
            # Создаём пользователя в Remnawave
            vpn_user = await remnawave.create_user(telegram_id=user.id, days=days)
            if vpn_user:
                user.vpn_uuid = vpn_user.uuid
                user.vless_link = vpn_user.subscription_url
                new_end = now + timedelta(days=days)
            else:
                new_end = (user.subscription_end if (user.subscription_end and user.subscription_end > now) else now) + timedelta(days=days)
                await message.answer("⚠️ Remnawave недоступен, подписка обновлена только в БД")

        user.subscription_end = new_end
        user.is_active = True
        await session.commit()

        await message.answer(
            f"✅ Подписка выдана!\n\n"
            f"👤 Пользователь: <code>{target_id}</code>\n"
            f"📅 Дней добавлено: <b>{days}</b>\n"
            f"⏳ Истекает: <b>{new_end.strftime('%d.%m.%Y %H:%M')}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"give_sub error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка БД: <code>{e}</code>", parse_mode="HTML")


# ─── /info [user_id] ─────────────────────────────────────────────
@admin_router.message(Command("info"), F.func(admin_only))
async def cmd_info(message: types.Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /info <user_id>")
        return

    log_action(message.from_user.id, f"/info target={parts[1]}")

    try:
        # Ищем по ID или username
        target = parts[1].lstrip("@")
        if target.isdigit():
            user = await session.get(User, int(target))
        else:
            result = await session.execute(
                select(User).where(User.username == target)
            )
            user = result.scalar_one_or_none()

        if not user:
            await message.answer(f"❌ Пользователь <code>{target}</code> не найден", parse_mode="HTML")
            return

        now = datetime.now()
        if user.subscription_end and user.subscription_end > now:
            days_left = (user.subscription_end - now).days
            sub_status = f"✅ Активна (осталось {days_left} д.)"
        elif user.subscription_end:
            sub_status = "⚠️ Истекла"
        else:
            sub_status = "❌ Нет подписки"

        # Транзакции
        txs = (await session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user.id,
                Transaction.status == "CONFIRMED"
            )
        )).scalar() or 0

        total_paid = (await session.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.user_id == user.id,
                Transaction.status == "CONFIRMED"
            )
        )).scalar() or 0.0

        await message.answer(
            f"👤 <b>Карточка пользователя</b>\n\n"
            f"🆔 Telegram ID: <code>{user.id}</code>\n"
            f"📛 Username: @{user.username or '—'}\n"
            f"📝 Имя: {user.full_name}\n"
            f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📡 Статус подписки: {sub_status}\n"
            f"⏳ Истекает: {user.subscription_end.strftime('%d.%m.%Y %H:%M') if user.subscription_end else '—'}\n"
            f"🎁 Триал использован: {'Да' if user.trial_used else 'Нет'}\n"
            f"👥 Реферал от: {user.referred_by or '—'}\n"
            f"💰 Реф. баланс: {user.referral_balance:.2f} ₽\n\n"
            f"💳 Оплат: {txs} на сумму {total_paid:.2f} ₽\n"
            f"🔑 VPN UUID: <code>{user.vpn_uuid or '—'}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"info error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка БД: <code>{e}</code>", parse_mode="HTML")


# ─── /broadcast [текст] ─────────────────────────────────────────
@admin_router.message(Command("broadcast"), F.func(admin_only))
async def cmd_broadcast(message: types.Message, session: AsyncSession):
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast <текст сообщения>")
        return

    log_action(message.from_user.id, f"/broadcast text={text[:50]}")

    try:
        result = await session.execute(select(User.id))
        user_ids = [row[0] for row in result.fetchall()]

        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await message.bot.send_message(uid, text, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)  # ~20 msg/sec — в рамках лимита Telegram

        await message.answer(
            f"📢 Рассылка завершена\n✅ Доставлено: {sent}\n❌ Не доставлено: {failed}"
        )
    except Exception as e:
        logger.error(f"broadcast error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ─── /admin_help ─────────────────────────────────────────────────
@admin_router.message(Command("admin_help"), F.func(admin_only))
async def cmd_admin_help(message: types.Message):
    log_action(message.from_user.id, "/admin_help")
    await message.answer(
        "🔧 <b>Скрытая админ-панель</b>\n\n"
        "/users_stats — статистика пользователей\n"
        "/give_sub <id> <дни> — выдать подписку\n"
        "/info <id или @username> — карточка пользователя\n"
        "/broadcast <текст> — рассылка всем\n"
        "/admin_help — эта справка",
        parse_mode="HTML"
    )
