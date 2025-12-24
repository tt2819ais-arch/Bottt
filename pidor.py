import json
import logging
import re
import os
import pytesseract
import hashlib
import secrets
from PIL import Image
import io
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
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
SUPER_ADMINS = ["@MaksimXyila"]
EMAIL_PATTERN = r"sir\+\d+@outluk\.ru"
SUM_PATTERN = r"^(!\d+|\d+!)$"
ACTIVATION_KEYWORDS = [
    "Подключаю", "подключаю", 
    "Щас подключу", "щас подключу", 
    "Щас подключат", "Ждем подключения"
]

# Состояния для ConversationHandler
AUTH_STATE, PASSWORD_STATE, CREATE_PASSWORD_STATE = range(3)

# Триггеры на слова с ответами
TRIGGER_WORDS = {
    r'\bблять\b': 'соси хуй',
    r'\bдолбаеб\b': 'твой батя',
    r'\bишак\b': 'ишаков только ебут',
    r'\bджаляб\b': 'котакбас блять',
}

# Директория для данных
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# JSON файлы для хранения данных
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
AGENTS_FILE = os.path.join(DATA_DIR, "agents.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
AUTH_FILE = os.path.join(DATA_DIR, "auth.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")

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
        self.auth_data = self.load_data(AUTH_FILE, {
            "passwords": {},
            "used_passwords": {},
            "creation_date": datetime.now().isoformat()
        })
        self.sessions = self.load_data(SESSIONS_FILE, {
            "sessions": {},
            "last_cleanup": datetime.now().isoformat()
        })
        self.last_sum = None
        
        # Очистка старых сессий при запуске
        self.cleanup_old_sessions()
        
        logger.info(f"Загруженные администраторы: {self.admins.get('admins', [])}")
        logger.info(f"Загружено паролей: {len(self.auth_data.get('passwords', {}))}")
        logger.info(f"Активные сессии: {len(self.sessions.get('sessions', {}))}")
    
    @staticmethod
    def get_default_admins():
        return {
            "super_admins": ["@MaksimXyila"],
            "admins": ["@MaksimXyila"],
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
        super_admins_list = [self.normalize_username(admin) for admin in self.admins.get("super_admins", [])]
        
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
    
    # ============ АВТОРИЗАЦИЯ И СЕССИИ ============
    
    def hash_password(self, password: str) -> str:
        """Хэширует пароль"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def generate_password(self, owner: str) -> Tuple[str, str]:
        """Генерирует новый пароль для пользователя"""
        # Генерируем случайный пароль из 8 символов (буквы и цифры)
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        password = ''.join(secrets.choice(alphabet) for _ in range(8))
        
        # Хэшируем пароль
        password_hash = self.hash_password(password)
        
        # Сохраняем пароль
        if "passwords" not in self.auth_data:
            self.auth_data["passwords"] = {}
        
        self.auth_data["passwords"][password_hash] = {
            "owner": owner,
            "created_at": datetime.now().isoformat(),
            "used": False,
            "used_by": None,
            "used_at": None
        }
        
        self.save_data(AUTH_FILE, self.auth_data)
        
        return password, password_hash
    
    def use_password(self, password: str, username: str) -> bool:
        """Использует пароль для авторизации"""
        password_hash = self.hash_password(password)
        
        if password_hash in self.auth_data.get("passwords", {}):
            password_info = self.auth_data["passwords"][password_hash]
            
            # Проверяем, не использован ли уже пароль
            if password_info.get("used"):
                return False
            
            # Помечаем пароль как использованный
            password_info["used"] = True
            password_info["used_by"] = username
            password_info["used_at"] = datetime.now().isoformat()
            
            # Сохраняем в списке использованных паролей
            if "used_passwords" not in self.auth_data:
                self.auth_data["used_passwords"] = {}
            
            self.auth_data["used_passwords"][username] = {
                "password_hash": password_hash,
                "used_at": datetime.now().isoformat()
            }
            
            self.save_data(AUTH_FILE, self.auth_data)
            
            # Добавляем пользователя в админы
            self.add_admin(username)
            
            logger.info(f"Пароль использован для авторизации: {username}")
            return True
        
        return False
    
    def create_session(self, user_id: int, username: str) -> str:
        """Создает сессию для пользователя"""
        session_token = secrets.token_hex(16)
        
        if "sessions" not in self.sessions:
            self.sessions["sessions"] = {}
        
        self.sessions["sessions"][session_token] = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat()
        }
        
        self.save_data(SESSIONS_FILE, self.sessions)
        
        return session_token
    
    def validate_session(self, user_id: int, username: str) -> bool:
        """Проверяет валидность сессии пользователя"""
        if not username:
            return False
        
        # Проверяем, есть ли активная сессия
        for session_token, session_info in self.sessions.get("sessions", {}).items():
            if (session_info.get("user_id") == user_id and 
                session_info.get("username") == username):
                
                # Обновляем время последней активности
                session_info["last_activity"] = datetime.now().isoformat()
                self.save_data(SESSIONS_FILE, self.sessions)
                return True
        
        return False
    
    def cleanup_old_sessions(self):
        """Очищает старые сессии (старше 30 дней)"""
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        sessions_to_remove = []
        for session_token, session_info in self.sessions.get("sessions", {}).items():
            last_activity = datetime.fromisoformat(session_info.get("last_activity", datetime.now().isoformat()))
            if last_activity < thirty_days_ago:
                sessions_to_remove.append(session_token)
        
        for session_token in sessions_to_remove:
            del self.sessions["sessions"][session_token]
        
        if sessions_to_remove:
            self.sessions["last_cleanup"] = datetime.now().isoformat()
            self.save_data(SESSIONS_FILE, self.sessions)
            logger.info(f"Удалено {len(sessions_to_remove)} старых сессий")
    
    def get_password_stats(self) -> Dict:
        """Получает статистику по паролям"""
        passwords = self.auth_data.get("passwords", {})
        
        total = len(passwords)
        used = sum(1 for p in passwords.values() if p.get("used", False))
        available = total - used
        
        return {
            "total": total,
            "used": used,
            "available": available
        }
    
    def get_all_passwords(self) -> List[Dict]:
        """Получает список всех паролей (только для суперадмина)"""
        result = []
        passwords = self.auth_data.get("passwords", {})
        
        for password_hash, info in passwords.items():
            result.append({
                "password_hash": password_hash[:8] + "...",  # Только часть хэша для безопасности
                "owner": info.get("owner", "Неизвестно"),
                "used": info.get("used", False),
                "used_by": info.get("used_by"),
                "created_at": info.get("created_at", ""),
                "used_at": info.get("used_at")
            })
        
        return result
    
    def revoke_password(self, password_hash_prefix: str) -> bool:
        """Отзывает пароль (делает его использованным)"""
        for password_hash, info in self.auth_data.get("passwords", {}).items():
            if password_hash.startswith(password_hash_prefix):
                if not info.get("used", False):
                    info["used"] = True
                    info["used_at"] = datetime.now().isoformat()
                    self.save_data(AUTH_FILE, self.auth_data)
                    logger.info(f"Пароль отозван: {password_hash_prefix}...")
                    return True
        return False
    
    # ============ ОСТАЛЬНЫЕ МЕТОДЫ ============
    
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
                    "has_received_questionnaire": False
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
    
    def reset_stats(self):
        """Сбрасывает статистику открутки"""
        self.stats["spent_amount"] = 0
        self.stats["remaining_amount"] = self.stats.get("total_amount", 0)
        self.stats["transactions"] = []
        self.save_data(STATS_FILE, self.stats)
        logger.info("Статистика открутки сброшена")
    
    def get_stats_message(self) -> str:
        """Формирует сообщение со статистикой"""
        msg = "СТАТИСТИКА ОТКРУТКИ И АГЕНТОВ\n\n"
        
        msg += f"ОТКРУТКА:\n"
        msg += f"Общая сумма: ₽{self.stats.get('total_amount', 0):,}\n"
        msg += f"Откручено: ₽{self.stats.get('spent_amount', 0):,}\n"
        msg += f"Осталось: ₽{self.stats.get('remaining_amount', 0):,}\n\n"
        
        agents = self.agents.get("agents", {})
        active_agent = self.get_active_agent()
        
        msg += f"АГЕНТОВ ВСЕГО: {len(agents)}\n"
        msg += f"АКТИВНЫЙ АГЕНТ: {active_agent if active_agent else 'нет'}\n\n"
        
        msg += "СПИСОК АГЕНТОВ:\n"
        if agents:
            for agent_username, agent_info in agents.items():
                status = agent_info.get("status", "неизвестно")
                active = " (активный)" if agent_info.get("active_agent") else ""
                in_chat = " (в чате)" if agent_info.get("in_chat") else ""
                has_questionnaire = " (анкета отправлена)" if agent_info.get("has_received_questionnaire") else ""
                
                msg += f"{agent_username}: {status}{active}{in_chat}{has_questionnaire}\n"
                msg += f"Добавлен: {agent_info.get('added_by', 'неизвестно')}\n"
                
                if agent_info.get('activation_date'):
                    msg += f"Активирован: {agent_info['activation_date'][:10]}\n"
                msg += "\n"
        else:
            msg += "Нет добавленных агентов\n\n"
        
        msg += "АДМИНИСТРАТОРЫ:\n"
        admins_list = self.admins.get("admins", [])
        for admin in admins_list:
            if self.is_super_admin(admin):
                msg += f"{admin} (суперадмин)\n"
            else:
                msg += f"{admin}\n"
        
        # Добавляем статистику паролей
        password_stats = self.get_password_stats()
        msg += f"\nСТАТИСТИКА ПАРОЛЕЙ:\n"
        msg += f"Всего создано: {password_stats['total']}\n"
        msg += f"Использовано: {password_stats['used']}\n"
        msg += f"Доступно: {password_stats['available']}\n"
        
        return msg

# Инициализация менеджера
bot_manager = BotManager()

# ============ ФУНКЦИИ ДЛЯ АВТОРИЗАЦИИ ============

async def check_auth(update: Update) -> bool:
    """Проверяет авторизацию пользователя"""
    user = update.effective_user
    if not user or not user.username:
        return False
    
    username = f"@{user.username}"
    user_id = user.id
    
    # Проверяем сессию
    if bot_manager.validate_session(user_id, username):
        return True
    
    # Если нет сессии, проверяем админку (для обратной совместимости)
    return bot_manager.is_admin(username)

async def check_super_admin(update: Update) -> bool:
    """Проверяет права суперадмина"""
    user = update.effective_user
    if not user or not user.username:
        return False
    
    username = f"@{user.username}"
    return bot_manager.is_super_admin(username)

# ============ ОБРАБОТЧИКИ АВТОРИЗАЦИИ ============

async def start_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start в личных сообщениях"""
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    logger.info(f"Команда /start в ЛС от {user.username}")
    
    if chat_type == "private":
        # Проверяем авторизацию
        if await check_auth(update):
            await update.message.reply_text(
                "✅ Вы уже авторизованы!\n"
                "Можете использовать бота в группе.\n\n"
                "Команды для группы:\n"
                "/help - список команд\n"
                "/stats - статистика\n\n"
                "Для управления паролями:\n"
                "/create_password - создать пароль\n"
                "/passwords_list - список паролей"
            )
        else:
            # Показываем меню авторизации
            keyboard = [
                [InlineKeyboardButton("🔑 Авторизоваться", callback_data="auth_login")],
                [InlineKeyboardButton("ℹ️ Помощь", callback_data="auth_help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "👋 Добро пожаловать!\n"
                "Для работы с ботом в группе необходимо авторизоваться.\n\n"
                "Если у вас есть пароль - нажмите 'Авторизоваться'\n"
                "Если вы суперадмин - вы можете создавать пароли",
                reply_markup=reply_markup
            )
    
    return AUTH_STATE

async def auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик колбэков авторизации"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "auth_login":
        await query.edit_message_text(
            "Введите ваш пароль для авторизации:\n"
            "(пароль выдает суперадмин)"
        )
        return PASSWORD_STATE
    
    elif query.data == "auth_help":
        await query.edit_message_text(
            "ℹ️ СИСТЕМА АВТОРИЗАЦИИ\n\n"
            "1. Получите пароль от суперадмина (@MaksimXyila)\n"
            "2. Нажмите 'Авторизоваться' и введите пароль\n"
            "3. После авторизации вы сможете использовать бота в группе\n\n"
            "⚠️ Один пароль может использовать только один человек!\n"
            "📱 Авторизация сохраняется даже после перезагрузки бота\n"
            "❌ Сессия сбрасывается только при удалении чата с ботом"
        )
        return ConversationHandler.END
    
    return AUTH_STATE

async def process_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода пароля"""
    user = update.effective_user
    password = update.message.text.strip()
    
    username = f"@{user.username}"
    
    logger.info(f"Попытка авторизации: {username}")
    
    # Проверяем пароль
    if bot_manager.use_password(password, username):
        # Создаем сессию
        bot_manager.create_session(user.id, username)
        
        await update.message.reply_text(
            "✅ Авторизация успешна!\n\n"
            "Теперь вы можете использовать бота в группе.\n"
            "Ваши права:\n"
            "- Работа с откруткой\n"
            "- Управление агентами\n"
            "- Использование калькулятора\n\n"
            "Перейдите в группу и используйте команды!"
        )
        
        logger.info(f"Успешная авторизация: {username}")
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неверный пароль или пароль уже использован!\n\n"
            "Возможные причины:\n"
            "1. Пароль введен с ошибкой\n"
            "2. Пароль уже использован другим пользователем\n"
            "3. Пароль не существует\n\n"
            "Обратитесь к суперадмину @MaksimXyila"
        )
        return AUTH_STATE

async def cancel_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена авторизации"""
    await update.message.reply_text("Авторизация отменена.")
    return ConversationHandler.END

# ============ КОМАНДЫ УПРАВЛЕНИЯ ПАРОЛЯМИ ============

async def create_password_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание нового пароля (только для суперадмина)"""
    user = update.effective_user
    
    if not await check_super_admin(update):
        await update.message.reply_text("❌ Эта команда доступна только суперадмину!")
        return
    
    # Получаем имя владельца (опционально)
    owner = context.args[0] if context.args else user.username
    
    # Генерируем пароль
    password, password_hash = bot_manager.generate_password(owner)
    
    # Формируем сообщение
    stats = bot_manager.get_password_stats()
    
    message = (
        "🔑 НОВЫЙ ПАРОЛЬ СОЗДАН\n\n"
        f"Пароль: `{password}`\n"
        f"Для: {owner}\n"
        f"Хэш: {password_hash[:8]}...\n\n"
        f"📊 Статистика паролей:\n"
        f"Всего: {stats['total']}\n"
        f"Использовано: {stats['used']}\n"
        f"Доступно: {stats['available']}\n\n"
        "⚠️ Сохраните пароль в надежном месте!\n"
        "Один пароль можно использовать только один раз."
    )
    
    await update.message.reply_text(message, parse_mode='Markdown')
    logger.info(f"Создан новый пароль для {owner}")

async def passwords_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр списка паролей (только для суперадмина)"""
    if not await check_super_admin(update):
        await update.message.reply_text("❌ Эта команда доступна только суперадмину!")
        return
    
    passwords = bot_manager.get_all_passwords()
    stats = bot_manager.get_password_stats()
    
    if not passwords:
        await update.message.reply_text("📭 Нет созданных паролей")
        return
    
    message = f"📋 СПИСОК ПАРОЛЕЙ\n\n"
    message += f"Всего: {stats['total']} | Использовано: {stats['used']} | Доступно: {stats['available']}\n\n"
    
    for i, pwd in enumerate(passwords[:20], 1):  # Показываем первые 20
        status = "✅ Использован" if pwd["used"] else "🟢 Доступен"
        used_by = f" ({pwd['used_by']})" if pwd["used_by"] else ""
        
        message += (
            f"{i}. Хэш: {pwd['password_hash']}\n"
            f"   Создан для: {pwd['owner']}\n"
            f"   Статус: {status}{used_by}\n"
            f"   Создан: {pwd['created_at'][:10]}\n"
        )
        
        if pwd["used_at"]:
            message += f"   Использован: {pwd['used_at'][:10]}\n"
        
        message += "\n"
    
    if len(passwords) > 20:
        message += f"\n... и еще {len(passwords) - 20} паролей\n"
    
    await update.message.reply_text(message)

async def revoke_password_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отзыв пароля (только для суперадмина)"""
    if not await check_super_admin(update):
        await update.message.reply_text("❌ Эта команда доступна только суперадмину!")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /revoke_password [начало_хэша]\nПример: /revoke_password a1b2c3d4")
        return
    
    hash_prefix = context.args[0]
    
    if bot_manager.revoke_password(hash_prefix):
        await update.message.reply_text(f"✅ Пароль с хэшем {hash_prefix}... отозван")
    else:
        await update.message.reply_text("❌ Пароль не найден или уже использован")

# ============ ОБРАБОТКА ФОТОГРАФИЙ ============

def extract_amount_from_image(image: Image.Image) -> Optional[int]:
    """Извлекает сумму пополнения с фотографии"""
    try:
        # Используем Tesseract для OCR
        text = pytesseract.image_to_string(image, lang='rus+eng')
        
        # Ищем суммы с плюсом (пополнения)
        # Паттерны для поиска сумм в формате +9 012 ₽ или +9,012 ₽
        patterns = [
            r'\+\s*[\d\s,]+\s*₽',  # +9 012 ₽
            r'\+\s*[\d,]+',         # +9,012
            r'пополнени[ея]\s*[\d\s,]+',  # пополнение 9 012
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Берем первое пополнение
                amount_str = matches[0]
                
                # Извлекаем только цифры
                digits = re.sub(r'[^\d]', '', amount_str)
                
                if digits:
                    amount = int(digits)
                    logger.info(f"Найдена сумма на фото: {amount} (из текста: {amount_str})")
                    return amount
        
        # Если не нашли по паттернам, ищем любые суммы с плюсом в начале строки
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('+'):
                # Извлекаем цифры из строки
                digits = re.sub(r'[^\d]', '', line)
                if digits:
                    amount = int(digits)
                    logger.info(f"Найдена сумма в строке: {amount} (строка: {line})")
                    return amount
        
        logger.warning(f"Не удалось найти сумму на фото. Текст:\n{text}")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка обработки изображения: {e}")
        return None

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фотографий в группе"""
    # Проверяем авторизацию
    if not await check_auth(update):
        return
    
    user = update.effective_user
    message = update.message
    
    logger.info(f"Получено фото от {user.username}")
    
    # Скачиваем фото
    try:
        photo_file = await message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Открываем изображение
        image = Image.open(io.BytesIO(photo_bytes))
        
        # Извлекаем сумму
        amount = extract_amount_from_image(image)
        
        if amount:
            # Тегаем @ar_got и пишем сообщение
            response = f"@ar_got Вход {amount:,} ₽"
            await message.reply_text(response)
            
            logger.info(f"Обработано фото: {amount} ₽ от {user.username}")
        else:
            await message.reply_text("❌ Не удалось распознать сумму пополнения на фото")
            logger.warning(f"Не удалось распознать сумму на фото от {user.username}")
    
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await message.reply_text("❌ Ошибка обработки фотографии")

# ============ ОСТАЛЬНЫЕ ФУНКЦИИ ============

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
    
    # Проверяем авторизацию для группового чата
    if chat_type == "group" or chat_type == "supergroup":
        if not await check_auth(update):
            await update.message.reply_text(
                "❌ Вы не авторизованы!\n\n"
                "Для работы в группе необходимо:\n"
                "1. Написать боту в ЛС /start\n"
                "2. Авторизоваться с паролем\n"
                "3. Вернуться в группу"
            )
            return
    
    await update.message.reply_text(
        "Бот для управления откруткой и агентами активирован.\n"
        "Используйте /help для просмотра команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /help от {update.effective_user.username}")
    
    help_text = """БОТ ДЛЯ УПРАВЛЕНИЯ ОТКРУТКОЙ И АГЕНТАМИ

ОСНОВНЫЕ КОМАНДЫ:

/rub [сумма] - установить общую сумму для открутки
/stats - статистика по открутке и агентам
/add_admin @username - добавить администратора
/remove_admin @username - удалить администратора
/reset - сбросить счетчик открутки
/reset_agents - сбросить всех агентов
/remove_agent @username - удалить конкретного агента
/agent - инструкция для агентов

📸 ОБРАБОТКА ФОТО:
Отправьте скриншот с пополнением - бот автоматически определит сумму и тегнет @ar_got

СИСТЕМА ОТКРУТКИ:
1. Установите общую сумму: /rub 100000
2. Отправляйте суммы в формате: 9500! или !9500
3. Сразу после суммы отправьте email: sir+123456@outluk.ru
4. Бот автоматически посчитает остаток

УПРАВЛЕНИЕ АГЕНТАМИ:
1. Добавить агента: отправьте "агент @username"
2. Если агент уже в чате: отправьте "агент @username уже в чате"
3. Когда агент зайдет в группу - бот отправит анкету
4. После заполнения анкеты отправьте: "Подключаю" (или аналоги)
5. Бот отправит финальную инструкцию агенту

КАЛЬКУЛЯТОР:
Напишите математическое выражение: 100+200, 500/2, 1000*0.1

КЛЮЧЕВЫЕ СЛОВА ДЛЯ АКТИВАЦИИ АГЕНТА:
Подключаю, подключаю, Щас подключу, щас подключу, Щас подключат, Ждем подключения

ДЛЯ АНКЕТЫ:
Напишите "анкета" для получения формы для заполнения

ДЛЯ ПОЛУЧЕНИЯ ИНСТРУКЦИИ:
Напишите "хелп"

⚙️ КОМАНДЫ ДЛЯ СУПЕРАДМИНА (@MaksimXyila):
/create_password [владелец] - создать пароль
/passwords_list - список всех паролей
/revoke_password [хэш] - отозвать пароль

🔐 СИСТЕМА АВТОРИЗАЦИИ:
1. Каждый пользователь должен авторизоваться в ЛС с ботом
2. Один пароль = один пользователь
3. Авторизация сохраняется до удаления чата с ботом"""
    
    await update.message.reply_text(help_text)

async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инструкция для агентов"""
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /agent от {update.effective_user.username}")
    
    instruction = """ИНСТРУКЦИЯ ДЛЯ АГЕНТОВ:

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

async def rub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /rub"""
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /rub от {update.effective_user.username}")
    
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
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /add_admin от {update.effective_user.username}")
    
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
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /remove_admin от {update.effective_user.username}")
    
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
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /stats от {update.effective_user.username}")
    
    stats_message = bot_manager.get_stats_message()
    await update.message.reply_text(stats_message)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /reset от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
        return
    
    bot_manager.reset_stats()
    await update.message.reply_text("Счетчик открутки сброшен")

async def reset_agents_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset_agents"""
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /reset_agents от {update.effective_user.username}")
    
    if not await check_super_admin(update):
        await update.message.reply_text("Эта команда доступна только суперадминам")
        return
    
    count = bot_manager.reset_all_agents()
    await update.message.reply_text(f"Все агенты сброшены. Удалено: {count}")

async def remove_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /remove_agent"""
    # Проверяем авторизацию для группового чата
    if update.effective_chat.type in ["group", "supergroup"]:
        if not await check_auth(update):
            return
    
    logger.info(f"Команда /remove_agent от {update.effective_user.username}")
    
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
    # Проверяем авторизацию для группового чата
    if not await check_auth(update):
        return
    
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
    
    # 3. Проверяем калькулятор (работает для всех)
    # Улучшенный паттерн для калькулятора
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
                # Округляем до 2 знаков после запятой
                result_str = f"{result:.2f}".rstrip('0').rstrip('.')
            
            await update.message.reply_text(f"= {result_str}")
        else:
            await update.message.reply_text("Ошибка вычисления")
        return
    
    # 4. Проверяем слово "хелп" (для агентов и всех)
    if message_text.lower() == "хелп":
        instruction = f"""{username} - Сейчас тебе будет приходить денюжка. Каждое поступление - мне скрин из истории операций. Не отдельного перевода, а прям страницу истории, списком.
Следи за этим, мне надо сразу сообщать (скидывать скрин), как прилетит денюжка.

Как накопится необходимая сумма - отправлю реквизиты и сумму (конкретная сумма!). Надо будет перевести, только внимательно.

После перевода отправляешь квитанцию на указанную почту."""
        
        await update.message.reply_text(instruction)
        return
    
    # 5. Добавление агента
    if message_text.lower().startswith('агент '):
        parts = message_text.split()
        if len(parts) >= 2:
            agent_username = parts[1]
            
            # Проверяем, если сообщение содержит "уже в чате"
            if 'уже' in message_text.lower() and 'чате' in message_text.lower():
                # Агент уже в чате - отправляем анкету и активируем
                if bot_manager.send_questionnaire_to_existing_agent(agent_username):
                    # Отправляем анкету
                    await send_questionnaire(chat.id, agent_username, context)
                    logger.info(f"Отправлена анкета агенту {agent_username} который уже в чате")
                else:
                    # Сначала добавляем агента, потом отправляем анкету
                    if bot_manager.add_agent(agent_username, username):
                        bot_manager.mark_agent_in_chat(agent_username)
                        bot_manager.send_questionnaire_to_existing_agent(agent_username)
                        
                        # Отправляем анкету
                        await send_questionnaire(chat.id, agent_username, context)
                        logger.info(f"Добавлен и отправлена анкета агенту {agent_username} который уже в чате")
                    else:
                        await update.message.reply_text("Этот агент уже добавлен")
            else:
                # Обычное добавление агента (без отправки анкеты сразу)
                if bot_manager.add_agent(agent_username, username):
                    await update.message.reply_text("Агент добавлен. Анкета будет отправлена когда он зайдет в чат.")
                    logger.info(f"Добавлен агент {agent_username} пользователем {username}")
                else:
                    await update.message.reply_text("Этот агент уже добавлен")
        return
    
    # 6. Активация агента
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
    
    # 7. Обработка сумм для открутки
    if re.match(SUM_PATTERN, message_text):
        try:
            amount = int(message_text.strip('!'))
            if amount > 0:
                bot_manager.last_sum = amount
                logger.info(f"Получена сумма для открутки: {amount}")
        except ValueError:
            pass
        return
    
    # 8. Обработка email для открутки
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
    logger.info("БОТ ЗАПУЩЕН С СИСТЕМОЙ АВТОРИЗАЦИИ")
    logger.info(f"Главный суперадмин: {SUPER_ADMINS}")
    logger.info(f"Активные сессии: {len(bot_manager.sessions.get('sessions', {}))}")
    logger.info("Триггерные слова настроены")
    logger.info("OCR система активирована")
    logger.info("=" * 50)
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # ============ ConversationHandler для авторизации ============
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_private, filters.ChatType.PRIVATE)],
        states={
            AUTH_STATE: [
                CallbackQueryHandler(auth_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_password)
            ],
            PASSWORD_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_auth)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    
    # ============ Команды в личных сообщениях ============
    application.add_handler(CommandHandler("create_password", create_password_command, filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("passwords_list", passwords_list_command, filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("revoke_password", revoke_password_command, filters.ChatType.PRIVATE))
    
    # ============ Команды в групповых чатах ============
    command_handlers = [
        ("start", start_command),
        ("help", help_command),
        ("agent", agent_command),
        ("rub", rub_command),
        ("stats", stats_command),
        ("reset", reset_command),
        ("add_admin", add_admin_command),
        ("remove_admin", remove_admin_command),
        ("reset_agents", reset_agents_command),
        ("remove_agent", remove_agent_command),
    ]
    
    for command, handler in command_handlers:
        application.add_handler(CommandHandler(command, handler, filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
    
    # ============ Обработка фотографий в группах ============
    application.add_handler(MessageHandler(
        filters.PHOTO & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_photo_message
    ))
    
    # ============ Обработка новых участников ============
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        handle_new_chat_members
    ))
    
    # ============ Обработка текстовых сообщений в группе ============
    application.add_handler(MessageHandler(
        filters.TEXT & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_text_message
    ))
    
    # Запуск бота
    logger.info("Бот запущен...")
    logger.info("Ожидаю сообщения...")
    
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
