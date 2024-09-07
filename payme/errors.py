from fastapi import HTTPException
from typing import Union


class BasePaymeException(HTTPException):
    status_code = 200
    error_code = None
    message = None
    request_id = None

    def __init__(self, error_message: Union[str, dict] = None, rq_id: str = None):
        self.error: dict = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "data": error_message,


            }}


class PermissionDenied(BasePaymeException):
    status_code = 200
    error_code = -32504
    message = "Permission denied"


class MethodNotFound(BasePaymeException):
    status_code = 405
    error_code = -32601
    message = 'Method not found'


class OrderDoesNotExist(BasePaymeException):
    status_code = 200
    error_code = -31050
    message = {
        "uz": "Buyurtma topilmadi",
        "ru": "Заказ не существует",
        "en": "Order does not exist"
    }


class IncorrectAmount(BasePaymeException):
    """custom exception for incorrect amount"""
    status_code = 200
    error_code = -31001
    message = {
        'ru': 'Неверная сумма',
        'uz': 'Incorrect amount',
        'en': 'Incorrect amount',
    }


class PerformTransactionDoesNotExist(BasePaymeException):
    status_code = 200
    error_code = -31050
    message = {
        "uz": "Buyurtma topilmadi",
        "ru": "Заказ не существует",
        "en": "Order does not exist"
    }


class TransactionDoesNotExist(BasePaymeException):
    status_code = 200
    error_code = -31003
    message = {
        "uz": "transaction topilmadi",
        "ru": "транзакция не существует",
        "en": "transaction does not exist"
    }


class TooManyRequests(BasePaymeException):
    status_code = 200
    error_code = -31099
    message = {
        "uz": "Buyurtma tolovni amalga oshirish jarayonida",
        "ru": "Транзакция в очереди",
        "en": "Order payment status is queued"
    }
