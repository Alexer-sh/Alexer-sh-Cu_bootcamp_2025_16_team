import logging
import json
import os
import asyncio
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command


logging.basicConfig(level=logging.INFO)
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

USERS_FILE = 'users.json'
EVENTS_FILE = 'events.json'
PENDING_EVENTS_FILE = 'photo.json'
MENU_IMAGE_PATH = 'photo.jpg'
AI_TOKEN = 4096
AI_MODEL = "gpt-4o"
AI_URL = "https://us-central1-chatgpt-c1cfb.cloudfunctions.net/callTurbo"
AI_HEADERS = {
    "Host": "us-central1-chatgpt-c1cfb.cloudfunctions.net",
    "accept": "/",
    "content-type": "application/json",
    "user-agent": "AI Chatbot/3.6 (com.highteqsolutions.chatgpt; build:8; iOS 16.7.2) Alamofire/5.9.1",
    "accept-language": "ru-US;q=1.0"
}


async def get_ai_response(user_message, ai_context=""):
    current_message = f"\nUser: {user_message}"

    data = {
        'max_tokens': AI_TOKEN,
        'responseType': 'normal',
        'osType': 'iOS',
        'model': AI_MODEL,
        'value': f"ПРОШЛЫЕ СООБЩЕНИЯ: {ai_context}{current_message}",
        'search': user_message
    }

    try:
        response = await asyncio.to_thread(
            lambda: requests.post(AI_URL, headers=AI_HEADERS, data=json.dumps(data))
        )

        if response.status_code == 200:
            response_data = response.json()

            content = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

            if content:
                return content, ai_context + current_message + f"\nAI: {content}"
            else:
                return "Извините, не удалось получить ответ от ИИ.", ai_context
        else:
            return f"Ошибка при обращении к ИИ: статус код {response.status_code}", ai_context
    except Exception as e:
        return f"Произошла ошибка при выполнении запроса к ИИ: {e}", ai_context


def ensure_files_exist():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

    if not os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)

    if not os.path.exists(PENDING_EVENTS_FILE):
        with open(PENDING_EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)


