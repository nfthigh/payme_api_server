import os
import json
import time
import base64
import logging
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

# Загружаем переменные окружения из файла .env
load_dotenv()

# Для Click сервер оставляем MERCHANT_ID (не меняем его), а для PayMe используем отдельную переменную
PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID")  # новое значение для PayMe
MERCHANT_KEY = os.getenv("MERCHANT_KEY")
# Остальные переменные, используемые в PayMe‑сервисе:
CHECKOUT_URL = os.getenv("CHECKOUT_URL")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(__name__)

# Логирование: вывод в консоль (stdout)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Создаем таблицу для PayMe с отдельными именами столбцов
    create_table_query = """
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        payment_amount INTEGER NOT NULL,
        status TEXT NOT NULL,
        create_time BIGINT,
        perform_time BIGINT,
        cancel_time BIGINT,
        transaction_id TEXT,
        cancel_reason TEXT,
        items TEXT
    );
    """
    cur.execute(create_table_query)
    conn.commit()
    cur.close()
    conn.close()

init_db()

def current_timestamp():
    return int(round(time.time() * 1000))

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

# --- Функции работы с базой данных ---
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

# --- Основная бизнес-логика PayMe ---
def check_perform_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    order_id = account.get("order_id")
    if order_id is None:
        return error_order_id(payload)
    order = get_order_by_id(order_id)
    if not order:
        return error_order_id(payload)
    if order["payment_amount"] != params.get("amount"):
        return error_amount(payload)
    # Заглушка для товара "Кружка"
    stub_items = [
        {
            "discount": 0,
            "title": "Кружка",
            "price": 100000,
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
    order_id = account.get("order_id")
    if order_id is None:
        return error_order_id(payload)
    order = get_order_by_id(order_id)
    if not order:
        return error_order_id(payload)
    if order["payment_amount"] != params.get("amount"):
        return error_amount(payload)
    transaction_id = params.get("id")
    if order["status"] == "pending":
        create_time = current_timestamp()
        update_order(order_id, {
            "status": "processing",
            "create_time": create_time,
            "transaction_id": transaction_id
        })
        return {
            "id": payload.get("id"),
            "result": {
                "create_time": create_time,
                "transaction": "000" + order_id,
                "state": 1
            }
        }
    elif order["status"] == "processing":
        if order.get("transaction_id") == transaction_id:
            return {
                "id": payload.get("id"),
                "result": {
                    "create_time": order.get("create_time"),
                    "transaction": "000" + order_id,
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
    if order["status"] == "processing":
        perform_time = current_timestamp()
        update_order(order_id, {
            "status": "completed",
            "perform_time": perform_time
        })
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + order_id,
                "perform_time": perform_time,
                "state": 2
            }
        }
    elif order["status"] == "completed":
        return {
            "id": payload.get("id"),
            "result": {
                "transaction": "000" + order_id,
                "perform_time": order.get("perform_time"),
                "state": 2
            }
        }
    elif order["status"] in ["cancelled", "refunded"]:
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
    if order["status"] == "processing":
        state = 1
    elif order["status"] == "completed":
        state = 2
    elif order["status"] == "cancelled":
        state = -1
    elif order["status"] == "refunded":
        state = -2
    else:
        return error_transaction(payload)
    return {
        "id": payload.get("id"),
        "result": {
            "create_time": order.get("create_time", 0),
            "perform_time": order.get("perform_time", 0),
            "cancel_time": order.get("cancel_time", 0),
            "transaction": "000" + order_id,
            "state": state,
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
    if order["status"] in ["pending", "processing"]:
        new_status = "cancelled"
        state = -1
    elif order["status"] == "completed":
        new_status = "refunded"
        state = -2
    elif order["status"] in ["cancelled", "refunded"]:
        cancel_time = order.get("cancel_time", cancel_time)
        state = -1 if order["status"] == "cancelled" else -2
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
            "transaction": "000" + order_id,
            "cancel_time": cancel_time,
            "state": state
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
    
    # Если в запросе передаётся merchant — проверяем, что он совпадает с нашим PAYME_MERCHANT_ID
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

if __name__ == '__main__':
    port = int(os.environ["PORT"])
    app.run(host='0.0.0.0', port=port)
