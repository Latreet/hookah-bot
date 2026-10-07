import asyncio
import logging
import os
from datetime import datetime

import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from dotenv import load_dotenv

load_dotenv()

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID  = int(os.getenv("ADMIN_ID"))
GROUP_ID  = None
DB_PATH   = "orders.db"
# ==================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# ---------------- FSM ----------------
class Catering(StatesGroup):
    hookahs = State()
    refills = State()
    flavor  = State()
    address = State()
    period  = State()
    name    = State()
    phone   = State()

class Rental(StatesGroup):
    hookahs       = State()
    refills_yn    = State()
    refills       = State()
    flavor        = State()
    address       = State()
    period        = State()
    delivery_time = State()
    name          = State()
    phone         = State()

# ---------------- DB ----------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT NOT NULL,
                user_id       INTEGER NOT NULL,
                username      TEXT,
                full_name     TEXT,
                client_name   TEXT,
                phone         TEXT,
                service       TEXT NOT NULL,
                hookahs       INTEGER,
                refills       INTEGER,
                flavor        TEXT,
                address       TEXT,
                period        TEXT,
                delivery_time TEXT,
                status        TEXT DEFAULT 'new'
            )
        """)
        # Добавляем новые колонки, если база была создана старой версией
        for col, typ in [("client_name", "TEXT"), ("address", "TEXT")]:
            try:
                await db.execute(f"ALTER TABLE orders ADD COLUMN {col} {typ}")
            except Exception:
                pass
        await db.commit()

async def save_order(user, data: dict, phone: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO orders
              (created_at, user_id, username, full_name, client_name, phone, service,
               hookahs, refills, flavor, address, period, delivery_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(timespec="seconds"),
            user.id, user.username, user.full_name,
            data.get("client_name"),
            phone,
            data.get("service"), data.get("hookahs"),
            data.get("refills"), data.get("flavor"),
            data.get("address"),
            data.get("period"), data.get("delivery_time"),
        ))
        await db.commit()
        return cur.lastrowid

async def fetch_last_orders(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        )
        return await cur.fetchall()

# ---------------- Клавиатуры ----------------
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💨 Кейтеринг кальяна", callback_data="start:cat")],
        [InlineKeyboardButton(text="📦 Аренда кальяна",    callback_data="start:rent")],
    ])

def count_kb(prefix: str, max_count: int = 10) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i in range(1, max_count + 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}:no")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")],
    ])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")],
    ])

def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )

# ---------------- Общие команды ----------------
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n"
        "Выбери услугу, которую хочешь заказать:",
        reply_markup=main_menu_kb(),
    )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выбери услугу:", reply_markup=main_menu_kb())

@dp.message(Command("orders"))
async def cmd_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    rows = await fetch_last_orders(10)
    if not rows:
        await message.answer("Заявок пока нет.")
        return
    for r in rows:
        lines = [
            f"<b>#{r['id']}</b> — {r['service']}",
            f"🕒 {r['created_at']}",
            f"Кальянов: {r['hookahs']} | Забивок: {r['refills'] or '—'}",
            f"Вкус: {r['flavor'] or '—'}",
            f"Адрес: {r['address'] or '—'}",
            f"Срок/время: {r['period']}",
        ]
        if r["delivery_time"]:
            lines.append(f"Доставка: {r['delivery_time']}")
        lines.append(f"👤 {r['client_name'] or r['full_name']}")
        lines.append(f"📞 {r['phone']} — @{r['username'] or '—'}")
        await message.answer("\n".join(lines), parse_mode="HTML")

@dp.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "Заказ отменён.\n\nВыбери услугу:",
        reply_markup=main_menu_kb(),
    )
    await cb.answer("Отменено")

# ---------------- Точки входа в потоки ----------------
@dp.callback_query(F.data == "start:cat")
async def start_catering(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(service="Кейтеринг кальяна")
    await state.set_state(Catering.hookahs)
    await cb.message.edit_text(
        "<b>💨 Кейтеринг кальяна</b>\n\nСколько кальянов требуется?",
        parse_mode="HTML", reply_markup=count_kb("cat_h"),
    )
    await cb.answer()

@dp.callback_query(F.data == "start:rent")
async def start_rental(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(service="Аренда кальяна")
    await state.set_state(Rental.hookahs)
    await cb.message.edit_text(
        "<b>📦 Аренда кальяна</b>\n\nСколько кальянов требуется?",
        parse_mode="HTML", reply_markup=count_kb("rent_h"),
    )
    await cb.answer()

# ============ КЕЙТЕРИНГ ============
@dp.callback_query(Catering.hookahs, F.data.startswith("cat_h:"))
async def cat_hookahs(cb: CallbackQuery, state: FSMContext):
    n = int(cb.data.split(":")[1])
    await state.update_data(hookahs=n)
    await state.set_state(Catering.refills)
    await cb.message.edit_text(
        f"<b>💨 Кейтеринг кальяна</b>\n"
        f"Кальянов: {n}\n\n"
        f"Сколько забивок требуется?",
        parse_mode="HTML", reply_markup=count_kb("cat_r"),
    )
    await cb.answer()

@dp.callback_query(Catering.refills, F.data.startswith("cat_r:"))
async def cat_refills(cb: CallbackQuery, state: FSMContext):
    n = int(cb.data.split(":")[1])
    await state.update_data(refills=n)
    await state.set_state(Catering.flavor)
    data = await state.get_data()
    await cb.message.edit_text(
        f"<b>💨 Кейтеринг кальяна</b>\n"
        f"Кальянов: {data['hookahs']} | Забивок: {n}\n\n"
        f"Напишите желаемый <b>вкус и крепость</b>.\n"
        f"Например: <i>Дыня — средняя крепость</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )
    await cb.answer()

@dp.message(Catering.flavor)
async def cat_flavor(message: Message, state: FSMContext):
    await state.update_data(flavor=message.text.strip())
    await state.set_state(Catering.address)
    await message.answer(
        "Укажите <b>адрес</b>, куда требуется кейтеринг.\n"
        "Например: <i>ул. Ленина, 15, кафе «Уют»</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Catering.address)
async def cat_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(Catering.period)
    await message.answer(
        "На какое <b>время</b> оформить заказ?\n"
        "Например: <i>сегодня 20:00</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Catering.period)
async def cat_period(message: Message, state: FSMContext):
    await state.update_data(period=message.text.strip())
    await state.set_state(Catering.name)
    await message.answer(
        "Как к вам <b>обращаться</b>?\n"
        "Например: <i>Денис</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Catering.name)
async def cat_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(Catering.phone)
    await message.answer(
        "Оставьте <b>номер телефона</b> для связи — нажмите кнопку ниже "
        "или введите вручную.",
        parse_mode="HTML", reply_markup=phone_kb(),
    )

@dp.message(Catering.phone, F.contact)
async def cat_phone_contact(message: Message, state: FSMContext):
    await finalize(message, state, message.contact.phone_number)

@dp.message(Catering.phone, F.text)
async def cat_phone_text(message: Message, state: FSMContext):
    await finalize(message, state, message.text.strip())

# ============ АРЕНДА ============
@dp.callback_query(Rental.hookahs, F.data.startswith("rent_h:"))
async def rent_hookahs(cb: CallbackQuery, state: FSMContext):
    n = int(cb.data.split(":")[1])
    await state.update_data(hookahs=n)
    await state.set_state(Rental.refills_yn)
    await cb.message.edit_text(
        f"<b>📦 Аренда кальяна</b>\n"
        f"Кальянов: {n}\n\n"
        f"Требуются ли забивки?",
        parse_mode="HTML", reply_markup=yes_no_kb("rent_yn"),
    )
    await cb.answer()

@dp.callback_query(Rental.refills_yn, F.data.startswith("rent_yn:"))
async def rent_yn(cb: CallbackQuery, state: FSMContext):
    ans = cb.data.split(":")[1]
    data = await state.get_data()
    if ans == "yes":
        await state.set_state(Rental.refills)
        await cb.message.edit_text(
            f"<b>📦 Аренда кальяна</b>\n"
            f"Кальянов: {data['hookahs']}\n\n"
            f"Сколько забивок требуется?",
            parse_mode="HTML", reply_markup=count_kb("rent_r"),
        )
    else:
        # Забивки не нужны — пропускаем шаги "вкус и крепость" и идём к адресу
        await state.update_data(refills=0, flavor="—")
        await state.set_state(Rental.address)
        await cb.message.edit_text(
            f"<b>📦 Аренда кальяна</b>\n"
            f"Кальянов: {data['hookahs']} | Забивки: нет\n\n"
            f"Укажите <b>адрес</b>, куда требуется доставка.\n"
            f"Например: <i>ул. Ленина, 15, кв. 42</i>",
            parse_mode="HTML", reply_markup=cancel_kb(),
        )
    await cb.answer()

@dp.callback_query(Rental.refills, F.data.startswith("rent_r:"))
async def rent_refills(cb: CallbackQuery, state: FSMContext):
    n = int(cb.data.split(":")[1])
    await state.update_data(refills=n)
    await state.set_state(Rental.flavor)
    data = await state.get_data()
    await cb.message.edit_text(
        f"<b>📦 Аренда кальяна</b>\n"
        f"Кальянов: {data['hookahs']} | Забивок: {n}\n\n"
        f"Напишите желаемый <b>вкус и крепость</b>.\n"
        f"Например: <i>Дыня — средняя крепость</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )
    await cb.answer()

@dp.message(Rental.flavor)
async def rent_flavor(message: Message, state: FSMContext):
    await state.update_data(flavor=message.text.strip())
    await state.set_state(Rental.address)
    await message.answer(
        "Укажите <b>адрес</b>, куда требуется доставка.\n"
        "Например: <i>ул. Ленина, 15, кв. 42</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Rental.address)
async def rent_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(Rental.period)
    await message.answer(
        "Укажите <b>срок аренды</b>.\n"
        "Например: <i>на 3 часа</i> или <i>на сутки</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Rental.period)
async def rent_period(message: Message, state: FSMContext):
    await state.update_data(period=message.text.strip())
    await state.set_state(Rental.delivery_time)
    await message.answer(
        "Укажите <b>время доставки</b>.\n"
        "Например: <i>сегодня к 19:00</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Rental.delivery_time)
async def rent_delivery(message: Message, state: FSMContext):
    await state.update_data(delivery_time=message.text.strip())
    await state.set_state(Rental.name)
    await message.answer(
        "Как к вам <b>обращаться</b>?\n"
        "Например: <i>Денис</i>",
        parse_mode="HTML", reply_markup=cancel_kb(),
    )

@dp.message(Rental.name)
async def rent_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text.strip())
    await state.set_state(Rental.phone)
    await message.answer(
        "Оставьте <b>номер телефона</b> для связи — нажмите кнопку ниже "
        "или введите вручную.",
        parse_mode="HTML", reply_markup=phone_kb(),
    )

@dp.message(Rental.phone, F.contact)
async def rent_phone_contact(message: Message, state: FSMContext):
    await finalize(message, state, message.contact.phone_number)

@dp.message(Rental.phone, F.text)
async def rent_phone_text(message: Message, state: FSMContext):
    await finalize(message, state, message.text.strip())

# ---------------- Финал + уведомление ----------------
async def finalize(message: Message, state: FSMContext, phone: str):
    data = await state.get_data()
    await state.clear()

    order_id = await save_order(message.from_user, data, phone)

    await message.answer(
        "🎉 <b>Благодарим за заказ!</b>\n"
        f"Номер вашей заявки: <b>#{order_id}</b>\n"
        "В ближайшее время с вами свяжутся для подтверждения.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    await notify_admin(message, data, phone, order_id)

async def notify_admin(message: Message, data: dict, phone: str, order_id: int):
    user = message.from_user
    lines = [
        f"🆕 <b>Новая заявка #{order_id}</b>",
        "",
        f"Услуга: <b>{data['service']}</b>",
        f"Кальянов: {data['hookahs']}",
    ]
    if data.get("refills") is not None:
        lines.append(f"Забивок: {data['refills'] if data['refills'] else '—'}")
    lines.append(f"Вкус/крепость: {data.get('flavor', '—')}")
    lines.append(f"Адрес: {data.get('address', '—')}")
    lines.append(f"Срок/время: {data.get('period', '—')}")
    if data.get("delivery_time"):
        lines.append(f"Время доставки: {data['delivery_time']}")
    lines += [
        "",
        f"Имя клиента: {data.get('client_name', user.full_name)}",
        f"Telegram: {user.full_name} (@{user.username or '—'})",
        f"Телефон: {phone}",
        f"ID: <code>{user.id}</code>",
    ]
    text = "\n".join(lines)

    for chat_id in filter(None, [ADMIN_ID, GROUP_ID]):
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            logging.exception("Не отправилось в чат %s: %s", chat_id, e)

# ---------------- Веб-сервер для health check ----------------
async def handle_ping(request):
    return web.Response(text="Bot is alive")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем бота в фоне
    asyncio.create_task(dp.start_polling(bot))

    # Поднимаем маленький веб-сервер (нужен для Back4App / health check)
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Bot and web server are running on port {port}...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
