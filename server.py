import os
import json
import time
import base64
import logging
import sys
import hashlib
import requests
from urllib.parse import quote, unquote
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

# Загружаем переменные окружения из файла .env
load_dotenv()

# Параметры Payme
PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID")  # Например: 6758399fd33fb8548cede2a7
MERCHANT_KEY = os.getenv("MERCHANT_KEY")            # Например: IA5W7ZF%&poyI9C#qXiIaijDsTSMaQ9S%GAT
CHECKOUT_URL = os.getenv("CHECKOUT_URL", "https://checkout.paycom.uz")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL")    # Должен быть, например: https://payme-api-server.onrender.com/callback
DATABASE_URL = os.getenv("DATABASE_URL")

# Параметры для уведомлений через Telegram (если нужно)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

app = Flask(__name__)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Словарь с данными о товарах
PRODUCTS_DATA = {
    "Кружка": {
        "SPIC": "06912001036000000",
        "PackageCode": "1184747",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Брелок": {
        "SPIC": "07117001015000000",
        "PackageCode": "1156259",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Кепка": {
        "SPIC": "06506001022000000",
        "PackageCode": "1324746",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Визитка": {
        "SPIC": "04911001003000000",
        "PackageCode": "1156221",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Футболка": {
        "SPIC": "06109001001000000",
        "PackageCode": "1124331",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Худи": {
        "SPIC": "06212001012000000",
        "PackageCode": "1238867",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Пазл": {
        "SPIC": "04811001019000000",
        "PackageCode": "1748791",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Камень": {
        "SPIC": "04911001017000000",
        "PackageCode": "1156234",
        "CommissionInfo": {"TIN": "307022362"}
    },
    "Стакан": {
        "SPIC": "07013001008000000",
        "PackageCode": "1345854",
        "CommissionInfo": {"TIN": "307022362"}
    }
}

##############################
# Работа с базой данных (PostgreSQL)
##############################
def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

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
        payment_system TEXT,
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
    # Дополнительные столбцы, если нужно
    alter_list = [
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_amount INTEGER;",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS transaction_id TEXT;"
    ]
    for query in alter_list:
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

##############################
# Функции для уведомлений (Telegram)
##############################
def send_message_to_telegram(chat_id, text, token):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        logging.info("Уведомление Телеграм: %s", resp.json())
    except Exception as e:
        logging.error("Ошибка отправки в Телеграм: %s", e)

def notify_payment_success(order):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM clients WHERE user_id = %s", (order["user_id"],))
        client = cur.fetchone()
        cur.close()
        conn.close()
        if client:
            client_info = (f"Клиент: {client.get('name','N/A')} (@{client.get('username','')})\n"
                           f"Телефон: {client.get('contact','N/A')}")
        else:
            client_info = "Данные клиента не найдены."
        msg = (
            f"✅ Оплата заказа №{order['order_id']} успешно проведена!\n\n"
            f"{client_info}\n\n"
            f"Товар: {order.get('product','N/A')}\n"
            f"Кол-во: {order.get('quantity',0)}\n"
            f"Сумма: {order.get('payment_amount',0)} сум\n"
            f"Статус: {order.get('status','N/A')}"
        )
        send_message_to_telegram(order["user_id"], msg, TELEGRAM_BOT_TOKEN)
        if GROUP_CHAT_ID:
            send_message_to_telegram(GROUP_CHAT_ID, msg, TELEGRAM_BOT_TOKEN)
    except Exception as e:
        logging.error("Ошибка в notify_payment_success: %s", e)

