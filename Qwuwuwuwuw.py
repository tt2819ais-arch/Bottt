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
            "spent_amount": 0,  # Откручено через систему email
            "agent_balance": 0,  # Актуальный баланс от агентов
            "remaining_amount": 0,
            "transactions": []
        })
        self.notes = self.load_data(NOTES_FILE, {"notes": []})
        self.last_phone_number = None  # Для хранения номера телефона перед суммой
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
        """Обрабатывает транзакцию (система email)"""
        self.stats["spent_amount"] += amount
        self.stats["remaining_amount"] -= amount
        
        transaction = {
            "amount": amount,
            "email": email,
            "date": datetime.now().isoformat(),
            "type": "email"
        }
        
        if "transactions" not in self.stats:
            self.stats["transactions"] = []
        
        self.stats["transactions"].append(transaction)
        self.save_data(STATS_FILE, self.stats)
        logger.info(f"Обработана транзакция через email: {amount} руб")
    
    def process_agent_balance(self, agent_username: str, amount: int, sender_info: str):
        """Обрабатывает баланс от агента"""
        normalized = self.normalize_username(agent_username)
        
        if normalized in self.agents.get("agents", {}):
            self.agents["agents"][normalized]["last_balance_response"] = datetime.now().isoformat()
            self.agents["agents"][normalized]["balance_amount"] = amount
            
            # Добавляем в актуальный баланс (НЕ в откручено!)
            self.stats["agent_balance"] += amount
            
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
        self.stats["agent_balance"] = 0
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
    
    def add_phone_number_note(self, phone_number: str, amount: int, bank_info: str, added_by: str):
        """Добавляет заметку с номером телефона и суммой"""
        if "notes" not in self.notes:
            self.notes["notes"] = []
        
        # Определяем номер заметки
        note_number = len(self.notes["notes"]) + 1
        
        # Форматируем заметку
        note_text = f"{note_number}. Откручено: {amount:,} // {phone_number} {bank_info}"
        
        note = {
            "text": note_text,
            "added_by": added_by,
            "date": datetime.now().isoformat(),
            "type": "phone_transaction",
            "phone": phone_number,
            "amount": amount,
            "bank": bank_info
        }
        
        self.notes["notes"].append(note)
        self.save_data(NOTES_FILE, self.notes)
        logger.info(f"Добавлена заметка с телефоном: {phone_number}, сумма: {amount}, банк: {bank_info}")
    
    def get_notes_message(self) -> str:
        """Формирует сообщение со списком заметок"""
        notes = self.notes.get("notes", [])
        
        if not notes:
            return "Нет заметок"
        
        msg = "Список заметок:\n\n"
        
        for note in notes[-20:]:  # Показываем последние 20 заметок
            msg += f"{note['text']}\n"
        
        return msg
    
    def get_stats_message(self) -> str:
        """Формирует сообщение со статистикой"""
        msg = "Статистика открутки и агентов\n\n"
        
        msg += f"Открутка (система email):\n"
        msg += f"Общая сумма: ₽{self.stats.get('total_amount', 0):,}\n"
        msg += f"Откручено: ₽{self.stats.get('spent_amount', 0):,}\n"
        msg += f"Осталось: ₽{self.stats.get('remaining_amount', 0):,}\n\n"
        
        msg += f"Актуальный баланс (от агентов): ₽{self.stats.get('agent_balance', 0):,}\n\n"
        
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

# Функция для извлечения номера телефона
def extract_phone_number(text: str) -> Optional[str]:
    """Извлекает номер телефона из сообщения"""
    # Ищем номер телефона в формате +7XXXXXXXXXX
    phone_match = re.search(r'\+7\d{10}', text)
    if phone_match:
        return phone_match.group(0)
    
    # Ищем номер телефона с пробелами
    phone_match = re.search(r'\+7\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2}', text)
    if phone_match:
        # Убираем пробелы
        return re.sub(r'\s+', '', phone_match.group(0))
    
    return None

# Функция для извлечения банка из сообщения
def extract_bank_info(text: str) -> str:
    """Извлекает информацию о банке"""
    if '💚сбер💚' in text.lower():
        return '💚Сбер💚'
    elif '💛тбанк💛' in text.lower():
        return '💛Тбанк💛'
    elif 'сбер' in text.lower():
        return 'Сбер'
    elif 'тбанк' in text.lower() or 'т-банк' in text.lower():
        return 'Тбанк'
    else:
        return ''

# Функция для извлечения суммы в формате !число или число!
def extract_sum_format(text: str) -> Optional[int]:
    """Извлекает сумму из формата !число или число!"""
    match = re.match(r'^(!\d+|\d+!)$', text.strip())
    if match:
        try:
            # Убираем восклицательные знаки
            amount_str = match.group(0).replace('!', '')
            amount = int(amount_str)
            if amount > 0:
                return amount
        except ValueError:
            pass
    return None

