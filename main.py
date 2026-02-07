#!/usr/bin/env python3
"""
🎮 Inline Mini-Games Bot
Телеграм-бот с мини-играми, работающий в inline-режиме.
Использование: @ar_gotbot в любом чате

Автор: AI Assistant
Python 3.11+ / python-telegram-bot v20+
"""

import asyncio
import random
import uuid
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Callable
from abc import ABC, abstractmethod

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
)
from telegram.ext import (
    Application,
    InlineQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ═══════════════════════════════════════════════════════════════
# 🔧 КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = "7568864397:AAEI4RwDx7Gk_HMnmeCCYMaLkVJTMqKOfMw"
GAME_TIMEOUT = 120  # 2 минуты
CLEANUP_INTERVAL = 300  # 5 минут


# ═══════════════════════════════════════════════════════════════
# 💾 ХРАНИЛИЩЕ СОСТОЯНИЯ ИГР
# ═══════════════════════════════════════════════════════════════

class GameStorage:
    """
    Хранилище состояния всех активных игр в памяти.
    Для продакшена можно заменить на Redis/SQLite.
    """
    
    def __init__(self):
        self._games: Dict[str, dict] = {}
    
    def create(self, game_type: str, **data) -> str:
        """Создаёт новую игру, возвращает уникальный ID."""
        game_id = uuid.uuid4().hex[:8]
        self._games[game_id] = {
            "type": game_type,
            "created_at": time.time(),
            "updated_at": time.time(),
            "status": "active",
            **data
        }
        return game_id
    
    def get(self, game_id: str) -> Optional[dict]:
        """Получает игру по ID с проверкой таймаута."""
        game = self._games.get(game_id)
        if game and time.time() - game["updated_at"] > GAME_TIMEOUT:
            game["status"] = "timeout"
        return game
    
    def update(self, game_id: str, **data) -> None:
        """Обновляет данные игры."""
        if game_id in self._games:
            self._games[game_id].update(data)
            self._games[game_id]["updated_at"] = time.time()
    
    def delete(self, game_id: str) -> None:
        """Удаляет игру."""
        self._games.pop(game_id, None)
    
    def cleanup(self) -> int:
        """Удаляет старые игры (>1 час). Возвращает количество удалённых."""
        now = time.time()
        old_games = [
            gid for gid, g in self._games.items()
            if now - g["created_at"] > 3600
        ]
        for gid in old_games:
            del self._games[gid]
        return len(old_games)


# Глобальный экземпляр хранилища
storage = GameStorage()


# ═══════════════════════════════════════════════════════════════
# 🎯 БАЗОВЫЙ КЛАСС ИГРЫ
# ═══════════════════════════════════════════════════════════════

class BaseGame(ABC):
    """
    Абстрактный базовый класс для всех мини-игр.
    
    Для добавления новой игры:
    1. Наследуйтесь от BaseGame
    2. Определите name, description, emoji, prefix
    3. Реализуйте get_inline_result() и handle_callback()
    4. Добавьте класс в список GAME_REGISTRY
    """
    
    # Метаданные игры (переопределите в подклассах)
    name: str = "Базовая игра"
    description: str = "Описание игры"
    emoji: str = "🎮"
    prefix: str = "base"  # Уникальный префикс для callback_data
    
    @classmethod
    @abstractmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        """Возвращает inline-результат для отображения в меню игр."""
        pass
    
    @classmethod
    @abstractmethod
    async def handle_callback(
        cls,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: str,
        action: str
    ) -> None:
        """Обрабатывает нажатие кнопки в игре."""
        pass
    
    @classmethod
    def make_callback(cls, game_id: str, *args) -> str:
        """Создаёт callback_data для кнопки."""
        parts = [cls.prefix, game_id] + [str(a) for a in args]
        return ":".join(parts)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 1: КРЕСТИКИ-НОЛИКИ
# ═══════════════════════════════════════════════════════════════

class TicTacToe(BaseGame):
    """Классические крестики-нолики 3x3 для двух игроков."""
    
    name = "Крестики-нолики"
    description = "Классическая игра 3x3 для двоих"
    emoji = "⭕"
    prefix = "ttt"
    
    EMPTY, X, O = "⬜", "❌", "⭕"
    WINS = [
        [0,1,2], [3,4,5], [6,7,8],  # горизонтали
        [0,3,6], [1,4,7], [2,5,8],  # вертикали
        [0,4,8], [2,4,6]            # диагонали
    ]
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create(
            "tictactoe",
            board=[cls.EMPTY] * 9,
            players={"X": None, "O": None},
            turn="X"
        )
        return InlineQueryResultArticle(
            id=f"ttt_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"🎮 **{cls.name}**\n\n"
                             f"Ожидание игроков...\n"
                             f"Нажмите клетку, чтобы начать!",
                parse_mode="Markdown"
            ),
            reply_markup=cls._make_keyboard(game_id, [cls.EMPTY] * 9)
        )
    
    @classmethod
    def _make_keyboard(cls, game_id: str, board: list) -> InlineKeyboardMarkup:
        buttons = []
        for row in range(3):
            buttons.append([
                InlineKeyboardButton(
                    board[row*3 + col],
                    callback_data=cls.make_callback(game_id, row*3 + col)
                )
                for col in range(3)
            ])
        return InlineKeyboardMarkup(buttons)
    
    @classmethod
    def _check_winner(cls, board: list) -> Optional[str]:
        for line in cls.WINS:
            if board[line[0]] == board[line[1]] == board[line[2]] != cls.EMPTY:
                return board[line[0]]
        return "draw" if cls.EMPTY not in board else None
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        # Проверки
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        if game["status"] in ("timeout", "finished"):
            return await query.answer("⏰ Игра завершена!", show_alert=True)
        
        cell = int(action)
        board = game["board"]
        players = game["players"]
        turn = game["turn"]
        symbol = cls.X if turn == "X" else cls.O
        
        # Регистрация игроков
        if players["X"] is None:
            players["X"] = {"id": user.id, "name": user.first_name}
        elif players["O"] is None and user.id != players["X"]["id"]:
            players["O"] = {"id": user.id, "name": user.first_name}
        
        storage.update(game_id, players=players)
        
        # Проверка хода
        current_player = players.get(turn)
        if not current_player:
            return await query.answer("⏳ Ожидание второго игрока...", show_alert=True)
        if user.id != current_player["id"]:
            return await query.answer("🚫 Сейчас не ваш ход!", show_alert=True)
        if board[cell] != cls.EMPTY:
            return await query.answer("❌ Клетка занята!", show_alert=True)
        
        # Делаем ход
        board[cell] = symbol
        next_turn = "O" if turn == "X" else "X"
        winner = cls._check_winner(board)
        
        if winner:
            storage.update(game_id, board=board, status="finished")
            if winner == "draw":
                text = f"🎮 **{cls.name}**\n\n🤝 Ничья!"
            else:
                text = f"🎮 **{cls.name}**\n\n🏆 Победил {current_player['name']}! ({winner})"
        else:
            storage.update(game_id, board=board, turn=next_turn)
            next_sym = cls.O if next_turn == "O" else cls.X
            next_player = players.get(next_turn, {}).get("name", "???")
            text = f"🎮 **{cls.name}**\n\nХод: {next_player} ({next_sym})"
        
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=cls._make_keyboard(game_id, board)
        )
        await query.answer()


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 2: КАМЕНЬ-НОЖНИЦЫ-БУМАГА
# ═══════════════════════════════════════════════════════════════

