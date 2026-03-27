FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Запускаем простую версию
CMD ["uvicorn", "app_simple:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
