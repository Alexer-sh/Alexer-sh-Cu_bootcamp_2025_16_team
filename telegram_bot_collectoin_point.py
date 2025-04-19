import logging
import json
import os
import asyncio
import re
import datetime
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

# Глобальные константы для категорий мероприятий
EVENT_TYPES = {
    "party": {"name": "Тусовки", "emoji": "🎉"},
    "outdoor": {"name": "Выезды загород", "emoji": "🌳"},
    "excursion": {"name": "Экскурсии", "emoji": "🏛️"},
    "exhibition": {"name": "Выставки/музеи", "emoji": "🖼️"},
    "networking": {"name": "Знакомства", "emoji": "👋"},
    "boardgames": {"name": "Настольные игры", "emoji": "🎲"},
    "other": {"name": "Другое", "emoji": "🔍"}
}


async def get_ai_response(user_message, ai_context="", max_retries=3, timeout=30):
    current_message = f"\nUser: {user_message}"

    data = {
        'max_tokens': AI_TOKEN,
        'responseType': 'normal',
        'osType': 'iOS',
        'model': AI_MODEL,
        'value': f"ПРОШЛЫЕ СООБЩЕНИЯ: {ai_context}{current_message}",
        'search': user_message
    }

    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                lambda: requests.post(AI_URL, headers=AI_HEADERS,
                                      data=json.dumps(data), timeout=timeout)
            )

            if response.status_code == 200:
                response_data = response.json()
                content = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

                if content:
                    return content, ai_context + current_message + f"\nAI: {content}"
                else:
                    logging.warning("Пустой ответ от AI")
            else:
                logging.error(f"Ошибка AI API: {response.status_code}")

            # Пауза перед повторной попыткой
            if attempt < max_retries - 1:
                await asyncio.sleep(1)

        except Exception as e:
            logging.error(f"Ошибка при запросе к AI: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)

    return "Извините, не удалось получить ответ от ИИ.", ai_context


def load_data(filename):
    """Универсальная функция загрузки данных из JSON файла."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        default_data = [] if filename in [EVENTS_FILE, PENDING_EVENTS_FILE] else {}
        save_data(filename, default_data)
        return default_data
    except json.JSONDecodeError:
        logging.error(f"Ошибка декодирования JSON в файле {filename}")
        return [] if filename in [EVENTS_FILE, PENDING_EVENTS_FILE] else {}


def save_data(filename, data):
    """Универсальная функция сохранения данных в JSON файл."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_alpha(text: str) -> bool:
    # Разрешаем только буквы (латиница и кириллица) и пробелы
    return bool(re.fullmatch(r"[A-Za-zА-Яа-яЁё\s]+", text))


# Функция для проверки валидности ссылки (начинается с t.me)
def is_valid_telegram_link(link):
    return link.startswith("https://t.me/") or link.startswith("t.me/")

# Функция для проверки валидности даты в формате ДД.ММ.ГГГГ
def is_valid_date(date_text):
    try:
        datetime.datetime.strptime(date_text, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def ensure_files_exist():
    """Проверяет существование необходимых файлов и создаёт их при необходимости."""
    files_templates = {
        USERS_FILE: {},
        EVENTS_FILE: [],
        PENDING_EVENTS_FILE: []
    }

    for file, template in files_templates.items():
        if not os.path.exists(file):
            save_data(file, template)


def load_users():
    return load_data(USERS_FILE)


def save_user(user_id, user_data):
    users = load_users()
    users[user_id] = user_data
    save_data(USERS_FILE, users)


def load_events():
    return load_data(EVENTS_FILE)


def save_event(event_data):
    events = load_events()
    events.append(event_data)
    save_data(EVENTS_FILE, events)


def load_pending_events():
    return load_data(PENDING_EVENTS_FILE)


def save_pending_event(event_data):
    events = load_pending_events()
    events.append(event_data)
    save_data(PENDING_EVENTS_FILE, events)


def remove_pending_event(event_idx):
    events = load_pending_events()
    if 0 <= event_idx < len(events):
        removed_event = events.pop(event_idx)
        save_data(PENDING_EVENTS_FILE, events)
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
        save_data(USERS_FILE, users)
        return True
    return False


def format_event_caption(event, show_creator=True, include_links=True):
    """Форматирует текст с информацией о событии для отображения пользователю"""
    category = event.get("category", "unknown")
    category_emoji = EVENT_TYPES.get(category, {}).get("emoji", "🔍")
    category_name = EVENT_TYPES.get(category, {}).get("name", "Без категории")

    # Добавляем информацию о ссылках, если они есть
    links_info = ""
    if include_links:
        tg_link = event.get("tg_link", "")
        tg_chat_link = event.get("tg_chat_link", "")
        if tg_link:
            links_info += f"\n🔗 **Канал:** {tg_link}"
        if tg_chat_link:
            links_info += f"\n💬 **Чат:** {tg_chat_link}"

    creator_info = ""
    if show_creator and "creator_name" in event:
        creator_info = f"\n👤 **Создатель:** {event['creator_name']}"

    caption = (
        f"📌 **{event['name']}**\n\n"
        f"📝 **Описание:** {event['description']}\n"
        f"📅 **Дата и время:** {event['time']}\n"
        f"📍 **Место:** {event['location']}\n"
        f"🏷️ **Тип:** {category_emoji} {category_name}{links_info}{creator_info}"
    )
    return caption


def get_main_menu(user_id=None):
    keyboard_buttons = [
        [InlineKeyboardButton(text="🎭 Мероприятия", callback_data="view_events")],
        [InlineKeyboardButton(text="📅 Мои мероприятия", callback_data="my_events")],
        [InlineKeyboardButton(text="➕ Зарегистрировать мероприятие", callback_data="register_event")]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def get_event_categories():
    """Создаёт клавиатуру со всеми категориями мероприятий"""
    keyboard = []

    # Добавляем все категории из EVENT_TYPES
    for key, value in EVENT_TYPES.items():
        keyboard.append([
            InlineKeyboardButton(
                text=f"{value['emoji']} {value['name']}",
                callback_data=f"category_{key}"
            )
        ])

    # Добавляем специальные функции
    keyboard.append([
        InlineKeyboardButton(text="🔍 Все мероприятия", callback_data="category_all")
    ])
    keyboard.append([
        InlineKeyboardButton(text="🤖 Посоветовать мероприятие", callback_data="consult_ai")
    ])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
        category_emoji = EVENT_TYPES.get(category, {}).get("emoji", "🔍")

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

    # Список зарегистрированных мероприятий
    registered_events = []
    if user_id in users and "registered_events" in users[user_id]:
        for event_idx in users[user_id]["registered_events"]:
            if event_idx < len(events):
                event = events[event_idx]
                registered_events.append({
                    "index": event_idx,
                    "event": event,
                    "is_creator": event.get("creator_id") == user_id,
                    "is_registered": True
                })

    # Добавляем созданные пользователем мероприятия, если они еще не в списке
    created_events = []
    for event_idx, event in enumerate(events):
        if event.get("creator_id") == user_id and not any(r.get("index") == event_idx for r in registered_events):
            created_events.append({
                "index": event_idx,
                "event": event,
                "is_creator": True,
                "is_registered": False
            })

    # Объединяем списки и сортируем по времени (если есть)
    all_user_events = registered_events + created_events

    keyboard_buttons = []
    start_idx = page * 5
    end_idx = min(start_idx + 5, len(all_user_events))

    for i in range(start_idx, end_idx):
        event_data = all_user_events[i]
        event = event_data["event"]
        event_idx = event_data["index"]
        category = event.get("category", "unknown")
        category_emoji = EVENT_TYPES.get(category, {}).get("emoji", "🔍")

        # Добавляем специальную метку для созданных мероприятий
        prefix = "👑 " if event_data["is_creator"] else ""

        keyboard_buttons.append([
            InlineKeyboardButton(text=f"{prefix}{category_emoji} {event['name']}",
                                 callback_data=f"my_event_{event_idx}")
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"my_page_{page - 1}"))
    if end_idx < len(all_user_events):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"my_page_{page + 1}"))

    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


class RegistrationStates(StatesGroup):
    name = State()
    faculty = State()


class EventRegistrationStates(StatesGroup):
    name = State()
    description = State()
    location = State()
    time = State()
    tg_link = State()
    tg_chat_link = State()
    category = State()


class AIConsultationStates(StatesGroup):
    conversation = State()

class EventEditStates(StatesGroup):
    event_idx = State()
    name = State()
    description = State()
    location = State()
    time = State()
    tg_link = State()
    tg_chat_link = State()
    category = State()


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
    if not is_alpha(name):
        await message.answer("⚠️ Имя должно содержать только буквы. Пожалуйста, введите корректное имя.")
        return
    await state.update_data(name=name)
    await message.answer("🏫 Введите ваш факультет (только буквы):")
    await state.set_state(RegistrationStates.faculty)

@dp.message(RegistrationStates.faculty)
async def process_faculty(message: types.Message, state: FSMContext):
    faculty = message.text.strip()
    if not is_alpha(faculty):
        await message.answer("⚠️ Факультет должен содержать только буквы. Пожалуйста, введите корректный факультет.")
        return
    data = await state.get_data()
    data.update({
        "faculty": faculty,
        "registered_events": [],
        "is_admin": False,
        "active_event_creations": 0
    })
    uid = str(message.from_user.id)
    save_user(uid, data)
    await message.answer_photo(photo=FSInputFile(MENU_IMAGE_PATH),
                               caption=f"✅ Регистрация завершена! Добро пожаловать, {data['name']}!",
                               reply_markup=get_main_menu(uid))
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
    user_id = str(callback_query.from_user.id)
    events = load_events()

    if event_idx >= len(events):
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_event_categories()
        )
        return

    event = events[event_idx]

    # Проверяем, является ли пользователь создателем мероприятия
    is_creator = event.get("creator_id") == user_id

    keyboard_buttons = []
    if is_creator:
        keyboard_buttons.append([InlineKeyboardButton(text="👑 Вы создатель этого мероприятия", callback_data="none")])
    else:
        keyboard_buttons.append(
            [InlineKeyboardButton(text="✅ Зарегистрироваться", callback_data=f"register_for_event_{event_idx}")])

    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_events")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    caption = format_event_caption(event, show_creator=True)

    try:
        await callback_query.message.edit_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