# Функция для проверки email
def extract_email(text: str) -> Optional[str]:
    """Извлекает email из сообщения"""
    match = re.search(EMAIL_PATTERN, text)
    if match:
        return match.group(0)
    return None

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
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений в группе"""
    message_text = update.message.text
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if not message_text:
        return
    
    logger.info(f"Сообщение от {user.username}: {message_text}")
    
    # Проверяем триггерные слова
    trigger_response = check_trigger_words(message_text)
    if trigger_response:
        await update.message.reply_text(trigger_response)
        return
    
    # Проверяем вопрос о балансе
    if is_balance_question(message_text):
        # Получаем активного агента
        active_agent = bot_manager.get_active_agent()
        if active_agent:
            await update.message.reply_text(
                f"Запросите баланс у активного агента: {active_agent}\n"
                "Пример сообщения агенту: 'скинь бал'"
            )
        else:
            await update.message.reply_text("Нет активного агента. Сначала установите активного агента")
        return
    
    # Обработка калькулятора
    if re.match(r'^[\d\+\-\*\/\.\s]+$', message_text) and len(message_text) < 50:
        result = calculate_expression(message_text)
        if result is not None:
            await update.message.reply_text(f"= {result}")
            return
    
    # Обработка команды "анкета"
    if message_text.lower().strip() == 'анкета':
        await send_questionnaire_to_user(chat_id, context)
        return
    
    # Обработка команды "хелп"
    if message_text.lower().strip() == 'хелп':
        await help_command(update, context)
        return
    
    # Проверяем права администратора для остальных команд
    if not await check_admin(update):
        return
    
    # Обработка системы email открутки
    email_match = extract_email(message_text)
    if email_match and bot_manager.last_sum:
        # Найден email после суммы
        amount = bot_manager.last_sum
        email = email_match
        
        bot_manager.process_transaction(amount, email)
        
        # Формируем сообщение
        remaining = bot_manager.stats["remaining_amount"]
        spent = bot_manager.stats["spent_amount"]
        total = bot_manager.stats["total_amount"]
        
        await update.message.reply_text(
            f"✅ Откручено: ₽{amount:,}\n"
            f"📧 Email: {email}\n"
            f"💸 Откручено всего: ₽{spent:,} / ₽{total:,}\n"
            f"💰 Осталось: ₽{remaining:,}"
        )
        
        # Сбрасываем временные данные
        bot_manager.last_sum = None
        return
    
    # Обработка суммы в формате !число или число!
    sum_amount = extract_sum_format(message_text)
    if sum_amount:
        bot_manager.last_sum = sum_amount
        await update.message.reply_text(f"Сумма ₽{sum_amount:,} запомнена. Теперь отправьте email: sir+123456@outluk.ru")
        return
    
    # Обработка добавления агента
    if re.match(r'^агент\s+@\w+', message_text, re.IGNORECASE):
        # Извлекаем юзернейм
        match = re.search(r'@\w+', message_text)
        if match:
            agent_username = match.group(0)
            added_by = f"@{user.username}"
            
            # Проверяем, есть ли "уже в чате"
            if 'уже в чате' in message_text.lower():
                # Отмечаем агента в чате
                if bot_manager.mark_agent_in_chat(agent_username):
                    # Отправляем анкету существующему агенту
                    bot_manager.send_questionnaire_to_existing_agent(agent_username)
                    await send_questionnaire(chat_id, agent_username, context)
                    await update.message.reply_text(f"Агент {agent_username} отмечен как находящийся в чате. Отправлена анкета.")
                else:
                    # Агент не найден, добавляем как нового
                    if bot_manager.add_agent(agent_username, added_by):
                        bot_manager.mark_agent_in_chat(agent_username)
                        bot_manager.send_questionnaire_to_existing_agent(agent_username)
                        await send_questionnaire(chat_id, agent_username, context)
                        await update.message.reply_text(f"Новый агент {agent_username} добавлен и отмечен в чате. Отправлена анкета.")
                    else:
                        await update.message.reply_text(f"Ошибка при добавлении агента {agent_username}")
            else:
                # Просто добавляем агента
                if bot_manager.add_agent(agent_username, added_by):
                    await update.message.reply_text(f"Агент {agent_username} добавлен. Когда он зайдет в чат, отправьте 'агент {agent_username} уже в чате'")
                else:
                    await update.message.reply_text(f"Агент {agent_username} уже существует")
        return
    
    # Обработка активации агента (ключевые слова)
    for keyword in ACTIVATION_KEYWORDS:
        if keyword in message_text:
            active_agent = bot_manager.get_active_agent()
            if active_agent:
                # Активируем существующего агента в чате
                bot_manager.activate_existing_agent(active_agent)
                bot_manager.update_agent_status(active_agent, AgentStatus.ACTIVE)
                
                instruction = f"""{active_agent}, инструкция:

1. Отправь свои данные (ФИО, карта, счет, телефон)
2. Жди ответа от администратора
3. После поступления перевода отправь скрин истории операций в чат
4. Администратор отправит реквизиты для перевода
5. Введи данные для перевода (номер телефона - проверь чтобы был правильный)
6. Отправь скрин и жди одобрения администрации (без одобрения не переводить!)
7. После одобрения жди когда тебе скинут почту для отправки чека
8. Отправь квитанцию на указанную почту

