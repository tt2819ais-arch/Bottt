import re
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"

# Суперадмины (фиксированные)
SUPER_ADMINS = ["@MaksimXyila", "@ar_got"]

# Целевая сумма для автоматического отчета
TARGET_AMOUNT = 5000

# Хранилище данных в памяти
class BotData:
    def __init__(self):
        self.agents = {}
        self.active_agent = None
        self.admin_mode = {}
        self.rub_mode = {}
        self.transfer_sequence = {}
        self.waiting_balance = {}
        
        self.agent_balance = {}
        self.agent_rolled = {}
        self.agent_info = {}
        
        # Для дебагга - логируем что происходит
        self.debug_log = []

bot_data = BotData()

def is_admin(update: Update) -> bool:
    user = update.effective_user
    message = update.effective_message
    
    if user.username and f"@{user.username}" in SUPER_ADMINS:
        return True
    
    if message.chat.type in ['group', 'supergroup']:
        try:
            member = message.chat.get_member(user.id)
            return member.status in ['administrator', 'creator']
        except:
            return False
    
    return False

def extract_username(text: str) -> str:
    match = re.search(r'@(\w+)', text)
    return f"@{match.group(1)}" if match else None

def is_agent(username: str) -> bool:
    return username in bot_data.agents

# Команды /start и /help
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - информация о боте"""
    help_text = (
        "🤖 Бот-администратор группового чата\n\n"
        "📋 Основные команды и триггеры:\n"
        "─────────────────────\n"
        "📌 Для админов:\n"
        "• агенту @username - назначить агента\n"
        "• делагент @username - зарегистрировать агента\n"
        "• делагент - сбросить всех агентов\n"
        "• Бал / Баланс / балик - запросить баланс агента\n"
        "• /rub [сумма] - установить сумму открутки\n"
        "• подключа / Подключаю - отправить инструкции агенту\n\n"
        "📌 Для всех:\n"
        "• хелп - получить инструкции\n"
        "• /help - эта справка\n\n"
        "📌 Цикл перевода (от админа):\n"
        "1. Реквизит (телефон/карта)\n"
        "2. Сумма! (например: 330!)\n"
        "3. Банк (💚Сбер💚 или 💛Тбанк💛)\n"
        "4. Почта (sir+123@outluk.ru)\n"
        "→ Бот выдаст статистику"
    )
    await update.message.reply_text(help_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - подробная справка"""
    await start_command(update, context)

async def rub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /rub для установки суммы"""
    if not is_admin(update):
        return
    
    chat_id = update.effective_chat.id
    
    # Проверяем, указана ли сумма в команде
    if context.args:
        amount_text = ' '.join(context.args)
        match = re.search(r'(\d+)', amount_text)
        if match:
            amount = int(match.group(1))
            
            if not bot_data.active_agent:
                await update.message.reply_text("❌ Нет активного агента. Сначала назначьте агента.")
                return
            
            # Устанавливаем сумму для активного агента
            bot_data.agent_rolled[bot_data.active_agent] = amount
            
            # Получаем баланс агента
            balance = bot_data.agent_balance.get(bot_data.active_agent, 0)
            remaining = balance - amount if balance >= amount else 0
            
            # Отправляем отчет
            report = (
                f"💰 Сумма установлена: {amount}₽\n"
                f"Баланс: {balance}₽\n"
                f"Откручено: {amount}₽\n"
                f"Осталось: {remaining}₽"
            )
            await update.message.reply_text(report)
            
            # Проверяем достижение целевой суммы
            if amount >= TARGET_AMOUNT:
                await send_auto_report(update, bot_data.active_agent, amount, "")
            
            return
    
    # Если сумма не указана, переходим в режим ожидания
    bot_data.rub_mode[chat_id] = True
    await update.message.reply_text("Введите сумму для установки:")

async def handle_transfer_sequence(update: Update, context: CallbackContext, text: str):
    """Обработка последовательности перевода"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Проверяем, является ли пользователь админом
    if not is_admin(update):
        return
    
    # Инициализируем последовательность если её нет
    if chat_id not in bot_data.transfer_sequence:
        bot_data.transfer_sequence[chat_id] = {"step": 0, "data": {}}
    
    current_data = bot_data.transfer_sequence[chat_id]
    
    # Шаг 1: Реквизит (телефон или карта)
    if current_data["step"] == 0:
        # Упрощаем проверку - любой текст может быть реквизитом
        if text and len(text) > 5:
            current_data["data"]["requisite"] = text
            current_data["step"] = 1
            bot_data.transfer_sequence[chat_id] = current_data
            logger.info(f"Шаг 1: Реквизит установлен: {text}")
        return
    
    # Шаг 2: Сумма с восклицательным знаком
    elif current_data["step"] == 1:
        # Проверяем разные форматы суммы
        sum_pattern = r'^!?\d+!?$'
        if re.match(sum_pattern, text):
            # Извлекаем число
            amount = int(re.sub(r'[!]', '', text))
            current_data["data"]["amount"] = amount
            current_data["step"] = 2
            bot_data.transfer_sequence[chat_id] = current_data
            logger.info(f"Шаг 2: Сумма установлена: {amount}")
        else:
            # Сбрасываем последовательность при неверном формате
            bot_data.transfer_sequence.pop(chat_id, None)
            logger.warning(f"Неверный формат суммы: {text}")
        return
    
    # Шаг 3: Банк
    elif current_data["step"] == 2:
        # Проверяем банк (с учетом возможных ошибок в эмодзи)
        if "сбер" in text.lower() or "💚" in text:
            current_data["data"]["bank"] = "💚Сбер💚"
            current_data["step"] = 3
            bot_data.transfer_sequence[chat_id] = current_data
            logger.info("Шаг 3: Банк установлен: Сбер")
        elif "тбанк" in text.lower() or "💛" in text:
            current_data["data"]["bank"] = "💛Тбанк💛"
            current_data["step"] = 3
            bot_data.transfer_sequence[chat_id] = current_data
            logger.info("Шаг 3: Банк установлен: Тбанк")
        else:
            bot_data.transfer_sequence.pop(chat_id, None)
            logger.warning(f"Неверный банк: {text}")
        return
    
    # Шаг 4: Почта
    elif current_data["step"] == 3:
        # Упрощенная проверка почты
        if "@outluk.ru" in text.lower() and "sir+" in text.lower():
            current_data["data"]["email"] = text
            current_data["step"] = 4
            bot_data.transfer_sequence[chat_id] = current_data
            
            # Отправляем отчет
            logger.info(f"Шаг 4: Почта получена: {text}")
            await send_transfer_report(update, current_data["data"])
            
            # Сбрасываем последовательность
            bot_data.transfer_sequence.pop(chat_id, None)
        else:
            bot_data.transfer_sequence.pop(chat_id, None)
            logger.warning(f"Неверный формат почты: {text}")
        return

