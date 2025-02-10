import os
import json
import time
import base64
import logging
import sys
import requests  # Для отправки уведомлений через Telegram Bot API
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

# Загружаем переменные окружения
load_dotenv()

# --- Переменные окружения ---
# Для PayMe:
PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID")       # Значение для PayMe
PAYME_MERCHANT_KEY = os.getenv("PAYME_MERCHANT_KEY")     # Ключ для формирования подписи PayMe

# Для авторизации:
MERCHANT_KEY = os.getenv("MERCHANT_KEY")
CHECKOUT_URL = os.getenv("CHECKOUT_URL")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL")         # Должна быть определена
DATABASE_URL = os.getenv("DATABASE_URL")

# Для уведомлений через Telegram:
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")  # Идентификатор группы администраторов (если используется)

app = Flask(__name__)

# --- Настройка логирования ---
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Функция подключения к базе данных ---
def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# --- Инициализация базы данных ---
def init_db():
    conn = get_db()
    cur = conn.cursor()
    create_table_query = """
    CREATE TABLE IF NOT EXISTS orders (
        order_id SERIAL PRIMARY KEY,
        user_id BIGINT,
        merchant_trans_id TEXT,
        product TEXT,
        quantity INTEGER,
        design_text TEXT,
        design_photo TEXT,
        location_lat REAL,
        location_lon REAL,
        status TEXT NOT NULL,
        payment_amount INTEGER,
        payment_system TEXT,  -- "click" или "payme"
        create_time BIGINT,
        perform_time BIGINT,
        cancel_time BIGINT,
        order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        delivery_comment TEXT,
        items TEXT,
        transaction_id TEXT
    );
    """
    cur.execute(create_table_query)
    conn.commit()
    # Добавляем недостающие столбцы, если они отсутствуют
    alter_queries = [
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id BIGINT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS merchant_trans_id TEXT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS product TEXT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS design_text TEXT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS design_photo TEXT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS location_lat REAL;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS location_lon REAL;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS create_time BIGINT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS perform_time BIGINT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_time BIGINT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_comment TEXT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS transaction_id TEXT;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_system TEXT;"
    ]
    for query in alter_queries:
        try:
            cur.execute(query)
        except Exception as e:
            logging.error("Ошибка ALTER TABLE: %s", e)
    conn.commit()
    cur.close()
    conn.close()

init_db()

def current_timestamp():
    return int(round(time.time() * 1000))

# --- Функция для отправки сообщения через Telegram Bot API ---
def send_message_to_telegram(chat_id, text, token):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        logging.info("Уведомление отправлено: %s", response.json())
    except Exception as e:
        logging.error("Ошибка отправки сообщения в Telegram: %s", e)

# --- Функция для уведомления об успешном платеже ---
def notify_payment_success(order):
    try:
        # Получаем данные клиента из таблицы clients (если такая таблица существует)
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM clients WHERE user_id = %s", (order["user_id"],))
        client = cur.fetchone()
        cur.close()
        conn.close()

        if client:
            client_info = (f"Клиент: {client.get('name', 'Неизвестный')} "
                           f"(@{client.get('username', 'нет')})\nТелефон: {client.get('contact', 'не указан')}")
        else:
            client_info = "Данные клиента не найдены"

        message_text = (
            f"✅ Оплата заказа №{order['order_id']} успешно проведена!\n\n"
            f"{client_info}\n\n"
            f"Товар: {order.get('product', 'не указан')}\n"
            f"Количество: {order.get('quantity', 'не указано')}\n"
            f"Сумма: {order.get('payment_amount', '0')} сум\n"
            f"Комментарий к доставке: {order.get('delivery_comment', '')}"
        )

        send_message_to_telegram(order["user_id"], message_text, TELEGRAM_BOT_TOKEN)
        if GROUP_CHAT_ID:
            send_message_to_telegram(GROUP_CHAT_ID, message_text, TELEGRAM_BOT_TOKEN)
    except Exception as e:
        logging.error("Ошибка отправки уведомления о платеже: %s", e)