class RockPaperScissors(BaseGame):
    """Камень-ножницы-бумага для двоих."""
    
    name = "Камень-Ножницы-Бумага"
    description = "Классическая игра на двоих"
    emoji = "✊"
    prefix = "rps"
    
    MOVES = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create("rps", players={})
        return InlineQueryResultArticle(
            id=f"rps_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"✊📄✂️ **{cls.name}**\n\nВыберите свой ход!\n"
                             f"Игра начнётся, когда 2 игрока сделают выбор.",
                parse_mode="Markdown"
            ),
            reply_markup=cls._make_keyboard(game_id)
        )
    
    @classmethod
    def _make_keyboard(cls, game_id: str, finished: bool = False) -> InlineKeyboardMarkup:
        if finished:
            return InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Новая игра", callback_data=f"rps:{game_id}:new")
            ]])
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(emoji, callback_data=cls.make_callback(game_id, move))
            for move, emoji in cls.MOVES.items()
        ]])
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        
        if action == "new":
            # Создаём новую игру
            new_id = storage.create("rps", players={})
            return await query.edit_message_text(
                f"✊📄✂️ **{cls.name}**\n\nНовая игра! Выберите ход.",
                parse_mode="Markdown",
                reply_markup=cls._make_keyboard(new_id)
            )
        
        players = game["players"]
        uid = str(user.id)
        
        if uid in players:
            return await query.answer("✅ Вы уже сделали выбор!", show_alert=True)
        
        if len(players) >= 2:
            return await query.answer("🚫 Игра уже заполнена!", show_alert=True)
        
        # Записываем выбор
        players[uid] = {"name": user.first_name, "move": action}
        storage.update(game_id, players=players)
        
        if len(players) == 1:
            await query.answer("✅ Выбор принят! Ждём соперника...")
            return await query.edit_message_text(
                f"✊📄✂️ **{cls.name}**\n\n{user.first_name} сделал выбор! 🤫\n"
                f"Ожидание второго игрока...",
                parse_mode="Markdown",
                reply_markup=cls._make_keyboard(game_id)
            )
        
        # Оба сделали выбор — определяем победителя
        p1, p2 = list(players.values())
        m1, m2 = p1["move"], p2["move"]
        e1, e2 = cls.MOVES[m1], cls.MOVES[m2]
        
        if m1 == m2:
            result = "🤝 Ничья!"
        elif cls.BEATS[m1] == m2:
            result = f"🏆 {p1['name']} побеждает!"
        else:
            result = f"🏆 {p2['name']} побеждает!"
        
        storage.update(game_id, status="finished")
        
        await query.edit_message_text(
            f"✊📄✂️ **{cls.name}**\n\n"
            f"{p1['name']}: {e1}\n{p2['name']}: {e2}\n\n{result}",
            parse_mode="Markdown",
            reply_markup=cls._make_keyboard(game_id, finished=True)
        )
        await query.answer()


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 3: УДАЧНО / НЕУДАЧНО
# ═══════════════════════════════════════════════════════════════

