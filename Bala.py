import re
import logging
from datetime import datetime
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
        self.agents = {}  # username -> {status, phone, card, account, name}
        self.active_agent = None
        self.admin_mode = {}
        self.rub_mode = {}
        self.transfer_sequence = {}
        self.waiting_balance = {}  # chat_id -> target_username для баланса
        
        # Данные агентов
        self.agent_balance = {}  # username -> баланс
        self.agent_rolled = {}   # username -> ОБЩАЯ сумма открутки
        self.agent_transfers = {}  # username -> список переводов [{amount, requisite, bank, date}]
        self.agent_notes = {}    # username -> заметки
        
        self.notes_history = []  # история всех реквизитов

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
        "• Бал @username - запросить баланс конкретного агента\n"
        "• /rub [сумма!] - начать прокрутку (например: /rub 1000!)\n"
        "• подключа / Подключаю - отправить инструкции агенту\n"
        "• /notes - история реквизитов\n\n"
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
    """Обработка команды /rub для установки суммы открутки"""
    if not is_admin(update):
        return
    
    if not bot_data.active_agent:
        await update.message.reply_text("❌ Нет активного агента. Сначала назначьте агента.")
        return
    
    # Проверяем, указана ли сумма в команде
    if context.args:
        amount_text = ' '.join(context.args)
        # Проверяем формат с !
        if '!' in amount_text:
            match = re.search(r'(\d+)', amount_text)
            if match:
                amount = int(match.group(1))
                
                # Устанавливаем сумму открутки для активного агента
                bot_data.agent_rolled[bot_data.active_agent] = amount
                
                # Получаем баланс агента
                balance = bot_data.agent_balance.get(bot_data.active_agent, 0)
                remaining = balance - amount if balance >= amount else 0
                
                # Отправляем отчет
                report = (
                    f"💰 Начата прокрутка для {bot_data.active_agent}\n"
                    f"─────────────────────\n"
                    f"Сумма открутки: {amount}₽\n"
                    f"Баланс агента: {balance}₽\n"
                    f"Остаток после открутки: {remaining}₽\n"
                    f"─────────────────────\n"
                    f"Теперь отправьте реквизиты для перевода"
                )
                await update.message.reply_text(report)
                return
        else:
            await update.message.reply_text("❌ Используйте формат: /rub 1000!")
            return
    
    await update.message.reply_text("❌ Используйте: /rub [сумма!] (например: /rub 1000!)")

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /notes - история реквизитов"""
    if not is_admin(update):
        return
    
    if not bot_data.notes_history:
        await update.message.reply_text("📝 История реквизитов пуста.")
        return
    
    notes_text = "📝 История реквизитов:\n─────────────────────\n"
    
    for i, note in enumerate(bot_data.notes_history[-10:], 1):  # Последние 10 записей
        notes_text += f"{i}. {note['requisite']}, {note['amount']}₽, {note['bank']}\n"
    
    notes_text += f"\nВсего записей: {len(bot_data.notes_history)}"
    await update.message.reply_text(notes_text)

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
        if text and len(text) > 5:
            current_data["data"]["requisite"] = text
            current_data["step"] = 1
            bot_data.transfer_sequence[chat_id] = current_data
            logger.info(f"Шаг 1: Реквизит установлен: {text}")
        return
    
    # Шаг 2: Сумма с восклицательным знаком
    elif current_data["step"] == 1:
        sum_pattern = r'^!?\d+!?$'
        if re.match(sum_pattern, text):
            amount = int(re.sub(r'[!]', '', text))
            current_data["data"]["amount"] = amount
            current_data["step"] = 2
            bot_data.transfer_sequence[chat_id] = current_data
            logger.info(f"Шаг 2: Сумма установлена: {amount}")
        else:
            bot_data.transfer_sequence.pop(chat_id, None)
            logger.warning(f"Неверный формат суммы: {text}")
        return
    
    # Шаг 3: Банк
    elif current_data["step"] == 2:
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
        if "@outluk.ru" in text.lower() and "sir+" in text.lower():
            current_data["data"]["email"] = text
            current_data["step"] = 4
            bot_data.transfer_sequence[chat_id] = current_data
            
            # Сохраняем в историю реквизитов
            bot_data.notes_history.append({
                "requisite": current_data["data"].get("requisite", ""),
                "amount": current_data["data"].get("amount", 0),
                "bank": current_data["data"].get("bank", ""),
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "agent": bot_data.active_agent
            })
            
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
        await update.effective_message.reply_text("⚠️ Нет активного агента.")
        return
    
    agent_username = bot_data.active_agent
    balance = bot_data.agent_balance.get(agent_username, 0)
    amount = data.get("amount", 0)
    
    # "Откручено" - это сумма текущего перевода
    # НЕ складываем с предыдущими!
    bot_data.agent_rolled[agent_username] = amount
    
    remaining = balance - amount if balance >= amount else 0
    
    # Сохраняем перевод
    if agent_username not in bot_data.agent_transfers:
        bot_data.agent_transfers[agent_username] = []
    
    bot_data.agent_transfers[agent_username].append({
        "amount": amount,
        "requisite": data.get("requisite", ""),
        "bank": data.get("bank", ""),
        "date": datetime.now().strftime("%d.%m.%Y %H:%M")
    })
    
    report = (
        f"📊 Статистика для {agent_username}:\n"
        f"─────────────────────\n"
        f"Баланс на карте: {balance}₽\n"
        f"Откручено (переведено): {amount}₽\n"
        f"Осталось на карте: {remaining}₽\n"
        f"─────────────────────\n"
        f"Реквизит: {data.get('requisite', '')}\n"
        f"Банк: {data.get('bank', '')}"
    )
    
    await update.effective_message.reply_text(report)
    
    # Проверка на достижение целевой суммы
    total_rolled = sum(t["amount"] for t in bot_data.agent_transfers.get(agent_username, []))
    if total_rolled >= TARGET_AMOUNT:
        await send_auto_report(update, agent_username, total_rolled, data.get("bank", ""))

async def send_auto_report(update: Update, agent_username: str, rolled_amount: int, bank: str):
    """Автоматический отчет при достижении суммы"""
    phone = bot_data.agents.get(agent_username, {}).get("phone", "не указан")
    
    report = (
        f"🎯 ЦЕЛЕВАЯ СУММА ДОСТИГНУТА!\n"
        f"─────────────────────\n"
        f"Агент: {agent_username}\n"
        f"Номер телефона: {phone}\n"
        f"Общая открутка: {rolled_amount}₽\n"
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
    
    logger.info(f"Сообщение от @{user.username}: {text}")
    
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
    
    # Запрос баланса от админа с указанием агента: Бал @username
    if admin and text_lower.startswith("бал"):
        # Ищем username в сообщении
        target_username = extract_username(text)
        
        if target_username:
            # Проверяем, что это агент
            if target_username not in bot_data.agents:
                await message.reply_text(f"❌ {target_username} не является агентом.")
                return
            
            # Устанавливаем ожидание ответа от ЭТОГО агента
            bot_data.waiting_balance[chat_id] = target_username
            await message.reply_text(f"⏳ Ожидаю ответ от {target_username} с суммой баланса...")
        else:
            # Если username не указан, используем активного агента
            if bot_data.active_agent:
                bot_data.waiting_balance[chat_id] = bot_data.active_agent
                await message.reply_text(f"⏳ Ожидаю ответ от {bot_data.active_agent} с суммой баланса...")
            else:
                await message.reply_text("❌ Укажите агента: Бал @username")
        return
    
    # Обработка ответа на запрос баланса ОТ АГЕНТА
    if chat_id in bot_data.waiting_balance:
        target_username = bot_data.waiting_balance[chat_id]
        
        # Проверяем, что отвечает ПРАВИЛЬНЫЙ агент
        if user.username and f"@{user.username}" == target_username:
            if re.fullmatch(r'\d+', text):
                amount = int(text)
                bot_data.agent_balance[target_username] = amount
                bot_data.waiting_balance.pop(chat_id, None)
                await message.reply_text(f"✅ Баланс {target_username} установлен: {amount}₽")
                return
        else:
            # Если отвечает не тот пользователь
            await message.reply_text(f"⏳ Жду ответ от {target_username}...")
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
            # Сброс ВСЕХ данных при команде "делагент"
            bot_data.agents.clear()
            bot_data.active_agent = None
            bot_data.agent_balance.clear()
            bot_data.agent_rolled.clear()
            bot_data.agent_info.clear()
            bot_data.agent_transfers.clear()
            bot_data.notes_history.clear()
            bot_data.waiting_balance.clear()
            bot_data.transfer_sequence.clear()
            bot_data.admin_mode.clear()
            bot_data.rub_mode.clear()
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
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rub", rub_command))
    application.add_handler(CommandHandler("notes", notes_command))
    
    # Обработчик всех текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    print("📋 Доступные команды: /start, /help, /rub, /notes")
    print("📌 Триггеры: агенту @username, делагент, Бал @username, хелп, подключа")
    print("💸 Цикл перевода: реквизит → сумма! → банк → почта")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