Есть вопросы? Пропиши «хелп»"""
                
                await context.bot.send_message(chat_id=chat_id, text=instruction)
                await update.message.reply_text(f"Агент {active_agent} активирован и получил инструкцию")
            else:
                await update.message.reply_text("Нет активного агента. Сначала установите активного агента")
            return
    
    # Обработка установки активного агента
    if message_text.lower().startswith('активный агент'):
        # Извлекаем юзернейм
        match = re.search(r'@\w+', message_text)
        if match:
            agent_username = match.group(0)
            bot_manager.set_active_agent(agent_username)
            await update.message.reply_text(f"Установлен активный агент: {agent_username}")
        else:
            await update.message.reply_text("Использование: активный агент @username")
        return
    
    # Обработка заметок с номерами телефонов
    # Проверяем наличие номера телефона
    phone_number = extract_phone_number(message_text)
    if phone_number:
        # Сохраняем номер телефона для следующего сообщения
        bot_manager.last_phone_number = phone_number
        logger.info(f"Обнаружен номер телефона: {phone_number}")
        # Не отправляем ответ, ждем следующее сообщение с суммой
        return
    
    # Проверяем, есть ли сохраненный номер телефона
    if bot_manager.last_phone_number:
        # Пытаемся извлечь сумму из текущего сообщения
        amount = extract_sum_format(message_text)
        if amount:
            # Извлекаем информацию о банке
            bank_info = extract_bank_info(message_text)
            
            # Добавляем заметку с телефоном и суммой
            bot_manager.add_phone_number_note(
                bot_manager.last_phone_number,
                amount,
                bank_info,
                f"@{user.username}"
            )
            
            # НЕ добавляем в открутку (spent_amount)
            # Вместо этого добавляем в актуальный баланс (agent_balance)
            # Но нужно найти активного агента для этого
            active_agent = bot_manager.get_active_agent()
            if active_agent:
                bot_manager.process_agent_balance(
                    active_agent,
                    amount,
                    bot_manager.last_phone_number
                )
            
            await update.message.reply_text(
                f"✅ Заметка добавлена: {amount:,} руб, телефон: {bot_manager.last_phone_number} {bank_info}\n"
                f"💰 Актуальный баланс (от агентов): ₽{bot_manager.stats.get('agent_balance', 0):,}"
            )
            
            # Сбрасываем временные данные
            bot_manager.last_phone_number = None
            return
    
    # Обработка баланса от агента (в ответ на сообщение агента)
    # Проверяем, если это сообщение от агента с суммой
    amount = extract_amount_from_message(message_text)
    if amount:
        # Проверяем, является ли отправитель агентом
        sender_username = f"@{user.username}"
        normalized_sender = bot_manager.normalize_username(sender_username)
        
        if normalized_sender in bot_manager.agents.get("agents", {}):
            # Это агент отправляет баланс
            sender_info = extract_sender_info(message_text)
            
            if bot_manager.process_agent_balance(normalized_sender, amount, sender_info):
                await update.message.reply_text(
                    f"✅ Баланс агента {normalized_sender} обновлен: ₽{amount:,}\n"
                    f"💳 Отправитель: {sender_info}\n"
                    f"💰 Актуальный баланс (от агентов): ₽{bot_manager.stats.get('agent_balance', 0):,}"
                )
            return
    
    # Обработка простых заметок
    if message_text.startswith('заметка ') or message_text.startswith('Заметка '):
        note_text = message_text[7:].strip()  # Убираем "заметка "
        if note_text:
            bot_manager.add_note(note_text, f"@{user.username}")
            await update.message.reply_text(f"Заметка добавлена: {note_text[:100]}...")
        return

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников чата"""
    chat_id = update.effective_chat.id
    
    for new_member in update.message.new_chat_members:
        username = f"@{new_member.username}" if new_member.username else new_member.first_name
        
        logger.info(f"Новый участник чата: {username} (ID: {new_member.id})")
        
        # Проверяем, является ли новый участник агентом
        normalized_username = bot_manager.normalize_username(username)
        
        if normalized_username in bot_manager.agents.get("agents", {}):
            # Агент вошел в чат
            bot_manager.mark_agent_in_chat(normalized_username)
            
            # Если агент еще не получал анкету, отправляем
            agent_info = bot_manager.agents["agents"][normalized_username]
            if not agent_info.get("has_received_questionnaire", False):
                bot_manager.send_questionnaire_to_existing_agent(normalized_username)
                await send_questionnaire(chat_id, username, context)
                logger.info(f"Отправлена анкета агенту {username} при входе в чат")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке команды. Попробуйте еще раз."
        )

def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("agent", agent_command))
    application.add_handler(CommandHandler("notes", notes_command))
    application.add_handler(CommandHandler("rub", rub_command))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("reset_agents", reset_agents_command))
    application.add_handler(CommandHandler("remove_agent", remove_agent_command))
    
    # Регистрируем обработчики сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_group_message
    ))
    
    # Обработчик новых участников чата
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
