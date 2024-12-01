import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import BOT_API, RATINGS_FILE, ADDRESSES_FILE
from LLM.answer import generate_response
from collections import Counter
from string import punctuation
from aiogram.types import FSInputFile

STOP_WORDS = set("""
и в во не на что он как так его но все она это был быть бы кто мне мне тебе там тут их чем был был бы 
есть нет до ли ведь же уж вам вас им ему ей мы они вы он её ещё между почему потому только из за чем перед 
для о чтобы если все так то когда было или их же это того что хотя под нам ними где где сюда здесь """.split() +
"""
the and in is on it at an of for or to not he she we they was were be you your me mine his her their our
this that those these here there when where how why whom by with if then else because too also just only 
about from into over under but yet nor so very can could should would shall """.split())

user_contexts = {}
MAX_CONTEXT_SIZE = 10
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_API)
dp = Dispatcher()
router = Router()
dp.include_router(router)

if not os.path.exists(RATINGS_FILE):
    with open(RATINGS_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["user_id", "username", "rating"])

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/setaddress"), KeyboardButton(text="/question")],
        [KeyboardButton(text="/start"), KeyboardButton(text="/rate")]
    ],
    resize_keyboard=True
)

keyboard_with_question = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Задать вопрос")],  
        [KeyboardButton(text="/start"), KeyboardButton(text="/rate"), KeyboardButton(text="/setaddress")]
    ],
    resize_keyboard=True
)

def rating_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.add(InlineKeyboardButton(text=f"⭐️ {i}", callback_data=f"rate:{i}"))
    return builder.as_markup()

def extract_keywords(text: str) -> list:
    words = text.lower().translate(str.maketrans("", "", punctuation)).split()
    keywords = [word for word in words if word not in STOP_WORDS]
    return keywords

def update_user_context(user_id: int, keywords: list):
    if user_id not in user_contexts:
        user_contexts[user_id] = []
    user_contexts[user_id].extend(keywords)
    keyword_counts = Counter(user_contexts[user_id])
    user_contexts[user_id] = [
        word for word, _ in keyword_counts.most_common(MAX_CONTEXT_SIZE)
    ]

async def get_custom_llm_response(prompt: str, user_id: int) -> str:
    try:
        keywords = extract_keywords(prompt)
        update_user_context(user_id, keywords)
        context = " ".join(user_contexts[user_id])        
        enriched_prompt = f"Контекст: {context}\nВопрос: {prompt}"
        response = generate_response(question=enriched_prompt, user_context=context, user_id=user_id)
        return response
    except Exception as e:
        logging.error(f"Ошибка при запросе к LLM: {e}")
        return "⚠️ Извините, произошла ошибка при обработке вашего запроса."

@router.message(Command("start"))
async def send_welcome(message: Message):
    await message.answer(
        "👋 Привет! Я ваш AI-помощник 🤖. Готов ответить на ваши вопросы!\n\n"
        "📋 Доступные команды:\n"
        "   /start — Начать работу с ботом\n"
        "   /rate — Оценить мою работу\n"
        "   /setaddress — Указать домашний адрес для наиболее релевантных ответов\n"
        "   /question — Задать вопрос\n\n"
        "Напишите мне сообщение, чтобы я мог помочь вам!",
        reply_markup=keyboard
    )

user_states = {}

def edit_address_keyboard():
    return InlineKeyboardBuilder().add(InlineKeyboardButton(text="Редактировать", callback_data="edit_address")).as_markup()

def get_user_address(user_id: int) -> str:
    try:
        if os.path.exists(ADDRESSES_FILE):
            with open(ADDRESSES_FILE, mode="r", newline="", encoding="utf-8") as file:
                reader = csv.reader(file)
                next(reader)  
                for row in reader:
                    if int(row[0]) == user_id:  
                        return row[2]  
    except Exception as e:
        logging.error(f"Ошибка при чтении файла адресов: {e}")
    return None