# Обновляем обработчик просмотра своего мероприятия, добавляя кнопку удаления
@dp.callback_query(lambda c: c.data.startswith("my_event_"))
async def process_my_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)
    events = load_events()

    if event_idx >= len(events):
        await callback_query.message.edit_caption(
            caption="⚠️ Мероприятие не найдено",
            reply_markup=get_main_menu()
        )
        return

    event = events[event_idx]
    is_creator = event.get("creator_id") == user_id

    # Проверяем, зарегистрирован ли пользователь на мероприятие
    users = load_users()
    is_registered = False
    if user_id in users and "registered_events" in users[user_id]:
        is_registered = event_idx in users[user_id]["registered_events"]

    # Различные кнопки для создателя и участника
    keyboard_buttons = []
    if is_creator:
        keyboard_buttons.append(
            [InlineKeyboardButton(text="👑 Вы создатель этого мероприятия", callback_data=f"creator_info_{event_idx}")])
        keyboard_buttons.append([InlineKeyboardButton(text="✏️ Редактировать мероприятие",
                                                      callback_data=f"edit_event_{event_idx}")])
        keyboard_buttons.append([InlineKeyboardButton(text="👥 Список участников",
                                                      callback_data=f"view_participants_{event_idx}")])
        # Добавляем кнопку удаления для создателя
        keyboard_buttons.append([InlineKeyboardButton(text="🗑️ Удалить мероприятие",
                                                      callback_data=f"delete_event_{event_idx}")])
    # Добавляем кнопку отмены регистрации для обычных пользователей
    elif is_registered:
        keyboard_buttons.append([InlineKeyboardButton(text="❌ Отменить регистрацию",
                                                      callback_data=f"cancel_registration_{event_idx}")])

    keyboard_buttons.append([InlineKeyboardButton(text="📅 Назад к моим мероприятиям", callback_data="my_events")])
    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    caption = format_event_caption(event, show_creator=True)

    try:
        await callback_query.message.edit_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