def load_users():
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_user(user_id, user_data):
    users = load_users()
    users[user_id] = user_data
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def load_events():
    with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_event(event_data):
    events = load_events()
    events.append(event_data)
    with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def load_pending_events():
    with open(PENDING_EVENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_pending_event(event_data):
    events = load_pending_events()
    events.append(event_data)
    with open(PENDING_EVENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def remove_pending_event(event_idx):
    events = load_pending_events()
    if 0 <= event_idx < len(events):
        removed_event = events.pop(event_idx)
        with open(PENDING_EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        return removed_event
    return None


def register_user_for_event(user_id, event_idx):
    users = load_users()
    if user_id not in users:
        return False

    if "registered_events" not in users[user_id]:
        users[user_id]["registered_events"] = []

    if event_idx not in users[user_id]["registered_events"]:
        users[user_id]["registered_events"].append(event_idx)
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        return True
    return False


def get_events_list_text():
    events = load_events()
    if not events:
        return "📢 В настоящее время нет доступных мероприятий."

    result = "📋 **Список доступных мероприятий:**\n\n"
    for idx, event in enumerate(events):
        category = event.get("category", "unknown")
        category_emoji = ""
        if category == "party":
            category_emoji = "🎉"
        elif category == "outdoor":
            category_emoji = "🌳"
        elif category == "excursion":
            category_emoji = "🏛️"
        elif category == "exhibition":
            category_emoji = "🖼️"
        elif category == "networking":
            category_emoji = "👋"
        elif category == "boardgames":
            category_emoji = "🎲"
        elif category == "other":
            category_emoji = "🔍"

        category_name = event.get("category_name", "Без категории")

        result += f"**{idx + 1}. {event['name']}**\n"
        result += f"   {category_emoji} Категория: {category_name}\n"
        result += f"   📝 {event['description'][:50]}...\n"
        result += f"   📅 {event['time']}\n"
        result += f"   📍 {event['location']}\n\n"

    return result


def get_all_events_info():
    events = load_events()
    if not events:
        return "В настоящее время нет доступных мероприятий."

    result = "Список всех мероприятий:\n\n"
    for idx, event in enumerate(events):
        category = event.get("category", "unknown")
        category_emoji = ""
        if category == "party":
            category_emoji = "🎉"
        elif category == "outdoor":
            category_emoji = "🌳"
        elif category == "excursion":
            category_emoji = "🏛️"
        elif category == "exhibition":
            category_emoji = "🖼️"
        elif category == "networking":
            category_emoji = "👋"
        elif category == "boardgames":
            category_emoji = "🎲"
        elif category == "other":
            category_emoji = "🔍"

        category_name = event.get("category_name", "Без категории")

        result += f"{idx + 1}. {event['name']}\n"
        result += f"   Категория: {category_emoji} {category_name}\n"
        result += f"   Описание: {event['description']}\n"
        result += f"   Дата и время: {event['time']}\n"
        result += f"   Место: {event['location']}\n\n"

    return result


class RegistrationStates(StatesGroup):
    name = State()
    faculty = State()


class EventRegistrationStates(StatesGroup):
    name = State()
    description = State()
    location = State()
    time = State()
    tg_link = State()  # Новое состояние для ссылки на Telegram канал
    tg_chat_link = State()  # Новое состояние для ссылки на Telegram беседу
    category = State()


class AIConsultationStates(StatesGroup):
    conversation = State()


class AdminPasswordState(StatesGroup):
    waiting_password = State()


def get_main_menu(user_id=None):
    keyboard_buttons = [
        [InlineKeyboardButton(text="🎭 Мероприятия", callback_data="view_events")],
        [InlineKeyboardButton(text="📅 Мои мероприятия", callback_data="my_events")],
        [InlineKeyboardButton(text="➕ Зарегистрировать мероприятие", callback_data="register_event")]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_event_categories():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎉 Тусовки", callback_data="category_party")],
        [InlineKeyboardButton(text="🌳 Выезды загород", callback_data="category_outdoor")],
        [InlineKeyboardButton(text="🏛️ Экскурсии", callback_data="category_excursion")],
        [InlineKeyboardButton(text="🖼️ Выставки/музеи", callback_data="category_exhibition")],
        [InlineKeyboardButton(text="👋 Знакомства", callback_data="category_networking")],
        [InlineKeyboardButton(text="🎲 Настольные игры", callback_data="category_boardgames")],
        [InlineKeyboardButton(text="🔍 Другое", callback_data="category_other")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard


def get_pending_events_list(page=0):
    events = load_pending_events()

    keyboard_buttons = []
    start_idx = page * 5
    end_idx = min(start_idx + 5, len(events))

    for i in range(start_idx, end_idx):
        event = events[i]
        category = event.get("category", "unknown")
        category_emoji = ""
        if category == "party":
            category_emoji = "🎉"
        elif category == "outdoor":
            category_emoji = "🌳"
        elif category == "excursion":
            category_emoji = "🏛️"
        elif category == "exhibition":
            category_emoji = "🖼️"
        elif category == "networking":
            category_emoji = "👋"
        elif category == "boardgames":
            category_emoji = "🎲"
        elif category == "other":
            category_emoji = "🔍"

        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{category_emoji} {event['name']}", callback_data=f"pending_event_{i}")
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"pending_page_{page - 1}"))
    if end_idx < len(events):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"pending_page_{page + 1}"))

    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад к панели администратора", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_recommendations_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Посоветоваться с ИИ", callback_data="consult_ai")],
        [InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_categories")]
    ])
    return keyboard


def get_end_consultation_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔚 Завершить консультацию", callback_data="end_consultation")]
    ])
    return keyboard


def get_pending_event_actions(event_idx):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_event_{event_idx}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_event_{event_idx}")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="approve_events")]
    ])
    return keyboard


