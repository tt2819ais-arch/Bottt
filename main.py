import sys, os, subprocess

# --- Добавляем текущую папку в sys.path ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- Автоустановка пакетов ---
for package in ["telethon", "requests"]:
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import importlib, requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession

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

# --- Проверка сессии ---
client = None
if os.path.exists(SESSION_FILE):
    client = TelegramClient(StringSession(open(SESSION_FILE).read()), API_ID, API_HASH)

# --- Если сессии нет, авторизация через бота ---
if client is None:
    auth_client = TelegramClient("auth_temp", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    print("Отправьте /login боту в Telegram для авторизации юзербота")

    @auth_client.on(events.NewMessage(pattern="/login"))
    async def login(event):
        await event.reply("Введи номер телефона (+70000000000):")
        async with auth_client.conversation(event.chat_id) as conv:
            phone = (await conv.get_response()).raw_text
            user_client = TelegramClient(StringSession(), API_ID, API_HASH)
            await user_client.connect()
            await user_client.send_code_request(phone)
            await event.reply("Введи код, который придёт на Telegram или SMS:")
            code = (await conv.get_response()).raw_text
            try:
                await user_client.sign_in(phone, code)
            except Exception as e:
                if "SESSION_PASSWORD_NEEDED" in str(e):
                    await event.reply("У тебя включена 2FA. Введи пароль Telegram:")
                    password = (await conv.get_response()).raw_text
                    await user_client.sign_in(password=password)
            # Сохраняем сессию
            with open(SESSION_FILE, "w") as f:
                f.write(user_client.session.save())
            await event.reply("✅ Готово! Юзербот авторизован.")
            await user_client.disconnect()
            auth_client.disconnect()

    auth_client.run_until_disconnected()
    client = TelegramClient(StringSession(open(SESSION_FILE).read()), API_ID, API_HASH)

# --- Основной клиент ---
@client.on(events.NewMessage(pattern=r"\\.dlm (.+)"))
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

@client.on(events.NewMessage(pattern=r"\\.modules"))
async def modules(event):
    lst = [f[:-3] for f in os.listdir(MODULES_PATH) if f.endswith(".py")]
    await event.reply("📦 Модули:\\n" + "\\n".join(lst))

@client.on(events.NewMessage(pattern=r"\\.rmm (.+)"))
async def rmm(event):
    name = event.pattern_match.group(1)
    p = f"{MODULES_PATH}/{name}.py"
    if os.path.exists(p):
        os.remove(p)
        await event.reply("🗑️ Удалено")
    else:
        await event.reply("Нет такого модуля")

@client.on(events.NewMessage(pattern=r"\\.reload"))
async def reload(event):
    importlib.invalidate_caches()
    load_all_modules(client)
    await event.reply("🔄 Готово")

# --- Старт юзербота ---
client.start()
load_all_modules(client)
client.run_until_disconnected()
