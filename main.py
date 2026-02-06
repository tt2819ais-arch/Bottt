import sys, os, subprocess
import importlib.util
import asyncio
import requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# --- Настройки ---
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BOT_TOKEN = "7568864397:AAEI4RwDx7Gk_HMnmeCCYMaLkVJTMqKOfMw"
MODULES_PATH = "modules"
SESSION_FILE = "user.session"

# --- Автоустановка библиотек ---
for package in ["telethon", "requests"]:
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# --- Функция загрузки модулей ---
def load_all_modules(client):
    if not os.path.exists(MODULES_PATH):
        os.makedirs(MODULES_PATH)
    for f in os.listdir(MODULES_PATH):
        if f.endswith(".py") and not f.startswith("_"):
            name = f[:-3]
            try:
                path = os.path.join(MODULES_PATH, f)
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "on_load"):
                    client.loop.create_task(mod.on_load(client))
                print("[MODULE] Loaded", name)
            except Exception as e:
                print("[ERROR loading]", f, e)

# --- Авторизация ---
async def get_client():
    client = None
    if os.path.exists(SESSION_FILE):
        try:
            session_string = open(SESSION_FILE).read().strip()
            if session_string:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    print("✅ Используем существующую сессию")
                    return client
                else:
                    await client.disconnect()
        except Exception as e:
            print("Ошибка при загрузке сессии:", e)
    
    # --- Если нет сессии, авторизация через бот ---
    auth_bot = TelegramClient("auth_bot", API_ID, API_HASH)
    await auth_bot.start(bot_token=BOT_TOKEN)
    print("Бот запущен для авторизации. Отправьте /login в ЛС боту.")

    @auth_bot.on(events.NewMessage(pattern="/login"))
    async def login_handler(event):
        async with auth_bot.conversation(event.chat_id, timeout=300) as conv:
            await conv.send_message("📱 Введите номер телефона в международном формате (+79123456789):")
            phone = (await conv.get_response()).text.strip()

            user_client = TelegramClient(StringSession(), API_ID, API_HASH)
            await user_client.connect()
            try:
                sent_code = await user_client.send_code_request(phone)
                await conv.send_message(f"✅ Код отправлен ({sent_code.type}). Введите код:")
                code = (await conv.get_response()).text.strip().replace("-", "").replace(" ", "")
                try:
                    await user_client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    await conv.send_message("🔐 Требуется пароль 2FA. Введите пароль:")
                    password = (await conv.get_response()).text.strip()
                    await user_client.sign_in(password=password)

                # Сохраняем сессию
                session_string = user_client.session.save()
                with open(SESSION_FILE, "w") as f:
                    f.write(session_string)
                
                await conv.send_message("✅ Авторизация завершена! Перезапустите бота.")
                await user_client.disconnect()
                await auth_bot.disconnect()
            except Exception as e:
                await conv.send_message(f"❌ Ошибка авторизации: {e}")
                await user_client.disconnect()

    await auth_bot.run_until_disconnected()
    return None

# --- Основной запуск ---
async def main():
    client = await get_client()
    if client is None:
        return

    # --- Команды модулей ---
    @client.on(events.NewMessage(pattern=r"\.dlm (.+)"))
    async def dlm(event):
        url = event.pattern_match.group(1)
        name = url.split("/")[-1]
        try:
            data = requests.get(url).content
            path = os.path.join(MODULES_PATH, name)
            with open(path, "wb") as f:
                f.write(data)
            # Импортируем модуль напрямую
            spec = importlib.util.spec_from_file_location(name[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "on_load"):
                await mod.on_load(client)
            await event.reply("✅ Модуль установлен")
        except Exception as e:
            await event.reply(f"❌ Ошибка: {e}")

    @client.on(events.NewMessage(pattern=r"\.modules"))
    async def modules_list(event):
        lst = [f[:-3] for f in os.listdir(MODULES_PATH) if f.endswith(".py")]
        await event.reply("📦 Модули:\n" + ("\n".join(lst) if lst else "Нет модулей"))

    @client.on(events.NewMessage(pattern=r"\.rmm (.+)"))
    async def rmm(event):
        name = event.pattern_match.group(1)
        path = os.path.join(MODULES_PATH, name + ".py")
        if os.path.exists(path):
            os.remove(path)
            await event.reply("🗑️ Модуль удалён")
        else:
            await event.reply("❌ Модуль не найден")

    @client.on(events.NewMessage(pattern=r"\.reload"))
    async def reload(event):
        importlib.invalidate_caches()
        load_all_modules(client)
        await event.reply("🔄 Модули перезагружены")

    print("✅ Юзербот запущен")
    load_all_modules(client)
    await client.run_until_disconnected()

# --- Запуск ---
if __name__ == "__main__":
    if not os.path.exists(MODULES_PATH):
        os.makedirs(MODULES_PATH)
    asyncio.run(main())