@router.message(Command("setaddress"))
async def set_address(message: Message):
    try:
        current_address = get_user_address(message.from_user.id)
        if current_address:
            await message.answer(
                f"📍 Ваш текущий адрес: *{current_address}*\n\n"
                "Если хотите изменить адрес, нажмите кнопку 'Редактировать'.\n Формат: г.Санкт-Петербург, Невский проспект, дом 60",
                parse_mode="Markdown",
                reply_markup=edit_address_keyboard()
            )
        else:
            user_input = message.text[len("/setaddress "):].strip()
            if not user_input:
                await message.answer("📍 Укажите адрес после команды. Пример:\n`/setaddress г.Санкт-Петербург, Невский проспект, дом 60`", parse_mode="Markdown")
                return
            if not os.path.exists(ADDRESSES_FILE):
                with open(ADDRESSES_FILE, mode="w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow(["user_id", "username", "address"])
            with open(ADDRESSES_FILE, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([message.from_user.id, message.from_user.username, user_input])
            await message.answer(f"✅ Ваш адрес успешно сохранён: *{user_input}*", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при сохранении адреса: {e}")
        await message.answer("⚠️ Извините, произошла ошибка при сохранении адреса.")

async def update_user_address(user_id: int, new_address: str):
    try:
        if not os.path.exists(ADDRESSES_FILE):
            logging.error("Файл с адресами не найден.")
            return False
        rows = []
        updated = False
        with open(ADDRESSES_FILE, mode="r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            header = next(reader)  
            rows.append(header)
            for row in reader:
                if int(row[0]) == user_id:
                    row[2] = new_address
                    updated = True
                rows.append(row)
        if not updated:
            logging.warning(f"Пользователь с ID {user_id} не найден в файле.")
            return False
        with open(ADDRESSES_FILE, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerows(rows)
        logging.info(f"Адрес пользователя с ID {user_id} успешно обновлен.")
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении адреса: {e}")
        return False

@router.callback_query(lambda callback: callback.data == "edit_address")
async def edit_address(callback_query):
    try:
        user_states[callback_query.from_user.id] = "editing_address"
        await callback_query.message.answer(
            "🖊️ Пожалуйста, введите новый адрес:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Отменить")]
                ],
                resize_keyboard=True
            )
        )
    except Exception as e:
        logging.error(f"Ошибка при редактировании адреса: {e}")
        await callback_query.message.answer("⚠️ Извините, произошла ошибка при редактировании адреса.")

@router.message(lambda message: message.text == "Отменить")
async def cancel_edit(message: Message):
    user_states.pop(message.from_user.id, None)  
    await message.answer(
        "Вы отменили процесс редактирования адреса.",
        reply_markup=keyboard  
    )

@router.message(lambda message: message.from_user.id in user_states and user_states[message.from_user.id] == "editing_address")
async def handle_new_address(message: Message):
    try:
        user_input = message.text.strip()
        if not user_input:
            await message.answer("❓ Пожалуйста, введите новый адрес.")
            return
        success = await update_user_address(message.from_user.id, user_input)
        if success:
            user_states.pop(message.from_user.id, None)  
            await message.answer(f"✅ Ваш новый адрес успешно сохранён: *{user_input}*", parse_mode="Markdown")
        else:
            await message.answer("⚠️ Не удалось обновить ваш адрес. Попробуйте ещё раз.")
    except Exception as e:
        logging.error(f"Ошибка при обработке нового адреса: {e}")
        await message.answer("⚠️ Извините, произошла ошибка при редактировании адреса.")

@router.message(lambda message: message.text == "Отменить")
async def cancel_edit(message: Message):
    await message.answer(
        "Вы отменили процесс редактирования адреса.",
        reply_markup=keyboard  
    )

@router.message(Command("rate"))
async def rate_bot(message: Message):
    try:
        photo = FSInputFile("us.jpg")
        await message.answer_photo(
            photo=photo,
            caption="⭐️ Пожалуйста, оцените мою работу, выбрав количество звёздочек ниже:",
            reply_markup=rating_keyboard()
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке фотографии: {e}")
        await message.answer("⚠️ Извините, произошла ошибка при отображении фотографии.")

@router.callback_query(lambda callback: callback.data.startswith("rate:"))
async def handle_rating(callback_query: CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        rating = int(callback_query.data.split(":")[1])
        existing_ratings = []
        user_rating = None
        try:
            with open(RATINGS_FILE, mode="r", encoding="utf-8") as file:
                reader = csv.reader(file)
                for row in reader:
                    existing_ratings.append(row)
                    if str(user_id) == row[0]:  
                        user_rating = int(row[2])  
        except FileNotFoundError:
            pass  

        if user_rating is not None:
            
            await bot.send_message(
                chat_id=callback_query.from_user.id,
                text=(
                    f"Вы уже поставили оценку: {user_rating} ⭐️.\n"
                    "Хотите изменить её?"
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Да, изменить", callback_data=f"change_rate:{rating}")],
                        [InlineKeyboardButton(text="Нет, оставить как есть", callback_data="cancel_change")]
                    ]
                )
            )
        else:
            with open(RATINGS_FILE, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([user_id, username, rating])

            await bot.send_message(
                chat_id=callback_query.from_user.id,
                text=f"Спасибо за вашу оценку: {rating} ⭐️"
            )

    except Exception as e:
        logging.error(f"Ошибка при обработке оценки: {e}")
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text="⚠️ Ошибка при сохранении вашей оценки."
        )

@router.callback_query(lambda callback: callback.data.startswith("change_rate:"))
async def change_rate(callback_query: CallbackQuery):
    try:
        new_rating = int(callback_query.data.split(":")[1])
        user_id = callback_query.from_user.id
        updated_ratings = []
        with open(RATINGS_FILE, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            for row in reader:
                if str(row[0]) == str(user_id):
                    row[2] = str(new_rating)  
                updated_ratings.append(row)
        
        with open(RATINGS_FILE, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerows(updated_ratings)

        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text=f"Спасибо за изменение вашей оценки: {new_rating} ⭐️"
        )

    except Exception as e:
        logging.error(f"Ошибка при обработке изменения оценки: {e}")
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text="⚠️ Ошибка при изменении вашей оценки."
        )

@router.callback_query(lambda callback: callback.data == "cancel_change")
async def cancel_change(callback_query: CallbackQuery):
    try:
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text="Оценка оставлена без изменений."
        )
    except Exception as e:
        logging.error(f"Ошибка при отмене изменения оценки: {e}")
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text="⚠️ Ошибка при отмене изменения оценки."
        )