# --- Функция для проверки суммы с учетом платежной системы ---
def is_amount_correct(order_amount, callback_amount, payment_system):
    # Если система не задана или равна "payme", то callback_amount должен быть равен order_amount * 100
    if not payment_system or payment_system.lower() == "payme":
        return int(order_amount) * 100 == int(callback_amount)
    elif payment_system.lower() == "click":
        return int(order_amount) == int(callback_amount)
    else:
        return int(order_amount) == int(callback_amount)

# --- Функция для генерации ссылки оплаты через PayMe ---
async def create_payme_payment_link(user_id: int, amount: int, merchant_trans_id: str) -> str:
    lang = "ru"
    description = "Оплата заказа"
    callback_url = f"{CALLBACK_BASE_URL}?order_id={merchant_trans_id}"
    payme_amount = amount * 100  # умножаем сумму на 100 (например, 500 → 50000)
    payment_url = (
        f"{os.getenv('PAYME_SELF_URL')}/payment?"
        f"order_id={merchant_trans_id}&"
        f"amount={payme_amount}&"
        f"merchant={PAYME_MERCHANT_ID}&"
        f"callback={callback_url}&"
        f"lang={lang}&"
        f"description={description}"
    )
    signature_string = f"{merchant_trans_id}{payme_amount}{PAYME_MERCHANT_KEY}"
    signature = hashlib.md5(signature_string.encode()).hexdigest()
    payment_url += f"&signature={signature}"
    return payment_url

# --- Функция для генерации ссылки оплаты через Click (если потребуется) ---
async def create_payment_link(user_id: int, amount: int, merchant_trans_id: str) -> str:
    action = "0"
    sign_time = time.strftime("%Y-%m-%d %H:%M:%S")
    signature_string = f"{merchant_trans_id}{os.getenv('SERVICE_ID')}{SECRET_KEY}{amount}{action}{sign_time}"
    signature = hashlib.md5(signature_string.encode()).hexdigest()
    payment_url = (
        f"https://my.click.uz/services/pay?service_id={os.getenv('SERVICE_ID')}&merchant_id={MERCHANT_ID}&amount={amount:.2f}"
        f"&transaction_param={merchant_trans_id}&return_url={os.getenv('RETURN_URL')}&signature={signature}"
    )
    return payment_url

# --- Функции работы с базой данных ---
def get_order_by_merchant_trans_id(merchant_trans_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE merchant_trans_id = %s", (merchant_trans_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

def get_order_by_id(order_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

def get_order_by_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE transaction_id = %s", (transaction_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

def update_order(order_id, fields):
    conn = get_db()
    cur = conn.cursor()
    set_clause = ", ".join([f"{key} = %s" for key in fields.keys()])
    values = list(fields.values())
    values.append(order_id)
    query = f"UPDATE orders SET {set_clause} WHERE order_id = %s"
    cur.execute(query, values)
    conn.commit()
    cur.close()
    conn.close()

# --- Бизнес-логика PayMe ---
def check_perform_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")  # order_id содержит UUID (merchant_trans_id)
    if merchant_trans_id is None:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct(order["payment_amount"], params.get("amount"), order.get("payment_system", "payme")):
        return error_amount(payload)
    stub_items = [
        {
            "discount": 0,
            "title": "Кружка",
            "price": order["payment_amount"],
            "count": 1,
            "code": "06912001036000000",
            "units": 796,
            "vat_percent": 12,
            "package_code": "1184747"
        }
    ]
    return {
        "id": payload.get("id"),
        "result": {
            "allow": True,
            "detail": {
                "receipt_type": 0,
                "items": stub_items
            }
        },
        "error": None
    }

def create_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")
    if merchant_trans_id is None:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct(order["payment_amount"], params.get("amount"), order.get("payment_system", "payme")):
        return error_amount(payload)
    transaction_id = params.get("id")
    if order["status"].lower() in ["pending", "одобрен"]:
        create_time = current_timestamp()
        update_order(order["order_id"], {
            "status": "processing",
            "create_time": create_time,
            "transaction_id": transaction_id
        })
        return {
            "id": payload.get("id"),
            "result": {
                "create_time": create_time,
                "transaction": "000" + str(order["order_id"]),
                "state": 1
            }
        }
    elif order["status"].lower() == "processing":
        if order.get("transaction_id") == transaction_id:
            return {
                "id": payload.get("id"),
                "result": {
                    "create_time": order.get("create_time"),
                    "transaction": "000" + str(order["order_id"]),
                    "state": 1
                }
            }
        else:
            return error_has_another_transaction(payload)
    else:
        return error_unknown(payload)

def perform_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order["status"].lower() == "processing":
        perform_time = current_timestamp()
        update_order(order_id, {
            "status": "completed",
            "perform_time": perform_time
        })
        updated_order = get_order_by_id(order_id)
        notify_payment_success(updated_order)
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order_id),
                "perform_time": perform_time,
                "state": 2
            }
        }
    elif order["status"].lower() == "completed":
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order_id),
                "perform_time": order.get("perform_time"),
                "state": 2
            }
        }
    elif order["status"].lower() in ["cancelled", "refunded"]:
        return error_cancelled_transaction(payload)
    else:
        return error_unknown(payload)

