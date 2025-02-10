import os
import json
import time
import base64
import logging
import sys
from flask import Flask, request, jsonify

import psycopg2
from psycopg2.extras import RealDictCursor

from dotenv import load_dotenv

load_dotenv()

PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID")       # 6758399fd33fb8548cede2a7
PAYME_MERCHANT_KEY = os.getenv("PAYME_MERCHANT_KEY")     # IA5W7ZF%&poyI9C#qXiIaijDsTSMaQ9S%GAT

DATABASE_URL = os.getenv("DATABASE_URL")
CHECKOUT_URL = "https://checkout.paycom.uz"
app = Flask(__name__)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        create_table = """
        CREATE TABLE IF NOT EXISTS payme_orders (
            order_id TEXT PRIMARY KEY,
            total_amount INTEGER NOT NULL,
            status TEXT NOT NULL,
            create_time BIGINT,
            perform_time BIGINT,
            cancel_time BIGINT,
            transaction_id TEXT,
            cancel_reason TEXT,
            items TEXT
        );
        """
        cur.execute(create_table)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("Таблица payme_orders создана или уже существует.")
    except Exception as e:
        logging.error("Ошибка инициализации payme_orders: %s", e)

init_db()

def current_timestamp():
    return int(round(time.time() * 1000))

def get_order_by_id(order_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM payme_orders WHERE order_id=%s", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    return order

def error_order_not_found(payload):
    return {
        "error": {
            "code": -31099,
            "message": {
                "ru": "Order not found",
                "uz": "Order not found",
                "en": "Order not found"
            },
            "data": "order"
        },
        "result": None,
        "id": payload.get("id", 0)
    }

#############################################
# Эндпоинт /payme_form - генерируем HTML-форму
#############################################
@app.route('/payme_form', methods=['GET'])
def payme_form():
    order_id = request.args.get("order_id")
    if not order_id:
        return "No order_id provided", 400
    order = get_order_by_id(order_id)
    if not order:
        return "Order not found", 404
    # Генерируем авто-submit HTML-форму
    total_amount = order["total_amount"]
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Оплата заказа {order_id}</title>
</head>
<body onload="document.forms[0].submit()">
    <form action="{CHECKOUT_URL}" method="POST">
        <input type="hidden" name="account[order_id]" value="{order_id}">
        <input type="hidden" name="amount" value="{total_amount}">
        <input type="hidden" name="merchant" value="{PAYME_MERCHANT_ID}">
        <input type="hidden" name="callback" value="{request.url_root}callback?order_id={order_id}">
        <input type="hidden" name="lang" value="ru">
        <input type="hidden" name="description" value="Оплата заказа {order_id} через Payme">
    </form>
    <p>Переадресация на Payme...</p>
</body>
</html>
"""
    return html

#############################################
# Эндпоинт /callback - обрабатывает запросы Payme
#############################################
@app.route('/callback', methods=['POST'])
def payme_callback():
    raw_data = request.data.decode('utf-8')
    logging.info("Received raw data: %s", raw_data)
    payload = None
    try:
        payload = json.loads(raw_data)
    except:
        return jsonify(error_invalid_json()), 200

    # Проверка авторизации
    headers = dict(request.headers)
    auth_header = headers.get("Authorization", "")
    expected = "Basic " + base64.b64encode(f"Paycom:{PAYME_MERCHANT_KEY}".encode()).decode()
    if auth_header.strip() != expected.strip():
        resp = error_authorization(payload)
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

    logging.info("Response: %s", resp)
    return jsonify(resp), 200

#############################################
# Заглушки методов Payme
#############################################
def check_perform_transaction(payload):
    params = payload.get("params", {})
    account = params.get("account", {})
    order_id = account.get("order_id")
    if not order_id:
        return error_order_not_found(payload)
    order = get_order_by_id(order_id)
    if not order:
        return error_order_not_found(payload)
    if order["total_amount"] != params.get("amount"):
        return error_amount(payload)
    # Возврат заглушки detail.items, SKU берем из SPIC
    # Для Payme SKU передаётся как code, 
    # здесь можно поставить order['something'] или заглушку
    items = [
      {
        "discount": 0,
        "title": "Мой Товар",
        "price": order["total_amount"],  # например
        "count": 1,
        "code": "06912001036000000",  # SKU/код
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
                "items": items
            }
        }
    }

def create_transaction(payload):
    # ...
    return {
        "id": payload.get("id"),
        "error": {
            "code": -31008,
            "message": {"ru":"Not implemented", "en":"Not implemented"},
            "data": None
        }
    }

def perform_transaction(payload):
    # ...
    return {
        "id": payload.get("id"),
        "error": {
            "code": -31008,
            "message": {"ru":"Not implemented", "en":"Not implemented"},
            "data": None
        }
    }

def check_transaction(payload):
    # ...
    return {
        "id": payload.get("id"),
        "error": {
            "code": -31008,
            "message": {"ru":"Not implemented", "en":"Not implemented"},
            "data": None
        }
    }

def cancel_transaction(payload):
    # ...
    return {
        "id": payload.get("id"),
        "error": {
            "code": -31008,
            "message": {"ru":"Not implemented", "en":"Not implemented"},
            "data": None
        }
    }

def change_password(payload):
    # ...
    return {
        "id": payload.get("id"),
        "error": {
            "code": -31008,
            "message": {"ru":"Not implemented", "en":"Not implemented"},
            "data": None
        }
    }

#############################################
# Ошибки Payme
#############################################
def error_invalid_json():
    return {
        "error": {
            "code": -32700,
            "message": {"ru":"Could not parse JSON","uz":"Could not parse JSON","en":"Could not parse JSON"}
        },
        "id": 0
    }

def error_authorization(payload):
    return {
        "error": {
            "code": -32504,
            "message": {"ru":"Error during authorization","en":"Error during authorization","uz":"Error during authorization"},
            "data": None
        },
        "id": payload.get("id", 0)
    }

def error_unknown_method(payload):
    return {
        "error":{
            "code": -32601,
            "message":{"ru":"Unknown method","en":"Unknown method","uz":"Unknown method"},
            "data":payload.get("method", "")
        },
        "id": payload.get("id", 0)
    }

def error_amount(payload):
    return {
        "error":{
            "code": -31001,
            "message":{"ru":"Order amount is incorrect", "en":"Order amount is incorrect","uz":"Order amount is incorrect"},
            "data":"amount"
        },
        "id": payload.get("id", 0)
    }

#############################################
# Запуск сервера локально
#############################################
if __name__ == '__main__':
    from waitress import serve
    port = 5000
    # app.run(host='0.0.0.0', port=port)  # или waitress
    serve(app, host='0.0.0.0', port=port)
