#!/usr/bin/env python3
"""Скрипт, который просто добавляет товар в корзину на сайте.

По умолчанию работает с https://yerussia2026.ru/, но подходит для любого
магазина: кнопка «В корзину» ищется по типовым текстам и селекторам
(Bitrix, WooCommerce, Tilda, InSales, кастомные вёрстки).

Примеры:
    # посмотреть, какие кнопки есть на странице (ничего не нажимает)
    python add_to_cart.py --url https://yerussia2026.ru/ --dump

    # добавить товар в корзину и сохранить сессию корзины в cart_state.json
    python add_to_cart.py --url https://yerussia2026.ru/product/123

    # 3 штуки, свой селектор кнопки, скриншот результата
    python add_to_cart.py --url ... --qty 3 --selector "#buy-btn" --screenshot cart.png

    # ждать появления кнопки до 10 минут (товара пока нет в наличии)
    python add_to_cart.py --url ... --wait-stock 600

Требуется: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import (
        Error as PlaywrightError,
        Locator,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except ImportError:  # pragma: no cover
    sys.exit("Нужен playwright: pip install playwright && playwright install chromium")


DEFAULT_URL = "https://yerussia2026.ru/"

# Тексты кнопки добавления в корзину (регистр не важен, ищется подстрока).
BUTTON_TEXTS = [
    "добавить в корзину",
    "в корзину",
    "купить",
    "оформить",
    "заказать",
    "add to cart",
    "buy now",
]

# Типовые селекторы кнопки для популярных движков.
BUTTON_SELECTORS = [
    "button[name='add-to-cart']",                 # WooCommerce
    "a[href*='add-to-cart']",
    "a[href*='ADD2BASKET']", "a[href*='add2basket']",  # Bitrix
    "[onclick*='add2basket' i]", "[onclick*='addToBasket' i]",
    "[data-event='addToCart']",
    ".t-store__card__btn", ".js-store-buttons-wrapper button",  # Tilda
    ".product__buy", ".btn-buy", ".buy-button", ".button-buy",
    "[class*='add-to-cart' i]", "[class*='addtocart' i]",
    "[class*='to-basket' i]", "[class*='tobasket' i]",
    "[data-testid*='add-to-cart' i]",
]

# Где искать счётчик товаров в корзине (для проверки, что добавилось).
COUNTER_SELECTORS = [
    "[class*='cart' i][class*='count' i]", "[class*='basket' i][class*='count' i]",
    "[class*='cart' i][class*='quantity' i]", "[class*='cart' i][class*='total' i]",
    "[data-cart-count]", "#cart-count", ".cart-counter", ".basket-count",
    ".t706__carticon-counter",                     # Tilda
    ".header-cart__count", ".minicart__count",
]

# Кнопки согласия с cookie / всплывающих баннеров, которые перекрывают клик.
CONSENT_TEXTS = ["принять", "согласен", "согласна", "хорошо", "ок, понятно", "accept", "принимаю"]

# Признаки успеха, если счётчика на сайте нет.
SUCCESS_PATTERNS = [
    "товар добавлен", "добавлен в корзину", "добавлено в корзину",
    "уже в корзине", "перейти в корзину", "оформить заказ",
    "added to your cart", "added to cart",
]

QTY_INPUT_SELECTORS = [
    "input[name*='quant' i]", "input[name*='kol' i]", "input[name*='qty' i]",
    "input[class*='quant' i]", "input[class*='qty' i]", "input[data-quantity]",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Добавляет товар в корзину на сайте (по умолчанию yerussia2026.ru).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--url", default=DEFAULT_URL, help="страница товара или каталога")
    p.add_argument("--qty", type=int, default=1, help="сколько единиц добавить")
    p.add_argument("--selector", help="свой CSS/XPath-селектор кнопки (приоритетнее автопоиска)")
    p.add_argument("--text", help="свой текст кнопки, например «Оплатить участие»")
    p.add_argument(
        "--card-selector",
        help="селектор карточки товара: сначала кликнуть по ней (каталог/попап Tilda), потом искать кнопку",
    )
    p.add_argument("--state", default="cart_state.json",
                   help="файл cookies/localStorage — корзина сохраняется между запусками")
    p.add_argument("--no-state", action="store_true", help="не читать и не сохранять сессию")
    p.add_argument("--screenshot", help="куда сохранить скриншот страницы после добавления")
    p.add_argument("--timeout", type=int, default=30_000, help="таймаут навигации и поиска, мс")
    p.add_argument("--attempts", type=int, default=3, help="попыток нажать кнопку при неудаче")
    p.add_argument("--wait-stock", type=int, default=0,
                   help="секунд ждать появления кнопки, перезагружая страницу (0 — не ждать)")
    p.add_argument("--reload-every", type=int, default=20, help="интервал перезагрузки при --wait-stock, сек")
    p.add_argument("--headed", action="store_true", help="показать окно браузера")
    p.add_argument("--keep-open", type=int, default=0, help="держать браузер открытым N секунд в конце")
    p.add_argument("--dump", action="store_true",
                   help="только показать найденные кнопки и счётчики, ничего не нажимать")
    p.add_argument("--proxy", help="прокси, например http://user:pass@host:3128")
    p.add_argument("--user-agent", help="свой User-Agent")
    p.add_argument("--browser-path", default=os.environ.get("CHROMIUM_PATH"),
                   help="путь к бинарнику Chromium, если он уже установлен в системе "
                        "(иначе берётся браузер playwright); можно задать через CHROMIUM_PATH")
    return p.parse_args(argv)


def first_usable(locator: Locator, limit: int = 20) -> Locator | None:
    """Первый видимый и доступный для клика элемент из набора."""
    try:
        count = min(locator.count(), limit)
    except PlaywrightError:
        return None
    for i in range(count):
        item = locator.nth(i)
        try:
            if item.is_visible() and item.is_enabled():
                return item
        except PlaywrightError:
            continue
    return None


def candidate_locators(frame, texts: list[str], selectors: list[str]) -> list[Locator]:
    out: list[Locator] = []
    for sel in selectors:
        out.append(frame.locator(sel))
    for text in texts:
        safe = text.replace('"', '\\"')
        out.append(frame.locator(
            f'button:has-text("{safe}"), a:has-text("{safe}"), '
            f'[role="button"]:has-text("{safe}"), input[type="submit"][value*="{safe}" i]'
        ))
    return out


def find_button(page, args) -> Locator | None:
    """Ищет кнопку добавления в корзину в основном документе и во всех iframe."""
    texts = [args.text] if args.text else BUTTON_TEXTS
    selectors = [args.selector] if args.selector else BUTTON_SELECTORS
    for frame in [page, *page.frames]:
        for locator in candidate_locators(frame, texts, selectors):
            found = first_usable(locator)
            if found is not None:
                return found
    return None


def read_cart_count(page) -> int | None:
    for frame in [page, *page.frames]:
        for sel in COUNTER_SELECTORS:
            locator = frame.locator(sel)
            try:
                count = min(locator.count(), 5)
            except PlaywrightError:
                continue
            for i in range(count):
                try:
                    text = (locator.nth(i).inner_text(timeout=1_000) or "").strip()
                except (PlaywrightError, PlaywrightTimeout):
                    continue
                match = re.search(r"\d+", text)
                if match:
                    return int(match.group())
    return None


def page_says_success(page) -> bool:
    try:
        body = (page.inner_text("body", timeout=3_000) or "").lower()
    except (PlaywrightError, PlaywrightTimeout):
        return False
    return any(pattern in body for pattern in SUCCESS_PATTERNS)


def dismiss_consent(page) -> None:
    for text in CONSENT_TEXTS:
        safe = text.replace('"', '\\"')
        button = first_usable(page.locator(
            f'button:has-text("{safe}"), a:has-text("{safe}"), [role="button"]:has-text("{safe}")'
        ), limit=5)
        if button is None:
            continue
        try:
            button.click(timeout=2_000)
            page.wait_for_timeout(300)
            return
        except (PlaywrightError, PlaywrightTimeout):
            continue


def set_quantity(page, qty: int) -> bool:
    """Пробует вписать количество в поле. True — получилось, дальше клик один раз."""
    if qty <= 1:
        return True
    for frame in [page, *page.frames]:
        for sel in QTY_INPUT_SELECTORS:
            field = first_usable(frame.locator(sel), limit=3)
            if field is None:
                continue
            try:
                field.fill(str(qty), timeout=3_000)
                print(f"  количество {qty} проставлено в поле {sel}")
                return True
            except (PlaywrightError, PlaywrightTimeout):
                continue
    return False


def dump_page(page) -> None:
    print("\n--- кликабельные элементы на странице ---")
    seen: set[str] = set()
    for frame in [page, *page.frames]:
        locator = frame.locator("button, a, [role='button'], input[type='submit']")
        try:
            total = min(locator.count(), 200)
        except PlaywrightError:
            continue
        for i in range(total):
            item = locator.nth(i)
            try:
                if not item.is_visible():
                    continue
                info = item.evaluate(
                    "el => ({tag: el.tagName.toLowerCase(), text: (el.innerText || el.value || '').trim()"
                    ".slice(0, 60), cls: el.className || '', id: el.id || '', href: el.getAttribute('href') || ''})"
                )
            except PlaywrightError:
                continue
            if not info["text"] and not info["cls"]:
                continue
            line = f"<{info['tag']}> {info['text']!r} class={info['cls']!r} id={info['id']!r} href={info['href']!r}"
            if line in seen:
                continue
            seen.add(line)
            print(" ", line)
    print("--- счётчик корзины ---")
    print(" ", read_cart_count(page))


def open_page(page, url: str, timeout: int) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout, 10_000))
    except PlaywrightTimeout:
        pass
    dismiss_consent(page)


def wait_for_button(page, args) -> Locator | None:
    """Ждёт кнопку, периодически перезагружая страницу (товар не в наличии)."""
    deadline = time.monotonic() + args.wait_stock
    while True:
        button = find_button(page, args)
        if button is not None:
            return button
        if time.monotonic() >= deadline:
            return None
        print(f"  кнопка не найдена, повтор через {args.reload_every} с…")
        time.sleep(args.reload_every)
        try:
            open_page(page, args.url, args.timeout)
        except (PlaywrightError, PlaywrightTimeout) as exc:
            print(f"  перезагрузка не удалась: {exc}")


def add_to_cart(page, args) -> dict:
    before = read_cart_count(page)
    print(f"корзина до: {before if before is not None else 'счётчик не найден'}")

    button = wait_for_button(page, args) if args.wait_stock else find_button(page, args)
    if button is None:
        return {"ok": False, "reason": "кнопка добавления в корзину не найдена (см. --dump/--selector)"}

    try:
        label = (button.inner_text(timeout=2_000) or "").strip()
    except (PlaywrightError, PlaywrightTimeout):
        label = ""
    print(f"кнопка найдена: {label!r}")

    qty_in_field = set_quantity(page, args.qty)
    clicks = 1 if qty_in_field else max(args.qty, 1)

    clicked = 0
    for click_no in range(clicks):
        for attempt in range(1, args.attempts + 1):
            try:
                button.scroll_into_view_if_needed(timeout=5_000)
                button.click(timeout=args.timeout)
                clicked += 1
                break
            except (PlaywrightError, PlaywrightTimeout) as exc:
                print(f"  попытка {attempt}/{args.attempts} не удалась: {str(exc).splitlines()[0]}")
                page.wait_for_timeout(1_000)
                refreshed = find_button(page, args)
                if refreshed is not None:
                    button = refreshed
        else:
            return {"ok": False, "reason": "клик не прошёл", "clicked": clicked}
        page.wait_for_timeout(1_500)
        if click_no + 1 < clicks:
            refreshed = find_button(page, args)
            if refreshed is not None:
                button = refreshed

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass

    after = read_cart_count(page)
    print(f"корзина после: {after if after is not None else 'счётчик не найден'}")

    if after is not None and (before is None or after > before):
        ok, reason = True, "счётчик корзины увеличился"
    elif page_says_success(page):
        ok, reason = True, "на странице появилось подтверждение добавления"
    elif after is not None and before is not None and after == before:
        ok, reason = False, "счётчик корзины не изменился"
    else:
        ok, reason = False, "подтверждения добавления не найдено — проверьте скриншот/корзину вручную"

    return {"ok": ok, "reason": reason, "clicks": clicked,
            "cart_before": before, "cart_after": after}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state_path = None if args.no_state else Path(args.state)

    with sync_playwright() as pw:
        launch: dict = {"headless": not args.headed}
        if args.proxy:
            launch["proxy"] = {"server": args.proxy}
        if args.browser_path:
            launch["executable_path"] = args.browser_path
        browser = pw.chromium.launch(**launch)

        context_args: dict = {"locale": "ru-RU", "viewport": {"width": 1440, "height": 900}}
        if args.user_agent:
            context_args["user_agent"] = args.user_agent
        if state_path and state_path.exists():
            context_args["storage_state"] = str(state_path)
            print(f"сессия загружена из {state_path}")
        context = browser.new_context(**context_args)
        context.set_default_timeout(args.timeout)
        page = context.new_page()

        result: dict
        try:
            print(f"открываю {args.url}")
            open_page(page, args.url, args.timeout)

            if args.card_selector:
                card = first_usable(page.locator(args.card_selector))
                if card is None:
                    print(f"карточка {args.card_selector!r} не найдена, продолжаю без неё")
                else:
                    card.click()
                    page.wait_for_timeout(1_500)

            if args.dump:
                dump_page(page)
                result = {"ok": True, "reason": "режим --dump, ничего не нажималось"}
            else:
                result = add_to_cart(page, args)
        except (PlaywrightError, PlaywrightTimeout) as exc:
            result = {"ok": False, "reason": f"ошибка браузера: {str(exc).splitlines()[0]}"}

        if args.screenshot:
            try:
                page.screenshot(path=args.screenshot, full_page=True)
                print(f"скриншот: {args.screenshot}")
            except (PlaywrightError, PlaywrightTimeout) as exc:
                print(f"скриншот не сохранён: {exc}")

        if state_path:
            try:
                context.storage_state(path=str(state_path))
                print(f"сессия корзины сохранена в {state_path}")
            except PlaywrightError as exc:
                print(f"сессию сохранить не удалось: {exc}")

        if args.keep_open:
            page.wait_for_timeout(args.keep_open * 1_000)

        context.close()
        browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
