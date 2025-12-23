import json
import logging
import re
import os
from datetime import datetime
from typing import Dict, Optional
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
    COMPLETED = "завершен"

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
        
        logger.info(f"Загруженные администраторы: {self.admins.get('admins', [])}")
    
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
                    return data
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")
        
        return default_data or {}
    
    def save_data(self, filename: str, data: dict):
        """Сохраняет данные в JSON файл"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения {filename}: {e}")
    
    def normalize_username(self, username: str) -> str:
        """Нормализует юзернейм"""
        if not username:
            return ""
        
        username = username.strip().lower()
        
        if not username.startswith('@'):
            username = f"@{username}"
        
        return username
    
    def is_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь администратором"""
        if not username:
            return False
        
        normalized = self.normalize_username(username)
        admins_list = [self.normalize_username(admin) for admin in self.admins.get("admins", [])]
        
        return normalized in admins_list
    
    def is_super_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь суперадмином"""
        if not username:
            return False
        
        normalized = self.normalize_username(username)
        super_admin = self.normalize_username(self.admins.get("super_admin", ""))
        
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
                    "activated": False,
                    "active_drop": False,
                    "completed": False
                }
                
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
    
    def remove_drop(self, username: str) -> bool:
        """Удаляет дропа"""
        normalized = self.normalize_username(username)
        
        if normalized in self.drops.get("drops", {}):
            del self.drops["drops"][normalized]
            
            self.drops["statistics"].append({
                "type": "Удаление",
                "username": normalized,
                "date": datetime.now().isoformat(),
                "action": "удален"
            })
            
            self.save_data(DROPS_FILE, self.drops)
            logger.info(f"Удален дроп: {normalized}")
            return True
        return False
    
    def reset_all_drops(self):
        """Сбрасывает всех дропов"""
        drops_count = len(self.drops.get("drops", {}))
        
        self.drops["drops"] = {}
        self.drops["statistics"].append({
            "type": "Сброс",
            "date": datetime.now().isoformat(),
            "action": "сброшены все дропы",
            "count": drops_count
        })
        
        self.save_data(DROPS_FILE, self.drops)
        logger.info(f"Сброшены все дропы (было: {drops_count})")
        return drops_count
    
    def update_drop_status(self, username: str, status: DropStatus):
        """Обновляет статус дропа"""
        normalized = self.normalize_username(username)
        
        if normalized in self.drops.get("drops", {}):
            self.drops["drops"][normalized]["status"] = status.value
            
            if status == DropStatus.ACTIVE:
                self.drops["drops"][normalized]["activated"] = True
                self.drops["drops"][normalized]["activation_date"] = datetime.now().isoformat()
            elif status == DropStatus.COMPLETED:
                self.drops["drops"][normalized]["completed"] = True
                self.drops["drops"][normalized]["completion_date"] = datetime.now().isoformat()
            
            self.save_data(DROPS_FILE, self.drops)
    
    def set_active_drop(self, username: str):
        """Устанавливает активного дропа"""
        normalized = self.normalize_username(username)
        
        for drop in self.drops.get("drops", {}).values():
            drop["active_drop"] = False
        
        if normalized in self.drops.get("drops", {}):
            self.drops["drops"][normalized]["active_drop"] = True
            self.save_data(DROPS_FILE, self.drops)
            logger.info(f"Установлен активный дроп: {normalized}")
    
    def get_active_drop(self) -> Optional[str]:
        """Получает активного дропа"""
        for username, drop_info in self.drops.get("drops", {}).items():
            if drop_info.get("active_drop"):
                return username
        return None
    
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
        msg = "СТАТИСТИКА ОТКРУТКИ И ДРОПОВ\n\n"
        
        msg += f"ОТКРУТКА:\n"
        msg += f"Общая сумма: ₽{self.stats.get('total_amount', 0):,}\n"
        msg += f"Откручено: ₽{self.stats.get('spent_amount', 0):,}\n"
        msg += f"Осталось: ₽{self.stats.get('remaining_amount', 0):,}\n\n"
        
        drops = self.drops.get("drops", {})
        active_drop = self.get_active_drop()
        
        msg += f"ДРОПОВ ВСЕГО: {len(drops)}\n"
        msg += f"АКТИВНЫЙ ДРОП: {active_drop if active_drop else 'нет'}\n\n"
        
        msg += "СПИСОК ДРОПОВ:\n"
        if drops:
            for drop_username, drop_info in drops.items():
                status = drop_info.get("status", "неизвестно")
                active = " (активный)" if drop_info.get("active_drop") else ""
                
                msg += f"{drop_username}: {status}{active}\n"
                msg += f"Добавлен: {drop_info.get('added_by', 'неизвестно')}\n"
                
                if drop_info.get('activation_date'):
                    msg += f"Активирован: {drop_info['activation_date'][:10]}\n"
                msg += "\n"
        else:
            msg += "Нет добавленных дропов\n\n"
        
        msg += "АДМИНИСТРАТОРЫ:\n"
        admins_list = self.admins.get("admins", [])
        for admin in admins_list:
            if self.is_super_admin(admin):
                msg += f"{admin} (суперадмин)\n"
            else:
                msg += f"{admin}\n"
        
        return msg

# Инициализация менеджера
bot_manager = BotManager()

async def check_admin(update: Update) -> bool:
    """Проверяет права администратора для группового чата"""
    user = update.effective_user
    if not user or not user.username:
        return False
    
    username = f"@{user.username}"
    return bot_manager.is_admin(username)

async def check_super_admin(update: Update) -> bool:
    """Проверяет права суперадмина для группового чата"""
    user = update.effective_user
    if not user or not user.username:
        return False
    
    username = f"@{user.username}"
    return bot_manager.is_super_admin(username)

# Функция для калькулятора
def calculate_expression(expression: str) -> Optional[float]:
    """Вычисляет математическое выражение"""
    try:
        expression = expression.strip().replace(' ', '')
        
        if not re.match(r'^[\d\+\-\*\/\.\(\)]+$', expression):
            return None
        
        result = eval(expression, {"__builtins__": {}}, {})
        
        if isinstance(result, (int, float)):
            return result
        
    except Exception:
        return None
    
    return None

# Команды для группового чата
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    chat_type = update.effective_chat.type
    logger.info(f"Команда /start от {user.username} в чате типа: {chat_type}")
    
    await update.message.reply_text(
        "Бот для управления откруткой и дропами активирован.\n"
        "Используйте /help для просмотра команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    logger.info(f"Команда /help от {update.effective_user.username}")
    
    help_text = """БОТ ДЛЯ УПРАВЛЕНИЯ ОТКРУТКОЙ И ДРОПАМИ

