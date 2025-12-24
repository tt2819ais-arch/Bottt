FROM python:3.11-slim

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование requirements.txt первым для лучшего кэширования
COPY requirements.txt .

# Упрощенная установка Python зависимостей
RUN echo "Установка зависимостей..." \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && echo "Зависимости установлены успешно"

# Копирование исходного кода
COPY . .

# Проверка установленных пакетов
RUN echo "=== Проверка установленных пакетов ===" \
    && pip list

# Запуск бота
CMD ["python", "bot.py"]
