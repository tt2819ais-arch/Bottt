import subprocess, sys

# Автоустановка зависимостей
for package in ["telethon", "requests"]:
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import os, importlib, requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from loader import load_all_modules

API_ID=2040
API_HASH="b18441a1ff607e10a989891a5462e627"

def get_session():
    if not os.path.exists("user.session"):
        print("Сначала запусти auth_bot.py")
        exit()
    return open("user.session").read()

client=TelegramClient(StringSession(get_session()), API_ID, API_HASH)

@client.on(events.NewMessage(pattern=r"\.dlm (.+)"))
async def dlm(event):
    url=event.pattern_match.group(1)
    name=url.split("/")[-1]
    try:
        data=requests.get(url).content
        open(f"modules/{name}","wb").write(data)
        m=importlib.import_module(f"modules.{name[:-3]}")
        if hasattr(m,"on_load"):
            await m.on_load(client)
        await event.reply("✅ Модуль установлен")
    except Exception as e:
        await event.reply(str(e))

@client.on(events.NewMessage(pattern=r"\.modules"))
async def modules(event):
    lst=[f[:-3] for f in os.listdir("modules") if f.endswith(".py")]
    await event.reply("📦 Модули:\n" + "\n".join(lst))

@client.on(events.NewMessage(pattern=r"\.rmm (.+)"))
async def rmm(event):
    name=event.pattern_match.group(1)
    p=f"modules/{name}.py"
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

client.start()
load_all_modules(client)
client.run_until_disconnected()