# Обработчик нажатия на кнопку удаления (запрос подтверждения)
@dp.callback_query(lambda c: c.data.startswith("delete_event_"))
async def confirm_delete_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    events = load_events()
    if event_idx >= len(events):
        await callback_query.message.answer("⚠️ Мероприятие не найдено")
        return

    event = events[event_idx]

    # Проверяем, является ли пользователь создателем
    if event.get("creator_id") != user_id:
        await callback_query.message.answer("⚠️ Только создатель мероприятия может удалить его")
        return

    # Формируем клавиатуру для подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{event_idx}"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data=f"my_event_{event_idx}")
        ]
    ])

    # Запрашиваем подтверждение
    await callback_query.message.edit_caption(
        caption=f"❓ Вы уверены, что хотите удалить мероприятие \"{event['name']}\"?\n\nЭто действие невозможно отменить!",
        reply_markup=keyboard
    )


# Обработчик подтверждения удаления
@dp.callback_query(lambda c: c.data.startswith("confirm_delete_"))
async def perform_delete_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    events = load_events()
    if event_idx >= len(events):
        await callback_query.message.answer("⚠️ Мероприятие не найдено")
        return

    event = events[event_idx]

    # Проверяем, является ли пользователь создателем
    if event.get("creator_id") != user_id:
        await callback_query.message.answer("⚠️ Только создатель мероприятия может удалить его")
        return

    # Запоминаем название мероприятия перед удалением
    event_name = event.get("name", "Мероприятие")

    # Удаляем мероприятие
    success = delete_event(event_idx)

    if success:
        await callback_query.message.edit_caption(
            caption=f"✅ Мероприятие \"{event_name}\" успешно удалено",
            reply_markup=get_main_menu(user_id)
        )
    else:
        await callback_query.message.edit_caption(
            caption=f"⚠️ Не удалось удалить мероприятие",
            reply_markup=get_main_menu(user_id)
        )


