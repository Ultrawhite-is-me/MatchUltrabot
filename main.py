import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InputMediaPhoto
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          filters, ContextTypes, ConversationHandler)
import sqlite3
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Подключение к базе данных
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
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
LIKES_SHOWING = 6

# Папка для хранения фотографий
PHOTO_DIR = 'photos'
if not os.path.exists(PHOTO_DIR):
    os.makedirs(PHOTO_DIR)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для знакомств. Давай создадим твою анкету. Как тебя зовут?"
    )
    return NAME

# Данные пользователя
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
    photo_path = f'{PHOTO_DIR}/{update.message.from_user.id}_{len(context.user_data["photos"])}.jpg'
    
    await photo_file.download_to_drive(photo_path)
    
    context.user_data['photos'].append(photo_path)
    if len(context.user_data['photos']) < 3:
        await update.message.reply_text(f"Фото {len(context.user_data['photos'])} получено, жду еще {3 - len(context.user_data['photos'])} фото(а).")
        return PHOTOS
    else:
        await update.message.reply_text("Теперь отправь краткое описание о себе (максимум 50 символов)")
        return SHORT_DESC

async def get_short_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['short_description'] = update.message.text[:50]  # Ограничение до 50 символов
    await update.message.reply_text("Теперь отправь полное описание о себе (максимум 300 символов)")
    return FULL_DESC

async def get_full_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_description'] = update.message.text[:300]  # Ограничение до 300 символов
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
    INSERT OR REPLACE INTO users (user_id, username, name, age, photos, short_description, full_description, location)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        update.message.from_user.id,
        update.message.from_user.username,
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

# Обработчик поиска анкет
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # Получаем список всех пользователей, кроме текущего
    cursor.execute('SELECT user_id, name, age, photos, short_description, full_description, location FROM users WHERE user_id != ?', (user_id,))
    users = cursor.fetchall()
    if not users:
        await update.message.reply_text("Пока нет других пользователей")
        return
    context.user_data['search_results'] = users
    context.user_data['current_index'] = 0
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Полетели",
        reply_markup=ReplyKeyboardMarkup(
            [['❤️ Лайк', '🔍 Подробнее', '➡️ Далее']],
            one_time_keyboard=False,
            resize_keyboard=True
        )
    )
    await show_profile(update, context)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data['current_index']
    users = context.user_data['search_results']
    if index >= len(users):
        await update.message.reply_text("Больше нет анкет, пошли по новой")
        await search(update, context)  # Запускаем поиск заново
        return
    user = users[index]
    user_photos = user[3].split(',')

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=open(user_photos[0], 'rb'),
        caption=f"{user[1]} ({user[2]})\n{user[4]}",
    )

# Показать полный профиль
async def show_full_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data['current_index']
    users = context.user_data['search_results']

    user = users[index]
    user_photos = user[3].split(',')
    user_location = user[6]
    full_description = user[5]

    # Создаем медиа-группу для фотографий
    media_group = []
    for i, photo in enumerate(user_photos):
        if i < 3:
            if i == 0:
                media_group.append(InputMediaPhoto(
                    media=open(photo, 'rb'),
                    caption=f"{user[1]} ({user[2]})\n{full_description}"
                ))
            else:
                media_group.append(InputMediaPhoto(media=open(photo, 'rb')))

    # Отправляем клавиатуру отдельным сообщением
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Вот полный профиль",
        reply_markup=ReplyKeyboardMarkup(
            [['❤️ Лайк', '➡️ Далее', '❗️Пожаловаться']],
            one_time_keyboard=False,
            resize_keyboard=True
        )
    )

    # Отправляем медиа-группу
    if media_group:
        await update.message.reply_media_group(media=media_group)

# Лайк
async def handle_like_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    index = context.user_data.get('current_index', 0)
    users = context.user_data.get('search_results', [])
    if not users:
        await update.message.reply_text("Нет доступных анкет.")
        return

    if index >= len(users):
        await update.message.reply_text("Больше нет анкет, пошли по новой")
        await search(update, context)
        return

    current_user = users[index]
    if text == '❤️ Лайк':
        # Сохраняем лайк в базе данных
        cursor.execute('INSERT INTO likes (user_id, liked_user_id) VALUES (?, ?)', (
            update.message.from_user.id,
            current_user[0]
        ))
        conn.commit()
        await update.message.reply_text("Вы поставили лайк!")

        # Проверка на взаимный лайк
        cursor.execute('SELECT * FROM likes WHERE user_id = ? AND liked_user_id = ?', (
            current_user[0],
            update.message.from_user.id
        ))
        if cursor.fetchone():
            # Взаимный лайк
            await update.message.reply_text("У вас взаимная симпатия!")
            await context.bot.send_message(chat_id=current_user[0], text="У вас взаимная симпатия!")

            # Отправляем ссылки на профили друг друга
            await send_profile_link(update.message.from_user.id, current_user[0], context)
            await send_profile_link(current_user[0], update.message.from_user.id, context)
        else:
            # Уведомляем другого пользователя о новом лайке
            await notify_liked_user(update, context, current_user[0])

    elif text == '➡️ Далее':
        context.user_data['current_index'] += 1
        await show_profile(update, context)
        return
    elif text == '🔍 Подробнее':
        await show_full_profile(update, context)
        return
    else:
        await update.message.reply_text("Такой опции нет")
        return
    context.user_data['current_index'] += 1
    await show_profile(update, context)

