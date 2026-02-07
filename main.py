#!/usr/bin/env python3
"""
🎮 Inline Mini-Games + AI Bot
Использование: @ar_gotbot в любом чате
Python 3.11+ / python-telegram-bot v20+
"""

import asyncio
import random
import uuid
import time
from typing import Dict, List, Optional
from abc import ABC, abstractmethod

from telegram import (
    Update, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, InlineQueryHandler, CallbackQueryHandler, ContextTypes
)

from openai import OpenAI

# ========================
# 1. КОНФИГУРАЦИЯ
# ========================
BOT_TOKEN = "7568864397:AAEI4RwDx7Gk_HMnmeCCYMaLkVJTMqKOfMw"
AI_TOKEN = "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"  # Ваш токен OpenRouter
GAME_TIMEOUT = 120
CLEANUP_INTERVAL = 300

ai = OpenAI(api_key=AI_TOKEN)

# ========================
# 2. ХРАНИЛИЩЕ
# ========================
class GameStorage:
    def __init__(self):
        self._games: Dict[str, dict] = {}
    
    def create(self, game_type: str, **data) -> str:
        game_id = uuid.uuid4().hex[:8]
        self._games[game_id] = {"type": game_type, "created_at": time.time(), "updated_at": time.time(), "status": "active", **data}
        return game_id
    
    def get(self, game_id: str) -> Optional[dict]:
        game = self._games.get(game_id)
        if game and time.time() - game["updated_at"] > GAME_TIMEOUT:
            game["status"] = "timeout"
        return game
    
    def update(self, game_id: str, **data):
        if game_id in self._games:
            self._games[game_id].update(data)
            self._games[game_id]["updated_at"] = time.time()
    
    def cleanup(self) -> int:
        now = time.time()
        old_games = [gid for gid, g in self._games.items() if now - g["created_at"] > 3600]
        for gid in old_games: del self._games[gid]
        return len(old_games)

storage = GameStorage()

# ========================
# 3. БАЗОВЫЙ КЛАСС ИГР
# ========================
class BaseGame(ABC):
    name: str = "Базовая игра"
    description: str = "Описание"
    emoji: str = "🎮"
    prefix: str = "base"

    @classmethod
    @abstractmethod
    def get_inline_result(cls) -> InlineQueryResultArticle:
        pass

    @classmethod
    @abstractmethod
    async def handle_callback(cls, update: Update, context: ContextTypes.DEFAULT_TYPE, game_id: str, action: str):
        pass

    @classmethod
    def make_callback(cls, game_id: str, *args) -> str:
        return ":".join([cls.prefix, game_id] + [str(a) for a in args])

# ========================
# 4. MINI-GAMES
# ========================
# Здесь вставляйте все ваши классы TicTacToe, RPS, LuckGame и т.д.
# Например:
# GAME_REGISTRY: List[type] = [TicTacToe, RockPaperScissors, LuckGame, Quiz, GuessNumber, Slots, TruthOrDare, QuickReaction, MiniChess]
# GAME_MAP = {g.prefix: g for g in GAME_REGISTRY}

GAME_REGISTRY: List[type] = []  # Вставь свои классы здесь
GAME_MAP: Dict[str, type] = {g.prefix: g for g in GAME_REGISTRY}

# ========================
# 5. AI INLINE RESULT
# ========================
class AIInline:
    """Обрабатывает AI ответы прямо в inline"""
    prefix = "ai"

    @classmethod
    def get_inline_result(cls, query: str) -> InlineQueryResultArticle:
        return InlineQueryResultArticle(
            id=f"ai_{uuid.uuid4().hex[:8]}",
            title="🤖 AI Ответ",
            description="Ответ от AI на ваш вопрос",
            input_message_content=InputTextMessageContent(
                message_text=f"⏳ Обрабатывается AI запрос...\n\n**Вопрос:** {query}",
                parse_mode="Markdown"
            )
        )

    @classmethod
    async def handle_query(cls, query: str) -> str:
        """Запрос к AI через OpenRouter"""
        try:
            response = ai.chat.completions.create(
                model="TNG: DeepSeek R1T2 Chimera (free)",
                messages=[{"role":"user","content": query}]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"❌ Ошибка AI: {e}"

# ========================
# 6. ОБРАБОТЧИК INLINE
# ========================
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip().lower()
    results = []

    # 6.1 Мини-игры
    for game_class in GAME_REGISTRY:
        if query_text and query_text not in game_class.name.lower():
            continue
        try: results.append(game_class.get_inline_result())
        except Exception as e: print(f"Ошибка {game_class.name}: {e}")

    # 6.2 AI
    if query_text:
        results.append(AIInline.get_inline_result(query_text))

    await update.inline_query.answer(results, cache_time=0, is_personal=True)

# ========================
# 7. CALLBACK HANDLER
# ========================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if not data: return

    parts = data.split(":")
    prefix, game_id = parts[0], parts[1]
    action = ":".join(parts[2:]) if len(parts) > 2 else ""

    if prefix == AIInline.prefix:
        # AI inline — обрабатываем и редактируем сообщение
        user_query = query.message.text.split("**Вопрос:**")[-1].strip()
        answer = await AIInline.handle_query(user_query)
        await query.edit_message_text(f"🤖 **AI Ответ:**\n\n{answer}", parse_mode="Markdown")
        await query.answer()
        return

    game_class = GAME_MAP.get(prefix)
    if game_class:
        await game_class.handle_callback(update, context, game_id, action)
    else:
        await query.answer("❌ Неизвестная игра")

# ========================
# 8. ОЧИСТКА
# ========================
async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    deleted = storage.cleanup()
    if deleted > 0: print(f"🧹 Очищено {deleted} старых игр")

# ========================
# 9. ЗАПУСК
# ========================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(InlineQueryHandler(handle_inline_query))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.job_queue.run_repeating(cleanup_job, interval=CLEANUP_INTERVAL, first=60)
    print("✅ Inline Mini-Games + AI Bot запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
