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
SUPER_ADMINS = ["@MaksimXyila", "@ar_got"]
EMAIL_PATTERN = r"sir\+\d+@outluk\.ru"
SUM_PATTERN = r"^(!\d+|\d+!)$"
ACTIVATION_KEYWORDS = [
    "Подключаю", "подключаю", 
    "Щас подключу", "щас подключу", 
    "Щас подключат", "Ждем подключения"
]

# Триггеры на слова с ответами
TRIGGER_WORDS = {
    r'\bблять\b': 'соси хуй',
    r'\bдолбаеб\b': 'твой батя',
    r'\bишак\b': 'ишаков только ебут',
    r'\bджаляб\b': 'котакбас блять',
}

# Слова для проверки баланса агентов
BALANCE_WORDS = [
    "бал", "баланс", "балик", "скок бал", "какой бал", 
    "какой баланс", "сколько бал", "сколько балик", "сколько баланс"
]

# Директория для данных
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# JSON файлы для хранения данных
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
AGENTS_FILE = os.path.join(DATA_DIR, "agents.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")

class AgentStatus(Enum):
    ADDED = "добавлен"
    WELCOMED = "приветствован"
    ACTIVE = "активен"
    COMPLETED = "завершен"

class BotManager:
    """Менеджер для работы с данными бота"""
    
    def __init__(self):
        self.admins = self.load_data(ADMINS_FILE, self.get_default_admins())
        self.agents = self.load_data(AGENTS_FILE, {"agents": {}, "statistics": []})
        self.stats = self.load_data(STATS_FILE, {
            "total_amount": 0,
            "spent_amount": 0,
            "remaining_amount": 0,
            "transactions": []
        })
        self.notes = self.load_data(NOTES_FILE, {"notes": []})
        self.last_sum = None
        
        logger.info(f"Загруженные администраторы: {self.admins.get('admins', [])}")
    
    @staticmethod
    def get_default_admins():
        return {
            "super_admins": SUPER_ADMINS,
            "admins": SUPER_ADMINS.copy(),
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
        super_admins_list = [self.normalize_username(admin) for admin in self.admins.get("super_admins", SUPER_ADMINS)]
        
        return normalized in super_admins_list
    
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
    
    def add_agent(self, username: str, added_by: str) -> bool:
        """Добавляет агента"""
        normalized = self.normalize_username(username)
        added_by_normalized = self.normalize_username(added_by)
        
        if normalized:
            if "agents" not in self.agents:
                self.agents["agents"] = {}
            
            if normalized not in self.agents["agents"]:
                self.agents["agents"][normalized] = {
                    "status": AgentStatus.ADDED.value,
                    "added_by": added_by_normalized,
                    "added_date": datetime.now().isoformat(),
                    "welcomed": False,
                    "activated": False,
                    "active_agent": False,
                    "completed": False,
                    "in_chat": False,
                    "has_received_questionnaire": False,
                    "last_balance_response": None,
                    "balance_amount": 0
                }
                
                if "statistics" not in self.agents:
                    self.agents["statistics"] = []
                
                self.agents["statistics"].append({
                    "type": "Добавление",
                    "username": normalized,
                    "date": datetime.now().isoformat(),
                    "added_by": added_by_normalized
                })
                
                self.save_data(AGENTS_FILE, self.agents)
                logger.info(f"Добавлен агент: {normalized} от {added_by_normalized}")
                return True
        return False
    
    def mark_agent_in_chat(self, username: str) -> bool:
        """Отмечает, что агент находится в чате"""
        normalized = self.normalize_username(username)
        
        if normalized in self.agents.get("agents", {}):
            self.agents["agents"][normalized]["in_chat"] = True
            self.save_data(AGENTS_FILE, self.agents)
            logger.info(f"Агент {normalized} отмечен как находящийся в чате")
            return True
        return False
    
    def send_questionnaire_to_existing_agent(self, username: str) -> bool:
        """Отправляет анкету существующему агенту в чате"""
        normalized = self.normalize_username(username)
        
        if normalized in self.agents.get("agents", {}):
            agent_info = self.agents["agents"][normalized]
            
            # Если агент в чате и еще не получал анкету
            if agent_info.get("in_chat") and not agent_info.get("has_received_questionnaire"):
                agent_info["has_received_questionnaire"] = True
                agent_info["status"] = AgentStatus.WELCOMED.value
                agent_info["welcomed"] = True
                
                self.save_data(AGENTS_FILE, self.agents)
                logger.info(f"Отправлена анкета существующему агенту в чате: {normalized}")
                return True
        
        return False
    
    def activate_existing_agent(self, username: str) -> bool:
        """Активирует существующего агента в чате"""
        normalized = self.normalize_username(username)
        
        if normalized in self.agents.get("agents", {}):
            agent_info = self.agents["agents"][normalized]
            
            # Если агент уже в чате, активируем его
            if agent_info.get("in_chat") or agent_info.get("welcomed"):
                agent_info["status"] = AgentStatus.ACTIVE.value
                agent_info["activated"] = True
                agent_info["activation_date"] = datetime.now().isoformat()
                agent_info["active_agent"] = True
                
                self.save_data(AGENTS_FILE, self.agents)
                logger.info(f"Активирован существующий агент в чате: {normalized}")
                return True
        
        return False
    
    def remove_agent(self, username: str) -> bool:
        """Удаляет агента"""
        normalized = self.normalize_username(username)
        
        if normalized in self.agents.get("agents", {}):
            del self.agents["agents"][normalized]
            
            self.agents["statistics"].append({
                "type": "Удаление",
                "username": normalized,
                "date": datetime.now().isoformat(),
                "action": "удален"
            })
            
            self.save_data(AGENTS_FILE, self.agents)
            logger.info(f"Удален агент: {normalized}")
            return True
        return False
    
    def reset_all_agents(self):
        """Сбрасывает всех агентов"""
        agents_count = len(self.agents.get("agents", {}))
        
        self.agents["agents"] = {}
        self.agents["statistics"].append({
            "type": "Сброс",
            "date": datetime.now().isoformat(),
            "action": "сброшены все агенты",
            "count": agents_count
        })
        
        self.save_data(AGENTS_FILE, self.agents)
        logger.info(f"Сброшены все агенты (было: {agents_count})")
        return agents_count
    
    def update_agent_status(self, username: str, status: AgentStatus):
        """Обновляет статус агента"""
        normalized = self.normalize_username(username)
        
        if normalized in self.agents.get("agents", {}):
            self.agents["agents"][normalized]["status"] = status.value
            
            if status == AgentStatus.ACTIVE:
                self.agents["agents"][normalized]["activated"] = True
                self.agents["agents"][normalized]["activation_date"] = datetime.now().isoformat()
            elif status == AgentStatus.COMPLETED:
                self.agents["agents"][normalized]["completed"] = True
                self.agents["agents"][normalized]["completion_date"] = datetime.now().isoformat()
            
            self.save_data(AGENTS_FILE, self.agents)
    
    def set_active_agent(self, username: str):
        """Устанавливает активного агента"""
        normalized = self.normalize_username(username)
        
        for agent in self.agents.get("agents", {}).values():
            agent["active_agent"] = False
        
        if normalized in self.agents.get("agents", {}):
            self.agents["agents"][normalized]["active_agent"] = True
            self.save_data(AGENTS_FILE, self.agents)
            logger.info(f"Установлен активный агент: {normalized}")
    
    def get_active_agent(self) -> Optional[str]:
        """Получает активного агента"""
        for username, agent_info in self.agents.get("agents", {}).items():
            if agent_info.get("active_agent"):
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
    
    def process_agent_balance(self, agent_username: str, amount: int, sender_info: str):
        """Обрабатывает баланс от агента"""
        normalized = self.normalize_username(agent_username)
        
        if normalized in self.agents.get("agents", {}):
            self.agents["agents"][normalized]["last_balance_response"] = datetime.now().isoformat()
            self.agents["agents"][normalized]["balance_amount"] = amount
            
            # Добавляем в статистику открутки
            self.stats["spent_amount"] += amount
            self.stats["remaining_amount"] -= amount
            
            transaction = {
                "amount": amount,
                "type": "agent_balance",
                "agent": normalized,
                "sender_info": sender_info,
                "date": datetime.now().isoformat()
            }
            
            if "transactions" not in self.stats:
                self.stats["transactions"] = []
            
            self.stats["transactions"].append(transaction)
            self.save_data(STATS_FILE, self.stats)
            self.save_data(AGENTS_FILE, self.agents)
            
            logger.info(f"Обработан баланс агента {normalized}: {amount} руб, отправитель: {sender_info}")
            return True
        
        return False
    
    def reset_stats(self):
        """Сбрасывает статистику открутки"""
        self.stats["spent_amount"] = 0
        self.stats["remaining_amount"] = self.stats.get("total_amount", 0)
        self.stats["transactions"] = []
        self.save_data(STATS_FILE, self.stats)
        logger.info("Статистика открутки сброшена")
    
    def add_note(self, note_text: str, added_by: str):
        """Добавляет заметку"""
        if "notes" not in self.notes:
            self.notes["notes"] = []
        
        note = {
            "text": note_text,
            "added_by": added_by,
            "date": datetime.now().isoformat()
        }
        
        self.notes["notes"].append(note)
        self.save_data(NOTES_FILE, self.notes)
        logger.info(f"Добавлена заметка от {added_by}: {note_text[:50]}...")
    
    def get_notes_message(self) -> str:
        """Формирует сообщение со списком заметок"""
        notes = self.notes.get("notes", [])
        
        if not notes:
            return "Нет заметок"
        
        msg = "Список заметок:\n\n"
        
        for i, note in enumerate(notes[-10:], 1):  # Показываем последние 10 заметок
            msg += f"{i}. {note['text']}\n"
            msg += f"   Добавлено: {note['added_by']} ({note['date'][:10]})\n\n"
        
        return msg
    
    def get_stats_message(self) -> str:
        """Формирует сообщение со статистикой"""
        msg = "Статистика открутки и агентов\n\n"
        
        msg += f"Открутка:\n"
        msg += f"Общая сумма: ₽{self.stats.get('total_amount', 0):,}\n"
        msg += f"Откручено: ₽{self.stats.get('spent_amount', 0):,}\n"
        msg += f"Осталось: ₽{self.stats.get('remaining_amount', 0):,}\n\n"
        
        # Последние транзакции
        transactions = self.stats.get("transactions", [])
        if transactions:
            msg += "Последние операции:\n"
            for tx in transactions[-5:]:  # Последние 5 операций
                if tx.get("type") == "agent_balance":
                    msg += f"• Агент {tx.get('agent', 'неизвестно')}: ₽{tx.get('amount', 0):,}\n"
                else:
                    msg += f"• Открутка: ₽{tx.get('amount', 0):,}\n"
            msg += "\n"
        
        agents = self.agents.get("agents", {})
        active_agent = self.get_active_agent()
        
        msg += f"Агентов всего: {len(agents)}\n"
        msg += f"Активный агент: {active_agent if active_agent else 'нет'}\n\n"
        
        msg += "Список агентов:\n"
        if agents:
            for agent_username, agent_info in agents.items():
                status = agent_info.get("status", "неизвестно")
                active = " (активный)" if agent_info.get("active_agent") else ""
                in_chat = " (в чате)" if agent_info.get("in_chat") else ""
                
                msg += f"{agent_username}: {status}{active}{in_chat}\n"
                msg += f"Добавлен: {agent_info.get('added_by', 'неизвестно')}\n"
                
                balance = agent_info.get("balance_amount", 0)
                if balance > 0:
                    msg += f"Последний баланс: ₽{balance:,}\n"
                
                if agent_info.get('activation_date'):
                    msg += f"Активирован: {agent_info['activation_date'][:10]}\n"
                msg += "\n"
        else:
            msg += "Нет добавленных агентов\n\n"
        
        msg += "Администраторы:\n"
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
        # Убираем пробелы
        expression = expression.strip().replace(' ', '')
        
        # Проверяем, что выражение безопасное
        if not re.match(r'^[\d\+\-\*\/\.]+$', expression):
            return None
        
        # Используем безопасное вычисление
        result = eval(expression, {"__builtins__": {}}, {})
        
        if isinstance(result, (int, float)):
            return result
        
    except Exception as e:
        logger.error(f"Ошибка вычисления выражения {expression}: {e}")
        return None
    
    return None

# Функция для проверки триггерных слов
def check_trigger_words(text: str) -> Optional[str]:
    """Проверяет триггерные слова и возвращает ответ"""
    text_lower = text.lower()
    
    for pattern, response in TRIGGER_WORDS.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            return response
    
    return None

# Функция для проверки слов о балансе
def is_balance_question(text: str) -> bool:
    """Проверяет, является ли сообщение вопросом о балансе"""
    text_lower = text.lower().strip()
    
    for word in BALANCE_WORDS:
        if word in text_lower:
            return True
    
    return False

# Функция для извлечения суммы из сообщения агента
def extract_amount_from_message(text: str) -> Optional[int]:
    """Извлекает сумму из сообщения агента"""
    try:
        # Ищем числа в тексте
        numbers = re.findall(r'\d+', text)
        
        if numbers:
            # Берем первое найденное число
            amount = int(numbers[0])
            
            # Проверяем, что сумма разумная (от 100 до 1_000_000)
            if 100 <= amount <= 1_000_000:
                return amount
        
        return None
    except Exception as e:
        logger.error(f"Ошибка извлечения суммы: {e}")
        return None

# Функция для извлечения информации об отправителе
def extract_sender_info(text: str) -> str:
    """Извлекает информацию об отправителе (телефон или карта)"""
    # Ищем номер телефона
    phone_match = re.search(r'\+7\d{10}|\+7\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2}', text)
    if phone_match:
        return phone_match.group(0)
    
    # Ищем номер карты (16 или 18 цифр)
    card_match = re.search(r'\d{16}|\d{18}', text)
    if card_match:
        return card_match.group(0)
    
    # Если ничего не нашли, возвращаем "неизвестно"
    return "неизвестно"

async def send_questionnaire(chat_id: int, username: str, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет анкету агенту"""
    welcome_message = f"""Привет, {username}, заполни анкету:
1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
Скриншот трат за Ноябрь/Декабрь.

Есть вопросы? Пропиши «хелп»"""
    
    try:
        sent_message = await context.bot.send_message(chat_id=chat_id, text=welcome_message)
        await sent_message.pin(disable_notification=True)
        logger.info(f"Отправлена анкета агенту {username}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке анкеты: {e}")
        return False

async def send_questionnaire_to_user(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет анкету пользователю (команда 'анкета')"""
    questionnaire_message = """Заполни анкету:
1. ФИО:
2. Номер карты:
3. Номер счета:
4. Номер телефона:
Скриншот трат за Ноябрь/Декабрь.

Есть вопросы? Пропиши «хелп»"""
    
    try:
        await context.bot.send_message(chat_id=chat_id, text=questionnaire_message)
        logger.info(f"Отправлена анкета по запросу")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке анкеты: {e}")
        return False

# Команды для группового чата
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    chat_type = update.effective_chat.type
    logger.info(f"Команда /start от {user.username} в чате типа: {chat_type}")
    
    await update.message.reply_text(
        "Бот для управления откруткой и агентами активирован.\n"
        "Используйте /help для просмотра команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help - доступна всем"""
    logger.info(f"Команда /help от {update.effective_user.username}")
    
    help_text = """Бот для управления откруткой и агентами

Основные команды:

/rub [сумма] - установить общую сумму для открутки
/stats - статистика по открутке и агентам
/notes - список заметок
/add_admin @username - добавить администратора
/remove_admin @username - удалить администратора
/reset - сбросить счетчик открутки
/reset_agents - сбросить всех агентов
/remove_agent @username - удалить конкретного агента
/agent - инструкция для агентов

Система открутки:
1. Установите общую сумму: /rub 100000
2. Отправляйте суммы в формате: 9500! или !9500
3. Сразу после суммы отправьте email: sir+123456@outluk.ru
4. Бот автоматически посчитает остаток

Управление агентами:
1. Добавить агента: отправьте "агент @username"
2. Если агент уже в чате: отправьте "агент @username уже в чате"
3. Когда агент зайдет в группу - бот отправит анкету
4. После заполнения анкеты отправьте: "Подключаю" (или аналоги)
5. Бот отправит финальную инструкцию агенту

Калькулятор:
Напишите математическое выражение: 100+200, 500/2, 1000*0.1

Ключевые слова для активации агента:
Подключаю, подключаю, Щас подключу, щас подключу, Щас подключат, Ждем подключения

Для анкеты:
Напишите "анкета" для получения формы для заполнения

Для получения инструкции:
Напишите "хелп"

Внимание:
- Бот работает только с администраторами
- Суммы считаются только в указанных форматах
- Email должен быть строго в формате sir+[цифры]@outluk.ru
- Права админа выдаются только по юзернейму"""
    
    await update.message.reply_text(help_text)

async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инструкция для агентов"""
    logger.info(f"Команда /agent от {update.effective_user.username}")
    
    instruction = """Инструкция для агентов:

1. Отправь свои данные (ФИО, карта, счет, телефон)
2. Жди ответа от администратора
3. После поступления перевода отправь скрин истории операций в чат
4. Администратор отправит реквизиты для перевода
5. Введи данные для перевода (номер телефона - проверь чтобы был правильный)
6. Отправь скрин и жди одобрения администрации (без одобрения не переводить!)
7. После одобрения жди когда тебе скинут почту для отправки чека
8. Отправь квитанцию на указанную почту

Для получения анкеты пропишите «анкета»
Есть вопросы? Пропиши «хелп»"""
    
    await update.message.reply_text(instruction)

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список заметок"""
    logger.info(f"Команда /notes от {update.effective_user.username}")
    
    notes_message = bot_manager.get_notes_message()
    await update.message.reply_text(notes_message)

async def rub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rub"""
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
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
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
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
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
    if not await check_admin(update):
        await update.message.reply_text("У вас нет прав для использования этой команды")
        return
    
    stats_message = bot_manager.get_stats_message()
    await update.message.reply_text(stats_message)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
        return
    
    bot_manager.reset_stats()
    await update.message.reply_text("Счетчик открутки сброшен")

async def reset_agents_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset_agents"""
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
        return
    
    count = bot_manager.reset_all_agents()
    await update.message.reply_text(f"Все агенты сброшены. Удалено: {count}")

async def remove_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /remove_agent"""
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /remove_agent @username")
        return
    
    agent_username = context.args[0]
    
    if bot_manager.remove_agent(agent_username):
        await update.message.reply_text(f"Агент {agent_username} удален")
    else:
        await update.message.reply_text(f"Агент {agent_username} не найден")

# Обработка текстовых сообщений в группе
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений в группе"""
    user = update.effective_user
    message_text = update.message.text.strip()
    chat = update.effective_chat
    
    if not user or not user.username:
        return
    
    username = f"@{user.username}"
    logger.info(f"Сообщение от {username}: {message_text}")
    
    # 1. Проверяем триггерные слова (работает для всех)
    trigger_response = check_trigger_words(message_text)
    if trigger_response:
        await update.message.reply_text(trigger_response)
        return
    
    # 2. Проверяем слово "анкета" (работает для всех)
    if message_text.lower() == "анкета":
        await send_questionnaire_to_user(chat.id, context)
        return
    
    # 3. Проверяем слово "хелп" (работает для всех)
    if message_text.lower() == "хелп":
        instruction = f"""{username} - Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.

Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.

После перевода отправляешь квитанцию на указанную почту."""
        
        await update.message.reply_text(instruction)
        return
    
    # 4. Проверяем, является ли сообщение ответом агента на вопрос о балансе
    # Ищем, был ли предыдущий вопрос о балансе (это должен был быть админ)
    # Для простоты проверяем, является ли отправитель агентом
    agents = bot_manager.agents.get("agents", {})
    if username in agents:
        # Агент отправляет сообщение, проверяем, содержит ли оно сумму
        amount = extract_amount_from_message(message_text)
        if amount:
            # Извлекаем информацию об отправителе
            sender_info = extract_sender_info(message_text)
            
            # Обрабатываем баланс агента
            if bot_manager.process_agent_balance(username, amount, sender_info):
                # Формируем ответ с статистикой
                stats = bot_manager.stats
                response = (
                    f"Откручено ₽{amount:,}\n"
                    f"Откручено всего: ₽{stats.get('spent_amount', 0):,}\n"
                    f"Осталось: ₽{stats.get('remaining_amount', 0):,}"
                )
                await update.message.reply_text(response)
                logger.info(f"Обработан баланс агента {username}: {amount} руб")
            return
    
    # 5. Проверяем, является ли сообщение вопросом о балансе от админа
    if await check_admin(update) and is_balance_question(message_text):
        # Админ спрашивает о балансе - бот просто игнорирует, ждет ответа агента
        logger.info(f"Админ {username} спрашивает о балансе")
        return
    
    # 6. Проверяем калькулятор (работает для всех)
    calc_patterns = [
        r'^\s*\d+\s*\+\s*\d+\s*$',  # сложение
        r'^\s*\d+\s*\-\s*\d+\s*$',  # вычитание
        r'^\s*\d+\s*\*\s*\d+\s*$',  # умножение
        r'^\s*\d+\s*/\s*\d+\s*$',   # деление
    ]
    
    is_calc_expression = False
    for pattern in calc_patterns:
        if re.match(pattern, message_text):
            is_calc_expression = True
            break
    
    if is_calc_expression:
        logger.info(f"Обнаружено выражение калькулятора: {message_text}")
        result = calculate_expression(message_text)
        if result is not None:
            if result.is_integer():
                result_str = str(int(result))
            else:
                result_str = f"{result:.2f}".rstrip('0').rstrip('.')
            
            await update.message.reply_text(f"= {result_str}")
        else:
            await update.message.reply_text("Ошибка вычисления")
        return
    
    # 7. Проверяем права администратора для остальных функций
    if not await check_admin(update):
        logger.info(f"Пользователь {username} не является администратором")
        return
    
    # 8. Добавление агента (без "уже в чате")
    if message_text.lower().startswith('агент '):
        parts = message_text.split()
        if len(parts) >= 2:
            agent_username = parts[1]
            
            # Обычное добавление агента
            if bot_manager.add_agent(agent_username, username):
                await update.message.reply_text("Агент добавлен. Анкета будет отправлена когда он зайдет в чат.")
                logger.info(f"Добавлен агент {agent_username} пользователем {username}")
            else:
                await update.message.reply_text("Этот агент уже добавлен")
        return
    
    # 9. Активация агента
    if message_text in ACTIVATION_KEYWORDS:
        logger.info(f"Получено ключевое слово активации: {message_text}")
        agents = bot_manager.agents.get("agents", {})
        
        # Ищем агента со статусом "приветствован"
        target_agent = None
        for agent_username, agent_info in agents.items():
            if agent_info.get("status") == AgentStatus.WELCOMED.value:
                target_agent = agent_username
                break
        
        if target_agent:
            bot_manager.update_agent_status(target_agent, AgentStatus.ACTIVE)
            logger.info(f"Активирован агент {target_agent}")
            
            instruction = f"""{target_agent} - Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.

Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.

После перевода отправляешь квитанцию на указанную почту."""
            
            await update.message.reply_text(instruction)
        else:
            logger.info("Не найден агент для активации")
            await update.message.reply_text("Нет агента для активации. Сначала добавьте агента и дождитесь заполнения анкеты.")
        return
    
    # 10. Обработка сумм для открутки
    if re.match(SUM_PATTERN, message_text):
        try:
            amount = int(message_text.strip('!'))
            if amount > 0:
                bot_manager.last_sum = amount
                logger.info(f"Получена сумма для открутки: {amount}")
        except ValueError:
            pass
        return
    
    # 11. Обработка email для открутки
    if re.match(EMAIL_PATTERN, message_text) and bot_manager.last_sum is not None:
        # Проверяем, можно ли добавить больше чем остаток
        current_remaining = bot_manager.stats.get("remaining_amount", 0)
        
        if current_remaining <= 0:
            # Если остаток 0 или меньше, все равно добавляем транзакцию
            # Это для случая, когда откручивают больше установленной суммы
            bot_manager.process_transaction(bot_manager.last_sum, message_text)
            
            response = (
                f"Откручено ₽{bot_manager.last_sum:,}\n"
                f"Откручено всего: ₽{bot_manager.stats.get('spent_amount', 0):,}\n"
                f"Осталось: ₽{bot_manager.stats.get('remaining_amount', 0):,}"
            )
            await update.message.reply_text(response)
            logger.info(f"Обработана открутка сверх лимита: {bot_manager.last_sum}")
        else:
            bot_manager.process_transaction(bot_manager.last_sum, message_text)
            
            response = (
                f"Откручено ₽{bot_manager.last_sum:,}\n"
                f"Откручено всего: ₽{bot_manager.stats.get('spent_amount', 0):,}\n"
                f"Осталось: ₽{bot_manager.stats.get('remaining_amount', 0):,}"
            )
            await update.message.reply_text(response)
            logger.info(f"Обработана открутка: {bot_manager.last_sum}")
        
        bot_manager.last_sum = None
        return
    
    # 12. Проверяем, является ли сообщение заметкой
    # Формат: "1. Откуп 22:00 || 10.000₽ 💚Сбер💚 +7XXXXXXXXXX"
    note_patterns = [
        r'^\d+\.\s+[^|]+\|\|\s*\d+[.,]?\d*\s*₽',
        r'^\d+\.\s+[^|]+\|\|\s*\d+[.,]?\d*\s*руб',
        r'откуп.*\d+[.,]?\d*\s*₽.*\+7',
        r'откуп.*\d+[.,]?\d*\s*руб.*\+7'
    ]
    
    is_note = False
    for pattern in note_patterns:
        if re.search(pattern, message_text, re.IGNORECASE):
            is_note = True
            break
    
    if is_note:
        # Сохраняем заметку
        bot_manager.add_note(message_text, username)
        await update.message.reply_text("Заметка добавлена")
        return

# Обработка новых участников
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников чата"""
    if not update.message or not update.message.new_chat_members:
        return
    
    chat = update.effective_chat
    logger.info(f"Новые участники: {[user.username for user in update.message.new_chat_members]}")
    
    for new_member in update.message.new_chat_members:
        if new_member.username:
            username = f"@{new_member.username}"
            agents = bot_manager.agents.get("agents", {})
            
            if username in agents and not agents[username].get("welcomed", False):
                # Отправляем анкету новому агенту
                await send_questionnaire(chat.id, username, context)
                
                bot_manager.update_agent_status(username, AgentStatus.WELCOMED)
                bot_manager.agents["agents"][username]["welcomed"] = True
                bot_manager.mark_agent_in_chat(username)
                bot_manager.agents["agents"][username]["has_received_questionnaire"] = True
                bot_manager.save_data(AGENTS_FILE, bot_manager.agents)

def main():
    """Основная функция запуска бота"""
    logger.info("=" * 50)
    logger.info("БОТ ЗАПУЩЕН")
    logger.info(f"Суперадмины: {SUPER_ADMINS}")
    logger.info(f"Админы по умолчанию: {bot_manager.admins.get('admins', [])}")
    logger.info("Триггерные слова настроены")
    logger.info("Система баланса агентов активирована")
    logger.info("=" * 50)
    
    # Создаем приложение с настройками для групп
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    command_handlers = [
        ("start", start_command),
        ("help", help_command),
        ("agent", agent_command),
        ("notes", notes_command),
        ("rub", rub_command),
        ("stats", stats_command),
        ("reset", reset_command),
        ("add_admin", add_admin_command),
        ("remove_admin", remove_admin_command),
        ("reset_agents", reset_agents_command),
        ("remove_agent", remove_agent_command),
    ]
    
    for command, handler in command_handlers:
        application.add_handler(CommandHandler(command, handler))
    
    # Обработка новых участников
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    
    # Обработка текстовых сообщений в группе
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
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
