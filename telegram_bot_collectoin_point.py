import logging
import json
import os
import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

API_TOKEN = '7396576561:AAHb42DqAk6t4Zkjbyw2Q3kA9bIDac6d3xU'
ADMIN_PASSWORD = 'admin123'
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


def is_admin(user_id):
    users = load_users()
    return user_id in users and users[user_id].get("is_admin", False)


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
        event_type = "🏛️ Официальное" if event.get("is_official", False) else "🎉 Неформальное"
        category_name = event.get("category", "без категории")
        category_emoji = ""
        if category_name == "official":
            category_emoji = "🏛️"
        elif category_name == "informal":
            category_emoji = "🎉"
        elif category_name == "recommendations":
            category_emoji = "✨"
        elif category_name == "networking":
            category_emoji = "👋"

        result += f"**{idx + 1}. {event['name']}**\n"
        result += f"   {event_type}, Категория: {category_emoji} {category_name}\n"
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
        event_type = "Официальное" if event.get("is_official", False) else "Неформальное"
        category = event.get("category", "без категории")
        result += f"{idx + 1}. {event['name']}\n"
        result += f"   Тип: {event_type}, Категория: {category}\n"
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
    is_official = State()


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

    if user_id and is_admin(user_id):
        keyboard_buttons.append([InlineKeyboardButton(text="👑 Панель администратора", callback_data="admin_panel")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_event_categories():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛️ Официальные мероприятия", callback_data="category_official")],
        [InlineKeyboardButton(text="🎉 Неформальные", callback_data="category_informal")],
        [InlineKeyboardButton(text="✨ Рекомендации", callback_data="category_recommendations")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    return keyboard


def get_admin_panel():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Управление мероприятиями", callback_data="manage_events")],
        [InlineKeyboardButton(text="✅ Одобрить ожидающие мероприятия", callback_data="approve_events")],
        [InlineKeyboardButton(text="🏛️ Создать официальное мероприятие", callback_data="create_official_event")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main")]
    ])
    return keyboard


def get_pending_events_list(page=0):
    events = load_pending_events()

    keyboard_buttons = []
    start_idx = page * 5
    end_idx = min(start_idx + 5, len(events))

    for i in range(start_idx, end_idx):
        event = events[i]
        event_emoji = "🏛️" if event.get("is_official", False) else "🎉"
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{event_emoji} {event['name']}", callback_data=f"pending_event_{i}")
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
        event_emoji = "🏛️" if event.get("is_official", False) else "🎉"
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{event_emoji} {event['name']}", callback_data=f"event_{i}")
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
        event_emoji = "🏛️" if event.get("is_official", False) else "🎉"
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{event_emoji} {event['name']}", callback_data=f"my_event_{event_idx}")
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


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    await message.answer("👑 Введите пароль администратора:")
    await state.set_state(AdminPasswordState.waiting_password)


@dp.message(AdminPasswordState.waiting_password)
async def process_admin_password(message: types.Message, state: FSMContext):
    password = message.text.strip()

    if password == ADMIN_PASSWORD:
        user_id = str(message.from_user.id)
        users = load_users()

        if user_id in users:
            users[user_id]["is_admin"] = True
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=2)

            await message.answer("✅ Вы успешно назначены администратором!")
        else:
            await message.answer("⚠️ Вы должны сначала зарегистрироваться в системе.")
    else:
        await message.answer("❌ Неверный пароль.")

    await state.clear()


from aiogram.fsm.context import FSMContext
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


@dp.callback_query(lambda c: c.data == "admin_panel")
async def process_admin_panel(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)

    if not is_admin(user_id):
        await callback_query.message.edit_caption(
            caption="⚠️ У вас нет прав администратора.",
            reply_markup=get_main_menu(user_id)
        )
        return

    await callback_query.message.edit_caption(
        caption="👑 **Панель администратора**\n\nВыберите действие:",
        reply_markup=get_admin_panel(),
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "approve_events")
async def process_approve_events(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)

    if not is_admin(user_id):
        await callback_query.message.edit_caption(
            caption="⚠️ У вас нет прав администратора.",
            reply_markup=get_main_menu(user_id)
        )
        return

    pending_events = load_pending_events()

    if not pending_events:
        await callback_query.message.edit_caption(
            caption="📭 Нет ожидающих одобрения мероприятий.",
            reply_markup=get_admin_panel()
        )
        return

    await callback_query.message.edit_caption(
        caption="📋 Ожидающие одобрения мероприятия:",
        reply_markup=get_pending_events_list()
    )


@dp.callback_query(lambda c: c.data.startswith("pending_page_"))
async def process_pending_page(callback_query: types.CallbackQuery):
    await callback_query.answer()
    page = int(callback_query.data.split("_")[2])
    await callback_query.message.edit_reply_markup(
        reply_markup=get_pending_events_list(page)
    )


@dp.callback_query(lambda c: c.data.startswith("pending_event_"))
async def process_pending_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    if not is_admin(user_id):
        await callback_query.message.edit_caption(
            caption="⚠️ У вас нет прав администратора.",
            reply_markup=get_main_menu(user_id)
        )
        return

    pending_events = load_pending_events()

    if event_idx >= len(pending_events):
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_pending_events_list()
        )
        return

    event = pending_events[event_idx]

    event_type = "🏛️ Официальное" if event.get("is_official", False) else "🎉 Неформальное"

    caption = (
        f"📌 **{event['name']}**\n\n"
        f"📝 **Описание:** {event['description']}\n"
        f"📅 **Дата и время:** {event['time']}\n"
        f"📍 **Место:** {event['location']}\n"
        f"🏷️ **Тип:** {event_type}\n\n"
        f"👤 **Создатель:** {event.get('creator_name', 'Неизвестно')}"
    )

    try:
        await callback_query.message.edit_caption(
            caption=caption,
            reply_markup=get_pending_event_actions(event_idx),
            parse_mode="Markdown"
        )
    except Exception as e:
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=caption,
            reply_markup=get_pending_event_actions(event_idx),
            parse_mode="Markdown"
        )


