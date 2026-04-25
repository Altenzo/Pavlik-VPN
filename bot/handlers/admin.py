import asyncio
import logging
import logging.handlers
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.db.models.user import User
from apps.db.models.transaction import Transaction
from apps.db.repositories.promo_code import create_promo_code
from apps.services.vpn.remnawave_service import RemnawaveService, format_bytes
from config import config

admin_router = Router()
logger = logging.getLogger(__name__)

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
    internal_squad_uuids=config.INTERNAL_SQUAD_UUIDS,
    external_squad_uuid=config.EXTERNAL_SQUAD_UUID,
)


def log_action(admin_id: int, action: str):
    admin_logger.info(f"admin={admin_id} | {action}")


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def admin_only(message: types.Message) -> bool:
    return is_admin(message.from_user.id)


def admin_only_cb(callback: types.CallbackQuery) -> bool:
    return is_admin(callback.from_user.id)


# ─── FSM States для создания промокода ───────────────────────────
class PromoCreation(StatesGroup):
    select_discount = State()
    select_expiry = State()
    select_activations = State()
    enter_name = State()


# ─── Inline-клавиатуры для шагов создания промокода ──────────────
def _discount_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="10%", callback_data="promo_disc:10"),
        InlineKeyboardButton(text="20%", callback_data="promo_disc:20"),
        InlineKeyboardButton(text="50%", callback_data="promo_disc:50"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="promo_cancel"))
    return builder.as_markup()


def _expiry_kb(discount: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 день", callback_data="promo_exp:1"),
        InlineKeyboardButton(text="7 дней", callback_data="promo_exp:7"),
        InlineKeyboardButton(text="30 дней", callback_data="promo_exp:30"),
    )
    builder.row(
        InlineKeyboardButton(text="90 дней", callback_data="promo_exp:90"),
        InlineKeyboardButton(text="365 дней", callback_data="promo_exp:365"),
        InlineKeyboardButton(text="♾ Бессрочно", callback_data="promo_exp:0"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="promo_cancel"))
    return builder.as_markup()


def _activations_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1", callback_data="promo_act:1"),
        InlineKeyboardButton(text="5", callback_data="promo_act:5"),
        InlineKeyboardButton(text="10", callback_data="promo_act:10"),
    )
    builder.row(
        InlineKeyboardButton(text="50", callback_data="promo_act:50"),
        InlineKeyboardButton(text="100", callback_data="promo_act:100"),
        InlineKeyboardButton(text="♾ Без лимита", callback_data="promo_act:0"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="promo_cancel"))
    return builder.as_markup()


# ─── /blago_promo ────────────────────────────────────────────────
@admin_router.message(Command("blago_promo"), F.func(admin_only))
async def cmd_promo_start(message: types.Message, state: FSMContext):
    log_action(message.from_user.id, "/blago_promo")
    await state.set_state(PromoCreation.select_discount)
    await message.answer(
        "🎟 <b>Создание промокода</b>\n\n"
        "Шаг 1 из 4: Выберите размер скидки:",
        reply_markup=_discount_kb(),
        parse_mode="HTML"
    )