async def notify_liked_user(update: Update, context: ContextTypes.DEFAULT_TYPE, liked_user_id):
    # Отправляем уведомление
    try:
        await context.bot.send_message(
            chat_id=liked_user_id,
            text="У вас новый лайк! Используйте команду /likes, чтобы увидеть, кто лайкнул вас."
        )
    except Exception as e:
        print(f"Ошибка при отправке уведомления: {e}")

async def send_profile_link(to_user_id, profile_user_id, context):
    # Получаем данные профиля
    cursor.execute('SELECT name, username FROM users WHERE user_id = ?', (profile_user_id,))
    user = cursor.fetchone()
    if user:
        name, username = user
        # Формируем ссылку на профиль
        profile_link = f"https://t.me/{username}" if username else f"tg://user?id={profile_user_id}"
        
        # Отправляем сообщение пользователю
        await context.bot.send_message(
            chat_id=to_user_id,
            text=f'Удачного общения! 👉 <a href="{profile_link}">{name}</a>',
            parse_mode='HTML'
        )
    else:
        # Если пользователь не найден, отправляем сообщение об ошибке
        await context.bot.send_message(
            chat_id=to_user_id,
            text='Извините, профиль пользователя не найден.'
        )

# Команда /likes для просмотра лайков
async def likes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cursor.execute('SELECT user_id FROM likes WHERE liked_user_id = ?', (user_id,))
    likers = cursor.fetchall()

    if not likers:
        await update.message.reply_text("У вас нет лайков.")
        return ConversationHandler.END

    # Получаем информацию о пользователях, которые лайкнули
    liker_ids = [liker[0] for liker in likers]
    cursor.execute('SELECT user_id, name, age, photos, short_description FROM users WHERE user_id IN ({})'.format(','.join('?' * len(liker_ids))), liker_ids)
    users = cursor.fetchall()

    if not users:
        await update.message.reply_text("Не удалось найти пользователей, которые лайкнули вас.")
        return ConversationHandler.END

    context.user_data['likers'] = users
    context.user_data['likers_index'] = 0
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Вот пользователи, которым вы понравились",
        reply_markup=ReplyKeyboardMarkup(
            [['❤️ Лайк', '➡️ Далее']],
            one_time_keyboard=False,
            resize_keyboard=True
        )
    )
    await show_liker_profile(update, context)
    return LIKES_SHOWING

async def show_liker_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data['likers_index']
    users = context.user_data['likers']
    if index >= len(users):
        await update.message.reply_text("Больше нет лайков.")
        return ConversationHandler.END
    user = users[index]
    user_photos = user[3].split(',')

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=open(user_photos[0], 'rb'),
        caption=f"{user[1]} ({user[2]})\n{user[4]}",
    )

# Обработчик для лайков в разделе /likes
async def handle_like_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    index = context.user_data.get('likers_index', 0)
    users = context.user_data.get('likers', [])
    if not users:
        await update.message.reply_text("У вас нет лайков.")
        return ConversationHandler.END

    if index >= len(users):
        await update.message.reply_text("Больше нет лайков.")
        return ConversationHandler.END

    current_user = users[index]
    if text == '❤️ Лайк':
        # Сохраняем лайк в базе данных
        cursor.execute('INSERT INTO likes (user_id, liked_user_id) VALUES (?, ?)', (
            update.message.from_user.id,
            current_user[0]
        ))
        conn.commit()
        #await update.message.reply_text("Вы поставили лайк!")

        # Проверка на взаимный лайк
        cursor.execute('SELECT * FROM likes WHERE user_id = ? AND liked_user_id = ?', (
            current_user[0],
            update.message.from_user.id
        ))
        if cursor.fetchone():
            # Взаимный лайк
            await update.message.reply_text("У вас взаимная симпатия!")
            await context.bot.send_message(chat_id=current_user[0], text="У вас взаимная симпатия!")

            # Отправляем ссылки на профили друг друга
            await send_profile_link(update.message.from_user.id, current_user[0], context)
            await send_profile_link(current_user[0], update.message.from_user.id, context)
    elif text == '➡️ Далее':
        context.user_data['likers_index'] += 1
        await show_liker_profile(update, context)
        return LIKES_SHOWING
    else:
        await update.message.reply_text("Такой опции нет")
        return LIKES_SHOWING

    context.user_data['likers_index'] += 1
    await show_liker_profile(update, context)
    return LIKES_SHOWING

# Добавьте эту функцию перед функцией main()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет и завершает разговор."""
    await update.message.reply_text(
        'Операция отменена. Используйте /start, чтобы начать заново.'
    )
    return ConversationHandler.END

# Основная функция и запуск бота
def main():
    application = ApplicationBuilder().token('YOUR_BOT_TOKEN_HERE').build()

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
        fallbacks=[CommandHandler('cancel', cancel)]
    )

# Основная функция и запуск бота
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
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    likes_handler = ConversationHandler(
        entry_points=[CommandHandler('likes', likes)],
        states={
            LIKES_SHOWING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_like_back)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(likes_handler)
    application.add_handler(CommandHandler('search', search))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_like_next))

    application.run_polling()

if __name__ == '__main__':
    main()