ОСНОВНЫЕ КОМАНДЫ:

/rub [сумма] - установить общую сумму для открутки
/stats - статистика по открутке и дропам
/add_admin @username - добавить администратора
/remove_admin @username - удалить администратора
/reset - сбросить счетчик открутки
/reset_drops - сбросить всех дропов
/remove_drop @username - удалить конкретного дропа
/drop - инструкция для дропов
/ask @username - отправить инструкцию дропу

СИСТЕМА ОТКРУТКИ:
1. Установите общую сумму: /rub 100000
2. Отправляйте суммы в формате: 9500! или !9500
3. Сразу после суммы отправьте email: sir+123456@outluk.ru
4. Бот автоматически посчитает остаток

УПРАВЛЕНИЕ ДРОПАМИ:
1. Добавить дропа: отправьте "дроп @username"
2. Когда дроп зайдет в группу - бот отправит анкету
3. После заполнения анкеты отправьте: "Подключаю" (или аналоги)
4. Бот отправит финальную инструкцию дропу

КАЛЬКУЛЯТОР:
Напишите математическое выражение: 100+200, 500/2, 1000*0.1

КЛЮЧЕВЫЕ СЛОВА ДЛЯ АКТИВАЦИИ ДРОПА:
Подключаю, подключаю, Щас подключу, щас подключу, Щас подключат, Ждем подключения

ВНИМАНИЕ:
- Бот работает только с администраторами
- Суммы считаются только в указанных форматах
- Email должен быть строго в формате sir+[цифры]@outluk.ru
- Права админа выдаются только по юзернейму

