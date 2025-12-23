import json
import logging
import re
import os
from datetime import datetime
from typing import Dict
from enum import Enum

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

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

# Директория для данных
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# JSON файлы для хранения данных
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
DROPS_FILE = os.path.join(DATA_DIR, "drops.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")

class DropStatus(Enum):
    ADDED = "добавлен"
    WELCOMED = "приветствован"
    ACTIVE = "активен"

class BotManager:
    """Менеджер для работы с данными бота"""
    
    def __init__(self):
        self.admins = self.load_data(ADMINS_FILE, self.get_default_admins())
        self.drops = self.load_data(DROPS_FILE, {"drops": {}, "statistics": []})
        self.stats = self.load_data(STATS_FILE, {
            "total_amount": 0,
            "spent_amount": 0,
            "remaining_amount": 0,
            "transactions": []
        })
        self.last_sum = None
        
        # Логируем загруженных администраторов для отладки
        logger.info(f"Загруженные администраторы: {self.admins.get('admins', [])}")
        logger.info(f"Суперадмин: {self.admins.get('super_admin', '')}")
    
    @staticmethod
    def get_default_admins():
        return {
            "super_admin": SUPER_ADMIN,
            "admins": [SUPER_ADMIN, DEFAULT_ADMIN],
            "creation_date": datetime.now().isoformat()
        }
    
    @staticmethod
    def load_data(filename: str, default_data: dict = None) -> dict:
        """Загружает данные из JSON файла"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Загружены данные из {filename}")
                    return data
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")
        
        logger.info(f"Используются данные по умолчанию для {filename}")
        return default_data or {}
    
    def save_data(self, filename: str, data: dict):
        """Сохраняет данные в JSON файл"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Данные сохранены в {filename}")
        except Exception as e:
            logger.error(f"Ошибка сохранения {filename}: {e}")
    
    def normalize_username(self, username: str) -> str:
        """Нормализует юзернейм (добавляет @ если нужно)"""
        if not username:
            return ""
        
        username = username.strip().lower()
        
        # Убираем @telegram если он есть
        if username.endswith("@telegram"):
            username = username.replace("@telegram", "")
        
        # Добавляем @ в начало если его нет
        if not username.startswith('@'):
            username = f"@{username}"
        
        return username
    
    def is_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь администратором"""
        if not username:
            return False
        
        normalized = self.normalize_username(username)
        admins_list = [self.normalize_username(admin) for admin in self.admins.get("admins", [])]
        
        # Для отладки
        logger.info(f"Проверка админа: '{username}' -> нормализованный: '{normalized}'")
        logger.info(f"Список админов: {admins_list}")
        
        return normalized in admins_list
    
    def is_super_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь суперадмином"""
        if not username:
            return False
        
        normalized = self.normalize_username(username)
        super_admin = self.normalize_username(self.admins.get("super_admin", ""))
        
        logger.info(f"Проверка суперадмина: '{username}' -> нормализованный: '{normalized}'")
        logger.info(f"Суперадмин в базе: '{super_admin}'")
        
        return normalized == super_admin
    
    def add_admin(self, username: str) -> bool:
        """Добавляет администратора"""
        normalized = self.normalize_username(username)
        
        if normalized and normalized not in self.admins["admins"]:
            self.admins["admins"].append(normalized)
            self.save_data(ADMINS_FILE, self.admins)
            logger.info(f"Добавлен администратор: {normalized}")
            return True
        return False
    
    def remove_admin(self, username: str) -> bool:
        """Удаляет администратора"""
        normalized = self.normalize_username(username)
        
        if normalized in self.admins["admins"] and not self.is_super_admin(normalized):
            self.admins["admins"].remove(normalized)
            self.save_data(ADMINS_FILE, self.admins)
            logger.info(f"Удален администратор: {normalized}")
            return True
        return False
    
    def add_drop(self, username: str, added_by: str) -> bool:
        """Добавляет дропа"""
        normalized = self.normalize_username(username)
        added_by_normalized = self.normalize_username(added_by)
        
        if normalized:
            if "drops" not in self.drops:
                self.drops["drops"] = {}
            
            if normalized not in self.drops["drops"]:
                self.drops["drops"][normalized] = {
                    "status": DropStatus.ADDED.value,
                    "added_by": added_by_normalized,
                    "added_date": datetime.now().isoformat(),
                    "welcomed": False,
                    "activated": False
                }
                
                # Добавляем в статистику
                if "statistics" not in self.drops:
                    self.drops["statistics"] = []
                
                self.drops["statistics"].append({
                    "type": "Вход",
                    "username": normalized,
                    "date": datetime.now().isoformat(),
                    "added_by": added_by_normalized
                })
                
                self.save_data(DROPS_FILE, self.drops)
                logger.info(f"Добавлен дроп: {normalized} от {added_by_normalized}")
                return True
        return False
    
    def update_drop_status(self, username: str, status: DropStatus):
        """Обновляет статус дропа"""
        normalized = self.normalize_username(username)
        
        if normalized in self.drops.get("drops", {}):
            self.drops["drops"][normalized]["status"] = status.value
            if status == DropStatus.ACTIVE:
                self.drops["drops"][normalized]["activated"] = True
                self.drops["drops"][normalized]["activation_date"] = datetime.now().isoformat()
            self.save_data(DROPS_FILE, self.drops)
    
    def set_total_amount(self, amount: int):
        """Устанавливает общую сумму для открутки"""
        self.stats["total_amount"] = amount
        self.stats["remaining_amount"] = amount
        self.save_data(STATS_FILE, self.stats)
        logger.info(f"Установлена общая сумма: {amount}")
    
    def process_transaction(self, amount: int, email: str):
        """Обрабатывает транзакцию"""
        self.stats["spent_amount"] += amount
        self.stats["remaining_amount"] -= amount
        
        transaction = {
            "amount": amount,
            "email": email,
            "date": datetime.now().isoformat()
        }
        
        if "transactions" not in self.stats:
            self.stats["transactions"] = []
        
        self.stats["transactions"].append(transaction)
        self.save_data(STATS_FILE, self.stats)
        logger.info(f"Обработана транзакция: {amount} руб, email: {email}")
    
    def reset_stats(self):
        """Сбрасывает статистику открутки"""
        self.stats["spent_amount"] = 0
        self.stats["remaining_amount"] = self.stats.get("total_amount", 0)
        self.stats["transactions"] = []
        self.save_data(STATS_FILE, self.stats)
        logger.info("Статистика открутки сброшена")
    
    def get_stats_message(self) -> str:
        """Формирует сообщение со статистикой"""
        msg = "📊 СТАТИСТИКА ОТКРУТКИ И ДРОПОВ\n\n"
        
        # Статистика открутки
        msg += f"💰 ОТКРУТКА:\n"
        msg += f"• Общая сумма: ₽{self.stats.get('total_amount', 0):,}\n"
        msg += f"• Откручено: ₽{self.stats.get('spent_amount', 0):,}\n"
        msg += f"• Осталось: ₽{self.stats.get('remaining_amount', 0):,}\n\n"
        
        # Список дропов
        msg += "👥 ДРОПЫ:\n"
        drops = self.drops.get("drops", {})
        if drops:
            for drop_username, drop_info in drops.items():
                status = drop_info.get("status", "неизвестно")
                status_emoji = {
                    "добавлен": "⏳",
                    "приветствован": "👋",
                    "активен": "✅"
                }.get(status, "❓")
                
                msg += f"{status_emoji} {drop_username}: {status}\n"
                msg += f"   Добавлен: {drop_info.get('added_by', 'неизвестно')}\n"
                
                activation_date = drop_info.get('activation_date')
                if activation_date:
                    msg += f"   Активирован: {activation_date[:10]}\n"
        else:
            msg += "Нет добавленных дропов\n\n"
        
        # Список администраторов
        msg += "\n🔑 АДМИНИСТРАТОРЫ:\n"
        admins_list = self.admins.get("admins", [])
        for admin in admins_list:
            normalized_admin = self.normalize_username(admin)
            if self.is_super_admin(normalized_admin):
                msg += f"👑 {normalized_admin} (суперадмин)\n"
            else:
                msg += f"• {normalized_admin}\n"
        
        return msg