def get_events_list(category, page=0):
    events = load_events()
    if category != "all":
        events = [e for e in events if e.get("category") == category]

    keyboard_buttons = []
    start_idx = page * 5
    end_idx = min(start_idx + 5, len(events))

    for i in range(start_idx, end_idx):
        event = events[i]
        category = event.get("category", "unknown")
        category_emoji = ""
        if category == "party":
            category_emoji = "🎉"
        elif category == "outdoor":
            category_emoji = "🌳"
        elif category == "excursion":
            category_emoji = "🏛️"
        elif category == "exhibition":
            category_emoji = "🖼️"
        elif category == "networking":
            category_emoji = "👋"
        elif category == "boardgames":
            category_emoji = "🎲"
        elif category == "other":
            category_emoji = "🔍"

        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{category_emoji} {event['name']}", callback_data=f"event_{i}")
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page_{category}_{page - 1}"))
    if end_idx < len(events):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"page_{category}_{page + 1}"))

    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_my_events_list(user_id, page=0):
    users = load_users()
    events = load_events()

    registered_events = []
    if user_id in users and "registered_events" in users[user_id]:
        for event_idx in users[user_id]["registered_events"]:
            if event_idx < len(events):
                registered_events.append((event_idx, events[event_idx]))

    keyboard_buttons = []
    start_idx = page * 5
    end_idx = min(start_idx + 5, len(registered_events))

    for i in range(start_idx, end_idx):
        event_idx, event = registered_events[i]
        category = event.get("category", "unknown")
        category_emoji = ""
        if category == "party":
            category_emoji = "🎉"
        elif category == "outdoor":
            category_emoji = "🌳"
        elif category == "excursion":
            category_emoji = "🏛️"
        elif category == "exhibition":
            category_emoji = "🖼️"
        elif category == "networking":
            category_emoji = "👋"
        elif category == "boardgames":
            category_emoji = "🎲"
        elif category == "other":
            category_emoji = "🔍"

        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{category_emoji} {event['name']}", callback_data=f"my_event_{event_idx}")
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"my_page_{page - 1}"))
    if end_idx < len(registered_events):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"my_page_{page + 1}"))

    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    users = load_users()

    if user_id in users:
        await message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=f"👋 Добро пожаловать обратно, {users[user_id]['name']}!",
            reply_markup=get_main_menu(user_id)
        )
    else:
        await message.answer("👋 Добро пожаловать! Пожалуйста, введите ваше имя и фамилию:")
        await state.set_state(RegistrationStates.name)


@dp.message(RegistrationStates.name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await message.answer("🏫 Введите ваш факультет:")
    await state.set_state(RegistrationStates.faculty)


@dp.message(RegistrationStates.faculty)
async def process_faculty(message: types.Message, state: FSMContext):
    faculty = message.text.strip()
    user_data = await state.get_data()
    user_data["faculty"] = faculty
    user_data["registered_events"] = []
    user_data["is_admin"] = False
    user_id = str(message.from_user.id)

    save_user(user_id, user_data)

    await message.answer_photo(
        photo=FSInputFile(MENU_IMAGE_PATH),
        caption=f"✅ Регистрация завершена! Добро пожаловать, {user_data['name']}!",
        reply_markup=get_main_menu(user_id)
    )
    await state.clear()


@dp.callback_query(lambda c: c.data.startswith("pending_page_"))
async def process_pending_page(callback_query: types.CallbackQuery):
    await callback_query.answer()
    page = int(callback_query.data.split("_")[2])
    await callback_query.message.edit_reply_markup(
        reply_markup=get_pending_events_list(page)
    )


@dp.callback_query(lambda c: c.data.startswith("page_"))
async def process_page(callback_query: types.CallbackQuery):
    await callback_query.answer()
    _, category, page = callback_query.data.split("_")
    page = int(page)
    await callback_query.message.edit_reply_markup(
        reply_markup=get_events_list(category, page)
    )


@dp.callback_query(lambda c: c.data.startswith("my_page_"))
async def process_my_page(callback_query: types.CallbackQuery):
    await callback_query.answer()
    page = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)
    await callback_query.message.edit_reply_markup(
        reply_markup=get_my_events_list(user_id, page)
    )


@dp.callback_query(lambda c: c.data.startswith("event_") and c.data.split("_")[1].isdigit())
async def process_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[1])
    events = load_events()

    if event_idx >= len(events):
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_event_categories()
        )
        return

    event = events[event_idx]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Зарегистрироваться", callback_data=f"register_for_event_{event_idx}")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_events")]
    ])

    category = event.get("category", "unknown")
    category_emoji = ""
    if category == "party":
        category_emoji = "🎉"
    elif category == "outdoor":
        category_emoji = "🌳"
    elif category == "excursion":
        category_emoji = "🏛️"
    elif category == "exhibition":
        category_emoji = "🖼️"
    elif category == "networking":
        category_emoji = "👋"
    elif category == "boardgames":
        category_emoji = "🎲"
    elif category == "other":
        category_emoji = "🔍"

    category_name = event.get("category_name", "Без категории")
    event_type = f"{category_emoji} {category_name}"

    # Добавляем информацию о ссылках, если они есть
    links_info = ""
    tg_link = event.get("tg_link", "")
    tg_chat_link = event.get("tg_chat_link", "")

    if tg_link:
        links_info += f"\n🔗 **Канал:** {tg_link}"
    if tg_chat_link:
        links_info += f"\n💬 **Чат:** {tg_chat_link}"

    caption = (
        f"📌 **{event['name']}**\n\n"
        f"📝 **Описание:** {event['description']}\n"
        f"📅 **Дата и время:** {event['time']}\n"
        f"📍 **Место:** {event['location']}\n"
        f"🏷️ **Тип:** {event_type}{links_info}"
    )

    try:
        await callback_query.message.edit_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