Администраторы по умолчанию: @MaksimXyila @ar_got"""
    
    await update.message.reply_text(help_text)

async def drop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инструкция для дропов"""
    logger.info(f"Команда /drop от {update.effective_user.username}")
    
    instruction = """ИНСТРУКЦИЯ ДЛЯ ДРОПОВ:

1. Отправь свои данные (ФИО, карта, счет, телефон)
2. Жди ответа от администратора
3. После поступления перевода отправь скрин истории операций в чат
4. Администратор отправит реквизиты для перевода
5. Введи данные для перевода (номер телефона - проверь чтобы был правильный)
6. Отправь скрин и жди одобрения администрации (без одобрения не переводить!)
7. После одобрения жди когда тебе скинут почту для отправки чека
8. Отправь квитанцию на указанную почту"""
    
    await update.message.reply_text(instruction)

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет инструкцию конкретному дропу"""
    logger.info(f"Команда /ask от {update.effective_user.username}")
    
    if not await check_admin(update):
        await update.message.reply_text("У вас нет прав для использования этой команды")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /ask @username")
        return
    
    username = context.args[0]
    
    instruction = f"""{username} - Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.

Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.

После перевода отправляешь квитанцию на указанную почту."""
    
    await update.message.reply_text(instruction)
    logger.info(f"Отправлена инструкция дропу {username}")

async def rub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rub"""
    logger.info(f"Команда /rub от {update.effective_user.username}")
    
    if not await check_admin(update):
        await update.message.reply_text("У вас нет прав для использования этой команды")
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
        await update.message.reply_text(f"Общая сумма открутки установлена: ₽{amount:,}")
    except ValueError:
        await update.message.reply_text("Неверный формат суммы!")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /add_admin"""
    logger.info(f"Команда /add_admin от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только @MaksimXyila")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /add_admin @username")
        return
    
    new_admin = context.args[0]
    
    if bot_manager.add_admin(new_admin):
        await update.message.reply_text(f"Администратор {new_admin} добавлен")
    else:
        await update.message.reply_text(f"Администратор {new_admin} уже существует или неверный формат")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /remove_admin"""
    logger.info(f"Команда /remove_admin от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только @MaksimXyila")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /remove_admin @username")
        return
    
    admin_to_remove = context.args[0]
    
    if bot_manager.is_super_admin(admin_to_remove):
        await update.message.reply_text("Нельзя удалить суперадмина!")
        return
    
    if bot_manager.remove_admin(admin_to_remove):
        await update.message.reply_text(f"Администратор {admin_to_remove} удален")
    else:
        await update.message.reply_text(f"Администратор {admin_to_remove} не найден")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    logger.info(f"Команда /stats от {update.effective_user.username}")
    
    if not await check_admin(update):
        await update.message.reply_text("У вас нет прав для использования этой команды")
        return
    
    stats_message = bot_manager.get_stats_message()
    await update.message.reply_text(stats_message)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    logger.info(f"Команда /reset от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только @MaksimXyila")
        return
    
    bot_manager.reset_stats()
    await update.message.reply_text("Счетчик открутки сброшен")

async def reset_drops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset_drops"""
    logger.info(f"Команда /reset_drops от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только @MaksimXyila")
        return
    
    count = bot_manager.reset_all_drops()
    await update.message.reply_text(f"Все дропы сброшены. Удалено: {count}")

async def remove_drop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /remove_drop"""
    logger.info(f"Команда /remove_drop от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только @MaksimXyila")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /remove_drop @username")
        return
    
    drop_username = context.args[0]
    
    if bot_manager.remove_drop(drop_username):
        await update.message.reply_text(f"Дроп {drop_username} удален")
    else:
        await update.message.reply_text(f"Дроп {drop_username} не найден")

# Обработка текстовых сообщений в группе
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений в группе"""
    user = update.effective_user
    message_text = update.message.text.strip()
    chat_type = update.effective_chat.type
    
    if not user or not user.username:
        return
    
    username = f"@{user.username}"
    logger.info(f"Сообщение от {username} в {chat_type}: {message_text[:50]}")
    
    # 1. Сначала проверяем калькулятор (работает для всех)
    if re.match(r'^\d+[\+\-\*\/]\d+$', message_text.replace(' ', '')):
        result = calculate_expression(message_text)
        if result is not None:
            if result.is_integer():
                result_str = str(int(result))
            else:
                result_str = str(result)
            
            await update.message.reply_text(f"= {result_str}")
            return
    
    # 2. Проверяем права администратора для остальных функций
    if not bot_manager.is_admin(username):
        logger.info(f"Пользователь {username} не является администратором")
        return
    
    # 3. Добавление дропа
    if message_text.lower().startswith('дроп '):
        parts = message_text.split()
        if len(parts) == 2 and (parts[1].startswith('@') or parts[1]):
            if bot_manager.add_drop(parts[1], username):
                await update.message.reply_text("Дроп добавлен")
                logger.info(f"Добавлен дроп {parts[1]} пользователем {username}")
            else:
                await update.message.reply_text("Этот дроп уже добавлен")
        return
    
    # 4. Активация дропа
    if message_text in ACTIVATION_KEYWORDS:
        logger.info(f"Получено ключевое слово активации: {message_text}")
        drops = bot_manager.drops.get("drops", {})
        
        # Ищем дропа со статусом "приветствован"
        target_drop = None
        for drop_username, drop_info in drops.items():
            if drop_info.get("status") == DropStatus.WELCOMED.value:
                target_drop = drop_username
                break
        
        if target_drop:
            bot_manager.update_drop_status(target_drop, DropStatus.ACTIVE)
            logger.info(f"Активирован дроп {target_drop}")
            
            instruction = f"""{target_drop} - Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.

Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.