# Обработчик для кнопки "Вы создатель этого мероприятия"
@dp.callback_query(lambda c: c.data.startswith("creator_info_"))
async def creator_info(callback_query: types.CallbackQuery):
    await callback_query.answer("Вы являетесь создателем этого мероприятия")

# Функция для удаления мероприятия
def delete_event(event_idx):
    events = load_events()
    users = load_users()

    # Проверяем, что индекс корректный
    if event_idx >= len(events):
        return False

    # Удаляем мероприятие из списка мероприятий
    removed_event = events.pop(event_idx)

    # Удаляем регистрации пользователей на это мероприятие
    for user_id, user_data in users.items():
        if "registered_events" in user_data:
            # Удаляем индекс текущего мероприятия, если он есть
            if event_idx in user_data["registered_events"]:
                user_data["registered_events"].remove(event_idx)

            # Корректируем индексы мероприятий, которые идут после удаленного
            updated_registrations = []
            for reg_idx in user_data["registered_events"]:
                if reg_idx > event_idx:
                    updated_registrations.append(reg_idx - 1)
                else:
                    updated_registrations.append(reg_idx)

            user_data["registered_events"] = updated_registrations

    # Сохраняем обновленные данные
    save_data(EVENTS_FILE, events)
    save_data(USERS_FILE, users)

    return True


def cancel_user_registration_for_event(user_id, event_idx):
    users = load_users()
    if user_id not in users:
        return False

    if "registered_events" not in users[user_id]:
        return False

    if event_idx in users[user_id]["registered_events"]:
        users[user_id]["registered_events"].remove(event_idx)
        save_data(USERS_FILE, users)
        return True
    return False


@dp.callback_query(lambda c: c.data.startswith("cancel_registration_"))
async def cancel_event_registration(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    events = load_events()
    if event_idx >= len(events):
        await callback_query.message.answer("⚠️ Мероприятие не найдено")
        return

    event = events[event_idx]

    # Проверяем, не является ли пользователь создателем мероприятия
    if event.get("creator_id") == user_id:
        await callback_query.message.answer("⚠️ Создатель мероприятия не может отменить свою регистрацию")
        return

    success = cancel_user_registration_for_event(user_id, event_idx)

    if success:
        caption = f"✅ Регистрация на мероприятие \"{event['name']}\" отменена"
    else:
        caption = f"ℹ️ Вы не были зарегистрированы на это мероприятие"

    await callback_query.message.answer_photo(
        photo=FSInputFile(MENU_IMAGE_PATH),
        caption=caption,
        reply_markup=get_main_menu(user_id)
    )


# Функция для создания клавиатуры с кнопкой отмены
def get_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить создание мероприятия", callback_data="cancel_event_creation")]
    ])


@dp.callback_query(lambda c: c.data == "register_event")
async def process_register_event(callback_query: types.CallbackQuery, state: FSMContext):
    uid = str(callback_query.from_user.id)
    users = load_users()
    if uid in users:
        if users[uid].get('active_event_creations', 0) >= 1:
            await callback_query.answer("⚠️ Вы уже создали 1 мероприятие, нельзя создать больше.")
            return
        users[uid]['active_event_creations'] = users[uid].get('active_event_creations', 0) + 1
        save_user(uid, users[uid])
    await callback_query.answer()
    await callback_query.message.answer("📝 Введите название мероприятия:", reply_markup=get_cancel_keyboard())
    await state.set_state(EventRegistrationStates.name)

@dp.message(EventRegistrationStates.name)
async def process_event_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("📋 Введите описание мероприятия:")
    await state.set_state(EventRegistrationStates.description)


