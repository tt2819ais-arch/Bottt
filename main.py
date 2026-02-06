import sys, os, subprocess

# --- Добавляем текущую папку в sys.path ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- Автоустановка пакетов ---
for package in ["telethon", "requests"]:
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import importlib, requests, asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# --- Настройки API ---
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BOT_TOKEN = "7568864397:AAEI4RwDx7Gk_HMnmeCCYMaLkVJTMqKOfMw"

MODULES_PATH = "modules"
SESSION_FILE = "user.session"

# --- Автозагрузка модулей ---
def load_all_modules(client):
    for f in os.listdir(MODULES_PATH):
        if f.endswith(".py") and not f.startswith("_"):
            name = f[:-3]
            try:
                m = importlib.import_module(f"{MODULES_PATH}.{name}")
                if hasattr(m, "on_load"):
                    client.loop.create_task(m.on_load(client))
                print("[MODULE] Loaded", name)
            except Exception as e:
                print("[ERROR loading]", f, e)

# --- Основная функция авторизации ---
async def authorize_user():
    if os.path.exists(SESSION_FILE):
        try:
            session_string = open(SESSION_FILE).read().strip()
            if session_string:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                
                # Проверяем валидность сессии
                if await client.is_user_authorized():
                    print("Сессия валидна")
                    return client
                else:
                    print("Сессия невалидна")
                    client.disconnect()
        except Exception as e:
            print(f"Ошибка при загрузке сессии: {e}")
    
    # Если нет валидной сессии, создаем новую
    auth_client = TelegramClient("auth_temp", API_ID, API_HASH)
    await auth_client.start(bot_token=BOT_TOKEN)
    
    print("Бот запущен. Отправьте /login в личные сообщения боту.")
    
    @auth_client.on(events.NewMessage(pattern="/login"))
    async def login_handler(event):
        async with auth_client.conversation(event.chat_id, timeout=300) as conv:
            try:
                await conv.send_message("📱 Пришлите номер телефона в международном формате (например, +79123456789):")
                
                phone_msg = await conv.get_response()
                phone = phone_msg.text.strip()
                
                # Создаем нового клиента для пользователя
                user_client = TelegramClient(StringSession(), API_ID, API_HASH)
                await user_client.connect()
                
                # Отправляем запрос кода
                try:
                    sent_code = await user_client.send_code_request(phone)
                    print(f"Код отправлен через: {sent_code.type}")
                    
                    await conv.send_message("✅ Код отправлен. Пришлите код из Telegram или SMS:")
                    
                    code_msg = await conv.get_response()
                    code = code_msg.text.strip().replace("-", "")
                    
                    # Пытаемся войти с кодом
                    try:
                        await user_client.sign_in(phone, code)
                    except SessionPasswordNeededError:
                        await conv.send_message("🔐 Требуется пароль 2FA. Пришлите пароль:")
                        password_msg = await conv.get_response()
                        password = password_msg.text.strip()
                        await user_client.sign_in(password=password)
                    except Exception as e:
                        # Если код неверный, пробуем как телефонный код
                        await user_client.sign_in(phone=phone, code=code)
                    
                    # Сохраняем сессию
                    session_string = user_client.session.save()
                    with open(SESSION_FILE, "w") as f:
                        f.write(session_string)
                    
                    await conv.send_message("✅ Авторизация успешна! Сессия сохранена.")
                    
                    # Закрываем соединения
                    await user_client.disconnect()
                    await auth_client.disconnect()
                    
                    # Возвращаем авторизованного клиента
                    authorized_client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                    await authorized_client.connect()
                    return authorized_client
                    
                except Exception as e:
                    await conv.send_message(f"❌ Ошибка при отправке кода: {str(e)}")
                    return None
                    
            except Exception as e:
                await conv.send_message(f"❌ Ошибка: {str(e)}")
                return None
    
    # Ждем команды /login
    await auth_client.run_until_disconnected()

