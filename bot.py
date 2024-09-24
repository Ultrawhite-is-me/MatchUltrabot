import telebot
from telebot import types
import sqlite3

API_TOKEN = '7023423273:AAGItyStfMF2jYzTMpoOgj2WJbiw0zb-xw0'
bot = telebot.TeleBot(API_TOKEN)

# Словарь для хранения состояний пользователей
user_data = {}

import sqlite3

# Создаем соединение с базой данных (если файла базы данных не существует, он будет создан)
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()

# Создаем таблицу для хранения анкет
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER UNIQUE,
    name TEXT,
    age INTEGER,
    photo TEXT
)
''')

# Сохраняем изменения и закрываем соединение с базой данных
conn.commit()
conn.close()

# Состояния пользователя
class UserState:
    WAITING_FOR_NAME = 1
    WAITING_FOR_AGE = 2
    WAITING_FOR_PHOTO = 3

# Функция для сохранения данных в базу данных
def save_user_data(chat_id, name, age, photo):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO users (chat_id, name, age, photo) VALUES (?, ?, ?, ?)
    ''', (chat_id, name, age, photo))
    conn.commit()
    conn.close()

# Обработчик команды /start и /help
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Здравствуйте! Как я могу вам помочь?\nДля начала анкеты введите /anketa")

# Обработчик команды /anketa
@bot.message_handler(commands=['anketa'])
def start_anketa(message):
    bot.reply_to(message, "Пожалуйста, введите ваше имя:")
    user_data[message.chat.id] = {'state': UserState.WAITING_FOR_NAME}

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id

    if chat_id in user_data:
        state = user_data[chat_id].get('state')

        if state == UserState.WAITING_FOR_NAME:
            user_data[chat_id]['name'] = message.text
            user_data[chat_id]['state'] = UserState.WAITING_FOR_AGE
            bot.reply_to(message, "Спасибо! Теперь введите ваш возраст:")

        elif state == UserState.WAITING_FOR_AGE:
            try:
                age = int(message.text)
                user_data[chat_id]['age'] = age
                user_data[chat_id]['state'] = UserState.WAITING_FOR_PHOTO
                bot.reply_to(message, "Отлично! Теперь отправьте ваше фото:")
            except ValueError:
                bot.reply_to(message, "Пожалуйста, введите корректный возраст (число).")

        elif state == UserState.WAITING_FOR_PHOTO:
            bot.reply_to(message, "Пожалуйста, отправьте фото.")
    else:
        bot.reply_to(message, "Я вас не понимаю. Пожалуйста, начните с команды /anketa.")

# Обработчик фото
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id

    if chat_id in user_data and user_data[chat_id].get('state') == UserState.WAITING_FOR_PHOTO:
        user_data[chat_id]['photo'] = message.photo[-1].file_id  # Сохраняем file_id последнего фото (наибольшего разрешения)
        user_data[chat_id]['state'] = None  # Сбрасываем состояние

        # Сохранение данных в базу данных
        save_user_data(chat_id, user_data[chat_id]['name'], user_data[chat_id]['age'], user_data[chat_id]['photo'])

        bot.reply_to(message, "Спасибо! Ваша анкета заполнена.")
        # Здесь можно добавить код для отправки данных администратору

        # Пример отправки анкеты администратору (замените chat_id на ID администратора)
        admin_chat_id = 'YOUR_ADMIN_CHAT_ID_HERE'
        bot.send_message(admin_chat_id, f"Новая анкета:\nИмя: {user_data[chat_id]['name']}\nВозраст: {user_data[chat_id]['age']}")
        bot.send_photo(admin_chat_id, user_data[chat_id]['photo'])
    else:
        bot.reply_to(message, "Я вас не понимаю. Пожалуйста, начните с команды /anketa.")

bot.polling()