@dp.message(EventRegistrationStates.description)
async def process_event_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer(
        "📍 Введите место проведения мероприятия:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EventRegistrationStates.location)


@dp.message(EventRegistrationStates.location)
async def process_event_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await message.answer(
        "📅 Введите дату и время проведения мероприятия:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EventRegistrationStates.time)


@dp.message(EventRegistrationStates.time)
async def process_event_time(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    # Проверяем формат даты ДД.ММ.ГГГГ
    if not is_valid_date(date_str):
        await message.answer("⚠️ Дата должна быть в формате ДД.ММ.ГГГГ. Попробуйте ещё раз:", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(time=date_str)
    await message.answer(
        "🔗 Введите ссылку на Telegram канал (или напишите 'нет', если его нет):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EventRegistrationStates.tg_link)
@dp.message(EventRegistrationStates.tg_link)
async def reg_tg_link(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if link.lower() != 'нет' and not is_valid_telegram_link(link):
        await message.answer("⚠️ Ссылка должна начинаться с t.me/ или https://t.me/. Попробуйте ещё раз:")
        return

    if link.lower() == 'нет':
        link = ""
    await state.update_data(tg_link=link)
    await message.answer("💬 Введите ссылку на Telegram чат (или напишите 'нет', если её нет):", reply_markup=get_cancel_keyboard())
    await state.set_state(EventRegistrationStates.tg_chat_link)

@dp.message(EventRegistrationStates.tg_chat_link)
async def reg_tg_chat(message: types.Message, state: FSMContext):
    tg_chat_link = message.text.strip()
    if tg_chat_link.lower() != 'нет' and not is_valid_telegram_link(tg_chat_link):
        await message.answer("⚠️ Ссылка должна начинаться с t.me/ или https://t.me/. Попробуйте ещё раз:")
        return
    if tg_chat_link.lower() == 'нет':
        tg_chat_link = ""
    await state.update_data(tg_chat_link=tg_chat_link)
    # Для последнего шага объединяем клавиатуру выбора типа с кнопкой отмены
    event_type_keyboard = get_event_type_keyboard()
    keyboard_buttons = list(event_type_keyboard.inline_keyboard)
    keyboard_buttons.append(
        [InlineKeyboardButton(text="❌ Отменить создание мероприятия", callback_data="cancel_event_creation")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("🏷️ Выберите тип мероприятия:", reply_markup=keyboard)
    await state.set_state(EventRegistrationStates.category)


# Обработчик кнопки отмены создания мероприятия
@dp.callback_query(lambda c: c.data == "cancel_event_creation")
async def cancel_event_creation(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer("Создание мероприятия отменено")
    await state.clear()
    uid = str(callback_query.from_user.id)
    users = load_users()
    if uid in users:
        if users[uid].get('active_event_creations', 0)==1:
            users[uid]['active_event_creations'] = users[uid].get('active_event_creations', 0) - 1
            save_user(uid, users[uid])
            await callback_query.answer()
            await callback_query.message.answer("📝 Введите название мероприятия:", reply_markup=get_cancel_keyboard())
            await state.set_state(EventRegistrationStates.name)
            await callback_query.message.answer_photo(
                photo=FSInputFile(MENU_IMAGE_PATH),
                caption="❌ Создание мероприятия отменено",
                reply_markup=get_main_menu(str(callback_query.from_user.id))
            )
def get_event_type_keyboard():
    """Создаёт клавиатуру для выбора типа мероприятия"""
    keyboard = []
    for key, value in EVENT_TYPES.items():
        keyboard.append([
            InlineKeyboardButton(text=f"{value['emoji']} {value['name']}",
                                 callback_data=f"event_type_{key}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@dp.callback_query(lambda c: c.data.startswith("event_type_"))
async def process_event_type(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    event_type = callback_query.data.split("_")[2]
    user_id = str(callback_query.from_user.id)

    # Проверка валидности типа мероприятия
    if event_type not in EVENT_TYPES:
        await callback_query.message.answer("⚠️ Неверный тип мероприятия. Попробуйте снова.")
        return

    event_data = await state.get_data()
    event_data["category"] = event_type
    event_data["category_name"] = EVENT_TYPES[event_type]["name"]

    # Добавляем базовую валидацию ссылок
    for link_key in ["tg_link", "tg_chat_link"]:
        if link_key in event_data and event_data[link_key]:
            link = event_data[link_key]
            if not link.startswith(("https://t.me/", "https://telegram.me/")):
                event_data[link_key] = f"https://t.me/{link.lstrip('@')}"

    users = load_users()
    if user_id in users:
        # Сохраняем информацию о создателе
        event_data["creator_id"] = user_id
        event_data["creator_name"] = users[user_id]["name"]
        event_data["created_at"] = datetime.datetime.now().isoformat()

    save_event(event_data)

    await callback_query.message.answer_photo(
        photo=FSInputFile(MENU_IMAGE_PATH),
        caption="✅ Мероприятие успешно зарегистрировано!",
        reply_markup=get_main_menu(user_id)
    )
    uid = str(callback_query.from_user.id)
    users = load_users()
    if uid in users:
        if users[uid].get('active_event_creations', 0) == 1:
            users[uid]['active_event_creations'] = users[uid].get('active_event_creations', 0) - 1
            save_user(uid, users[uid])
    await state.clear()


@dp.callback_query(lambda c: c.data.startswith("register_for_event_"))
async def register_for_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[3])
    user_id = str(callback_query.from_user.id)

    try:
        events = load_events()
        event = events[event_idx]

        # Проверка, не является ли пользователь создателем мероприятия
        if event.get("creator_id") == user_id:
            await callback_query.message.answer_photo(
                photo=FSInputFile(MENU_IMAGE_PATH),
                caption=f"ℹ️ Вы являетесь создателем этого мероприятия и автоматически зарегистрированы на него.",
                reply_markup=get_main_menu(user_id)
            )
            return

        success = register_user_for_event(user_id, event_idx)

        if success:
            # Формируем текст с ссылками
            links_text = ""
            for link_type, prefix in [("tg_link", "🔗 Telegram канал"),
                                      ("tg_chat_link", "💬 Telegram чат")]:
                if link := event.get(link_type):
                    links_text += f"\n\n{prefix}: {link}"

            caption = f"✅ Вы успешно зарегистрировались на мероприятие \"{event['name']}\"!{links_text}"
        else:
            caption = f"ℹ️ Вы уже зарегистрированы на это мероприятие"

        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption=caption,
            reply_markup=get_main_menu(user_id)
        )
    except (IndexError, KeyError):
        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption="⚠️ Мероприятие не найдено",
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


@dp.callback_query(lambda c: c.data.startswith("my_event_"))
async def view_my_event(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    events = load_events()
    if event_idx >= len(events):
        await callback_query.message.answer("⚠️ Мероприятие не найдено")
        return

    event = events[event_idx]
    is_creator = event.get("creator_id") == user_id

    # Формируем текст мероприятия
    caption = format_event_caption(event, show_creator=False)

    # Кнопка редактирования показывается только создателю
    buttons = []
    if is_creator:
        buttons.append([InlineKeyboardButton(text="✏️ Редактировать мероприятие",
                                             callback_data=f"edit_event_{event_idx}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад к моим мероприятиям",
                                         callback_data="my_events")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback_query.message.edit_caption(caption=caption, reply_markup=keyboard)


# Начало процесса редактирования
@dp.callback_query(lambda c: c.data.startswith("edit_event_"))
async def start_edit_event(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    events = load_events()
    if event_idx >= len(events):
        await callback_query.message.answer("⚠️ Мероприятие не найдено")
        return

    event = events[event_idx]

    # Проверяем, является ли пользователь создателем
    if event.get("creator_id") != user_id:
        await callback_query.message.answer("⚠️ Вы не являетесь создателем этого мероприятия")
        return

    # Сохраняем индекс мероприятия и текущие данные
    await state.update_data(event_idx=event_idx, original_event=event)
    await state.set_state(EventEditStates.name)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
    ])

    await callback_query.message.answer(
        f"✏️ Редактирование мероприятия\n\nТекущее название: {event['name']}\n\nВведите новое название или нажмите кнопку, чтобы оставить текущее:",
        reply_markup=keyboard
    )


# Функция для получения списка зарегистрированных пользователей на мероприятие
def get_registered_users_for_event(event_idx):
    users = load_users()
    registered_users = []

    for user_id, user_data in users.items():
        if "registered_events" in user_data and event_idx in user_data["registered_events"]:
            registered_users.append({
                "id": user_id,
                "name": user_data.get("name", "Пользователь"),
                "faculty": user_data.get("faculty", "")
            })

    return registered_users


# Обработчик для просмотра списка участников
@dp.callback_query(lambda c: c.data.startswith("view_participants_"))
async def view_event_participants(callback_query: types.CallbackQuery):
    await callback_query.answer()
    event_idx = int(callback_query.data.split("_")[2])
    user_id = str(callback_query.from_user.id)

    events = load_events()
    if event_idx >= len(events):
        await callback_query.message.answer("⚠️ Мероприятие не найдено")
        return

    event = events[event_idx]

    # Проверяем, является ли пользователь создателем
    if event.get("creator_id") != user_id:
        await callback_query.message.answer("⚠️ Только создатель мероприятия может просматривать список участников")
        return

    # Получаем список зарегистрированных пользователей
    registered_users = get_registered_users_for_event(event_idx)

    # Формируем текст сообщения
    event_name = event.get("name", "Мероприятие")
    if registered_users:
        participants_text = "\n".join([f"{i + 1}. {user['name']} ({user['faculty']})"
                                       for i, user in enumerate(registered_users)])
        caption = f"👥 Участники мероприятия \"{event_name}\" ({len(registered_users)}):\n\n{participants_text}"
    else:
        caption = f"👥 На мероприятие \"{event_name}\" пока никто не зарегистрировался"

    # Кнопка возврата к мероприятию
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к мероприятию", callback_data=f"my_event_{event_idx}")],
        [InlineKeyboardButton(text="🏠 Назад в меню", callback_data="back_to_main")]
    ])

    await callback_query.message.answer_photo(
        photo=FSInputFile(MENU_IMAGE_PATH),
        caption=caption,
        reply_markup=keyboard
    )


# Обработчик для сохранения текущего значения
@dp.callback_query(lambda c: c.data == "keep_current")
async def keep_current_value(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    original_event = data.get("original_event", {})

    # Определяем, какое поле сохраняем и переходим к следующему
    if current_state == EventEditStates.name.state:
        await state.update_data(name=original_event.get("name", ""))
        await state.set_state(EventEditStates.description)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
        ])

        await callback_query.message.answer(
            f"Текущее описание: {original_event.get('description', '')}\n\nВведите новое описание или нажмите кнопку, чтобы оставить текущее:",
            reply_markup=keyboard
        )

    elif current_state == EventEditStates.description.state:
        await state.update_data(description=original_event.get("description", ""))
        await state.set_state(EventEditStates.location)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
        ])

        await callback_query.message.answer(
            f"Текущее место: {original_event.get('location', '')}\n\nВведите новое место или нажмите кнопку, чтобы оставить текущее:",
            reply_markup=keyboard
        )

    elif current_state == EventEditStates.location.state:
        await state.update_data(location=original_event.get("location", ""))
        await state.set_state(EventEditStates.time)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
        ])

        await callback_query.message.answer(
            f"Текущая дата и время: {original_event.get('time', '')}\n\nВведите новую дату и время или нажмите кнопку, чтобы оставить текущее:",
            reply_markup=keyboard
        )

    elif current_state == EventEditStates.time.state:
        await state.update_data(time=original_event.get("time", ""))
        await state.set_state(EventEditStates.tg_link)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
        ])

        await callback_query.message.answer(
            f"Текущая ссылка на Telegram канал: {original_event.get('tg_link', 'нет')}\n\nВведите новую ссылку или нажмите кнопку, чтобы оставить текущее:",
            reply_markup=keyboard
        )

    elif current_state == EventEditStates.tg_link.state:
        await state.update_data(tg_link=original_event.get("tg_link", ""))
        await state.set_state(EventEditStates.tg_chat_link)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
        ])

        await callback_query.message.answer(
            f"Текущая ссылка на Telegram беседу: {original_event.get('tg_chat_link', 'нет')}\n\nВведите новую ссылку или нажмите кнопку, чтобы оставить текущее:",
            reply_markup=keyboard
        )

    elif current_state == EventEditStates.tg_chat_link.state:
        await state.update_data(tg_chat_link=original_event.get("tg_chat_link", ""))

        # Показываем выбор категории
        keyboard = get_event_type_keyboard()
        current_category = original_event.get("category", "")
        category_name = EVENT_TYPES.get(current_category, {}).get("name", "Не указана")

        await callback_query.message.answer(
            f"Текущая категория: {category_name}\n\nВыберите новую категорию или нажмите 'Оставить текущее':",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                *keyboard.inline_keyboard,
                [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_category")]
            ])
        )

        await state.set_state(EventEditStates.category)


# Обработчик для сохранения текущей категории
@dp.callback_query(lambda c: c.data == "keep_category")
async def keep_current_category(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    data = await state.get_data()
    original_event = data.get("original_event", {})

    # Сохраняем текущую категорию
    await state.update_data(category=original_event.get("category", ""))

    # Завершаем редактирование
    await complete_edit(callback_query, state)


# Обработчики ввода для редактирования полей
@dp.message(EventEditStates.name)
async def process_edit_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    data = await state.get_data()
    original_event = data.get("original_event", {})

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
    ])

    await message.answer(
        f"Текущее описание: {original_event.get('description', '')}\n\nВведите новое описание или нажмите кнопку, чтобы оставить текущее:",
        reply_markup=keyboard
    )
    await state.set_state(EventEditStates.description)