@admin_router.callback_query(
    F.data.startswith("promo_disc:"),
    F.func(admin_only_cb),
    StateFilter(PromoCreation.select_discount)
)
async def promo_select_discount(callback: types.CallbackQuery, state: FSMContext):
    discount = int(callback.data.split(":")[1])
    await state.update_data(discount=discount)
    await state.set_state(PromoCreation.select_expiry)
    await callback.message.edit_text(
        f"🎟 <b>Создание промокода</b>\n\n"
        f"✅ Скидка: <b>{discount}%</b>\n\n"
        f"Шаг 2 из 4: Выберите срок действия:",
        reply_markup=_expiry_kb(discount),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(
    F.data.startswith("promo_exp:"),
    F.func(admin_only_cb),
    StateFilter(PromoCreation.select_expiry)
)
async def promo_select_expiry(callback: types.CallbackQuery, state: FSMContext):
    days = int(callback.data.split(":")[1])
    data = await state.get_data()
    discount = data["discount"]

    if days == 0:
        expiry_text = "♾ Бессрочно"
        await state.update_data(expires_at=None, expiry_text=expiry_text)
    else:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
        expiry_text = f"{days} дн."
        await state.update_data(expires_at=expires_at, expiry_text=expiry_text)

    await state.set_state(PromoCreation.select_activations)
    await callback.message.edit_text(
        f"🎟 <b>Создание промокода</b>\n\n"
        f"✅ Скидка: <b>{discount}%</b>\n"
        f"✅ Срок: <b>{expiry_text}</b>\n\n"
        f"Шаг 3 из 4: Выберите количество активаций:",
        reply_markup=_activations_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.callback_query(
    F.data.startswith("promo_act:"),
    F.func(admin_only_cb),
    StateFilter(PromoCreation.select_activations)
)
async def promo_select_activations(callback: types.CallbackQuery, state: FSMContext):
    max_act = int(callback.data.split(":")[1])
    data = await state.get_data()
    discount = data["discount"]
    expiry_text = data.get("expiry_text", "—")

    max_act_val = None if max_act == 0 else max_act
    act_text = "♾ Без лимита" if max_act == 0 else str(max_act)

    await state.update_data(max_activations=max_act_val, act_text=act_text)
    await state.set_state(PromoCreation.enter_name)
    await callback.message.edit_text(
        f"🎟 <b>Создание промокода</b>\n\n"
        f"✅ Скидка: <b>{discount}%</b>\n"
        f"✅ Срок: <b>{expiry_text}</b>\n"
        f"✅ Активаций: <b>{act_text}</b>\n\n"
        f"Шаг 4 из 4: <b>Введите название промокода</b>\n"
        f"<i>Только латинские буквы, цифры и '_' (2–32 символа)\n"
        f"Например: SUMMER2025 или VIP_10</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(StateFilter(PromoCreation.enter_name), F.func(admin_only))
async def promo_enter_name(message: types.Message, state: FSMContext, session: AsyncSession):
    code = (message.text or "").strip().upper()

    if not re.match(r'^[A-Z0-9_]{2,32}$', code):
        await message.answer(
            "❌ Некорректное название.\n"
            "Допустимы только латинские буквы, цифры и '_' (2–32 символа).\n\n"
            "Попробуйте ещё раз:"
        )
        return

    data = await state.get_data()
    discount = data["discount"]
    expires_at_str = data.get("expires_at")
    max_activations = data.get("max_activations")
    expiry_text = data.get("expiry_text", "—")
    act_text = data.get("act_text", "—")

    expires_at = datetime.fromisoformat(expires_at_str) if expires_at_str else None

    try:
        promo = await create_promo_code(
            session,
            code=code,
            discount=discount,
            created_by=message.from_user.id,
            expires_at=expires_at,
            max_activations=max_activations,
        )
        await state.clear()
        log_action(message.from_user.id, f"/blago_promo create code={code} discount={discount}%")
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🎟 Код: <code>{promo.code}</code>\n"
            f"💰 Скидка: <b>{promo.discount}%</b>\n"
            f"⏳ Срок: <b>{expiry_text}</b>\n"
            f"🔢 Активаций: <b>{act_text}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        if "unique" in str(e).lower():
            await message.answer(
                f"❌ Промокод <code>{code}</code> уже существует.\n"
                f"Введите другое название:",
                parse_mode="HTML"
            )
        else:
            await state.clear()
            logger.error(f"promo create error: {e}", exc_info=True)
            await message.answer(f"❌ Ошибка создания промокода: <code>{e}</code>", parse_mode="HTML")


@admin_router.callback_query(F.data == "promo_cancel", F.func(admin_only_cb))
async def promo_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание промокода отменено.")
    await callback.answer()


# ─── /blago_users_stats ──────────────────────────────────────────
@admin_router.message(Command("blago_users_stats"), F.func(admin_only))
async def cmd_users_stats(message: types.Message, session: AsyncSession):
    log_action(message.from_user.id, "/blago_users_stats")
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

        banned = (await session.execute(
            select(func.count(User.id)).where(User.is_banned == True)
        )).scalar() or 0

        revenue = (await session.execute(
            select(func.sum(Transaction.amount)).where(Transaction.status == "CONFIRMED")
        )).scalar() or 0.0

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= today_start)
        )).scalar() or 0

        await message.answer(
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{total}</b>\n"
            f"✅ Активных подписок: <b>{active}</b>\n"
            f"🎁 Использовали триал: <b>{trial}</b>\n"
            f"🆕 Новых сегодня: <b>{new_today}</b>\n"
            f"🚫 Заблокировано: <b>{banned}</b>\n"
            f"💰 Общая выручка: <b>{revenue:.2f} ₽</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"users_stats error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка БД: <code>{e}</code>", parse_mode="HTML")


# ─── /blago_give_sub [user_id] [days] ───────────────────────────
@admin_router.message(Command("blago_give_sub"), F.func(admin_only))
async def cmd_give_sub(message: types.Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /blago_give_sub <user_id> <days>")
        return

    try:
        target_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("❌ user_id и days должны быть числами")
        return

    if days <= 0 or days > 3650:
        await message.answer("❌ Количество дней должно быть от 1 до 3650")
        return

    log_action(message.from_user.id, f"/blago_give_sub user={target_id} days={days}")

    try:
        user = await session.get(User, target_id)
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден в БД")
            return

        now = datetime.now()

        if user.vpn_uuid:
            current_end = user.subscription_end if (user.subscription_end and user.subscription_end > now) else now
            new_end = current_end + timedelta(days=days)
            ok = await remnawave.extend_user(user.vpn_uuid, new_expire_dt=new_end)
            if not ok:
                await message.answer("⚠️ Обновлено в БД, но Remnawave вернул ошибку — проверь панель.")
        else:
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


# ─── /blago_info [user_id] ───────────────────────────────────────
@admin_router.message(Command("blago_info"), F.func(admin_only))
async def cmd_info(message: types.Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /blago_info <user_id>")
        return

    log_action(message.from_user.id, f"/blago_info target={parts[1]}")

    try:
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

        ban_line = f"\n🚫 Заблокирован: <b>Да</b> ({user.ban_reason or '—'})" if user.is_banned else ""

        traffic_line = ""
        devices_block = ""
        if user.vpn_uuid:
            vpn_info = await remnawave.get_user(user.vpn_uuid)
            if vpn_info:
                used = format_bytes(vpn_info.used_traffic_bytes)
                limit = (
                    format_bytes(vpn_info.traffic_limit_bytes)
                    if vpn_info.traffic_limit_bytes > 0 else "∞"
                )
                online_str = (
                    vpn_info.online_at.strftime('%d.%m.%Y %H:%M')
                    if vpn_info.online_at else "—"
                )
                traffic_line = (
                    f"\n📊 Трафик: <b>{used}</b> / {limit}"
                    f"\n🟢 Был онлайн: {online_str}"
                )

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
                devices_block = (
                    f"\n\n📱 Устройства ({len(devices)}):\n" + "\n".join(lines)
                )
            else:
                devices_block = "\n\n📱 Устройства: пока не подключались"

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
            f"💰 Реф. баланс: {user.referral_balance:.2f} ₽"
            f"{ban_line}\n\n"
            f"💳 Оплат: {txs} на сумму {total_paid:.2f} ₽\n"
            f"🔑 VPN UUID: <code>{user.vpn_uuid or '—'}</code>"
            f"{traffic_line}"
            f"{devices_block}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"info error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка БД: <code>{e}</code>", parse_mode="HTML")


# ─── /blago_ban [user_id] [reason] ──────────────────────────────
@admin_router.message(Command("blago_ban"), F.func(admin_only))
async def cmd_ban(message: types.Message, session: AsyncSession):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /blago_ban <user_id> [причина]")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом")
        return

    if target_id in config.ADMIN_IDS:
        await message.answer("❌ Нельзя заблокировать администратора")
        return

    reason = parts[2] if len(parts) > 2 else "Нарушение правил"
    log_action(message.from_user.id, f"/blago_ban user={target_id} reason={reason}")

    try:
        user = await session.get(User, target_id)
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден")
            return

        user.is_banned = True
        user.ban_reason = reason
        await session.commit()

        await message.answer(
            f"🚫 <b>Пользователь заблокирован</b>\n\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"📝 Причина: {reason}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"ban error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ─── /blago_unban [user_id] ──────────────────────────────────────
@admin_router.message(Command("blago_unban"), F.func(admin_only))
async def cmd_unban(message: types.Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /blago_unban <user_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом")
        return

    log_action(message.from_user.id, f"/blago_unban user={target_id}")

    try:
        user = await session.get(User, target_id)
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден")
            return

        user.is_banned = False
        user.ban_reason = None
        await session.commit()

        await message.answer(
            f"✅ <b>Пользователь разблокирован</b>\n\n"
            f"🆔 ID: <code>{target_id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"unban error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ─── /blago_broadcast [текст] ───────────────────────────────────
@admin_router.message(Command("blago_broadcast"), F.func(admin_only))
async def cmd_broadcast(message: types.Message, session: AsyncSession):
    text = message.text.removeprefix("/blago_broadcast").strip()
    if not text:
        await message.answer("Использование: /blago_broadcast <текст сообщения>")
        return

    log_action(message.from_user.id, f"/blago_broadcast text={text[:50]}")

    try:
        result = await session.execute(select(User.id).where(User.is_banned == False))
        user_ids = [row[0] for row in result.fetchall()]

        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await message.bot.send_message(uid, text, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)

        await message.answer(
            f"📢 Рассылка завершена\n✅ Доставлено: {sent}\n❌ Не доставлено: {failed}"
        )
    except Exception as e:
        logger.error(f"broadcast error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ─── /blago_backup ───────────────────────────────────────────────
@admin_router.message(Command("blago_backup"), F.func(admin_only))
async def cmd_backup(message: types.Message):
    log_action(message.from_user.id, "/blago_backup")
    await message.answer("⏳ Создаю дамп БД...")

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{config.DB_NAME}_{timestamp}.sql"

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, filename)

            env = os.environ.copy()
            env["PGPASSWORD"] = config.DB_PASS

            result = subprocess.run(
                [
                    "pg_dump",
                    "-h", config.DB_HOST,
                    "-p", str(config.DB_PORT),
                    "-U", config.DB_USER,
                    "-d", config.DB_NAME,
                    "-f", filepath,
                ],
                env=env,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                await message.answer(f"❌ pg_dump завершился с ошибкой:\n<code>{result.stderr}</code>", parse_mode="HTML")
                return

            with open(filepath, "rb") as f:
                await message.answer_document(
                    types.BufferedInputFile(f.read(), filename=filename),
                    caption=f"✅ Бэкап БД <b>{config.DB_NAME}</b>\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    parse_mode="HTML",
                )
    except FileNotFoundError:
        await message.answer("❌ <code>pg_dump</code> не найден на сервере. Установи postgresql-client.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"backup error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ─── /blago_help ─────────────────────────────────────────────────
@admin_router.message(Command("blago_help"), F.func(admin_only))
async def cmd_admin_help(message: types.Message):
    log_action(message.from_user.id, "/blago_help")
    await message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        "/blago_users_stats — статистика пользователей\n"
        "/blago_give_sub &lt;id&gt; &lt;дни&gt; — выдать подписку\n"
        "/blago_info &lt;id или @username&gt; — карточка пользователя\n"
        "/blago_broadcast &lt;текст&gt; — рассылка всем (кроме забаненных)\n"
        "/blago_backup — скачать дамп БД\n"
        "/blago_promo — создать промокод (интерактивно)\n"
        "/blago_ban &lt;id&gt; [причина] — заблокировать пользователя\n"
        "/blago_unban &lt;id&gt; — разблокировать пользователя\n"
        "/blago_help — эта справка",
        parse_mode="HTML"
    )