class LuckGame(BaseGame):
    """Простая игра на удачу — 50/50 шанс."""
    
    name = "Удачно / Неудачно"
    description = "Проверь свою удачу! 🍀"
    emoji = "🍀"
    prefix = "luck"
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create("luck", results=[])
        return InlineQueryResultArticle(
            id=f"luck_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"🍀 **{cls.name}**\n\n"
                             f"Нажмите кнопку и узнайте свою судьбу!",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Испытать удачу!", callback_data=cls.make_callback(game_id, "try"))
            ]])
        )
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        
        results = game["results"]
        
        # Проверяем, не играл ли уже
        for r in results:
            if r["id"] == user.id:
                emoji = "✅" if r["luck"] else "❌"
                return await query.answer(f"Вы уже играли! Результат: {emoji}", show_alert=True)
        
        # Бросаем жребий
        is_lucky = random.choice([True, False])
        results.append({"id": user.id, "name": user.first_name, "luck": is_lucky})
        storage.update(game_id, results=results)
        
        # Формируем текст с результатами
        result_lines = [
            f"{'✅' if r['luck'] else '❌'} {r['name']}"
            for r in results[-10:]  # Последние 10
        ]
        
        text = f"🍀 **{cls.name}**\n\n**Результаты:**\n" + "\n".join(result_lines)
        
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Испытать удачу!", callback_data=cls.make_callback(game_id, "try"))
            ]])
        )
        
        emoji = "✅ УДАЧНО!" if is_lucky else "❌ НЕУДАЧНО!"
        await query.answer(emoji, show_alert=True)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 4: ВИКТОРИНА
# ═══════════════════════════════════════════════════════════════