# --- Основной запуск ---
async def main():
    # Пытаемся загрузить существующую сессию
    client = None
    if os.path.exists(SESSION_FILE):
        try:
            session_string = open(SESSION_FILE).read().strip()
            if session_string:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                
                if not await client.is_user_authorized():
                    print("Сессия устарела, требуется новая авторизация")
                    await client.disconnect()
                    client = None
                else:
                    print("✅ Используем существующую сессию")
        except Exception as e:
            print(f"Ошибка при загрузке сессии: {e}")
            client = None
    
    # Если нет валидной сессии, запускаем процесс авторизации
    if client is None:
        print("Требуется авторизация...")
        auth_bot = TelegramClient("auth_bot", API_ID, API_HASH)
        await auth_bot.start(bot_token=BOT_TOKEN)
        
        @auth_bot.on(events.NewMessage(pattern="/login"))
        async def login_command(event):
            async with auth_bot.conversation(event.chat_id, timeout=300) as conv:
                try:
                    await conv.send_message("📱 Пришлите номер телефона в международном формате (например, +79123456789):")
                    
                    phone_msg = await conv.get_response()
                    phone = phone_msg.text.strip()
                    
                    # Создаем временного клиента для авторизации
                    temp_client = TelegramClient(StringSession(), API_ID, API_HASH)
                    await temp_client.connect()
                    
                    try:
                        # Отправляем запрос кода
                        sent_code = await temp_client.send_code_request(phone)
                        print(f"Код отправлен через: {sent_code.type}")
                        
                        await conv.send_message(f"✅ Код отправлен через {sent_code.type}. Пришлите код:")
                        
                        code_msg = await conv.get_response()
                        code = code_msg.text.strip().replace("-", "").replace(" ", "")
                        
                        # Пытаемся войти
                        try:
                            await temp_client.sign_in(phone=phone, code=code)
                        except SessionPasswordNeededError:
                            await conv.send_message("🔐 Требуется пароль 2FA. Пришлите пароль:")
                            password_msg = await conv.get_response()
                            password = password_msg.text.strip()
                            await temp_client.sign_in(password=password)
                        
                        # Сохраняем сессию
                        session_string = temp_client.session.save()
                        with open(SESSION_FILE, "w") as f:
                            f.write(session_string)
                        
                        await conv.send_message("✅ Авторизация успешна! Перезапустите бота.")
                        await temp_client.disconnect()
                        
                    except Exception as e:
                        await conv.send_message(f"❌ Ошибка: {str(e)}")
                        if 'temp_client' in locals():
                            await temp_client.disconnect()
                        
                except Exception as e:
                    await conv.send_message(f"❌ Ошибка в процессе: {str(e)}")
        
        print("Бот запущен для авторизации. Отправьте /login в ЛС боту.")
        await auth_bot.run_until_disconnected()
        return
    
    # --- Основные команды бота ---
    @client.on(events.NewMessage(pattern=r"\.dlm (.+)"))
    async def dlm(event):
        url = event.pattern_match.group(1)
        name = url.split("/")[-1]
        try:
            data = requests.get(url).content
            with open(f"{MODULES_PATH}/{name}", "wb") as f:
                f.write(data)
            m = importlib.import_module(f"{MODULES_PATH}.{name[:-3]}")
            if hasattr(m, "on_load"):
                await m.on_load(client)
            await event.reply("✅ Модуль установлен")
        except Exception as e:
            await event.reply(str(e))

    @client.on(events.NewMessage(pattern=r"\.modules"))
    async def modules_list(event):
        lst = [f[:-3] for f in os.listdir(MODULES_PATH) if f.endswith(".py")]
        await event.reply("📦 Модули:\n" + "\n".join(lst) if lst else "Нет модулей")

    @client.on(events.NewMessage(pattern=r"\.rmm (.+)"))
    async def rmm(event):
        name = event.pattern_match.group(1)
        p = f"{MODULES_PATH}/{name}.py"
        if os.path.exists(p):
            os.remove(p)
            await event.reply("🗑️ Удалено")
        else:
            await event.reply("Нет такого модуля")

    @client.on(events.NewMessage(pattern=r"\.reload"))
    async def reload(event):
        importlib.invalidate_caches()
        load_all_modules(client)
        await event.reply("🔄 Готово")

    # --- Старт юзербота ---
    print("✅ Юзербот запущен")
    load_all_modules(client)
    await client.run_until_disconnected()

if __name__ == "__main__":
    # Убедимся, что папка modules существует
    if not os.path.exists(MODULES_PATH):
        os.makedirs(MODULES_PATH)
    
    # Запускаем основную функцию
    asyncio.run(main())