@dp.callback_query(lambda c: c.data.startswith("my_event_"))
async def process_my_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    events = load_events()

    if event_idx >= len(events):
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_main_menu()
        )
        return

    event = events[event_idx]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Назад к моим мероприятиям", callback_data="my_events")],
        [InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_main")]
    ])

    category = event.get("category", "unknown")
    category_emoji = ""
    if category == "party":
        category_emoji = "🎉"
    elif category == "outdoor":
        category_emoji = "🌳"
    elif category == "excursion":
        category_emoji = "🏛️"
    elif category == "exhibition":
        category_emoji = "🖼️"
    elif category == "networking":
        category_emoji = "👋"
    elif category == "boardgames":
        category_emoji = "🎲"
    elif category == "other":
        category_emoji = "🔍"

    category_name = event.get("category_name", "Без категории")
    event_type = f"{category_emoji} {category_name}"

    # Добавляем информацию о ссылках, если они есть
    links_info = ""
    tg_link = event.get("tg_link", "")
    tg_chat_link = event.get("tg_chat_link", "")

    if tg_link:
        links_info += f"\n🔗 **Канал:** {tg_link}"
    if tg_chat_link:
        links_info += f"\n💬 **Чат:** {tg_chat_link}"

    caption = (
        f"📌 **{event['name']}**\n\n"
        f"📝 **Описание:** {event['description']}\n"
        f"📅 **Дата и время:** {event['time']}\n"
        f"📍 **Место:** {event['location']}\n"
        f"🏷️ **Тип:** {event_type}{links_info}"
    )

    try:
        await callback_query.message.edit_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


@dp.callback_query(lambda c: c.data == "register_event")
async def process_register_event(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer(
        "📝 Введите название мероприятия:"
    )
    await state.set_state(EventRegistrationStates.name)


@dp.message(EventRegistrationStates.name)
async def process_event_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("📋 Введите описание мероприятия:")
    await state.set_state(EventRegistrationStates.description)


@dp.message(EventRegistrationStates.description)
async def process_event_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer("📍 Введите место проведения мероприятия:")
    await state.set_state(EventRegistrationStates.location)


@dp.message(EventRegistrationStates.location)
async def process_event_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await message.answer("📅 Введите дату и время проведения мероприятия:")
    await state.set_state(EventRegistrationStates.time)


@dp.message(EventRegistrationStates.time)
async def process_event_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text.strip())
    await message.answer("🔗 Введите ссылку на Telegram канал (или напишите 'нет', если его нет):")
    await state.set_state(EventRegistrationStates.tg_link)


@dp.message(EventRegistrationStates.tg_link)
async def process_event_tg_link(message: types.Message, state: FSMContext):
    tg_link = message.text.strip()
    if tg_link.lower() == 'нет':
        tg_link = ""
    await state.update_data(tg_link=tg_link)
    await message.answer("💬 Введите ссылку на Telegram беседу (или напишите 'нет', если её нет):")
    await state.set_state(EventRegistrationStates.tg_chat_link)


@dp.message(EventRegistrationStates.tg_chat_link)
async def process_event_tg_chat_link(message: types.Message, state: FSMContext):
    tg_chat_link = message.text.strip()
    if tg_chat_link.lower() == 'нет':
        tg_chat_link = ""
    await state.update_data(tg_chat_link=tg_chat_link)

    # Новая клавиатура с типами мероприятий, включая "Другое"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎉 Тусовки", callback_data="event_type_party")],
        [InlineKeyboardButton(text="🌳 Выезды загород", callback_data="event_type_outdoor")],
        [InlineKeyboardButton(text="🏛️ Экскурсии", callback_data="event_type_excursion")],
        [InlineKeyboardButton(text="🖼️ Выставки/музеи", callback_data="event_type_exhibition")],
        [InlineKeyboardButton(text="👋 Знакомства", callback_data="event_type_networking")],
        [InlineKeyboardButton(text="🎲 Настольные игры", callback_data="event_type_boardgames")],
        [InlineKeyboardButton(text="🔍 Другое", callback_data="event_type_other")]
    ])

    await message.answer("🏷️ Выберите тип мероприятия:", reply_markup=keyboard)
    await state.set_state(EventRegistrationStates.category)


