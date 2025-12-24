FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей, включая TESSERACT OCR
RUN apt-get update && apt-get install -y \
    gcc \
    tesseract-ocr \
    tesseract-ocr-rus \  # Для русского языка
    libtesseract-dev \   # Для разработки
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание директории для данных
RUN mkdir -p /app/data

# Устанавливаем переменную окружения для языка
ENV TESSERACT_LANG=rus

# Запуск бота
CMD ["python", "bot.py"]
