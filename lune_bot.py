import telebot
import sqlite3
from datetime import datetime
import threading
import time
import os

# ========== НАСТРОЙКИ (берутся из переменных окружения) ==========
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
# =================================================================

bot = telebot.TeleBot(TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS slots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  time TEXT,
                  is_free INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS appointments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slot_id INTEGER,
                  user_id INTEGER,
                  username TEXT,
                  user_phone TEXT,
                  booking_date TEXT,
                  FOREIGN KEY(slot_id) REFERENCES slots(id))''')
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_free_slots():
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    c.execute("SELECT id, date, time FROM slots WHERE is_free = 1 ORDER BY date, time")
    slots = c.fetchall()
    conn.close()
    return slots

def get_all_slots_with_status():
    """Возвращает все слоты с указанием занят/свободен"""
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    c.execute('''SELECT id, date, time, is_free FROM slots ORDER BY date, time''')
    slots = c.fetchall()
    conn.close()
    return slots

def delete_slot(slot_id):
    """Удаляет слот и все записи клиентов, связанные с ним"""
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    try:
        # Удаляем записи клиентов
        c.execute("DELETE FROM appointments WHERE slot_id = ?", (slot_id,))
        # Удаляем сам слот
        c.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

def book_slot(slot_id, user_id, username, user_phone):
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    try:
        c.execute("UPDATE slots SET is_free = 0 WHERE id = ? AND is_free = 1", (slot_id,))
        if c.rowcount == 0:
            return False
        c.execute("INSERT INTO appointments (slot_id, user_id, username, user_phone, booking_date) VALUES (?, ?, ?, ?, ?)",
                  (slot_id, user_id, username, user_phone, datetime.now().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

def cancel_appointment(user_id, appointment_id):
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    try:
        c.execute("SELECT slot_id FROM appointments WHERE id = ? AND user_id = ?", (appointment_id, user_id))
        app = c.fetchone()
        if not app:
            return False
        c.execute("UPDATE slots SET is_free = 1 WHERE id = ?", (app[0],))
        c.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_user_appointments(user_id):
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    c.execute('''SELECT a.id, s.date, s.time 
                 FROM appointments a 
                 JOIN slots s ON a.slot_id = s.id 
                 WHERE a.user_id = ? 
                 ORDER BY s.date, s.time''', (user_id,))
    apps = c.fetchall()
    conn.close()
    return apps

def get_all_appointments():
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    c.execute('''SELECT a.id, s.date, s.time, a.username, a.user_phone
                 FROM appointments a
                 JOIN slots s ON a.slot_id = s.id
                 ORDER BY s.date, s.time''')
    apps = c.fetchall()
    conn.close()
    return apps

def add_slot(date, time):
    conn = sqlite3.connect('manicure.db')
    c = conn.cursor()
    c.execute("INSERT INTO slots (date, time, is_free) VALUES (?, ?, 1)", (date, time))
    conn.commit()
    conn.close()

# --- КОМАНДЫ ДЛЯ КЛИЕНТОВ ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('📝 Записаться', '📋 Мои записи', '❌ Отменить запись')
    bot.send_message(message.chat.id, 
        "👋 Добро пожаловать! Я помогу записаться к мастеру.\n\n"
        "📝 /schedule - показать свободные слоты\n"
        "📋 /my_appointments - мои записи\n"
        "❌ /cancel - отменить запись\n\n"
        "Или используй кнопки ниже:", 
        reply_markup=markup)

@bot.message_handler(commands=['schedule'])
def schedule(message):
    slots = get_free_slots()
    if not slots:
        bot.send_message(message.chat.id, "😔 Свободных слотов пока нет. Загляните позже!")
        return
    markup = telebot.types.InlineKeyboardMarkup()
    for slot in slots:
        slot_id, date, time = slot
        markup.add(telebot.types.InlineKeyboardButton(f"{date} {time}", callback_data=f"book_{slot_id}"))
    bot.send_message(message.chat.id, "Выберите удобное время:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('book_'))
def book_callback(call):
    slot_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    username = call.from_user.username or "Без имени"
    msg = bot.send_message(call.message.chat.id, "Пожалуйста, отправьте ваш номер телефона в формате: +7XXXXXXXXXX")
    bot.register_next_step_handler(msg, process_phone, slot_id, user_id, username)

def process_phone(message, slot_id, user_id, username):
    user_phone = message.text.strip()
    if book_slot(slot_id, user_id, username, user_phone):
        bot.send_message(message.chat.id, "✅ Вы успешно записаны!")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось записаться. Возможно, этот слот уже занят.")

@bot.message_handler(commands=['my_appointments'])
def my_appointments(message):
    apps = get_user_appointments(message.from_user.id)
    if not apps:
        bot.send_message(message.chat.id, "У вас пока нет записей.")
        return
    text = "📋 Ваши записи:\n\n"
    for app in apps:
        app_id, date, time = app
        text += f"🆔 {app_id}: {date} {time}\n"
    text += "\n❌ Чтобы отменить, используйте /cancel_app <id>"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['cancel_app'])
def cancel_app_cmd(message):
    try:
        app_id = int(message.text.split()[1])
    except:
        bot.send_message(message.chat.id, "Использование: /cancel_app <id_записи>")
        return
    if cancel_appointment(message.from_user.id, app_id):
        bot.send_message(message.chat.id, f"✅ Запись #{app_id} отменена.")
    else:
        bot.send_message(message.chat.id, "❌ Не удалось отменить запись. Проверьте ID.")

# --- КНОПКИ ДЛЯ КЛИЕНТОВ ---
@bot.message_handler(func=lambda message: message.text == '📝 Записаться')
def button_schedule(message):
    schedule(message)

@bot.message_handler(func=lambda message: message.text == '📋 Мои записи')
def button_my_appointments(message):
    my_appointments(message)

@bot.message_handler(func=lambda message: message.text == '❌ Отменить запись')
def button_cancel(message):
    bot.send_message(message.chat.id, "Чтобы отменить запись, используйте команду:\n/cancel_app <id_записи>\n\nID записи можно посмотреть в /my_appointments")

# --- АДМИН-КОМАНДЫ ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Нет доступа.")
        return
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('➕ Добавить слот', '📋 Все записи', '🗑 Удалить слот')  # НОВАЯ КНОПКА
    bot.send_message(message.chat.id, "👩‍💼 Админ-панель:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '➕ Добавить слот' and message.from_user.id == ADMIN_ID)
def add_slot_admin(message):
    msg = bot.send_message(message.chat.id, "Введите дату и время в формате:\nГГГГ-ММ-ДД ЧЧ:ММ\nНапример: 2025-12-31 14:00")
    bot.register_next_step_handler(msg, process_add_slot)

def process_add_slot(message):
    try:
        date_str, time_str = message.text.split()
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        add_slot(date_str, time_str)
        bot.send_message(message.chat.id, f"✅ Слот {date_str} {time_str} добавлен.")
    except:
        bot.send_message(message.chat.id, "❌ Неверный формат. Попробуйте снова.")

# НОВАЯ ФУНКЦИЯ: УДАЛЕНИЕ СЛОТА
@bot.message_handler(func=lambda message: message.text == '🗑 Удалить слот' and message.from_user.id == ADMIN_ID)
def delete_slot_menu(message):
    slots = get_all_slots_with_status()
    if not slots:
        bot.send_message(message.chat.id, "Нет ни одного слота.")
        return
    text = "🗓 *Все слоты:*\n"
    for slot_id, date, time, is_free in slots:
        status = "✅ свободен" if is_free == 1 else "❌ занят"
        text += f"🆔 `{slot_id}` → {date} {time} ({status})\n"
    text += "\n💡 Чтобы удалить, отправь команду:\n`/delete_slot ID`"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['delete_slot'])
def delete_slot_by_id(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        slot_id = int(message.text.split()[1])
    except:
        bot.send_message(message.chat.id, "❌ Использование: /delete_slot <ID_слота>")
        return
    if delete_slot(slot_id):
        bot.send_message(message.chat.id, f"✅ Слот #{slot_id} и все связанные записи удалены.")
    else:
        bot.send_message(message.chat.id, f"❌ Слот #{slot_id} не найден.")

@bot.message_handler(func=lambda message: message.text == '📋 Все записи' and message.from_user.id == ADMIN_ID)
def all_appointments_admin(message):
    apps = get_all_appointments()
    if not apps:
        bot.send_message(message.chat.id, "Записей пока нет.")
        return
    text = "📋 *ВСЕ ЗАПИСИ*\n\n"
    for app in apps:
        app_id, date, time, username, phone = app
        text += f"🆔 {app_id} | {date} {time}\n👤 @{username} | {phone}\n\n"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# --- ЗАПУСК БОТА ---
def reminder_checker():
    import time
    while True:
        conn = sqlite3.connect('manicure.db')
        c = conn.cursor()
        c.execute('''SELECT a.user_id, s.date, s.time 
                     FROM appointments a
                     JOIN slots s ON a.slot_id = s.id
                     WHERE julianday('now') - julianday(s.date || ' ' || s.time) BETWEEN -0.042 AND -0.04''')
        for user_id, date, slot_time in c.fetchall():
            bot.send_message(user_id, f"🔔 Напоминание: у вас запись на {date} в {slot_time} через час!")
        conn.close()
        time.sleep(60)

if __name__ == '__main__':
    init_db()
    print("Бот запущен...")
    reminder_thread = threading.Thread(target=reminder_checker, daemon=True)
    reminder_thread.start()
    bot.infinity_polling()