##############################
# Функции работы с заказами (orders)
##############################
def get_order_by_merchant_trans_id(merchant_trans_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE merchant_trans_id=%s", (merchant_trans_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_order_by_transaction_id(transaction_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE transaction_id=%s", (transaction_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_order_by_id(oid):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE order_id=%s", (oid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def update_order(order_id, fields: dict):
    conn = get_db()
    cur = conn.cursor()
    set_clause = ", ".join([f"{k}=%s" for k in fields.keys()])
    vals = list(fields.values())
    vals.append(order_id)
    q = f"UPDATE orders SET {set_clause} WHERE order_id=%s"
    cur.execute(q, vals)
    conn.commit()
    cur.close()
    conn.close()

##############################
# Маршруты для тестирования
##############################
@app.route("/", methods=["GET"])
def index():
    return "<h1>Payme Server is running</h1>", 200

@app.route('/payment', methods=['GET'])
def payment_form():
    order_id_param = request.args.get("order_id", "")
    amount = request.args.get("amount", "")
    merchant = request.args.get("merchant", PAYME_MERCHANT_ID)
    # Если параметр callback отсутствует или равен "None", используем CALLBACK_BASE_URL
    callback = request.args.get("callback")
    if not callback or callback.lower() == "none":
        callback = CALLBACK_BASE_URL or "https://payme-api-server.onrender.com/callback"
    lang = request.args.get("lang", "ru")
    description = request.args.get("description", "Оплата заказа")
    html_form = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Оплата заказа</title>
</head>
<body>
    <h1>Оплата заказа</h1>
    <form action="{CHECKOUT_URL}" method="POST">
        <input type="hidden" name="account[order_id]" value="{order_id_param}">
        <input type="hidden" name="amount" value="{amount}">
        <input type="hidden" name="merchant" value="{merchant}">
        <input type="hidden" name="callback" value="{callback}">
        <input type="hidden" name="lang" value="{lang}">
        <input type="hidden" name="description" value="{description}">
        <button type="submit">Оплатить</button>
    </form>
    <p>Order ID: {order_id_param}</p>
</body>
</html>
"""
    return html_form

##############################
# Payme JSON-RPC методы
##############################
def is_amount_correct_in_sums_vs_tiyins(order_amount_sums: int, payme_amount_tiyins: int):
    return order_amount_sums * 100 == payme_amount_tiyins

def check_perform_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")
    if not merchant_trans_id:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct_in_sums_vs_tiyins(order["payment_amount"], params.get("amount", 0)):
        return error_amount(payload)
    product = order.get("product", "Товар")
    product_data = PRODUCTS_DATA.get(product, {
        "SPIC": "",
        "PackageCode": "",
        "CommissionInfo": {}
    })
    items = [{
        "discount": 0,
        "title": product,
        "price": order["payment_amount"] * 100,
        "count": order.get("quantity", 1),
        "code": product_data.get("SPIC", ""),
        "units": 796,
        "vat_percent": 12,
        "package_code": product_data.get("PackageCode", "")
    }]
    return {
        "id": payload.get("id"),
        "result": {
            "allow": True,
            "detail": {
                "receipt_type": 0,
                "items": items
            }
        },
        "error": None
    }

def create_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    merchant_trans_id = account.get("order_id")
    if not merchant_trans_id:
        return error_order_id(payload)
    order = get_order_by_merchant_trans_id(merchant_trans_id)
    if not order:
        return error_order_id(payload)
    if not is_amount_correct_in_sums_vs_tiyins(order["payment_amount"], params.get("amount", 0)):
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
                    "create_time": order.get("create_time", 0),
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
    order = get_order_by_transaction_id(transaction_id)
    if not order:
        return error_transaction(payload)
    if order["status"].lower() == "processing":
        perform_time = current_timestamp()
        update_order(order["order_id"], {
            "status": "completed",
            "perform_time": perform_time
        })
        updated_order = get_order_by_id(order["order_id"])
        notify_payment_success(updated_order)
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order["order_id"]),
                "perform_time": perform_time,
                "state": 2
            }
        }
    elif order["status"].lower() == "completed":
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + str(order["order_id"]),
                "perform_time": order.get("perform_time", 0),
                "state": 2
            }
        }
    elif order["status"].lower() in ["cancelled", "refunded"]:
        return error_cancelled_transaction(payload)
    else:
        return error_unknown(payload)

def check_transaction(payload):
    params = payload.get("params", {})
    tid = params.get("id")
    order = get_order_by_transaction_id(tid)
    if not order or order.get("transaction_id") != tid:
        return error_transaction(payload)
    if order["status"].lower() == "processing":
        state = 1
    elif order["status"].lower() == "completed":
        state = 2
    elif order["status"].lower() == "cancelled":
        state = -1
    elif order["status"].lower() == "refunded":
        state = -2
    else:
        return error_transaction(payload)
    return {
        "id": payload.get("id"),
        "result": {
            "create_time": order.get("create_time", 0),
            "perform_time": order.get("perform_time", 0),
            "cancel_time": order.get("cancel_time", 0),
            "transaction": "000" + str(order["order_id"]),
            "state": state,
            "reason": order.get("cancel_reason")
        },
        "error": None
    }

def cancel_transaction(payload):
    params = payload.get("params", {})
    tid = params.get("id")
    order = get_order_by_transaction_id(tid)
    if not order or order.get("transaction_id") != tid:
        return error_transaction(payload)
    cancel_time = current_timestamp()
    if order["status"].lower() in ["pending", "processing", "одобрен"]:
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
    update_order(order["order_id"], {
        "status": new_status,
        "cancel_time": cancel_time,
        "cancel_reason": params.get("reason")
    })
    return {
        "id": payload.get("id"),
        "result": {
            "transaction": "000" + str(order["order_id"]),
            "cancel_time": cancel_time,
            "state": state_val
        }
    }

def change_password(payload):
    params = payload.get("params", {})
    new_pass = params.get("password")
    if new_pass != MERCHANT_KEY:
        return {
            "id": payload.get("id"),
            "result": {"success": True},
            "error": None
        }
    return error_password(payload)

##############################
# Функции формирования ошибок
##############################
def error_invalid_json():
    return {
        "error": {
            "code": -32700,
            "message": {"ru": "Could not parse JSON", "uz": "Could not parse JSON", "en": "Could not parse JSON"}
        },
        "id": 0
    }

def error_authorization(payload):
    return {
        "error": {
            "code": -32504,
            "message": {"ru": "Error during authorization", "en": "Error during authorization", "uz": "Error during authorization"},
            "data": None
        },
        "id": payload.get("id", 0)
    }

def error_unknown_method(payload):
    return {
        "error": {
            "code": -32601,
            "message": {"ru": "Unknown method", "en": "Unknown method", "uz": "Unknown method"},
            "data": payload.get("method", "")
        },
        "id": payload.get("id", 0)
    }

def error_order_id(payload):
    return {
        "error": {
            "code": -31099,
            "message": {"ru": "Order number cannot be found", "uz": "Order number cannot be found", "en": "Order number cannot be found"},
            "data": "order"
        },
        "id": payload.get("id", 0)
    }

def error_amount(payload):
    return {
        "error": {
            "code": -31001,
            "message": {"ru": "Order amount is incorrect", "uz": "Order amount is incorrect", "en": "Order amount is incorrect"},
            "data": "amount"
        },
        "id": payload.get("id", 0)
    }

def error_has_another_transaction(payload):
    return {
        "error": {
            "code": -31099,
            "message": {"ru": "Other transaction for this order is in progress", "en": "Other transaction for this order is in progress", "uz": "Other transaction for this order is in progress"},
            "data": "order"
        },
        "id": payload.get("id", 0)
    }

def error_unknown(payload):
    return {
        "error": {
            "code": -31008,
            "message": {"ru": "Unknown error", "en": "Unknown error", "uz": "Unknown error"},
            "data": None
        },
        "id": payload.get("id", 0)
    }

def error_transaction(payload):
    return {
        "error": {
            "code": -31003,
            "message": {"ru": "Transaction number is wrong", "en": "Transaction number is wrong", "uz": "Transaction number is wrong"},
            "data": "id"
        },
        "id": payload.get("id", 0)
    }

def error_cancelled_transaction(payload):
    return {
        "error": {
            "code": -31008,
            "message": {"ru": "Transaction was cancelled or refunded", "en": "Transaction was cancelled or refunded", "uz": "Transaction was cancelled or refunded"},
            "data": "order"
        },
        "id": payload.get("id", 0)
    }

def error_cancel(payload):
    return {
        "error": {
            "code": -31007,
            "message": {"ru": "It is impossible to cancel. The order is completed", "en": "It is impossible to cancel. The order is completed", "uz": "It is impossible to cancel. The order is completed"},
            "data": "order"
        },
        "id": payload.get("id", 0)
    }

def error_password(payload):
    return {
        "error": {
            "code": -32400,
            "message": {"ru": "Cannot change the password", "en": "Cannot change the password", "uz": "Cannot change the password"},
            "data": "password"
        },
        "result": None,
        "id": payload.get("id", 0)
    }

##############################
# Основной callback endpoint (JSON-RPC)
##############################
@app.route('/callback', methods=['POST'])
def callback_endpoint():
    try:
        raw_data = request.data.decode('utf-8')
        logging.info("Received raw data: %s", raw_data)
        payload = json.loads(raw_data)
    except Exception as e:
        logging.error("JSON parse error: %s", e)
        resp = error_invalid_json()
        logging.info("Response: %s", json.dumps(resp))
        return jsonify(resp), 200

    logging.info("Headers: %s", dict(request.headers))
    logging.info("Payload: %s", payload)

    # Авторизация через HTTP Basic (Paycom:MERCHANT_KEY)
    auth_header = request.headers.get("Authorization", "")
    expected = "Basic " + base64.b64encode(f"Paycom:{MERCHANT_KEY}".encode()).decode()
    if auth_header.strip() != expected.strip():
        resp = error_authorization(payload)
        logging.warning("Auth failed. Provided: %s, Expected: %s", auth_header, expected)
        logging.info("Response: %s", resp)
        return jsonify(resp), 200

    method = payload.get("method", "")
    if method == "CheckPerformTransaction":
        resp = check_perform_transaction(payload)
    elif method == "CreateTransaction":
        resp = create_transaction(payload)
    elif method == "PerformTransaction":
        resp = perform_transaction(payload)
    elif method == "CheckTransaction":
        resp = check_transaction(payload)
    elif method == "CancelTransaction":
        resp = cancel_transaction(payload)
    elif method == "ChangePassword":
        resp = change_password(payload)
    else:
        resp = error_unknown_method(payload)

    logging.info("Response: %s", json.dumps(resp))
    return jsonify(resp), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", "5000"))
    app.run(host='0.0.0.0', port=port)