async def send_transfer_report(update: Update, data: dict):
    """Отправка отчета о переводе"""
    if not bot_data.active_agent:
        await update.effective_message.reply_text("⚠️ Нет активного агента. Статистика не может быть рассчитана.")
        return
    
    agent_username = bot_data.active_agent
    balance = bot_data.agent_balance.get(agent_username, 0)
    amount = data.get("amount", 0)
    
    # Логика вычисления открученного и остатка
    current_rolled = bot_data.agent_rolled.get(agent_username, 0)
    new_rolled = current_rolled + amount
    bot_data.agent_rolled[agent_username] = new_rolled
    
    remaining = balance - new_rolled if balance >= new_rolled else 0
    
    report = (
        f"📊 Статистика для {agent_username}:\n"
        f"─────────────────────\n"
        f"Баланс: {balance}₽\n"
        f"Откручено: {new_rolled}₽\n"
        f"Осталось: {remaining}₽\n"
        f"─────────────────────\n"
        f"Последний перевод: {amount}₽"
    )
    
    await update.effective_message.reply_text(report)
    
    # Проверка на достижение целевой суммы
    if new_rolled >= TARGET_AMOUNT:
        await send_auto_report(update, agent_username, new_rolled, data.get("bank", ""))

async def send_auto_report(update: Update, agent_username: str, rolled_amount: int, bank: str):
    """Автоматический отчет при достижении суммы"""
    phone = bot_data.agent_info.get(agent_username, {}).get("phone", "не указан")
    
    report = (
        f"🎯 ЦЕЛЕВАЯ СУММА ДОСТИГНУТА!\n"
        f"─────────────────────\n"
        f"Агент: {agent_username}\n"
        f"Номер телефона: {phone}\n"
        f"Откручено: {rolled_amount}₽\n"
        f"Банк: {bank}\n"
        f"─────────────────────\n"
        f"✅ Автоматический отчет"
    )
    
    await update.effective_message.reply_text(report)

