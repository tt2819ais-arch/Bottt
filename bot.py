import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

from telegram import Update, ChatMember, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ChatMemberHandler
)
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8491774226:AAHvZR02IZ4lhUAmgFCuCOAYE9atAmbcYKc"

# Константы
SUPER_ADMIN = "@MaksimXyila"
DEFAULT_ADMIN = "@ar_got"
EMAIL_PATTERN = r"sir\+\d+@outluk\.ru"
SUM_PATTERN = r"^(!\d+|\d+!)$"
ACTIVATION_KEYWORDS = [
    "Подключаю", "подключаю", 
    "Щас подключу", "щас подключу", 
    "Щас подключат", "Ждем подключения"
]

# JSON файлы для хранения данных
ADMINS_FILE = "admins.json"
DROPS_FILE = "drops.json"
STATS_FILE = "stats.json"

# Инициализация структур данных
class DropStatus(Enum):
    ADDED = "добавлен"
    WELCOMED = "приветствован"
    ACTIVE = "активен"

class DataManager:
    """Менеджер для работы с JSON файлами"""
    
    @staticmethod
    def load_json(filename: str, default: dict = None) -> dict:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default if default is not None else {}
    
    @staticmethod
    def save_json(filename: str, data: dict):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def init_files():
        """Инициализация файлов при первом запуске"""
        # admins.json
        if not DataManager.load_json(ADMINS_FILE):
            admins = {
                "super_admin": SUPER_ADMIN,
                "admins": [SUPER_ADMIN, DEFAULT_ADMIN],
                "creation_date": datetime.now().isoformat()
            }
            DataManager.save_json(ADMINS_FILE, admins)
            logger.info("Файл admins.json инициализирован")
        
        # drops.json
        if not DataManager.load_json(DROPS_FILE):
            DataManager.save_json(DROPS_FILE, {"drops": {}})
            logger.info("Файл drops.json инициализирован")
        
        # stats.json
        if not DataManager.load_json(STATS_FILE):
            stats = {
                "total_amount": 0,
                "spent_amount": 0,
                "remaining_amount": 0,
                "transactions": []
            }
            DataManager.save_json(STATS_FILE, stats)
            logger.info("Файл stats.json инициализирован")