# Инициализация менеджера
bot_manager = BotManager()

async def check_admin(update: Update) -> bool:
    """Проверяет права администратора"""
    user = update.effective_user
    if not user:
        return False
    
    # Пробуем разные варианты юзернейма
    usernames_to_check = []
    
    if user.username:
        usernames_to_check.append(user.username)
        usernames_to_check.append(f"@{user.username}")
    
    # Проверяем все варианты
    for username in usernames_to_check:
        if bot_manager.is_admin(username):
            logger.info(f"Пользователь {username} является администратором")
            return True
    
    logger.info(f"Пользователь {user.username} НЕ является администратором")
    logger.info(f"ID пользователя: {user.id}")
    logger.info(f"Имя пользователя: {user.full_name}")
    
    return False

async def check_super_admin(update: Update) -> bool:
    """Проверяет права суперадмина"""
    user = update.effective_user
    if not user:
        return False
    
    # Пробуем разные варианты юзернейма
    usernames_to_check = []
    
    if user.username:
        usernames_to_check.append(user.username)
        usernames_to_check.append(f"@{user.username}")
    
    # Проверяем все варианты
    for username in usernames_to_check:
        if bot_manager.is_super_admin(username):
            logger.info(f"Пользователь {username} является суперадмином")
            return True
    
    return False

