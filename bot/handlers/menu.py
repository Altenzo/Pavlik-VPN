from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from apps.db.models.user import User
from apps.db.models.transaction import Transaction
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.keyboards.subscriptions import get_subscriptions_keyboard
from bot.keyboards.common import get_back_keyboard, get_back_to_profile_keyboard
from bot.keyboards.profile_kb import get_profile_keyboard
from bot.keyboards.trial_kb import get_trial_confirmation_keyboard

menu_router = Router()

@menu_router.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery, session: AsyncSession):
    """
    Личный кабинет (Главная)
    """
    user_id = callback.from_user.id
    user = await session.get(User, user_id)
    
    if not user:
        await callback.answer("Ошибка: Пользователь не найден.")
        return

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258262708838472996\">👤</tg-emoji> <b>Привет, {user.full_name}!</b>\n\n"
        f"<tg-emoji emoji-id=\"5258011929993026890\">🆔</tg-emoji> ID: <code>{user_id}</code>\n",
        reply_markup=get_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "history_tx")
async def show_history_tx(callback: types.CallbackQuery, session: AsyncSession):
    """
    История транзакций (последние 10)
    """
    user_id = callback.from_user.id
    
    # Получаем историю (последние 10 подтвержденных)
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
        f"{history_text}\n\n",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "my_subs")
async def show_my_subs(callback: types.CallbackQuery, session: AsyncSession):
    """
    Текущие подписки юзера
    """
    user_id = callback.from_user.id
    user = await session.get(User, user_id)

    sub_status = "<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> Не активна"
    if user.subscription_end:
        if user.subscription_end > datetime.now():
            sub_status = f"<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> Активна (до {user.subscription_end.strftime('%d.%m.%Y %H:%M')})"
        else:
            sub_status = "<tg-emoji emoji-id=\"5258474669769497337\">⚠️</tg-emoji> Истекла"

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5255813559572508065\">💎</tg-emoji> <b>Ваши подписки</b>\n\n"
        f"<tg-emoji emoji-id=\"5258330865674494479\">🆔</tg-emoji> Статус основной подписки: <b>{sub_status}</b>\n\n"
        f"<i>(В будущем здесь будет отображен список всех ваших приватных ключей)</i>",
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

from bot.keyboards.referral_kb import get_referral_keyboard
from sqlalchemy import func