@dp.callback_query(lambda c: c.data.startswith("approve_event_"))
async def approve_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    if not is_admin(user_id):
        await callback_query.message.edit_caption(
            caption="⚠️ У вас нет прав администратора.",
            reply_markup=get_main_menu(user_id)
        )
        return

    event = remove_pending_event(event_idx)

    if event:
        save_event(event)

        await callback_query.message.edit_caption(
            caption=f"✅ Мероприятие \"{event['name']}\" одобрено и добавлено в список!",
            reply_markup=get_admin_panel()
        )
    else:
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_admin_panel()
        )


@dp.callback_query(lambda c: c.data.startswith("reject_event_"))
async def reject_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    if not is_admin(user_id):
        await callback_query.message.edit_caption(
            caption="⚠️ У вас нет прав администратора.",
            reply_markup=get_main_menu(user_id)
        )
        return

    event = remove_pending_event(event_idx)

    if event:
        await callback_query.message.edit_caption(
            caption=f"❌ Мероприятие \"{event['name']}\" отклонено!",
            reply_markup=get_admin_panel()
        )
    else:
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_admin_panel()
        )


@dp.callback_query(lambda c: c.data == "create_official_event")
async def create_official_event(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)

    if not is_admin(user_id):
        await callback_query.message.edit_caption(
            caption="⚠️ У вас нет прав администратора.",
            reply_markup=get_main_menu(user_id)
        )
        return

    await state.update_data(is_official=True, is_admin_created=True)

    await callback_query.message.answer(
        "📝 Введите название официального мероприятия:"
    )
    await state.set_state(EventRegistrationStates.name)


@dp.callback_query(lambda c: c.data == "view_events")
async def process_view_events(callback_query: types.CallbackQuery):
    await callback_query.answer()

    try:
        await callback_query.message.edit_caption(
            caption="🎭 Выберите категорию мероприятий:",
            reply_markup=get_event_categories()
        )
    except Exception as e:
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption="🎭 Выберите категорию мероприятий:",
            reply_markup=get_event_categories()
        )


