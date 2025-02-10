import os
import time
import uuid
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

# Получаем настройки из переменных окружения
MERCHANT_ID = os.getenv("MERCHANT_ID")
CHECKOUT_URL = os.getenv("CHECKOUT_URL")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL")

# Для уникальности используем текущее время или UUID
order_id = str(int(time.time()))
# При необходимости можно использовать UUID:
# order_id = uuid.uuid4().hex

amount = 100000  # Цена в тийинах: 1000 сум = 100000 тийинов
lang = "ru"
description = "Оплата за Кружку"

# Формируем callback URL с параметром order_id
callback_url = f"{CALLBACK_BASE_URL}?order_id={order_id}"

# Формируем HTML-код формы для оплаты
html_form = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Оплата за Кружку</title>
</head>
<body>
    <h1>Оплата за Кружку</h1>
    <form action="{CHECKOUT_URL}" method="POST">
        <input type="hidden" name="account[order_id]" value="{order_id}">
        <input type="hidden" name="amount" value="{amount}">
        <input type="hidden" name="merchant" value="{MERCHANT_ID}">
        <input type="hidden" name="callback" value="{callback_url}">
        <input type="hidden" name="lang" value="{lang}">
        <input type="hidden" name="description" value="{description}">
        <button type="submit">Оплатить</button>
    </form>
    <p>Order ID: {order_id}</p>
</body>
</html>
"""

# Сохраним HTML в файл
filename = "payment.html"
with open(filename, "w", encoding="utf-8") as f:
    f.write(html_form)

print(f"Форма оплаты сгенерирована в файле {filename}. Откройте его в браузере для проведения оплаты.")