@dp.message(EventEditStates.description)
async def process_edit_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    data = await state.get_data()
    original_event = data.get("original_event", {})

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
    ])

    await message.answer(
        f"Текущее место: {original_event.get('location', '')}\n\nВведите новое место или нажмите кнопку, чтобы оставить текущее:",
        reply_markup=keyboard
    )
    await state.set_state(EventEditStates.location)


@dp.message(EventEditStates.location)
async def process_edit_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    data = await state.get_data()
    original_event = data.get("original_event", {})

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
    ])

    await message.answer(
        f"Текущая дата и время: {original_event.get('time', '')}\n\nВведите новую дату и время или нажмите кнопку, чтобы оставить текущее:",
        reply_markup=keyboard
    )
    await state.set_state(EventEditStates.time)


@dp.message(EventEditStates.time)
async def process_edit_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text.strip())
    data = await state.get_data()
    original_event = data.get("original_event", {})

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
    ])

    await message.answer(
        f"Текущая ссылка на Telegram канал: {original_event.get('tg_link', 'нет')}\n\nВведите новую ссылку или нажмите кнопку, чтобы оставить текущее:",
        reply_markup=keyboard
    )
    await state.set_state(EventEditStates.tg_link)


@dp.message(EventEditStates.tg_link)
async def process_edit_tg_link(message: types.Message, state: FSMContext):
    tg_link = message.text.strip()
    if tg_link.lower() == 'нет':
        tg_link = ""
    await state.update_data(tg_link=tg_link)

    data = await state.get_data()
    original_event = data.get("original_event", {})

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_current")]
    ])

    await message.answer(
        f"Текущая ссылка на Telegram беседу: {original_event.get('tg_chat_link', 'нет')}\n\nВведите новую ссылку или нажмите кнопку, чтобы оставить текущее:",
        reply_markup=keyboard
    )
    await state.set_state(EventEditStates.tg_chat_link)


