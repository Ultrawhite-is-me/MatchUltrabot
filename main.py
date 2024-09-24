import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import sqlite3

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Подключение к базе данных
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    age INTEGER,
    photos TEXT,
    short_description TEXT,
    full_description TEXT,
    location TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER,
    liked_user_id INTEGER
)
''')

# Константы для состояний ConversationHandler
NAME, AGE, PHOTOS, SHORT_DESC, FULL_DESC, LOCATION = range(6)

#Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для знакомств. Давай создадим твою анкету. Как тебя зовут?"
    )
    return NAME

#Данные пользователя
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Сколько тебе лет?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = update.message.text
    if not age.isdigit():
        await update.message.reply_text("Пожалуйста, введи числовое значение для возраста.")
        return AGE
    context.user_data['age'] = int(age)
    await update.message.reply_text("Отправь мне три твоих фотографии по очереди.")
    context.user_data['photos'] = []
    return PHOTOS

async def get_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f'photos/{update.message.from_user.id}_{len(context.user_data["photos"])}.jpg'
    
    # Измените эту строку
    await photo_file.download_to_drive(photo_path)
    
    context.user_data['photos'].append(photo_path)
    if len(context.user_data['photos']) < 3:
        await update.message.reply_text(f"Фото {len(context.user_data['photos'])} получено, жду еще {3 - len(context.user_data['photos'])} фото(а).")
        return PHOTOS
    else:
        await update.message.reply_text("Теперь отправь краткое описание о себе.")
        return SHORT_DESC


async def get_short_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['short_description'] = update.message.text
    await update.message.reply_text("Теперь отправь полное описание о себе.")
    return FULL_DESC

async def get_full_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_description'] = update.message.text
    await update.message.reply_text("Отправь свою геопозицию.")
    return LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location:
        location = f"{update.message.location.latitude},{update.message.location.longitude}"
    else:
        location = update.message.text
    context.user_data['location'] = location

    # Сохраняем данные в базу
    cursor.execute('''
    INSERT OR REPLACE INTO users (user_id, name, age, photos, short_description, full_description, location)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        update.message.from_user.id,
        context.user_data['name'],
        context.user_data['age'],
        ','.join(context.user_data['photos']),
        context.user_data['short_description'],
        context.user_data['full_description'],
        context.user_data['location']
    ))
    conn.commit()

    await update.message.reply_text("Твоя анкета сохранена! Теперь ты можешь смотреть анкеты других пользователей с помощью команды /search.")
    return ConversationHandler.END

#Обработчик поиска анкет
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # Получаем список всех пользователей, кроме текущего
    cursor.execute('SELECT user_id, age, photos, short_description FROM users WHERE user_id != ?', (user_id,))
    users = cursor.fetchall()
    if not users:
        await update.message.reply_text("Пока нет других пользователей.")
        return
    context.user_data['search_results'] = users
    context.user_data['current_index'] = 0
    await show_profile(update, context)

#Показ пользователя
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data['current_index']
    users = context.user_data['search_results']
    if index >= len(users):
        await update.message.reply_text("Больше нет анкет.")
        return
    user = users[index]
    user_photos = user[2].split(',')
    media_group = [InputMediaPhoto(open(photo, 'rb')) for photo in user_photos]
    await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
    await update.message.reply_text(
        f"Возраст: {user[1]}\nОписание: {user[3]}",
        reply_markup=ReplyKeyboardMarkup(
            [['❤️ Лайк', '➡️ Далее']],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )

async def handle_like_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    index = context.user_data['current_index']
    users = context.user_data['search_results']
    current_user = users[index]
    if text == '❤️ Лайк':
        # Сохраняем лайк в базе данных
        cursor.execute('INSERT INTO likes (user_id, liked_user_id) VALUES (?, ?)', (
            update.message.from_user.id,
            current_user[0]
        ))
        conn.commit()
        await update.message.reply_text("Вы поставили лайк!")
    elif text == '➡️ Далее':
        await update.message.reply_text("Переходим к следующей анкете.")
    else:
        await update.message.reply_text("Пожалуйста, выбери '❤️ Лайк' или '➡️ Далее'.")
        return
    context.user_data['current_index'] += 1
    await show_profile(update, context)

#Основная функция и запуск бота
def main():
    application = ApplicationBuilder().token('7023423273:AAGItyStfMF2jYzTMpoOgj2WJbiw0zb-xw0').build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            PHOTOS: [MessageHandler(filters.PHOTO, get_photos)],
            SHORT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_short_desc)],
            FULL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_desc)],
            LOCATION: [MessageHandler((filters.LOCATION | filters.TEXT) & ~filters.COMMAND, get_location)],
        },
        fallbacks=[]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('search', search))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_like_next))

    application.run_polling()

if __name__ == '__main__':
    main()