class Quiz(BaseGame):
    """Викторина с вопросами и 4 вариантами ответа."""
    
    name = "Викторина"
    description = "Проверь свои знания!"
    emoji = "❓"
    prefix = "quiz"
    
    QUESTIONS = [
        {"q": "Столица Франции?", "opts": ["Лондон", "Париж", "Берлин", "Рим"], "ans": 1},
        {"q": "Сколько планет в Солнечной системе?", "opts": ["7", "8", "9", "10"], "ans": 1},
        {"q": "Кто написал 'Евгений Онегин'?", "opts": ["Толстой", "Пушкин", "Гоголь", "Чехов"], "ans": 1},
        {"q": "Химический символ золота?", "opts": ["Ag", "Fe", "Au", "Cu"], "ans": 2},
        {"q": "В каком году был основан Google?", "opts": ["1996", "1998", "2000", "2002"], "ans": 1},
        {"q": "Самое большое животное на Земле?", "opts": ["Слон", "Кит", "Жираф", "Акула"], "ans": 1},
        {"q": "Сколько сторон у шестиугольника?", "opts": ["5", "6", "7", "8"], "ans": 1},
        {"q": "Автор теории относительности?", "opts": ["Ньютон", "Эйнштейн", "Бор", "Хокинг"], "ans": 1},
    ]
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        q = random.choice(cls.QUESTIONS)
        game_id = storage.create("quiz", question=q["q"], options=q["opts"], 
                                  answer=q["ans"], responses={})
        return InlineQueryResultArticle(
            id=f"quiz_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"❓ **Викторина**\n\n**{q['q']}**",
                parse_mode="Markdown"
            ),
            reply_markup=cls._make_keyboard(game_id, q["opts"])
        )
    
    @classmethod
    def _make_keyboard(cls, game_id: str, opts: list) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{i+1}. {opt}", callback_data=cls.make_callback(game_id, i))]
            for i, opt in enumerate(opts)
        ])
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        
        uid = str(user.id)
        if uid in game["responses"]:
            return await query.answer("Вы уже ответили!", show_alert=True)
        
        choice = int(action)
        correct = choice == game["answer"]
        
        game["responses"][uid] = {"name": user.first_name, "correct": correct}
        storage.update(game_id, responses=game["responses"])
        
        # Статистика
        correct_list = [r["name"] for r in game["responses"].values() if r["correct"]]
        wrong_list = [r["name"] for r in game["responses"].values() if not r["correct"]]
        
        text = f"❓ **Викторина**\n\n**{game['question']}**\n\n"
        if correct_list:
            text += f"✅ Верно: {', '.join(correct_list)}\n"
        if wrong_list:
            text += f"❌ Неверно: {', '.join(wrong_list)}"
        
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=cls._make_keyboard(game_id, game["options"])
        )
        
        if correct:
            await query.answer("✅ Правильно!", show_alert=True)
        else:
            await query.answer(f"❌ Неверно! Ответ: {game['options'][game['answer']]}", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 5: УГАДАЙ ЧИСЛО
# ═══════════════════════════════════════════════════════════════

class GuessNumber(BaseGame):
    """Угадай число от 1 до 100, сужая диапазон."""
    
    name = "Угадай число"
    description = "Угадай загаданное число от 1 до 100!"
    emoji = "🔢"
    prefix = "gnum"
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        secret = random.randint(1, 100)
        game_id = storage.create("guess", secret=secret, min=1, max=100, history=[])
        return InlineQueryResultArticle(
            id=f"gnum_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"🔢 **{cls.name}**\n\n"
                             f"Загадано число от 1 до 100!\n"
                             f"Выберите диапазон:",
                parse_mode="Markdown"
            ),
            reply_markup=cls._make_keyboard(game_id, 1, 100)
        )
    
    @classmethod
    def _make_keyboard(cls, game_id: str, lo: int, hi: int) -> InlineKeyboardMarkup:
        if lo == hi:
            return InlineKeyboardMarkup([[
                InlineKeyboardButton(f"🎯 {lo}", callback_data=cls.make_callback(game_id, lo, hi))
            ]])
        
        mid = (lo + hi) // 2
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⬇️ {lo}-{mid}", callback_data=cls.make_callback(game_id, lo, mid)),
                InlineKeyboardButton(f"⬆️ {mid+1}-{hi}", callback_data=cls.make_callback(game_id, mid+1, hi)),
            ],
            [InlineKeyboardButton("🎲 Случайное число", callback_data=cls.make_callback(game_id, "rand", lo, hi))]
        ])
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        if game["status"] == "finished":
            return await query.answer("🏆 Число уже угадано!", show_alert=True)
        
        secret = game["secret"]
        parts = action.split(":")
        
        if parts[0] == "rand":
            # Случайная попытка
            lo, hi = int(parts[1]), int(parts[2])
            guess = random.randint(lo, hi)
            
            if guess == secret:
                storage.update(game_id, status="finished")
                text = f"🔢 **{cls.name}**\n\n🎉 {user.first_name} угадал: **{secret}**!"
                await query.edit_message_text(text, parse_mode="Markdown")
                return await query.answer("🎉 УГАДАЛ!", show_alert=True)
            else:
                hint = "⬆️ Больше" if secret > guess else "⬇️ Меньше"
                await query.answer(f"Попытка: {guess}\n{hint}", show_alert=True)
                return
        
        lo, hi = int(parts[0]), int(parts[1])
        
        if not (lo <= secret <= hi):
            return await query.answer("❌ Число не в этом диапазоне!", show_alert=True)
        
        game["history"].append(f"{user.first_name}: {lo}-{hi}")
        storage.update(game_id, min=lo, max=hi, history=game["history"])
        
        if lo == hi:
            # Угадали!
            storage.update(game_id, status="finished")
            text = f"🔢 **{cls.name}**\n\n🎉 {user.first_name} угадал число: **{secret}**!"
            await query.edit_message_text(text, parse_mode="Markdown")
            return await query.answer("🎉 ПОБЕДА!", show_alert=True)
        
        history_text = "\n".join(game["history"][-5:])
        text = f"🔢 **{cls.name}**\n\nДиапазон сужен: {lo}-{hi}\n\n{history_text}"
        
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=cls._make_keyboard(game_id, lo, hi)
        )
        await query.answer("✅ Верный диапазон!")


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 6: СЛОТЫ
# ═══════════════════════════════════════════════════════════════

