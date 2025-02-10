import os
import time
import uuid
import psycopg2
from dotenv import load_dotenv

# Загружаем переменные окружения из .env (локально)
load_dotenv()

# Получаем настройки из переменных окружения
MERCHANT_ID = os.getenv("MERCHANT_ID")
CHECKOUT_URL = os.getenv("CHECKOUT_URL")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

# Генерируем уникальный order_id (например, по времени)
order_id = str(int(time.time()))
# При необходимости можно использовать UUID:
# order_id = uuid.uuid4().hex

amount = 100000  # 1000 сум = 100000 тийинов
lang = "ru"
description = "Оплата за Кружку"

# Формируем callback URL с параметром order_id
callback_url = f"{CALLBACK_BASE_URL}?order_id={order_id}"

# Генерируем HTML-код формы для оплаты
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

# Подключаемся к PostgreSQL и создаём заказ
try:
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    insert_query = """
    INSERT INTO orders (id, total_amount, status)
    VALUES (%s, %s, %s)
    ON CONFLICT (id) DO NOTHING;
    """
    cur.execute(insert_query, (order_id, amount, 'pending'))
    conn.commit()
    cur.close()
    conn.close()
    print("Заказ создан в базе данных с id:", order_id)
except Exception as e:
    print("Ошибка при вставке заказа в базу данных:", e)

# Определяем директорию, где находится скрипт, и сохраняем файл там
script_dir = os.path.dirname(os.path.abspath(__file__))
filename = os.path.join(script_dir, "payment.html")

try:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_form)
    print(f"Форма оплаты сгенерирована в файле: {filename}")
    print("Откройте этот файл в браузере для проведения оплаты.")
except Exception as e:
    print("Ошибка при записи файла:", e)