def check_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order.get("transaction_id") != transaction_id:
        return error_transaction(payload)
    if order["status"].lower() == "processing":
        state_val = 1
    elif order["status"].lower() == "completed":
        state_val = 2
    elif order["status"].lower() == "cancelled":
        state_val = -1
    elif order["status"].lower() == "refunded":
        state_val = -2
    else:
        return error_transaction(payload)
    return {
        "id": payload.get("id"),
        "result": {
            "create_time": order.get("create_time", 0),
            "perform_time": order.get("perform_time", 0),
            "cancel_time": order.get("cancel_time", 0),
            "transaction": "000" + str(order_id),
            "state": state_val,
            "reason": order.get("cancel_reason")
        },
        "error": None
    }

def cancel_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order.get("transaction_id") != transaction_id:
        return error_transaction(payload)
    cancel_time = current_timestamp()
    if order["status"].lower() in ["pending", "processing"]:
        new_status = "cancelled"
        state_val = -1
    elif order["status"].lower() == "completed":
        new_status = "refunded"
        state_val = -2
    elif order["status"].lower() in ["cancelled", "refunded"]:
        cancel_time = order.get("cancel_time", cancel_time)
        state_val = -1 if order["status"].lower() == "cancelled" else -2
    else:
        return error_cancel(payload)
    update_order(order_id, {
        "status": new_status,
        "cancel_time": cancel_time,
        "cancel_reason": params.get("reason")
    })
    return {
        "id": payload.get("id"),
        "result": {
            "transaction": "000" + str(order_id),
            "cancel_time": cancel_time,
            "state": state_val
        }
    }

def change_password(payload):
    params = payload.get("params", {})
    new_password = params.get("password")
    if new_password != MERCHANT_KEY:
        return {
            "id": payload.get("id"),
            "result": {"success": True},
            "error": None
        }
    return error_password(payload)

def get_order_by_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE transaction_id = %s", (transaction_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

# --- Функции формирования ошибок ---
def error_invalid_json():
    return {
        "error": {"code": -32700, "message": {"ru": "Could not parse JSON", "uz": "Could not parse JSON", "en": "Could not parse JSON"}, "data": None},
        "result": None,
        "id": 0
    }