class BotManager:
    """Основной менеджер бота"""
    
    def __init__(self):
        self.admins = DataManager.load_json(ADMINS_FILE)
        self.drops = DataManager.load_json(DROPS_FILE)
        self.stats = DataManager.load_json(STATS_FILE)
        self.last_sum = None  # Для хранения последней суммы перед email
    
    async def is_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь администратором"""
        if not username:
            return False
        return username in self.admins.get("admins", [])
    
    async def is_super_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь суперадмином"""
        return username == self.admins.get("super_admin")
    
    async def add_admin(self, username: str) -> bool:
        """Добавляет администратора"""
        if username not in self.admins["admins"]:
            self.admins["admins"].append(username)
            DataManager.save_json(ADMINS_FILE, self.admins)
            logger.info(f"Добавлен администратор: {username}")
            return True
        return False
    
    async def remove_admin(self, username: str) -> bool:
        """Удаляет администратора"""
        if username in self.admins["admins"] and username != SUPER_ADMIN:
            self.admins["admins"].remove(username)
            DataManager.save_json(ADMINS_FILE, self.admins)
            logger.info(f"Удален администратор: {username}")
            return True
        return False
    
    async def add_drop(self, username: str, added_by: str) -> bool:
        """Добавляет дропа"""
        if username not in self.drops["drops"]:
            self.drops["drops"][username] = {
                "status": DropStatus.ADDED.value,
                "added_by": added_by,
                "added_date": datetime.now().isoformat(),
                "welcomed": False,
                "activated": False,
                "activation_date": None
            }
            DataManager.save_json(DROPS_FILE, self.drops)
            logger.info(f"Добавлен дроп: {username} от {added_by}")
            return True
        return False
    
    async def update_drop_status(self, username: str, status: DropStatus):
        """Обновляет статус дропа"""
        if username in self.drops["drops"]:
            self.drops["drops"][username]["status"] = status.value
            if status == DropStatus.ACTIVE:
                self.drops["drops"][username]["activated"] = True
                self.drops["drops"][username]["activation_date"] = datetime.now().isoformat()
            DataManager.save_json(DROPS_FILE, self.drops)
    
    async def set_total_amount(self, amount: int):
        """Устанавливает общую сумму для открутки"""
        self.stats["total_amount"] = amount
        self.stats["remaining_amount"] = amount
        DataManager.save_json(STATS_FILE, self.stats)
        logger.info(f"Установлена общая сумма: {amount}")
    
    async def process_transaction(self, amount: int, email: str):
        """Обрабатывает транзакцию"""
        self.stats["spent_amount"] += amount
        self.stats["remaining_amount"] -= amount
        
        transaction = {
            "amount": amount,
            "email": email,
            "date": datetime.now().isoformat()
        }
        self.stats["transactions"].append(transaction)
        
        DataManager.save_json(STATS_FILE, self.stats)
        logger.info(f"Обработана транзакция: {amount} руб, email: {email}")
    
    async def reset_stats(self):
        """Сбрасывает статистику открутки"""
        self.stats["spent_amount"] = 0
        self.stats["remaining_amount"] = self.stats["total_amount"]
        self.stats["transactions"] = []
        DataManager.save_json(STATS_FILE, self.stats)
        logger.info("Статистика открутки сброшена")
    
    async def get_stats_message(self) -> str:
        """Формирует сообщение со статистикой"""
        msg = "📊 СТАТИСТИКА ОТКРУТКИ И ДРОПОВ\n\n"
        
        # Статистика открутки
        msg += f"💰 ОТКРУТКА:\n"
        msg += f"• Общая сумма: ₽{self.stats['total_amount']:,}\n"
        msg += f"• Откручено: ₽{self.stats['spent_amount']:,}\n"
        msg += f"• Осталось: ₽{self.stats['remaining_amount']:,}\n\n"
        
        # Список дропов
        msg += "👥 ДРОПЫ:\n"
        if self.drops["drops"]:
            for drop_username, drop_info in self.drops["drops"].items():
                status_emoji = {
                    DropStatus.ADDED.value: "⏳",
                    DropStatus.WELCOMED.value: "👋",
                    DropStatus.ACTIVE.value: "✅"
                }.get(drop_info["status"], "❓")
                
                msg += f"{status_emoji} {drop_username}: {drop_info['status']}\n"
                msg += f"   Добавлен: {drop_info['added_by']}\n"
                if drop_info.get('activation_date'):
                    msg += f"   Активирован: {drop_info['activation_date'][:10]}\n"
        else:
            msg += "Нет добавленных дропов\n\n"
        
        # Список администраторов
        msg += "\n🔑 АДМИНИСТРАТОРЫ:\n"
        for admin in self.admins["admins"]:
            if admin == self.admins["super_admin"]:
                msg += f"👑 {admin} (суперадмин)\n"
            else:
                msg += f"• {admin}\n"
        
        return msg

# Инициализация менеджера
bot_manager = BotManager()

