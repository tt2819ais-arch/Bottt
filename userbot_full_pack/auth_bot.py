from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import events

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BOT_TOKEN = "7568864397:AAEI4RwDx7Gk_HMnmeCCYMaLkVJTMqKOfMw"

bot = TelegramClient("auth_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.reply("Привет! Отправь /login чтобы авторизовать юзербота.")

@bot.on(events.NewMessage(pattern="/login"))
async def login(event):
    await event.reply("Введи номер телефона (+70000000000):")
    async with bot.conversation(event.chat_id) as conv:
        phone = (await conv.get_response()).raw_text
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        await event.reply("Введи код:")
        code = (await conv.get_response()).raw_text
        await client.sign_in(phone, code)
        with open("user.session","w") as f:
            f.write(client.session.save())
        await event.reply("Готово! Юзербот авторизован.")
        await client.disconnect()

bot.run_until_disconnected()