def error_order_id(payload):
    return {
        "error": {"code": -31099, "message": {"ru": "Order number cannot be found", "uz": "Order number cannot be found", "en": "Order number cannot be found"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_amount(payload):
    return {
        "error": {"code": -31001, "message": {"ru": "Order amount is incorrect", "uz": "Order amount is incorrect", "en": "Order amount is incorrect"}, "data": "amount"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_has_another_transaction(payload):
    return {
        "error": {"code": -31099, "message": {"ru": "Other transaction for this order is in progress", "uz": "Other transaction for this order is in progress", "en": "Other transaction for this order is in progress"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_unknown(payload):
    return {
        "error": {"code": -31008, "message": {"ru": "Unknown error", "uz": "Unknown error", "en": "Unknown error"}, "data": None},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_unknown_method(payload):
    return {
        "error": {"code": -32601, "message": {"ru": "Unknown method", "uz": "Unknown method", "en": "Unknown method"}, "data": payload.get("method", "")},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_transaction(payload):
    return {
        "error": {"code": -31003, "message": {"ru": "Transaction number is wrong", "uz": "Transaction number is wrong", "en": "Transaction number is wrong"}, "data": "id"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_cancelled_transaction(payload):
    return {
        "error": {"code": -31008, "message": {"ru": "Transaction was cancelled or refunded", "uz": "Transaction was cancelled or refunded", "en": "Transaction was cancelled or refunded"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_cancel(payload):
    return {
        "error": {"code": -31007, "message": {"ru": "It is impossible to cancel. The order is completed", "uz": "It is impossible to cancel. The order is completed", "en": "It is impossible to cancel. The order is completed"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_password(payload):
    return {
        "error": {"code": -32400, "message": {"ru": "Cannot change the password", "uz": "Cannot change the password", "en": "Cannot change the password"}, "data": "password"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_authorization(payload):
    return {
        "error": {"code": -32504, "message": {"ru": "Error during authorization", "uz": "Error during authorization", "en": "Error during authorization"}, "data": None},
        "result": None,
        "id": payload.get("id", 0)
    }

# ============================================================================
# Основная бизнес-логика PayMe (поиск заказа по merchant_trans_id)
def check_perform_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")
    if merchant_trans_id is None:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct(order["payment_amount"], params.get("amount"), order.get("payment_system", "payme")):
        return error_amount(payload)
    stub_items = [
        {
            "discount": 0,
            "title": "Кружка",
            "price": order["payment_amount"],
            "count": 1,
            "code": "06912001036000000",
            "units": 796,
            "vat_percent": 12,
            "package_code": "1184747"
        }
    ]
    return {
        "id": payload.get("id"),
        "result": {
            "allow": True,
            "detail": {
                "receipt_type": 0,
                "items": stub_items
            }
        },
        "error": None
    }

def create_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")
    if merchant_trans_id is None:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct(order["payment_amount"], params.get("amount"), order.get("payment_system", "payme")):
        return error_amount(payload)
    transaction_id = params.get("id")
    if order["status"].lower() in ["pending", "одобрен"]:
        create_time = current_timestamp()
        update_order(order["order_id"], {
            "status": "processing",
            "create_time": create_time,
            "transaction_id": transaction_id
        })
        return {
            "id": payload.get("id"),
            "result": {
                "create_time": create_time,
                "transaction": "000" + str(order["order_id"]),
                "state": 1
            }
        }
    elif order["status"].lower() == "processing":
        if order.get("transaction_id") == transaction_id:
            return {
                "id": payload.get("id"),
                "result": {
                    "create_time": order.get("create_time"),
                    "transaction": "000" + str(order["order_id"]),
                    "state": 1
                }
            }
        else:
            return error_has_another_transaction(payload)
    else:
        return error_unknown(payload)

def perform_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order["status"].lower() == "processing":
        perform_time = current_timestamp()
        update_order(order_id, {
            "status": "completed",
            "perform_time": perform_time
        })
        updated_order = get_order_by_id(order_id)
        notify_payment_success(updated_order)
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order_id),
                "perform_time": perform_time,
                "state": 2
            }
        }
    elif order["status"].lower() == "completed":
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order_id),
                "perform_time": order.get("perform_time"),
                "state": 2
            }
        }
    elif order["status"].lower() in ["cancelled", "refunded"]:
        return error_cancelled_transaction(payload)
    else:
        return error_unknown(payload)

def check_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order.get("transaction_id") != transaction_id:
        return error_transaction(payload)
    if order["status"].lower() == "processing":
        state_val = 1
    elif order["status"].lower() == "completed":
        state_val = 2
    elif order["status"].lower() == "cancelled":
        state_val = -1
    elif order["status"].lower() == "refunded":
        state_val = -2
    else:
        return error_transaction(payload)
    return {
        "id": payload.get("id"),
        "result": {
            "create_time": order.get("create_time", 0),
            "perform_time": order.get("perform_time", 0),
            "cancel_time": order.get("cancel_time", 0),
            "transaction": "000" + str(order_id),
            "state": state_val,
            "reason": order.get("cancel_reason")
        },
        "error": None
    }

def cancel_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order.get("transaction_id") != transaction_id:
        return error_transaction(payload)
    cancel_time = current_timestamp()
    if order["status"].lower() in ["pending", "processing"]:
        new_status = "cancelled"
        state_val = -1
    elif order["status"].lower() == "completed":
        new_status = "refunded"
        state_val = -2
    elif order["status"].lower() in ["cancelled", "refunded"]:
        cancel_time = order.get("cancel_time", cancel_time)
        state_val = -1 if order["status"].lower() == "cancelled" else -2
    else:
        return error_cancel(payload)
    update_order(order_id, {
        "status": new_status,
        "cancel_time": cancel_time,
        "cancel_reason": params.get("reason")
    })
    return {
        "id": payload.get("id"),
        "result": {
            "transaction": "000" + str(order_id),
            "cancel_time": cancel_time,
            "state": state_val
        }
    }

def change_password(payload):
    params = payload.get("params", {})
    new_password = params.get("password")
    if new_password != MERCHANT_KEY:
        return {
            "id": payload.get("id"),
            "result": {"success": True},
            "error": None
        }
    return error_password(payload)

def get_order_by_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE transaction_id = %s", (transaction_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

# ============================================================================
# Функции формирования ошибок
def error_invalid_json():
    return {
        "error": {"code": -32700, "message": {"ru": "Could not parse JSON", "uz": "Could not parse JSON", "en": "Could not parse JSON"}, "data": None},
        "result": None,
        "id": 0
    }

def error_order_id(payload):
    return {
        "error": {"code": -31099, "message": {"ru": "Order number cannot be found", "uz": "Order number cannot be found", "en": "Order number cannot be found"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_amount(payload):
    return {
        "error": {"code": -31001, "message": {"ru": "Order amount is incorrect", "uz": "Order amount is incorrect", "en": "Order amount is incorrect"}, "data": "amount"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_has_another_transaction(payload):
    return {
        "error": {"code": -31099, "message": {"ru": "Other transaction for this order is in progress", "uz": "Other transaction for this order is in progress", "en": "Other transaction for this order is in progress"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_unknown(payload):
    return {
        "error": {"code": -31008, "message": {"ru": "Unknown error", "uz": "Unknown error", "en": "Unknown error"}, "data": None},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_unknown_method(payload):
    return {
        "error": {"code": -32601, "message": {"ru": "Unknown method", "uz": "Unknown method", "en": "Unknown method"}, "data": payload.get("method", "")},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_transaction(payload):
    return {
        "error": {"code": -31003, "message": {"ru": "Transaction number is wrong", "uz": "Transaction number is wrong", "en": "Transaction number is wrong"}, "data": "id"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_cancelled_transaction(payload):
    return {
        "error": {"code": -31008, "message": {"ru": "Transaction was cancelled or refunded", "uz": "Transaction was cancelled or refunded", "en": "Transaction was cancelled or refunded"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_cancel(payload):
    return {
        "error": {"code": -31007, "message": {"ru": "It is impossible to cancel. The order is completed", "uz": "It is impossible to cancel. The order is completed", "en": "It is impossible to cancel. The order is completed"}, "data": "order"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_password(payload):
    return {
        "error": {"code": -32400, "message": {"ru": "Cannot change the password", "uz": "Cannot change the password", "en": "Cannot change the password"}, "data": "password"},
        "result": None,
        "id": payload.get("id", 0)
    }

def error_authorization(payload):
    return {
        "error": {"code": -32504, "message": {"ru": "Error during authorization", "uz": "Error during authorization", "en": "Error during authorization"}, "data": None},
        "result": None,
        "id": payload.get("id", 0)
    }

# ============================================================================
# Основная бизнес-логика PayMe (поиск заказа по merchant_trans_id)
def check_perform_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")  # order_id содержит UUID (merchant_trans_id)
    if merchant_trans_id is None:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct(order["payment_amount"], params.get("amount"), order.get("payment_system", "payme")):
        return error_amount(payload)
    stub_items = [
        {
            "discount": 0,
            "title": "Кружка",
            "price": order["payment_amount"],
            "count": 1,
            "code": "06912001036000000",
            "units": 796,
            "vat_percent": 12,
            "package_code": "1184747"
        }
    ]
    return {
        "id": payload.get("id"),
        "result": {
            "allow": True,
            "detail": {
                "receipt_type": 0,
                "items": stub_items
            }
        },
        "error": None
    }

def create_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")
    if merchant_trans_id is None:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct(order["payment_amount"], params.get("amount"), order.get("payment_system", "payme")):
        return error_amount(payload)
    transaction_id = params.get("id")
    if order["status"].lower() in ["pending", "одобрен"]:
        create_time = current_timestamp()
        update_order(order["order_id"], {
            "status": "processing",
            "create_time": create_time,
            "transaction_id": transaction_id
        })
        return {
            "id": payload.get("id"),
            "result": {
                "create_time": create_time,
                "transaction": "000" + str(order["order_id"]),
                "state": 1
            }
        }
    elif order["status"].lower() == "processing":
        if order.get("transaction_id") == transaction_id:
            return {
                "id": payload.get("id"),
                "result": {
                    "create_time": order.get("create_time"),
                    "transaction": "000" + str(order["order_id"]),
                    "state": 1
                }
            }
        else:
            return error_has_another_transaction(payload)
    else:
        return error_unknown(payload)

def perform_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order["status"].lower() == "processing":
        perform_time = current_timestamp()
        update_order(order_id, {
            "status": "completed",
            "perform_time": perform_time
        })
        updated_order = get_order_by_id(order_id)
        notify_payment_success(updated_order)
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order_id),
                "perform_time": perform_time,
                "state": 2
            }
        }
    elif order["status"].lower() == "completed":
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order_id),
                "perform_time": order.get("perform_time"),
                "state": 2
            }
        }
    elif order["status"].lower() in ["cancelled", "refunded"]:
        return error_cancelled_transaction(payload)
    else:
        return error_unknown(payload)

def check_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order.get("transaction_id") != transaction_id:
        return error_transaction(payload)
    if order["status"].lower() == "processing":
        state_val = 1
    elif order["status"].lower() == "completed":
        state_val = 2
    elif order["status"].lower() == "cancelled":
        state_val = -1
    elif order["status"].lower() == "refunded":
        state_val = -2
    else:
        return error_transaction(payload)
    return {
        "id": payload.get("id"),
        "result": {
            "create_time": order.get("create_time", 0),
            "perform_time": order.get("perform_time", 0),
            "cancel_time": order.get("cancel_time", 0),
            "transaction": "000" + str(order_id),
            "state": state_val,
            "reason": order.get("cancel_reason")
        },
        "error": None
    }

def cancel_transaction(payload):
    params = payload.get("params", {})
    transaction_id = params.get("id")
    order = get_order_by_transaction(transaction_id)
    if not order:
        return error_transaction(payload)
    order_id = order["order_id"]
    if order.get("transaction_id") != transaction_id:
        return error_transaction(payload)
    cancel_time = current_timestamp()
    if order["status"].lower() in ["pending", "processing"]:
        new_status = "cancelled"
        state_val = -1
    elif order["status"].lower() == "completed":
        new_status = "refunded"
        state_val = -2
    elif order["status"].lower() in ["cancelled", "refunded"]:
        cancel_time = order.get("cancel_time", cancel_time)
        state_val = -1 if order["status"].lower() == "cancelled" else -2
    else:
        return error_cancel(payload)
    update_order(order_id, {
        "status": new_status,
        "cancel_time": cancel_time,
        "cancel_reason": params.get("reason")
    })
    return {
        "id": payload.get("id"),
        "result": {
            "transaction": "000" + str(order_id),
            "cancel_time": cancel_time,
            "state": state_val
        }
    }

def change_password(payload):
    params = payload.get("params", {})
    new_password = params.get("password")
    if new_password != MERCHANT_KEY:
        return {
            "id": payload.get("id"),
            "result": {"success": True},
            "error": None
        }
    return error_password(payload)

def get_order_by_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE transaction_id = %s", (transaction_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

# ============================================================================
# Основной обработчик callback PayMe
# ============================================================================
@app.route('/callback', methods=['POST'])
def callback():
    try:
        raw_data = request.data.decode('utf-8')
        logging.info("Received raw data: %s", raw_data)
        payload = json.loads(raw_data)
    except Exception as e:
        logging.error("JSON parse error: %s", str(e))
        response = error_invalid_json()
        logging.info("Response: %s", json.dumps(response))
        return jsonify(response)
    
    logging.info("Headers: %s", dict(request.headers))
    logging.info("Payload: %s", payload)
    
    # Проверяем, что в параметрах передан merchant, и он соответствует нашему PAYME_MERCHANT_ID
    merchant_in_payload = payload.get("params", {}).get("merchant")
    if merchant_in_payload and merchant_in_payload != PAYME_MERCHANT_ID:
        logging.warning("Merchant ID mismatch: payload merchant '%s' != PAYME_MERCHANT_ID '%s'", merchant_in_payload, PAYME_MERCHANT_ID)
        response = error_authorization(payload)
        return jsonify(response)
    
    # Проверка авторизации через заголовок
    auth_header = request.headers.get("Authorization", "")
    expected_auth = "Basic " + base64.b64encode(f"Paycom:{MERCHANT_KEY}".encode()).decode()
    if auth_header.strip() != expected_auth.strip():
        response = error_authorization(payload)
        logging.warning("Authorization failed. Provided: %s, Expected: %s", auth_header, expected_auth)
        logging.info("Response: %s", json.dumps(response))
        return jsonify(response)
    
    method = payload.get("method", "")
    if method == "CheckPerformTransaction":
        response = check_perform_transaction(payload)
    elif method == "CreateTransaction":
        response = create_transaction(payload)
    elif method == "PerformTransaction":
        response = perform_transaction(payload)
    elif method == "CheckTransaction":
        response = check_transaction(payload)
    elif method == "CancelTransaction":
        response = cancel_transaction(payload)
    elif method == "ChangePassword":
        response = change_password(payload)
    else:
        response = error_unknown_method(payload)
    
    logging.info("Response: %s", json.dumps(response))
    return jsonify(response)

# ============================================================================
# Маршрут для GET-запросов по /payment – возвращает HTML-форму оплаты
@app.route('/payment', methods=['GET'])
def payment_form():
    order_id_param = request.args.get("order_id", "")
    amount = request.args.get("amount", "")
    merchant = request.args.get("merchant", "")
    callback = request.args.get("callback", "")
    lang = request.args.get("lang", "ru")
    description = request.args.get("description", "Оплата заказа")
    signature = request.args.get("signature", "")
    
    if not callback or callback.lower() == "none":
        callback = CALLBACK_BASE_URL if CALLBACK_BASE_URL else ""
    
    html_form = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Оплата за заказ</title>
</head>
<body>
    <h1>Оплата за заказ</h1>
    <form action="{CHECKOUT_URL}" method="POST">
        <input type="hidden" name="account[order_id]" value="{order_id_param}">
        <input type="hidden" name="amount" value="{amount}">
        <input type="hidden" name="merchant" value="{merchant}">
        <input type="hidden" name="callback" value="{callback}">
        <input type="hidden" name="lang" value="{lang}">
        <input type="hidden" name="description" value="{description}">
        <input type="hidden" name="signature" value="{signature}">
        <button type="submit">Оплатить</button>
    </form>
    <p>Order ID (merchant_trans_id): {order_id_param}</p>
</body>
</html>"""
    return html_form

# Обработка URL с завершающим слэшем
@app.route('/payment/', methods=['GET'])
def payment_form_slash():
    return payment_form()

# ============================================================================
# Запуск сервера
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