@dp.callback_query(lambda c: c.data.startswith("event_type_"))
async def process_event_type(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    event_type = callback_query.data.split("_")[2]
    user_id = str(callback_query.from_user.id)

    # Сопоставление типов и их названий для хранения, добавлена категория "Другое"
    event_types = {
        "party": "Тусовки",
        "outdoor": "Выезды загород",
        "excursion": "Экскурсии",
        "exhibition": "Выставки/музеи",
        "networking": "Знакомства",
        "boardgames": "Настольные игры",
        "other": "Другое"
    }

    event_data = await state.get_data()
    event_data["category"] = event_type
    event_data["category_name"] = event_types[event_type]

    users = load_users()
    if user_id in users:
        event_data["creator_id"] = user_id
        event_data["creator_name"] = users[user_id]["name"]

    # Сразу сохраняем мероприятие
    save_event(event_data)

    await callback_query.message.answer_photo(
        photo=FSInputFile(MENU_IMAGE_PATH),
        caption="✅ Мероприятие успешно зарегистрировано!",
        reply_markup=get_main_menu(user_id)
    )

    await state.clear()


@dp.callback_query(lambda c: c.data.startswith("register_for_event_"))
async def register_for_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[3])
    user_id = str(callback_query.from_user.id)
    events = load_events()

    if event_idx >= len(events):
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_main_menu(user_id)
        )
        return

    event = events[event_idx]

    success = register_user_for_event(user_id, event_idx)

    if success:
        # Добавляем ссылки при регистрации на мероприятие
        links_text = ""
        tg_link = event.get("tg_link", "")
        tg_chat_link = event.get("tg_chat_link", "")

        if tg_link:
            links_text += f"\n\n🔗 Telegram канал: {tg_link}"
        if tg_chat_link:
            links_text += f"\n💬 Telegram чат: {tg_chat_link}"

        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=f"✅ Вы успешно зарегистрировались на мероприятие \"{event['name']}\"!{links_text}",
            reply_markup=get_main_menu(user_id)
        )
    else:
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=f"ℹ️ Вы уже зарегистрированы на это мероприятие",
            reply_markup=get_main_menu(user_id)
        )


@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)
    await callback_query.message.edit_caption(
        caption="🏠 Главное меню",
        reply_markup=get_main_menu(user_id)
    )


@dp.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_caption(
        caption="🎭 Выберите категорию мероприятий:",
        reply_markup=get_event_categories()
    )


@dp.callback_query(lambda c: c.data == "back_to_events")
async def back_to_events(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_caption(
        caption="🎭 Выберите категорию мероприятий:",
        reply_markup=get_event_categories()
    )


@dp.callback_query(lambda c: c.data.startswith("category_"))
async def process_category_selection(callback_query: types.CallbackQuery):
    await callback_query.answer()
    category = callback_query.data.split("_")[1]

    category_names = {
        "party": "Тусовки",
        "outdoor": "Выезды загород",
        "excursion": "Экскурсии",
        "exhibition": "Выставки/музеи",
        "networking": "Знакомства",
        "boardgames": "Настольные игры",
        "other": "Другое"
    }

    category_emojis = {
        "party": "🎉",
        "outdoor": "🌳",
        "excursion": "🏛️",
        "exhibition": "🖼️",
        "networking": "👋",
        "boardgames": "🎲",
        "other": "🔍"
    }

    await callback_query.message.edit_caption(
        caption=f"{category_emojis.get(category, '')} Мероприятия категории «{category_names.get(category, category)}»",
        reply_markup=get_events_list(category, 0)
    )


@dp.callback_query(lambda c: c.data == "view_events")
async def view_events(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_caption(
        caption="🎭 Выберите категорию мероприятий:",
        reply_markup=get_event_categories()
    )


@dp.callback_query(lambda c: c.data == "my_events")
async def my_events(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)
    await callback_query.message.edit_caption(
        caption="📅 Мои мероприятия:",
        reply_markup=get_my_events_list(user_id, 0)
    )


async def main():
    ensure_files_exist()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())