@dp.callback_query(lambda c: c.data == "my_events")
async def process_my_events(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)
    users = load_users()

    if user_id not in users:
        await callback_query.message.edit_caption(
            caption="⚠️ Вы не зарегистрированы в системе",
            reply_markup=get_main_menu(user_id)
        )
        return

    if "registered_events" not in users[user_id] or not users[user_id]["registered_events"]:
        await callback_query.message.edit_caption(
            caption="📭 Вы не зарегистрированы ни на одно мероприятие",
            reply_markup=get_main_menu(user_id)
        )
        return

    await callback_query.message.edit_caption(
        caption="📅 Ваши мероприятия:",
        reply_markup=get_my_events_list(user_id)
    )


@dp.callback_query(lambda c: c.data.startswith("category_"))
async def process_category(callback_query: types.CallbackQuery):
    await callback_query.answer()
    category = callback_query.data.split("_")[1]

    if category == "recommendations":
        events_text = get_events_list_text()
        await callback_query.message.edit_caption(
            caption=f"✨ **Раздел рекомендаций**\n\n{events_text}\n🤖 **Хотите получить персональные рекомендации?**",
            reply_markup=get_recommendations_menu(),
            parse_mode="Markdown"
        )
        return

    events = load_events()
    filtered_events = [e for e in events if e.get("category") == category]

    category_emoji = "🎭"
    if category == "official":
        category_emoji = "🏛️"
    elif category == "informal":
        category_emoji = "🎉"
    elif category == "networking":
        category_emoji = "👋"

    if not filtered_events:
        await callback_query.message.edit_caption(
            caption=f"{category_emoji} В этой категории пока нет мероприятий",
            reply_markup=get_event_categories()
        )
    else:
        await callback_query.message.edit_caption(
            caption=f"{category_emoji} Список мероприятий в категории:",
            reply_markup=get_events_list(category)
        )


@dp.callback_query(lambda c: c.data == "consult_ai")
async def process_consult_ai(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()

    events_info = get_all_events_info()

    await state.update_data(ai_context="")

    await callback_query.message.answer(
        text="🤖 **Начинаю консультацию...**\n\nУ меня есть информация обо всех доступных мероприятиях. Расскажите, что вам интересно, и я помогу выбрать подходящее мероприятие!",
        parse_mode="Markdown",
        reply_markup=get_end_consultation_keyboard()
    )

    initial_message = (
        "Привет! Я интеллектуальный помощник по выбору мероприятий. "
        "Я знаю о следующих мероприятиях и могу помочь вам выбрать подходящее. "
        "Расскажите, какие мероприятия вас интересуют, или какие критерии важны для вас (тематика, время, формат)?"
    )

    ai_prompt = (
        f"Ты - ассистент бота для мероприятий. Твоя задача помочь пользователю выбрать подходящее мероприятие "
        f"из списка доступных. Вот информация о всех доступных мероприятиях:\n\n{events_info}\n\n"
        f"Используй эту информацию, чтобы рекомендовать пользователю конкретные мероприятия на основе его интересов, "
        f"времени, предпочтений по формату и т.д. Задавай уточняющие вопросы, если нужно. "
        f"Будь дружелюбным и полезным. Первое сообщение от пользователя: 'Помоги мне выбрать мероприятие'"
    )

    ai_response, new_context = await get_ai_response(ai_prompt)

    await state.update_data(ai_context=new_context)

    await state.set_state(AIConsultationStates.conversation)

    await callback_query.message.answer(
        text=ai_response,
        reply_markup=get_end_consultation_keyboard()
    )


@dp.message(AIConsultationStates.conversation)
async def process_ai_conversation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ai_context = data.get("ai_context", "")

    await message.answer("🤖 Думаю...")

    ai_response, new_context = await get_ai_response(message.text, ai_context)

    await state.update_data(ai_context=new_context)

    await message.answer(
        text=ai_response,
        reply_markup=get_end_consultation_keyboard()
    )


@dp.callback_query(lambda c: c.data == "end_consultation")
async def end_consultation(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)

    await state.clear()

    await callback_query.message.answer_photo(
        photo=FSInputFile(MENU_IMAGE_PATH),
        caption="✅ Консультация завершена. Возвращаемся в главное меню.",
        reply_markup=get_main_menu(user_id)
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

    event_type = "🏛️ Официальное" if event.get("is_official", False) else "🎉 Неформальное"

    caption = (
        f"📌 **{event['name']}**\n\n"
        f"📝 **Описание:** {event['description']}\n"
        f"📅 **Дата и время:** {event['time']}\n"
        f"📍 **Место:** {event['location']}\n"
        f"🏷️ **Тип:** {event_type}"
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

    event_type = "🏛️ Официальное" if event.get("is_official", False) else "🎉 Неформальное"

    caption = (
        f"📌 **{event['name']}**\n\n"
        f"📝 **Описание:** {event['description']}\n"
        f"📅 **Дата и время:** {event['time']}\n"
        f"📍 **Место:** {event['location']}\n"
        f"🏷️ **Тип:** {event_type}"
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
    user_id = str(message.from_user.id)

    user_data = await state.get_data()
    is_admin_created = user_data.get("is_admin_created", False)

    if is_admin_created:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏛️ Официальное", callback_data="set_category_official")],
            [InlineKeyboardButton(text="✨ Рекомендация", callback_data="set_category_recommendations")],
            [InlineKeyboardButton(text="👋 Знакомство", callback_data="set_category_networking")]
        ])

        await message.answer("📂 Выберите категорию официального мероприятия:", reply_markup=keyboard)
        await state.set_state(EventRegistrationStates.is_official)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏛️ Официальное", callback_data="event_type_official")],
            [InlineKeyboardButton(text="🎉 Неформальное", callback_data="event_type_informal")]
        ])

        await message.answer("🏷️ Выберите тип мероприятия:", reply_markup=keyboard)
        await state.set_state(EventRegistrationStates.is_official)