@router.message(Command("question"))
async def ask_question(message: Message):
    await message.answer(
        "❓ Нажмите на кнопку 'Задать вопрос', чтобы отправить свой вопрос.",
        reply_markup=keyboard_with_question
    )

@router.message(lambda message: message.text == "Задать вопрос")
async def ask_user_question(message: Message):
    await message.answer(
        "Пожалуйста, напишите свой вопрос, и я постараюсь на него ответить:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[  
                [KeyboardButton(text="Отменить")]  
            ],
            resize_keyboard=True
        )
    )

@router.message(lambda message: message.text != "Отменить")
async def handle_user_question(message: Message):
    try:
        user_input = message.text.strip()
        if not user_input:
            await message.answer("❓ Пожалуйста, введите свой вопрос.")
            return

        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = await get_custom_llm_response(user_input, message.from_user.id)
        await message.answer(response)
    except Exception as e:
        logging.error(f"Ошибка при обработке вопроса: {e}")
        await message.answer("⚠️ Извините, произошла ошибка при обработке вашего запроса.")

@router.message(lambda message: message.text == "Отменить")
async def cancel_question(message: Message):
    await message.answer(
        "Вы отменили процесс задавания вопроса.",
        reply_markup=keyboard  
    )

@router.message(lambda message: message.from_user.id not in user_states or user_states[message.from_user.id] != "editing_address")
async def handle_message(message: Message):
    user_input = message.text
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    response = await get_custom_llm_response(user_input, message.from_user.id)
    await message.answer(response)

async def main():
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