После перевода отправляешь квитанцию на указанную почту."""
            
            await update.message.reply_text(instruction)
        else:
            logger.info("Не найден дроп для активации")
        return
    
    # 5. Обработка сумм для открутки
    if re.match(SUM_PATTERN, message_text):
        try:
            amount = int(message_text.strip('!'))
            if amount > 0:
                bot_manager.last_sum = amount
                logger.info(f"Получена сумма для открутки: {amount}")
        except ValueError:
            pass
        return
    
    # 6. Обработка email для открутки
    if re.match(EMAIL_PATTERN, message_text) and bot_manager.last_sum is not None:
        if bot_manager.stats.get("remaining_amount", 0) >= bot_manager.last_sum:
            bot_manager.process_transaction(bot_manager.last_sum, message_text)
            
            response = (
                f"Откручено ₽{bot_manager.last_sum:,}/"
                f"Осталось ₽{bot_manager.stats.get('remaining_amount', 0):,}"
            )
            await update.message.reply_text(response)
            logger.info(f"Обработана открутка: {bot_manager.last_sum}")
        else:
            await update.message.reply_text(
                f"Недостаточно средств! Остаток: ₽{bot_manager.stats.get('remaining_amount', 0):,}"
            )
        
        bot_manager.last_sum = None
        return

# Обработка новых участников
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников чата"""
    if not update.message or not update.message.new_chat_members:
        return
    
    logger.info(f"Новые участники: {[user.username for user in update.message.new_chat_members]}")
    
    for new_member in update.message.new_chat_members:
        if new_member.username:
            username = f"@{new_member.username}"
            drops = bot_manager.drops.get("drops", {})
            
            if username in drops and not drops[username].get("welcomed", False):
                welcome_message = f"""Привет, {username}, заполни анкету:
1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
Скриншот трат за Ноябрь/Декабрь."""
                
                try:
                    sent_message = await update.message.reply_text(welcome_message)
                    await sent_message.pin(disable_notification=True)
                    logger.info(f"Отправлено приветствие для дропа {username}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке приветствия: {e}")
                
                bot_manager.update_drop_status(username, DropStatus.WELCOMED)
                bot_manager.drops["drops"][username]["welcomed"] = True
                bot_manager.save_data(DROPS_FILE, bot_manager.drops)

def main():
    """Основная функция запуска бота"""
    logger.info("=" * 50)
    logger.info("БОТ ЗАПУЩЕН ДЛЯ РАБОТЫ В ГРУППАХ")
    logger.info(f"Суперадмин: {SUPER_ADMIN}")
    logger.info(f"Админы по умолчанию: {bot_manager.admins.get('admins', [])}")
    logger.info("=" * 50)
    
    # Создаем приложение с настройками для групп
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    command_handlers = [
        ("start", start_command),
        ("help", help_command),
        ("drop", drop_command),
        ("ask", ask_command),
        ("rub", rub_command),
        ("stats", stats_command),
        ("reset", reset_command),
        ("add_admin", add_admin_command),
        ("remove_admin", remove_admin_command),
        ("reset_drops", reset_drops_command),
        ("remove_drop", remove_drop_command),
    ]
    
    for command, handler in command_handlers:
        application.add_handler(CommandHandler(command, handler))
    
    # Обработка новых участников
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    
    # Обработка текстовых сообщений (фильтр для групповых чатов)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_text_message
    ))
    
    # Запуск бота
    logger.info("Бот запущен для работы в групповых чатах...")
    logger.info("Ожидаю сообщения в группах...")
    
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=0.5
        )
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()