@dp.callback_query(lambda c: c.data.startswith("event_type_"))
async def process_event_type(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    event_type = callback_query.data.split("_")[2]
    is_official = event_type == "official"
    user_id = str(callback_query.from_user.id)

    if is_official and not is_admin(user_id):
        await callback_query.message.edit_text(
            "⚠️ Только администраторы могут создавать официальные мероприятия. Ваше мероприятие будет отправлено на проверку.",
            reply_markup=None
        )

    event_data = await state.get_data()
    event_data["is_official"] = is_official

    users = load_users()
    if user_id in users:
        event_data["creator_id"] = user_id
        event_data["creator_name"] = users[user_id]["name"]

    await state.update_data(is_official=is_official)

    if is_official:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏛️ Официальное", callback_data="set_category_official")],
            [InlineKeyboardButton(text="✨ Рекомендация", callback_data="set_category_recommendations")],
            [InlineKeyboardButton(text="👋 Знакомство", callback_data="set_category_networking")]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Неформальное", callback_data="set_category_informal")],
            [InlineKeyboardButton(text="✨ Рекомендация", callback_data="set_category_recommendations")],
            [InlineKeyboardButton(text="👋 Знакомство", callback_data="set_category_networking")]
        ])

    await callback_query.message.edit_text("📂 Выберите категорию мероприятия:", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data.startswith("set_category_"))
async def set_event_category(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = str(callback_query.from_user.id)

    current_state = await state.get_state()
    if current_state == EventRegistrationStates.is_official:
        category = callback_query.data.split("_")[2]
        user_data = await state.get_data()
        user_data["category"] = category

        is_official = user_data.get("is_official", False)
        is_admin_created = user_data.get("is_admin_created", False)

        if is_official and not is_admin(user_id) and not is_admin_created:
            save_pending_event(user_data)

            await callback_query.message.answer_photo(
                photo=FSInputFile(MENU_IMAGE_PATH),
                caption="📤 Ваше официальное мероприятие отправлено на проверку администратору. После одобрения оно появится в списке мероприятий.",
                reply_markup=get_main_menu(user_id)
            )
        else:
            save_event(user_data)

            await callback_query.message.answer_photo(
                photo=FSInputFile(MENU_IMAGE_PATH),
                caption="✅ Мероприятие успешно зарегистрировано!",
                reply_markup=get_main_menu(user_id)
            )

        await state.clear()
    else:
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption="⚠️ Что-то пошло не так",
            reply_markup=get_main_menu(user_id)
        )


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
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=f"✅ Вы успешно зарегистрировались на мероприятие \"{event['name']}\"!",
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


async def main():
    ensure_files_exist()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())