@dp.message(EventEditStates.tg_chat_link)
async def process_edit_tg_chat_link(message: types.Message, state: FSMContext):
    tg_chat_link = message.text.strip()
    if tg_chat_link.lower() == 'нет':
        tg_chat_link = ""
    await state.update_data(tg_chat_link=tg_chat_link)

    data = await state.get_data()
    original_event = data.get("original_event", {})

    # Показываем выбор категории
    keyboard = get_event_type_keyboard()
    current_category = original_event.get("category", "")
    category_name = EVENT_TYPES.get(current_category, {}).get("name", "Не указана")

    await message.answer(
        f"Текущая категория: {category_name}\n\nВыберите новую категорию или нажмите 'Оставить текущее':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            *keyboard.inline_keyboard,
            [InlineKeyboardButton(text="🔄 Оставить текущее", callback_data="keep_category")]
        ])
    )
    await state.set_state(EventEditStates.category)


# Обработчик выбора категории при редактировании
@dp.callback_query(lambda c: c.data.startswith("event_type_") and EventEditStates.category)
async def process_edit_category(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    event_type = callback_query.data.split("_")[2]

    # Проверка валидности типа мероприятия
    if event_type not in EVENT_TYPES:
        await callback_query.message.answer("⚠️ Неверный тип мероприятия. Попробуйте снова.")
        return

    await state.update_data(category=event_type)

    # Завершаем редактирование
    await complete_edit(callback_query, state)


# Функция завершения редактирования
async def complete_edit(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_idx = data.get("event_idx")
    original_event = data.get("original_event", {})

    # Обновляем данные мероприятия
    events = load_events()

    if event_idx < len(events):
        # Сохраняем обновленные поля
        for field in ["name", "description", "location", "time", "tg_link", "tg_chat_link", "category"]:
            if field in data:
                events[event_idx][field] = data[field]

        # Обновляем время редактирования
        events[event_idx]["edited_at"] = datetime.datetime.now().isoformat()

        # Сохраняем изменения
        save_data(EVENTS_FILE, events)

        await callback_query.message.answer_photo(
            photo=FSInputFile(MENU_IMAGE_PATH),
            caption="✅ Мероприятие успешно обновлено!",
            reply_markup=get_main_menu(str(callback_query.from_user.id))
        )
    else:
        await callback_query.message.answer("⚠️ Мероприятие не найдено")

    # Очищаем состояние
    await state.clear()


async def main():
    ensure_files_exist()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())