@menu_router.callback_query(F.data == "referrals")
async def show_referrals(callback: types.CallbackQuery, session: AsyncSession):
    """
    Реферальная система (35% с первого уровня)
    """
    user_id = callback.from_user.id
    user = await session.get(User, user_id)
    
    # Считаем количество приглашенных друзей
    stmt = select(func.count(User.id)).where(User.referred_by == user_id)
    res = await session.execute(stmt)
    ref_count = res.scalar() or 0
    
    # Формируем ссылку
    bot_username = (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    await callback.message.edit_text(
        f"<b><tg-emoji emoji-id=\"5258486128742244085\">👥</tg-emoji> Реферальная система</b>\n\n"
        f"Приглашайте друзей и получайте <b>35%</b> с каждой их покупки на свой баланс!\n\n"
        f"Ваша ссылка: <code>{ref_link}</code>\n\n"
        f"<b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: <b>{ref_count}</b>\n"
        f"<b><tg-emoji emoji-id=\"5258501105293205250\">💰</tg-emoji> Всего заработано:</b> {user.total_earned:.2f} ₽\n"
        f"<b><tg-emoji emoji-id=\"5258368777350816286\">💰</tg-emoji> Доступно для вывода:</b> {user.referral_balance:.2f} ₽\n\n"
        f"<i>Минимальная сумма для вывода: 1000 ₽. По всем вопросам обратитесь в поддержку.</i>",
        reply_markup=get_referral_keyboard(ref_link),
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "withdraw_referral")
async def withdraw_referral(callback: types.CallbackQuery, session: AsyncSession):
    """
    Вывод реферальных средств (HTML)
    """
    user = await session.get(User, callback.from_user.id)
    
    if user.referral_balance < 1000: # Например, минималка 1000 руб
        await callback.answer(f"❌ Минимальная сумма вывода — 1000 ₽\nВаш баланс: {user.referral_balance:.2f} ₽", show_alert=True)
        return
        
    await callback.message.edit_text(
        f"<b><tg-emoji emoji-id=\"5402429676763231362\">💰</tg-emoji> Вывод средств</b>\n\n"
        f"Ваш доступный баланс: <b>{user.referral_balance:.2f} ₽</b>\n\n"
        f"Для оформления выплаты на <b>USDT TRC-20</b> свяжитесь с поддержкой и "
        f"укажите ваш ID (<code>{user.id}</code>).\n\n"
        f"<tg-emoji emoji-id=\"5307761176132720417\">❓</tg-emoji> Поддержка: @pavlik_support",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

from bot.keyboards.payment_kb import get_payment_keyboard
from apps.services.payment.platega_service import PlategaService
from apps.db.repositories.transaction import create_transaction, get_transaction, update_transaction_id, update_transaction_status
from config import config

# Инициализируем сервис платежей
platega = PlategaService(config.PLATEGA_MERCHANT_ID, config.PLATEGA_SECRET)

from bot.keyboards.subscriptions import get_subscriptions_keyboard, get_payment_methods_keyboard

@menu_router.callback_query(F.data == "buy_subscription")
async def select_subscription(callback: types.CallbackQuery):
    """
    Выбор тарифа (Шаг 1)
    """
    await callback.message.edit_text(
        f'<tg-emoji emoji-id=\"5258389041006518073\">📦</tg-emoji> <b>Шаг 1: Выберите тариф:</b>\n\n'
        f"• Безлимит устройств\n"
        f"• Без логов\n"
        f"• Поддержка 24/7",
        reply_markup=get_subscriptions_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

from bot.keyboards.subscriptions import get_subscriptions_keyboard, get_payment_methods_keyboard

from bot.keyboards.subscriptions import get_subscriptions_keyboard, get_payment_methods_keyboard

@menu_router.callback_query(F.data.startswith("select_sub:"))
async def process_select_sub(callback: types.CallbackQuery):
    """
    Шаг 2: выбор способа оплаты после тарифа
    """
    _, tariff_key, amount = callback.data.split(":")
    
    await callback.message.edit_text(
        f'<tg-emoji emoji-id=\"5409048419211682843\">💲</tg-emoji> <b>Шаг 2: Выберите способ оплаты:</b>\n\n'
        f"Тариф: <b>{tariff_key}</b>\n"
        f"К оплате: <b>{amount} ₽</b>",
        reply_markup=get_payment_methods_keyboard(tariff_key, amount),
        parse_mode="HTML"
    )
    await callback.answer()

import asyncio  

async def auto_check_payment(message: types.Message, tx_id: int, external_id: str, session_maker):
    """
    Фоновая задача для автоматического подтверждения оплаты (Auto-confirm)
    """
    for _ in range(30): # Проверяем в течение 10 минут (30 * 20 сек)
        await asyncio.sleep(20)
        
        status = await platega.check_status(external_id)
        if status == "CONFIRMED":
            async with session_maker() as session:
                from apps.db.repositories.transaction import update_transaction_status
                await update_transaction_status(session, tx_id, "CONFIRMED")
            
            await message.edit_text(
                "<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> <b>Оплата подтверждена автоматически!</b>\n\n"
                "Ваша подписка активирована. Ожидайте данные для подключения! <tg-emoji emoji-id=\"5260221883940347555\">🚀</tg-emoji>",
                reply_markup=get_back_keyboard(),
                parse_mode="HTML"
            )
            return
        
        if status in ["CANCELED", "FAILED"]:
            async with session_maker() as session:
                from apps.db.repositories.transaction import update_transaction_status
                await update_transaction_status(session, tx_id, status)
            
            await message.edit_text(
                f"<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> <b>Платеж был отклонен или отменен.</b>\nСтатус: <b>{status}</b>",
                reply_markup=get_back_keyboard(),
                parse_mode="HTML"
            )
            return

@menu_router.callback_query(F.data.startswith("buy:"))
async def process_buy_tariff(callback: types.CallbackQuery, session: AsyncSession):
    """
    Процесс покупки тарифа и запуск авто-проверки
    """
    data = callback.data.split(":")
    tariff_key, amount, method = data[1], data[2], data[3]
    amount = float(amount)

    # Если выбрана КРИПТА
    if method == "crypto":
        await callback.answer(
            "🛑 Технические работы!\n\nВ данный момент прием криптовалют настраивается. Пожалуйста, используйте СБП или попробуйте позже!", 
            show_alert=True
        )
        return

    await callback.message.edit_text("⏳ <b>Формируем счет...</b>", parse_mode="HTML")

    from apps.db.repositories.transaction import create_transaction, update_transaction_id
    tx = await create_transaction(session, callback.from_user.id, amount, tariff_key, payment_method=method)
    
    # Расчет суммы для платежки (если комиссия 13% платится нами)
    # Формула: то, что видит клиент = amount_to_pay * 1.13. 
    # Значит, мы шлем: amount / 1.13, чтобы клиент увидел ровно 'amount'.
    amount_to_pay = round(amount / 1.13, 2)
    
    description = f"Оплата VPN: {tariff_key}"
    
    # Провайдер по методу (СБП)
    payment_data = await platega.create_transaction(amount_to_pay, description, str(tx.id))

    if not payment_data or "redirect" not in payment_data:
        await callback.message.edit_text(
            "<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> <b>Ошибка при создании счета.</b>\n"
            "Попробуйте позже или выберите другой способ.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        return

    await update_transaction_id(session, tx.id, payment_data["transactionId"])
    
    # Запускаем фоновую задачу (используем async_session из database.py)
    from apps.db.database import async_session
    asyncio.create_task(
        auto_check_payment(
            callback.message, 
            tx.id, 
            payment_data["transactionId"],
            async_session
        )
    )

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258477770735885832\">📄</tg-emoji> <b>Счет сформирован!</b>\n\n"
        f"Сумма: <b>{amount} ₽</b>\n"
        f"Метод: <b>СБП</b>\n\n"
        f"Нажмите кнопку ниже, чтобы перейти к оплате.",
        reply_markup=get_payment_keyboard(payment_data["redirect"], str(tx.id)),
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data.startswith("check_payment:"))
async def check_payment_status(callback: types.CallbackQuery, session: AsyncSession):
    """
    Проверка статуса платежа по кнопке
    """
    tx_id = int(callback.data.split(":")[1])
    tx = await get_transaction(session, tx_id)

    if not tx or not tx.platega_id:
        await callback.answer("Ошибка: Транзакция не найдена.", show_alert=True)
        return

    # Запрашиваем актуальный статус у Platega
    status = await platega.check_status(tx.platega_id)
    
    if status == "CONFIRMED":
        await update_transaction_status(session, tx_id, "CONFIRMED")
        await callback.message.edit_text(
            "<tg-emoji emoji-id=\"5260221883940347555\">✅</tg-emoji> <b>Оплата прошла успешно!</b>\n\n"
            "Ваша подписка активирована. В ближайшее время мы пришлем вам данные для подключения.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
    elif status == "PENDING":
        await callback.answer("⏳ Платеж еще обрабатывается. Попробуйте через минуту.", show_alert=True)
    else:
        # Если статус изменился на какой-то другой (CANCELED, FAILED и т.д.)
        await update_transaction_status(session, tx_id, status)
        await callback.message.edit_text(
            f"<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> <b>Статус платежа изменился.</b>\n\n"
            f"Текущий статус: <b>{status}</b>\n"
            f"Если вы считаете, что это ошибка, обратитесь в поддержку.",
            reply_markup=get_back_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()

@menu_router.callback_query(F.data == "instructions")
async def show_instructions(callback: types.CallbackQuery):
    """
    Инструкция (Помощь)
    """
    await callback.message.edit_text(
        "<tg-emoji emoji-id=\"5307761176132720417\">❓</tg-emoji> <b>Помощь и инструкции</b>\n\n"
        "Здесь будет ваша инструкция по подключению через строку vless...",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, session: AsyncSession):
    """
    Возврат в главное меню
    """
    user = await session.get(User, callback.from_user.id)
    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5258152182150077732\">⚡</tg-emoji> <b>Pavlik VPN — Ваш персональный ключ к свободе.</b>\n\n"
        f"Забудьте о границах в интернете. Мы обеспечиваем сверхбыстрое соединение, абсолютную анонимность и доступ к любому контенту в один клик.\n\n"
        f"<tg-emoji emoji-id=\"5260221883940347555\">🚀</tg-emoji> <b>Наши преимущества:</b>\n"
        f"  •  <b>Скорость:</b> До 1 Гбит/с без задержек.\n"
        f"  •  <b>Приватность:</b> Строгая политика No-Logs.\n"
        f"  •  <b>Простота:</b> Настройка за 30 секунд прямо в Telegram.\n\n"
        f"<i>Ваша безопасность — наша работа. Подключайтесь и летайте!</i>",
        reply_markup=get_main_menu_keyboard(user), # Передаем юзера
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "confirm_trial_request")
async def show_trial_confirmation(callback: types.CallbackQuery, session: AsyncSession):
    """
    Показывает окно подтверждения триала
    """
    user = await session.get(User, callback.from_user.id)
    if user.trial_used:
        await callback.answer("<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> Вы уже использовали пробный период!", show_alert=True)
        return

    # Рассчитываем дату окончания для текста
    end_date = (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y %H:%M")

    await callback.message.edit_text(
        f"<tg-emoji emoji-id=\"5199749070830197566\">🎁</tg-emoji> <b>Активация пробного периода</b>\n\n"
        f"Вы собираетесь активировать бесплатный доступ на <b>3 дня</b>.\n"
        f"Он будет действовать до: <b>{end_date}</b>\n\n"
        f"<tg-emoji emoji-id=\"5420323339723881652\">⚠️</tg-emoji> <b>Внимание:</b> Пробный период можно активировать только <b>один раз</b>.\n\n"
        f"<tg-emoji emoji-id=\"5258216851472654189\">💡</tg-emoji> <i>После активации вы сможете следить за статусом в разделе:\n"
        f"Профиль -> Мои подписки</i>",
        reply_markup=get_trial_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "claim_trial")
async def claim_trial(callback: types.CallbackQuery, session: AsyncSession):
    """
    Финальная активация пробного периода
    """
    user = await session.get(User, callback.from_user.id)
    
    if user.trial_used:
        await callback.answer("<tg-emoji emoji-id=\"5260342697075416641\">❌</tg-emoji> Вы уже использовали пробный период!", show_alert=True)
        return
        
    # Начисляем 3 дня
    now = datetime.now()
    if user.subscription_end and user.subscription_end > now:
        user.subscription_end += timedelta(days=3)
    else:
        user.subscription_end = now + timedelta(days=3)
        
    user.trial_used = True
    user.is_active = True
    await session.commit()
    
    await callback.message.edit_text(
        "<tg-emoji emoji-id=\"5260221883940347555\">✅</tg-emoji> <b>Пробный период успешно активирован!</b>\n\n"
        "Вам начислено <b>3 дня</b> бесплатного VPN.\n\n"
        "<tg-emoji emoji-id=\"5307761176132720417\">❓</tg-emoji> <i>Инструкция: теперь вы можете зайти в свой Профиль и увидеть "
        "актуальный срок действия подписки в подразделе «Мои подписки».</i>",
        reply_markup=get_main_menu_keyboard(user),
        parse_mode="HTML"
    )
    await callback.answer("<tg-emoji emoji-id=\"5260221883940347555\">✅</tg-emoji> Подписка активирована!", show_alert=True)