class Slots(BaseGame):
    """Мини-слоты — крути барабаны!"""
    
    name = "Слоты"
    description = "Крути барабаны и выигрывай!"
    emoji = "🎰"
    prefix = "slot"
    
    SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "🍀"]
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create("slots", spins=[])
        return InlineQueryResultArticle(
            id=f"slot_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"🎰 **{cls.name}**\n\n"
                             f"【 ❓ │ ❓ │ ❓ 】\n\n"
                             f"Нажмите кнопку, чтобы крутить!",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎰 Крутить!", callback_data=cls.make_callback(game_id, "spin"))
            ]])
        )
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        
        # Крутим!
        result = [random.choice(cls.SYMBOLS) for _ in range(3)]
        
        # Определяем выигрыш
        if result[0] == result[1] == result[2]:
            if result[0] == "7️⃣":
                outcome = "🎉 ДЖЕКПОТ!!!"
            elif result[0] == "💎":
                outcome = "💎 БРИЛЛИАНТЫ!"
            else:
                outcome = "🏆 ТРИ В РЯД!"
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            outcome = "👍 Два совпадения!"
        else:
            outcome = "😔 Не повезло..."
        
        # Сохраняем результат
        game["spins"].append({
            "name": user.first_name,
            "result": result,
            "outcome": outcome
        })
        storage.update(game_id, spins=game["spins"])
        
        # Показываем последние спины
        recent = game["spins"][-8:]
        spin_lines = [
            f"▸ {s['name']}: 【{' │ '.join(s['result'])}】 {s['outcome']}"
            for s in recent
        ]
        
        text = f"🎰 **{cls.name}**\n\n" + "\n".join(spin_lines)
        
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎰 Крутить!", callback_data=cls.make_callback(game_id, "spin"))
            ]])
        )
        await query.answer(outcome)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 7: ПРАВДА ИЛИ ДЕЙСТВИЕ
# ═══════════════════════════════════════════════════════════════