# Команда /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_admin(username):
        await update.message.reply_text(
            "Вы не являетесь администратором. "
            "Доступ к боту ограничен."
        )
        return
    
    welcome_message = (
        "🤖 Бот для управления откруткой и дропами активирован.\n\n"
        f"Суперадмин: {SUPER_ADMIN}\n"
        f"Администраторы: {', '.join(bot_manager.admins['admins'])}\n\n"
        "Используйте /help для просмотра всех команд."
    )
    await update.message.reply_text(welcome_message)

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_admin(username):
        return
    
    help_text = """
=== БОТ ДЛЯ УПРАВЛЕНИЯ ОТКРУТКОЙ И ДРОПАМИ ===

📊 ОСНОВНЫЕ КОМАНДЫ:

/rub [сумма] - установить общую сумму для открутки
/stats - статистика по открутке и дропам
/add_admin @username - добавить администратора
/remove_admin @username - удалить администратора
/reset - сбросить счетчик открутки (только @MaksimXyila)

🎯 СИСТЕМА ОТКРУТКИ:
1. Установите общую сумму: /rub 100000
2. Отправляйте суммы в формате: 9500! или !9500
3. Сразу после суммы отправьте email: sir+123456@outluk.ru
4. Бот автоматически посчитает остаток

👤 УПРАВЛЕНИЕ ДРОПАМИ:
1. Добавить дропа: отправьте "дроп @username"
2. Когда дроп зайдет в группу - бот отправит анкету
3. После заполнения анкеты отправьте: "Подключаю" (или аналоги)
4. Бот отправит финальную инструкцию дропу

🔑 КЛЮЧЕВЫЕ СЛОВА ДЛЯ АКТИВАЦИИ ДРОПА:
Подключаю, подключаю, Щас подключу, щас подключу, Щас подключат, Ждем подключения

⚠️ ВНИМАНИЕ:
- Бот работает только с администраторами
- Суммы считаются только в указанных форматах
- Email должен быть строго в формате sir+[цифры]@outluk.ru
- Права админа выдаются только по юзернейму (@)

Администраторы по умолчанию: @MaksimXyila @ar_got
    """
    
    await update.message.reply_text(help_text)

# Команда /rub
async def rub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rub"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_admin(username):
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /rub [сумма]\n"
            "Пример: /rub 100000"
        )
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("Сумма должна быть положительным числом!")
            return
        
        await bot_manager.set_total_amount(amount)
        await update.message.reply_text(
            f"Общая сумма открутки установлена: ₽{amount:,}"
        )
    except ValueError:
        await update.message.reply_text("Неверный формат суммы!")

# Команда /add_admin
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /add_admin"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_super_admin(username):
        await update.message.reply_text(
            "Эта команда доступна только @MaksimXyila"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /add_admin @username"
        )
        return
    
    new_admin = context.args[0].lower()
    if not new_admin.startswith('@'):
        await update.message.reply_text("Юзернейм должен начинаться с @")
        return
    
    if await bot_manager.add_admin(new_admin):
        await update.message.reply_text(f"Администратор {new_admin} добавлен")
    else:
        await update.message.reply_text(f"Администратор {new_admin} уже существует")

# Команда /remove_admin
async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /remove_admin"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_super_admin(username):
        await update.message.reply_text(
            "Эта команда доступна только @MaksimXyila"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "Использование: /remove_admin @username"
        )
        return
    
    admin_to_remove = context.args[0].lower()
    if not admin_to_remove.startswith('@'):
        await update.message.reply_text("Юзернейм должен начинаться с @")
        return
    
    if admin_to_remove == SUPER_ADMIN:
        await update.message.reply_text("Нельзя удалить суперадмина!")
        return
    
    if await bot_manager.remove_admin(admin_to_remove):
        await update.message.reply_text(f"Администратор {admin_to_remove} удален")
    else:
        await update.message.reply_text(f"Администратор {admin_to_remove} не найден")

# Команда /stats
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_admin(username):
        return
    
    stats_message = await bot_manager.get_stats_message()
    await update.message.reply_text(stats_message)