async def send_help_instructions(update: Update, username: str):
    """Отправка инструкций помощи"""
    instructions = (
        f"@{username}- Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. "
        "Не отдельного перевода, а прям страницу истории, списком.\n"
        "1. Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.\n"
        "2. Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). "
        "Надо будет перевести, только внимательно.\n"
        "3. После перевода отправляешь квитанцию на указанную почту."
    )
    await update.effective_message.reply_text(instructions)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений"""
    message = update.effective_message
    user = update.effective_user
    text = message.text.strip() if message.text else ""
    chat_id = message.chat_id
    
    # Игнорируем сообщения от самого бота
    if user.id == context.bot.id:
        return
    
    # Логируем входящее сообщение
    logger.info(f"Сообщение от @{user.username}: {text}")
    
    # Обработка ввода суммы для команды /rub
    if chat_id in bot_data.rub_mode and bot_data.rub_mode[chat_id]:
        if re.fullmatch(r'\d+', text):
            amount = int(text)
            
            if not bot_data.active_agent:
                await message.reply_text("❌ Нет активного агента.")
                bot_data.rub_mode.pop(chat_id, None)
                return
            
            # Устанавливаем сумму
            bot_data.agent_rolled[bot_data.active_agent] = amount
            
            # Получаем баланс
            balance = bot_data.agent_balance.get(bot_data.active_agent, 0)
            remaining = balance - amount if balance >= amount else 0
            
            # Отправляем отчет
            report = (
                f"💰 Сумма установлена: {amount}₽\n"
                f"Баланс: {balance}₽\n"
                f"Откручено: {amount}₽\n"
                f"Осталось: {remaining}₽"
            )
            await message.reply_text(report)
            
            # Проверка достижения цели
            if amount >= TARGET_AMOUNT:
                await send_auto_report(update, bot_data.active_agent, amount, "")
            
            # Выходим из режима
            bot_data.rub_mode.pop(chat_id, None)
            return
        else:
            await message.reply_text("❌ Введите корректное число.")
            bot_data.rub_mode.pop(chat_id, None)
            return
    
    # Обработка запроса баланса от агента
    if chat_id in bot_data.waiting_balance:
        if user.username and f"@{user.username}" in bot_data.agents:
            # Проверяем, что сообщение содержит только число
            if re.fullmatch(r'\d+', text):
                amount = int(text)
                bot_data.agent_balance[f"@{user.username}"] = amount
                bot_data.waiting_balance.pop(chat_id, None)
                await message.reply_text(f"✅ Баланс установлен: {amount}₽")
                return
    
    text_lower = text.lower()
    
    # 2.2. Запрос инструкции "хелп" от любого пользователя
    if text_lower == "хелп":
        await send_help_instructions(update, user.username)
        return
    
    # Проверка, является ли пользователь админом
    admin = is_admin(update)
    
    # 2.1. Назначение агента командой админа
    if admin and text.startswith("агенту "):
        username = extract_username(text)
        if username:
            bot_data.agents[username] = {"status": "new"}
            bot_data.active_agent = username
            await message.reply_text(
                f"{username}, заполни анкету.\n"
                "1. ФИО:\n"
                "2. Номер карты:\n"
                "3. Номер счета:\n"
                "4. Номер телефона:\n"
                "Скриншот трат за Ноябрь/Декабрь.\n"
                "Есть вопросы? Пропиши «хелп»"
            )
        return
    
    # 2.5. Запрос баланса от админа
    if admin and any(word in text_lower for word in ["баланс", "бал", "балик", "скок балик"]):
        if not bot_data.active_agent:
            await message.reply_text("⚠️ Нет активного агента.")
            return
        
        bot_data.waiting_balance[chat_id] = True
        await message.reply_text(f"⏳ Ожидаю ответ от {bot_data.active_agent} с суммой баланса...")
        return
    
    # 2.3. Подтверждение подключения (содержит "подключа")
    if admin and "подключа" in text_lower:
        if bot_data.active_agent:
            await send_help_instructions(update, bot_data.active_agent.replace("@", ""))
        else:
            await message.reply_text("⚠️ Сначала назначьте агента")
        return
    
    # 3. Административные команды
    if admin and text.startswith("делагент"):
        if " " in text:
            # Назначение агента
            username = extract_username(text)
            if username:
                bot_data.agents[username] = {"status": "new"}
                bot_data.active_agent = username
                await message.reply_text(
                    f"{username}, заполни анкету.\n"
                    "1. ФИО:\n"
                    "2. Номер карты:\n"
                    "3. Номер счета:\n"
                    "4. Номер телефона:\n"
                    "Скриншот трат за Ноябрь/Декабрь.\n"
                    "Есть вопросы? Пропиши «хелп»"
                )
        else:
            # Сброс всех агентов
            bot_data.agents.clear()
            bot_data.active_agent = None
            bot_data.agent_balance.clear()
            bot_data.agent_rolled.clear()
            bot_data.agent_info.clear()
            # Не отправляем сообщение в чат
        return
    
    # 2.4. Цикл фиксации задачи на перевод от админа
    if admin:
        await handle_transfer_sequence(update, context, text)
        return
    
    # Во всех остальных случаях не реагируем
    return

def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rub", rub_command))
    
    # Обработчик всех текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    print("📋 Доступные команды: /start, /help, /rub")
    print("📌 Триггеры: агенту @username, делагент, Бал, хелп, подключа")
    print("💸 Цикл перевода: реквизит → сумма! → банк → почта")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