class TruthOrDare(BaseGame):
    """Классическая игра Правда или Действие."""
    
    name = "Правда или Действие"
    description = "Выбери: правда или действие?"
    emoji = "🎭"
    prefix = "tod"
    
    TRUTHS = [
        "Какой самый неловкий момент в твоей жизни?",
        "О чём ты больше всего жалеешь?",
        "Какой твой самый большой страх?",
        "Что бы ты сделал с миллионом долларов?",
        "Какую тайну ты никому не рассказывал?",
        "Кого из присутствующих ты бы пригласил на свидание?",
        "Какая твоя самая глупая привычка?",
        "Что самое странное ты когда-либо ел?",
    ]
    
    DARES = [
        "Спой куплет любой песни!",
        "Сделай 15 приседаний!",
        "Отправь сообщение 'Привет!' последнему в чат-листе",
        "Изобрази любое животное!",
        "Позвони родителям и скажи 'Люблю вас!'",
        "Сделай комплимент следующему игроку",
        "Расскажи анекдот!",
        "Покажи последнее фото в галерее",
    ]
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create("tod", history=[])
        return InlineQueryResultArticle(
            id=f"tod_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"🎭 **{cls.name}**\n\nВыбери свою судьбу!",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🤔 Правда", callback_data=cls.make_callback(game_id, "truth")),
                InlineKeyboardButton("💪 Действие", callback_data=cls.make_callback(game_id, "dare")),
            ]])
        )
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        
        if action == "truth":
            task = random.choice(cls.TRUTHS)
            emoji = "🤔"
            label = "ПРАВДА"
        else:
            task = random.choice(cls.DARES)
            emoji = "💪"
            label = "ДЕЙСТВИЕ"
        
        game["history"].append({
            "name": user.first_name,
            "type": label,
            "task": task
        })
        storage.update(game_id, history=game["history"])
        
        # Показываем последние задания
        recent = game["history"][-5:]
        lines = [
            f"**{h['name']}** ({h['type']}):\n_{h['task']}_"
            for h in recent
        ]
        
        text = f"🎭 **{cls.name}**\n\n" + "\n\n".join(lines)
        
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🤔 Правда", callback_data=cls.make_callback(game_id, "truth")),
                InlineKeyboardButton("💪 Действие", callback_data=cls.make_callback(game_id, "dare")),
            ]])
        )
        await query.answer(f"{emoji} {label}!")


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 8: БЫСТРАЯ РЕАКЦИЯ
# ═══════════════════════════════════════════════════════════════

