#!/usr/bin/env python3
"""
🎮 Inline Mini-Games Bot + AI Inline Respond
Использование: @ar_gotbot в любом чате

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
GAME_TIMEOUT = 120
CLEANUP_INTERVAL = 300

# AI
from openai import AsyncOpenAI
AI_TOKEN = "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"

ai = AsyncOpenAI(api_key=AI_TOKEN)


# ═══════════════════════════════════════════════════════════════
# 💾 ХРАНИЛИЩЕ ИГР
# ═══════════════════════════════════════════════════════════════

class GameStorage:
    def __init__(self):
        self._games: Dict[str, dict] = {}
    
    def create(self, game_type: str, **data) -> str:
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
        game = self._games.get(game_id)
        if game and time.time() - game["updated_at"] > GAME_TIMEOUT:
            game["status"] = "timeout"
        return game
    
    def update(self, game_id: str, **data) -> None:
        if game_id in self._games:
            self._games[game_id].update(data)
            self._games[game_id]["updated_at"] = time.time()
    
    def delete(self, game_id: str) -> None:
        self._games.pop(game_id, None)
    
    def cleanup(self):
        now = time.time()
        old = [gid for gid, g in self._games.items() if now - g["created_at"] > 3600]
        for gid in old:
            del self._games[gid]
        return len(old)

storage = GameStorage()


# ═══════════════════════════════════════════════════════════════
# 🎯 БАЗОВЫЙ КЛАСС ИГР
# ═══════════════════════════════════════════════════════════════

class BaseGame(ABC):
    name: str = "Base"
    description: str = "Description"
    emoji: str = "🎮"
    prefix: str = "base"

    @classmethod
    @abstractmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        pass

    @classmethod
    @abstractmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE,
                              game_id: str, action: str) -> None:
        pass

    @classmethod
    def make_callback(cls, game_id: str, *args) -> str:
        return ":".join([cls.prefix, game_id] + [str(a) for a in args])


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 1: КРЕСТИКИ-НОЛИКИ
# ═══════════════════════════════════════════════════════════════

class TicTacToe(BaseGame):
    name = "Крестики-Нолики"
    description = "Классика 3x3"
    emoji = "⭕"
    prefix = "ttt"

    EMPTY, X, O = "⬜", "❌", "⭕"
    WINS = [
        [0,1,2],[3,4,5],[6,7,8],
        [0,3,6],[1,4,7],[2,5,8],
        [0,4,8],[2,4,6]
    ]

    @classmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        game_id = storage.create(
            "tictactoe",
            board=[cls.EMPTY]*9,
            players={"X": None, "O": None},
            turn="X"
        )
        return InlineQueryResultArticle(
            id=f"ttt_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                f"🎮 **{cls.name}**\n\nОжидание игроков...",
                parse_mode="Markdown"
            ),
            reply_markup=cls._kb(game_id, [cls.EMPTY]*9)
        )

    @classmethod
    def _kb(cls, game_id, board):
        buttons = []
        for r in range(3):
            row = []
            for c in range(3):
                idx = r*3+c
                row.append(InlineKeyboardButton(
                    board[idx],
                    callback_data=cls.make_callback(game_id, idx)
                ))
            buttons.append(row)
        return InlineKeyboardMarkup(buttons)

    @classmethod
    def _winner(cls, board):
        for line in cls.WINS:
            if board[line[0]] == board[line[1]] == board[line[2]] != cls.EMPTY:
                return board[line[0]]
        if cls.EMPTY not in board: return "draw"
        return None

    @classmethod
    async def handle_callback(cls, update, context, game_id, action):
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)
        if not game: return await query.answer("❌ Игра не найдена", show_alert=True)

        board = game["board"]
        players = game["players"]
        turn = game["turn"]

        cell = int(action)
        symbol = cls.X if turn == "X" else cls.O

        # регистрируем игроков
        if players["X"] is None:
            players["X"] = {"id": user.id, "name": user.first_name}
        elif players["O"] is None and user.id != players["X"]["id"]:
            players["O"] = {"id": user.id, "name": user.first_name}
        storage.update(game_id, players=players)

        current = players.get(turn)
        if user.id != current["id"]:
            return await query.answer("🚫 Не ваш ход", show_alert=True)
        if board[cell] != cls.EMPTY:
            return await query.answer("❌ Клетка занята", show_alert=True)

        board[cell] = symbol
        winner = cls._winner(board)

        if winner:
            storage.update(game_id, board=board, status="finished")
            if winner == "draw":
                text = "🤝 Ничья!"
            else:
                text = f"🏆 Победил {current['name']} ({winner})"
        else:
            next_turn = "O" if turn == "X" else "X"
            storage.update(game_id, board=board, turn=next_turn)
            next_p = players[next_turn]["name"]
            next_s = cls.O if next_turn == "O" else cls.X
            text = f"Ход: {next_p} ({next_s})"

        await query.edit_message_text(
            f"🎮 **{cls.name}**\n\n{text}",
            parse_mode="Markdown",
            reply_markup=cls._kb(game_id, board)
        )
        await query.answer()


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 2: КАМЕНЬ-НОЖНИЦЫ-БУМАГА
# ═══════════════════════════════════════════════════════════════

class RockPaperScissors(BaseGame):
    name = "Камень-Ножницы-Бумага"
    description = "Игра на двоих"
    emoji = "✊"
    prefix = "rps"

    MOVES = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}

    @classmethod
    def get_inline_result(cls):
        game_id = storage.create("rps", players={})
        return InlineQueryResultArticle(
            id=f"rps_{game_id}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                "✊📄✂️ **Игра началась!**\nВыберите ход.",
                parse_mode="Markdown"
            ),
            reply_markup=cls._kb(game_id)
        )

    @classmethod
    def _kb(cls, game_id, finished=False):
        if finished:
            return InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Новая игра", callback_data=f"rps:{game_id}:new")
            ]])
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(e, callback_data=cls.make_callback(game_id, m))
            for m, e in cls.MOVES.items()
        ]])

    @classmethod
    async def handle_callback(cls, update, context, game_id, action):
        query = update.callback_query
        user = query.from_user
        game = storage.get(game_id)

        if action == "new":
            new = storage.create("rps", players={})
            return await query.edit_message_text(
                "✊📄✂️ Новая игра! Сделайте выбор.",
                parse_mode="Markdown",
                reply_markup=cls._kb(new)
            )

        players = game["players"]
        uid = str(user.id)

        if uid in players:
            return await query.answer("Уже выбрал!", show_alert=True)

        if len(players) >= 2:
            return await query.answer("Игра заполнена!", show_alert=True)

        players[uid] = {"name": user.first_name, "move": action}
        storage.update(game_id, players=players)

        if len(players) == 1:
            return await query.edit_message_text(
                f"{user.first_name} сделал выбор! Ждём второго...",
                reply_markup=cls._kb(game_id)
            )

        # оба выбрали
        p1, p2 = list(players.values())
        m1, m2 = p1["move"], p2["move"]
        e1, e2 = cls.MOVES[m1], cls.MOVES[m2]

        if m1 == m2:
            result = "🤝 Ничья!"
        elif cls.BEATS[m1] == m2:
            result = f"🏆 Побеждает {p1['name']}!"
        else:
            result = f"🏆 Побеждает {p2['name']}!"

        await query.edit_message_text(
            f"{p1['name']}: {e1}\n{p2['name']}: {e2}\n\n{result}",
            reply_markup=cls._kb(game_id, True)
        )
        await query.answer()


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 3: УДАЧА
# ═══════════════════════════════════════════════════════════════

class LuckGame(BaseGame):
    name = "Удачно / Неудачно"
    description = "Проверка удачи"
    emoji = "🍀"
    prefix = "luck"

    @classmethod
    def get_inline_result(cls):
        gid = storage.create("luck", results=[])
        return InlineQueryResultArticle(
            id=f"luck_{gid}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                "🍀 **Проверь свою удачу!**",
                parse_mode="Markdown"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Испытать!", callback_data=cls.make_callback(gid, "try"))
            ]])
        )

    @classmethod
    async def handle_callback(cls, update, context, gid, action):
        query = update.callback_query
        user = query.from_user
        game = storage.get(gid)
        results = game["results"]

        for r in results:
            if r["id"] == user.id:
                return await query.answer("Вы уже играли!", show_alert=True)

        lucky = random.choice([True, False])
        results.append({"id": user.id, "name": user.first_name, "luck": lucky})
        storage.update(gid, results=results)

        lines = [f"{'✅' if r['luck'] else '❌'} {r['name']}" for r in results[-10:]]

        await query.edit_message_text(
            "🍀 **Результаты:**\n" + "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Ещё!", callback_data=cls.make_callback(gid, "try"))
            ]]),
            parse_mode="Markdown"
        )

        await query.answer("УДАЧНО!" if lucky else "НЕУДАЧНО!", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 4: ВИКТОРИНА
# ═══════════════════════════════════════════════════════════════

class Quiz(BaseGame):
    name = "Викторина"
    description = "Проверь знания"
    emoji = "❓"
    prefix = "quiz"

    QUESTIONS = [
        {"q":"Столица Франции?","opts":["Лондон","Париж","Берлин","Рим"],"ans":1},
        {"q":"Сколько планет?","opts":["7","8","9","10"],"ans":1},
        {"q":"Кто написал Онегина?","opts":["Толстой","Пушкин","Гоголь","Чехов"],"ans":1},
    ]

    @classmethod
    def get_inline_result(cls):
        q = random.choice(cls.QUESTIONS)
        gid = storage.create("quiz", question=q["q"], options=q["opts"],
                             answer=q["ans"], responses={})
        return InlineQueryResultArticle(
            id=f"quiz_{gid}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                f"❓ **{q['q']}**",
                parse_mode="Markdown"
            ),
            reply_markup=cls._kb(gid, q["opts"])
        )

    @classmethod
    def _kb(cls, gid, opts):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{i+1}. {opt}",
                                 callback_data=cls.make_callback(gid, i))]
            for i, opt in enumerate(opts)
        ])

    @classmethod
    async def handle_callback(cls, update, context, gid, action):
        query = update.callback_query
        user = query.from_user
        game = storage.get(gid)

        uid = str(user.id)
        if uid in game["responses"]:
            return await query.answer("Уже отвечали!", show_alert=True)

        choice = int(action)
        correct = choice == game["answer"]

        game["responses"][uid] = {"name": user.first_name, "correct": correct}
        storage.update(gid, responses=game["responses"])

        correct_list = [r["name"] for r in game["responses"].values() if r["correct"]]
        wrong_list = [r["name"] for r in game["responses"].values() if not r["correct"]]

        text = f"❓ **{game['question']}**\n\n"
        if correct_list:
            text += "✅ Верно: " + ", ".join(correct_list) + "\n"
        if wrong_list:
            text += "❌ Неверно: " + ", ".join(wrong_list)

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=cls._kb(gid, game["options"])
        )

        await query.answer("Правильно!" if correct else "Неверно!", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# 🎮 ИГРА 5: УГАДАЙ ЧИСЛО
# ═══════════════════════════════════════════════════════════════

class GuessNumber(BaseGame):
    name = "Угадай число"
    description = "От 1 до 100"
    emoji = "🔢"
    prefix = "gnum"

    @classmethod
    def get_inline_result(cls):
        secret = random.randint(1, 100)
        gid = storage.create("guess", secret=secret, min=1, max=100, history=[])
        return InlineQueryResultArticle(
            id=f"gnum_{gid}",
            title=f"{cls.emoji} {cls.name}",
            description=cls.description,
            input_message_content=InputTextMessageContent(
                "🔢 **Загадано число 1–100**\nВыберите диапазон:",
                parse_mode="Markdown"
            ),
            reply_markup=cls._kb(gid, 1, 100)
        )

    @classmethod
    def _kb(cls, gid, lo, hi):
        if lo == hi:
            return InlineKeyboardMarkup([[
                InlineKeyboardButton(f"🎯 {lo}", callback_data=cls.make_callback(gid, lo, hi))
            ]])
        mid = (lo + hi) // 2
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⬇️ {lo}-{mid}", callback_data=cls.make_callback(gid, lo, mid)),
                InlineKeyboardButton(f"⬆️ {mid+1}-{hi}", callback_data=cls.make_callback(gid, mid+1, hi)),
            ],
            [
                InlineKeyboardButton("🎲 Рандом", callback_data=cls.make_callback(gid, "rand", lo, hi))
            ]
        ])

    @classmethod
    async def handle_callback(cls, update, context, gid, action):
        query = update.callback_query
        game = storage.get(gid)
        secret = game["secret"]

        parts = action.split(":")

        if parts[0] == "rand":
            lo, hi = int(parts[1]), int(parts[2])
            guess = random.randint(lo, hi)
        else:
            guess = None
            lo, hi = int(parts[0]), int(parts[1])

        if guess == secret or lo == secret == hi:
            storage.update(gid, status="finished")
            return await query.edit_message_text(
                f"🎉 Число: {secret}\nТы угадал!",
                parse_mode="Markdown"
            )

        if guess:
            if guess < secret:
                new_lo, new_hi = guess + 1, hi
            else:
                new_lo, new_hi = lo, guess - 1
        else:
            new_lo, new_hi = lo, hi

        await query.edit_message_text(
            f"🔢 Идём дальше!\nДиапазон: {new_lo}-{new_hi}",
            parse_mode="Markdown",
            reply_markup=cls._kb(gid, new_lo, new_hi)
        )
        await query.answer()


# ═══════════════════════════════════════════════════════════════
# 🤖 INLINE AI — ГЛАВНАЯ НОВАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════

async def inline_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: InlineQuery = update.inline_query
    text = query.query.strip()

    if not text:
        return

    try:
        resp = await ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": text}],
            max_tokens=350
        )
        answer = resp.choices[0].message.content
    except Exception as e:
        answer = f"⚠️ Ошибка AI: {e}"

    result = InlineQueryResultArticle(
        id="ai_" + str(uuid.uuid4()),
        title="🤖 AI ответ",
        description=answer[:70],
        input_message_content=InputTextMessageContent(
            answer, parse_mode="Markdown"
        )
    )
    await query.answer([result], cache_time=0)


# ═══════════════════════════════════════════════════════════════
# 🚀 ЗАПУСК
# ═══════════════════════════════════════════════════════════════

async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # игровые callback'и
    app.add_handler(CallbackQueryHandler(lambda u,c: handle_callback_router(u,c)))

    # игры (inline menu)
    app.add_handler(InlineQueryHandler(inline_router, pattern="^$"))

    # AI — должен идти последним!
    app.add_handler(InlineQueryHandler(inline_ai))

    await app.run_polling()


# Роутер для inline-меню игр
def inline_router(update: Update, context):
    query = update.inline_query
    games = [
        TicTacToe.get_inline_result(),
        RockPaperScissors.get_inline_result(),
        LuckGame.get_inline_result(),
        Quiz.get_inline_result(),
        GuessNumber.get_inline_result()
    ]
    return query.answer(games, cache_time=0)


# Роутер callback-кнопок игр
async def handle_callback_router(update, context):
    query = update.callback_query
    data = query.data.split(":")
    
    prefix, game_id = data[0], data[1]
    action = ":".join(data[2:]) if len(data) > 2 else data[2] if len(data) > 2 else data[-1]

    mapping = {
        "ttt": TicTacToe,
        "rps": RockPaperScissors,
        "luck": LuckGame,
        "quiz": Quiz,
        "gnum": GuessNumber
    }

    if prefix in mapping:
        await mapping[prefix].handle_callback(update, context, game_id, action)

if __name__ == "__main__":
    asyncio.run(main())
