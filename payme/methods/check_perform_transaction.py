
from payme.errors import  OrderDoesNotExist, IncorrectAmount
from payme.loader import db


async def CheckPerformTransaction(params: dict) -> dict:
    order_id = int(params['order_id'])
    amount = float(params['amount'])

    order_details = await db.get_order(order_id)
    if order_details is None:
        raise OrderDoesNotExist(error_message={'account': {'order_id': order_id}})

    if order_details.price * order_details.session_quantity * 100 != amount:
        raise IncorrectAmount(error_message={'account': {'order_id': order_id}})

    details: dict = {
        'receipt_type': 0,
        "items": [{
            'title': f"Speaklish Sessions {order_details.user_id}",
            'price': order_details.price * 100,
            "count": order_details.session_quantity,
            'code': '10318001001000000',
            'package_code': '1501319',
            'vat_percent': 0
        }]
    }

    response = {
        "result": {
            "allow": True,
            'detail': details
        }
    }
    return response