class QuickReaction(BaseGame):
    """Кто первым нажмёт кнопку — тот победил!"""
    
    name = "Быстрая реакция"
    description = "Кто первым нажмёт кнопку?"
    emoji = "⚡"
    prefix = "qr"
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create("reaction", ready=False, winner=None, clicks=[])
        return InlineQueryResultArticle(
            id=f"qr_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"⚡ **{cls.name}**\n\n"
                             f"⏳ Приготовьтесь...\n"
                             f"Когда появится кнопка — жмите первым!",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⏳ Подготовка...", callback_data=cls.make_callback(game_id, "prepare"))
            ]])
        )
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        
        if action == "prepare":
            # Активируем игру
            storage.update(game_id, ready=True, start_time=time.time())
            
            await query.edit_message_text(
                f"⚡ **{cls.name}**\n\n"
                f"🔴 **ЖМИТЕ СЕЙЧАС!**",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔴 ЖМИ!", callback_data=cls.make_callback(game_id, "click"))
                ]])
            )
            return await query.answer("🏁 СТАРТ!")
        
        if action == "click":
            if game["winner"]:
                return await query.answer(f"🏆 Победитель: {game['winner']}", show_alert=True)
            
            reaction_time = time.time() - game.get("start_time", time.time())
            storage.update(game_id, winner=user.first_name, reaction=reaction_time)
            
            await query.edit_message_text(
                f"⚡ **{cls.name}**\n\n"
                f"🏆 **Победитель: {user.first_name}!**\n"
                f"⏱ Время реакции: {reaction_time:.3f} сек",
                parse_mode="Markdown"
            )
            return await query.answer("🏆 ВЫ ПОБЕДИЛИ!", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 9: МИНИ-ШАХМАТЫ (4x4)
# ═══════════════════════════════════════════════════════════════

class MiniChess(BaseGame):
    """Упрощённые шахматы на доске 4x4."""
    
    name = "Мини-шахматы"
    description = "Шахматы 4x4 для двоих"
    emoji = "♟️"
    prefix = "chess"
    
    PIECES = {
        "WK": "♔", "WQ": "♕", "WR": "♖", "WP": "♙",
        "BK": "♚", "BQ": "♛", "BR": "♜", "BP": "♟",
        "": "·"
    }
    
    INIT_BOARD = [
        ["BR", "BQ", "BK", "BR"],
        ["BP", "BP", "BP", "BP"],
        ["WP", "WP", "WP", "WP"],
        ["WR", "WQ", "WK", "WR"],
    ]
    
    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        board = [row[:] for row in cls.INIT_BOARD]
        game_id = storage.create(
            "chess",
            board=board,
            players={"W": None, "B": None},
            turn="W",
            selected=None
        )
        return InlineQueryResultArticle(
            id=f"chess_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                message_text=f"♟️ **{cls.name}** (4x4)\n\n"
                             f"⬜ Белые начинают!\n"
                             f"Нажмите на свою фигуру.",
                parse_mode="Markdown"
            ),
            reply_markup=cls._make_keyboard(game_id, board, None)
        )
    
    @classmethod
    def _make_keyboard(cls, game_id: str, board: list, selected: tuple) -> InlineKeyboardMarkup:
        buttons = []
        for r in range(4):
            row = []
            for c in range(4):
                piece = board[r][c]
                symbol = cls.PIECES.get(piece, "·")
                if selected == (r, c):
                    symbol = f"[{symbol}]"
                row.append(InlineKeyboardButton(
                    symbol, 
                    callback_data=cls.make_callback(game_id, r, c)
                ))
            buttons.append(row)
        return InlineKeyboardMarkup(buttons)
    
    @classmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        
        if not game:
            return await query.answer("❌ Игра не найдена!", show_alert=True)
        if game["status"] == "finished":
            return await query.answer("🏁 Игра завершена!", show_alert=True)
        
        parts = action.split(":")
        r, c = int(parts[0]), int(parts[1])
        
        board = game["board"]
        players = game["players"]
        turn = game["turn"]
        selected = game["selected"]
        
        # Регистрация игроков
        if players["W"] is None:
            players["W"] = {"id": user.id, "name": user.first_name}
        elif players["B"] is None and user.id != players["W"]["id"]:
            players["B"] = {"id": user.id, "name": user.first_name}
        storage.update(game_id, players=players)
        
        current = players.get(turn)
        if not current:
            return await query.answer("⏳ Ожидание второго игрока...", show_alert=True)
        if user.id != current["id"]:
            return await query.answer("🚫 Не ваш ход!", show_alert=True)
        
        piece = board[r][c]
        piece_color = piece[0] if piece else None
        
        if selected is None:
            # Выбираем фигуру
            if piece_color != turn:
                return await query.answer("Выберите свою фигуру!", show_alert=True)
            
            storage.update(game_id, selected=(r, c))
            color_name = "Белые ♔" if turn == "W" else "Чёрные ♚"
            
            await query.edit_message_text(
                f"♟️ **{cls.name}**\n\n{color_name} — фигура выбрана\nВыберите куда ходить",
                parse_mode="Markdown",
                reply_markup=cls._make_keyboard(game_id, board, (r, c))
            )
            return await query.answer("Фигура выбрана!")
        
        else:
            sr, sc = selected
            
            # Отмена выбора
            if (r, c) == (sr, sc):
                storage.update(game_id, selected=None)
                color_name = "Белые ♔" if turn == "W" else "Чёрные ♚"
                await query.edit_message_text(
                    f"♟️ **{cls.name}**\n\n{color_name} — выберите фигуру",
                    parse_mode="Markdown",
                    reply_markup=cls._make_keyboard(game_id, board, None)
                )
                return await query.answer("Выбор отменён")
            
            # Нельзя есть свои
            if piece_color == turn:
                return await query.answer("Нельзя есть свою фигуру!", show_alert=True)
            
            # Делаем ход
            captured = board[r][c]
            board[r][c] = board[sr][sc]
            board[sr][sc] = ""
            
            next_turn = "B" if turn == "W" else "W"
            
            # Проверка на взятие короля
            if captured in ("WK", "BK"):
                storage.update(game_id, board=board, status="finished")
                await query.edit_message_text(
                    f"♟️ **{cls.name}**\n\n🏆 **{current['name']} побеждает!**\nКороль взят!",
                    parse_mode="Markdown",
                    reply_markup=cls._make_keyboard(game_id, board, None)
                )
                return await query.answer("🏆 ПОБЕДА!", show_alert=True)
            
            storage.update(game_id, board=board, turn=next_turn, selected=None)
            
            next_player = players.get(next_turn, {}).get("name", "???")
            color_name = "Белые ♔" if next_turn == "W" else "Чёрные ♚"
            
            await query.edit_message_text(
                f"♟️ **{cls.name}**\n\n{color_name} — ход {next_player}",
                parse_mode="Markdown",
                reply_markup=cls._make_keyboard(game_id, board, None)
            )
            return await query.answer("Ход сделан!")