# Команда /reset
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    if not await bot_manager.is_super_admin(username):
        await update.message.reply_text(
            "Эта команда доступна только @MaksimXyila"
        )
        return
    
    await bot_manager.reset_stats()
    await update.message.reply_text("Счетчик открутки сброшен")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    username = update.effective_user.username
    if username:
        username = f"@{username}"
    
    # Пропускаем сообщения от не-администраторов
    if not await bot_manager.is_admin(username):
        return
    
    message_text = update.message.text.strip()
    
    # Обработка добавления дропа
    if message_text.lower().startswith('дроп '):
        parts = message_text.split()
        if len(parts) == 2 and parts[1].startswith('@'):
            drop_username = parts[1].lower()
            
            if await bot_manager.add_drop(drop_username, username):
                # Добавляем в статистику
                if "statistics" not in bot_manager.drops:
                    bot_manager.drops["statistics"] = []
                
                stat_entry = {
                    "type": "Вход",
                    "username": drop_username,
                    "date": datetime.now().isoformat(),
                    "added_by": username
                }
                bot_manager.drops["statistics"].append(stat_entry)
                DataManager.save_json(DROPS_FILE, bot_manager.drops)
                
                await update.message.reply_text("👌")
            else:
                await update.message.reply_text("Этот дроп уже добавлен")
        return
    
    # Обработка ключевых слов для активации дропа
    if message_text in ACTIVATION_KEYWORDS:
        # Ищем последнего добавленного дропа
        drops = bot_manager.drops["drops"]
        if drops:
            # Берем последнего дропа по дате добавления
            latest_drop = max(drops.items(), 
                            key=lambda x: x[1].get('added_date', ''))
            drop_username = latest_drop[0]
            
            if latest_drop[1]["status"] == DropStatus.WELCOMED.value:
                await bot_manager.update_drop_status(drop_username, DropStatus.ACTIVE)
                
                # Отправляем финальную инструкцию
                instruction = (
                    f"{{INFO}} {drop_username} дропа - Сейчас тебе будет приходить денюжка. "
                    "Каждое поступление - мне скрин из истории операций. Не отдельного перевода, "
                    "а прям страницу истории, списком.\n"
                    "Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.\n\n"
                    "Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). "
                    "Надо будет перевести, только внимательно (!!!).\n\n"
                    "После перевода отправляешь квитанцию на указанную почту."
                )
                await update.message.reply_text(instruction)
        return
    
    # Обработка сумм в формате "9500!" или "!9500"
    if re.match(SUM_PATTERN, message_text):
        try:
            amount = int(message_text.strip('!'))
            if amount > 0:
                bot_manager.last_sum = amount
                # Ждем email в следующем сообщении
            else:
                await update.message.reply_text("Сумма должна быть положительной!")
        except ValueError:
            pass
        return
    
    # Обработка email
    if re.match(EMAIL_PATTERN, message_text) and bot_manager.last_sum is not None:
        email = message_text
        
        # Проверяем, что остаток достаточен
        if bot_manager.stats["remaining_amount"] >= bot_manager.last_sum:
            await bot_manager.process_transaction(bot_manager.last_sum, email)
            
            response = (
                f"Откручено ₽{bot_manager.last_sum:,}/"
                f"Осталось ₽{bot_manager.stats['remaining_amount']:,}"
            )
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(
                f"Недостаточно средств! Остаток: ₽{bot_manager.stats['remaining_amount']:,}"
            )
        
        bot_manager.last_sum = None
        return

# Обработка новых участников группы
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников чата"""
    for new_member in update.message.new_chat_members:
        username = new_member.username
        if username:
            username = f"@{username}".lower()
            
            # Проверяем, является ли новый участник дропом
            if username in bot_manager.drops["drops"]:
                drop_info = bot_manager.drops["drops"][username]
                
                if not drop_info.get("welcomed", False):
                    # Отправляем приветственное сообщение
                    welcome_message = (
                        f"Привет, {username}, заполни анкету:\n"
                        "1. ФИО:\n"
                        "2. Номер карты:\n"
                        "3. Номер счета:\n"
                        "4. Номер телефона:\n"
                        "Скриншот трат за Ноябрь/Декабрь."
                    )
                    
                    sent_message = await update.message.reply_text(welcome_message)
                    
                    # Пытаемся закрепить сообщение
                    try:
                        await sent_message.pin()
                    except Exception as e:
                        logger.error(f"Не удалось закрепить сообщение: {e}")
                    
                    # Обновляем статус дропа
                    await bot_manager.update_drop_status(username, DropStatus.WELCOMED)
                    bot_manager.drops["drops"][username]["welcomed"] = True
                    DataManager.save_json(DROPS_FILE, bot_manager.drops)

# Основная функция
def main():
    """Основная функция запуска бота"""
    # Инициализация файлов
    DataManager.init_files()
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rub", rub_command))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("reset", reset_command))
    
    # Обработка новых участников
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    
    # Обработка текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