# Команды
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    logger.info(f"Команда /start от пользователя {update.effective_user.username}")
    
    if not await check_admin(update):
        await update.message.reply_text(
            "Вы не являетесь администратором. Доступ к боту ограничен.\n\n"
            f"Текущие администраторы: {', '.join(bot_manager.admins.get('admins', []))}"
        )
        return
    
    await update.message.reply_text(
        "🤖 Бот для управления откруткой и дропами активирован.\n"
        "Используйте /help для просмотра команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    if not await check_admin(update):
        return
    
    help_text = """=== БОТ ДЛЯ УПРАВЛЕНИЯ ОТКРУТКОЙ И ДРОПАМИ ===

📊 ОСНОВНЫЕ КОМАНДЫ:

/rub [сумма] - установить общую сумму для открутки
/stats - статистика по открутке и дропам
/add_admin @username - добавить администратора
/remove_admin @username - удалить администратора
/reset - сбросить счетчик открутки (только @MaksimXyila)
/whoami - показать информацию о себе

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

Администраторы по умолчанию: @MaksimXyila @ar_got"""
    
    await update.message.reply_text(help_text)

async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о текущем пользователе"""
    user = update.effective_user
    
    if not user:
        await update.message.reply_text("Не удалось определить пользователя")
        return
    
    username = f"@{user.username}" if user.username else "Нет юзернейма"
    user_id = user.id
    full_name = user.full_name
    
    # Проверяем права
    is_admin = await check_admin(update)
    is_super_admin = await check_super_admin(update)
    
    status = "👑 Суперадмин" if is_super_admin else "🔑 Администратор" if is_admin else "👤 Обычный пользователь"
    
    info_message = (
        f"👤 Информация о вас:\n\n"
        f"Имя: {full_name}\n"
        f"Юзернейм: {username}\n"
        f"ID: {user_id}\n"
        f"Статус: {status}\n\n"
    )
    
    if is_admin:
        info_message += "✅ Вы можете использовать команды бота"
    else:
        info_message += "❌ У вас нет прав для использования команд бота"
    
    await update.message.reply_text(info_message)

async def rub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rub"""
    if not await check_admin(update):
        await update.message.reply_text("❌ У вас нет прав для использования этой команды")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /rub [сумма]\nПример: /rub 100000")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("Сумма должна быть положительным числом!")
            return
        
        bot_manager.set_total_amount(amount)
        await update.message.reply_text(f"✅ Общая сумма открутки установлена: ₽{amount:,}")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат суммы!")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /add_admin"""
    if not await check_super_admin(update):
        await update.message.reply_text("❌ Эта команда доступна только @MaksimXyila")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_admin @username")
        return
    
    new_admin = context.args[0]
    
    if bot_manager.add_admin(new_admin):
        await update.message.reply_text(f"✅ Администратор {new_admin} добавлен")
    else:
        await update.message.reply_text(f"❌ Администратор {new_admin} уже существует или неверный формат")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /remove_admin"""
    if not await check_super_admin(update):
        await update.message.reply_text("❌ Эта команда доступна только @MaksimXyila")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /remove_admin @username")
        return
    
    admin_to_remove = context.args[0]
    
    if bot_manager.is_super_admin(admin_to_remove):
        await update.message.reply_text("❌ Нельзя удалить суперадмина!")
        return
    
    if bot_manager.remove_admin(admin_to_remove):
        await update.message.reply_text(f"✅ Администратор {admin_to_remove} удален")
    else:
        await update.message.reply_text(f"❌ Администратор {admin_to_remove} не найден")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    if not await check_admin(update):
        await update.message.reply_text("❌ У вас нет прав для использования этой команды")
        return
    
    stats_message = bot_manager.get_stats_message()
    await update.message.reply_text(stats_message)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    if not await check_super_admin(update):
        await update.message.reply_text("❌ Эта команда доступна только @MaksimXyila")
        return
    
    bot_manager.reset_stats()
    await update.message.reply_text("✅ Счетчик открутки сброшен")

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    if not await check_admin(update):
        # Логируем сообщения от не-админов
        user = update.effective_user
        if user:
            logger.info(f"Игнорируем сообщение от не-админа: {user.username} - {update.message.text[:50]}")
        return
    
    message_text = update.message.text.strip()
    
    # Добавление дропа
    if message_text.lower().startswith('дроп '):
        parts = message_text.split()
        if len(parts) == 2 and (parts[1].startswith('@') or parts[1]):
            username = update.effective_user.username
            added_by = f"@{username}" if username else "Неизвестно"
            
            if bot_manager.add_drop(parts[1], added_by):
                await update.message.reply_text("👌")
            else:
                await update.message.reply_text("❌ Этот дроп уже добавлен")
        return
    
    # Активация дропа
    if message_text in ACTIVATION_KEYWORDS:
        drops = bot_manager.drops.get("drops", {})
        for drop_username, drop_info in drops.items():
            if drop_info.get("status") == DropStatus.WELCOMED.value:
                bot_manager.update_drop_status(drop_username, DropStatus.ACTIVE)
                
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
                break
        return
    
    # Обработка сумм
    if re.match(SUM_PATTERN, message_text):
        try:
            amount = int(message_text.strip('!'))
            if amount > 0:
                bot_manager.last_sum = amount
                logger.info(f"Получена сумма: {amount}, ждем email")
        except ValueError:
            pass
        return
    
    # Обработка email
    if re.match(EMAIL_PATTERN, message_text) and bot_manager.last_sum is not None:
        if bot_manager.stats.get("remaining_amount", 0) >= bot_manager.last_sum:
            bot_manager.process_transaction(bot_manager.last_sum, message_text)
            
            response = (
                f"✅ Откручено ₽{bot_manager.last_sum:,}/"
                f"Осталось ₽{bot_manager.stats.get('remaining_amount', 0):,}"
            )
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(
                f"❌ Недостаточно средств! Остаток: ₽{bot_manager.stats.get('remaining_amount', 0):,}"
            )
        
        bot_manager.last_sum = None
        return

# Новые участники
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников чата"""
    if not update.message or not update.message.new_chat_members:
        return
    
    logger.info(f"Новые участники: {[user.username for user in update.message.new_chat_members]}")
    
    for new_member in update.message.new_chat_members:
        if new_member.username:
            username = f"@{new_member.username}"
            drops = bot_manager.drops.get("drops", {})
            
            logger.info(f"Проверяем является ли {username} дропом...")
            logger.info(f"Текущие дропы: {list(drops.keys())}")
            
            if username in drops and not drops[username].get("welcomed", False):
                welcome_message = (
                    f"Привет, {username}, заполни анкету:\n"
                    "1. ФИО:\n"
                    "2. Номер карты:\n"
                    "3. Номер счета:\n"
                    "4. Номер телефона:\n"
                    "Скриншот трат за Ноябрь/Декабрь."
                )
                
                try:
                    sent_message = await update.message.reply_text(welcome_message)
                    await sent_message.pin(disable_notification=True)
                    logger.info(f"Отправлено приветствие для дропа {username}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке приветствия: {e}")
                
                bot_manager.update_drop_status(username, DropStatus.WELCOMED)
                bot_manager.drops["drops"][username]["welcomed"] = True
                bot_manager.save_data(DROPS_FILE, bot_manager.drops)
            else:
                logger.info(f"{username} не является дропом или уже приветствован")

def main():
    """Основная функция запуска бота"""
    # Записываем информацию о запуске
    logger.info("=" * 50)
    logger.info("БОТ ЗАПУЩЕН")
    logger.info(f"Токен: {TOKEN[:10]}...")
    logger.info(f"Суперадмин: {SUPER_ADMIN}")
    logger.info(f"Админы по умолчанию: {bot_manager.admins.get('admins', [])}")
    logger.info("=" * 50)
    
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("whoami", whoami_command))
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
    logger.info("Бот запущен и ожидает сообщений...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