# ═══════════════════════════════════════════════════════════════
# 📋 РЕЕСТР ИГР
# ═══════════════════════════════════════════════════════════════

# Все игры регистрируются здесь
GAME_REGISTRY: List[type] = [
    TicTacToe,
    RockPaperScissors,
    LuckGame,
    Quiz,
    GuessNumber,
    Slots,
    TruthOrDare,
    QuickReaction,
    MiniChess,
]

# Маппинг prefix -> класс игры
GAME_MAP: Dict[str, type] = {
    game.prefix: game for game in GAME_REGISTRY
}


# ═══════════════════════════════════════════════════════════════
# 🤖 ОБРАБОТЧИКИ БОТА
# ═══════════════════════════════════════════════════════════════

async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик inline-запросов.
    Когда пользователь пишет @ar_gotbot, показываем список игр.
    """
    query = update.inline_query.query.lower().strip()
    
    results = []
    for game_class in GAME_REGISTRY:
        # Фильтрация по поисковому запросу
        if query and query not in game_class.name.lower():
            continue
        
        try:
            result = game_class.get_inline_result()
            results.append(result)
        except Exception as e:
            print(f"Ошибка при создании {game_class.name}: {e}")
    
    # Отправляем результаты (cache_time=0 чтобы каждый раз генерить новую игру)
    await update.inline_query.answer(results, cache_time=0, is_personal=True)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатий на inline-кнопки.
    Парсим callback_data и направляем в нужную игру.
    """
    query = update.callback_query
    data = query.data
    
    # Пустое действие
    if data == "noop":
        return await query.answer()
    
    try:
        parts = data.split(":")
        prefix = parts[0]
        game_id = parts[1]
        action = ":".join(parts[2:]) if len(parts) > 2 else ""
        
        game_class = GAME_MAP.get(prefix)
        if game_class:
            await game_class.handle_callback(update, context, game_id, action)
        else:
            await query.answer("❓ Неизвестная игра")
            
    except Exception as e:
        print(f"Ошибка callback: {e}")
        await query.answer("⚠️ Произошла ошибка")


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Периодическая очистка старых игр."""
    deleted = storage.cleanup()
    if deleted > 0:
        print(f"🧹 Очищено {deleted} старых игр")


# ═══════════════════════════════════════════════════════════════
# 🚀 ЗАПУСК
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    """Главная функция запуска бота."""
    print("=" * 50)
    print("🎮 Inline Mini-Games Bot")
    print("=" * 50)
    print(f"📋 Загружено игр: {len(GAME_REGISTRY)}")
    for game in GAME_REGISTRY:
        print(f"   {game.emoji} {game.name} [{game.prefix}]")
    print("=" * 50)
    
    # Создаём приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(InlineQueryHandler(handle_inline_query))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Периодическая очистка старых игр
    if app.job_queue:
        app.job_queue.run_repeating(
            cleanup_job, 
            interval=CLEANUP_INTERVAL, 
            first=60
        )
    
    print("\n✅ Бот запущен!")
    print("📱 Используйте: @ar_gotbot в любом чате")
    print("\nНажмите Ctrl+C для остановки\n")
    
    # Запуск
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
