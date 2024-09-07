import time
from datetime import datetime

from payme.errors import PerformTransactionDoesNotExist
from payme.loader import db
import logging


async def PerformTransaction(params: dict) -> dict:
    """Perform transaction which is resposible for payment process and updating transaction state
    if payment is successful, it will update transaction state to 2 and will send message to user"""
    try:
        transaction = await db.get_transaction_by_id(params.get('id'))

        if transaction is None:
            raise PerformTransactionDoesNotExist('transaction does not exist', rq_id=params.get('id'))
        msg = {
            'uz': "To'lov muvaffaqiyatli amalga oshirildi ✅"
        }
        logging.info(transaction.model_dump())
        if transaction.state != 2:
            order = await db.get_order(transaction.order_id)
            user_id = order.user_id
            # todo do what you want with user_id and msg when payment is successful

            try:
                pass # send message to user
                logging.info(f'{user_id} paid for {transaction.amount} ')
                # todo do what you want with user_id and msg when payment is successful

            except Exception as e:
                logging.error(e)
                raise e

        transaction.state = 2
        transaction.updated_at = datetime.now()

        if transaction.perform_time == 0 or transaction.perform_time is None:
            transaction.perform_time = int(time.time() * 1000)

        await db.update_transaction(transaction)
        response: dict = {
            "result": {
                "perform_time": transaction.perform_time,
                "transaction": transaction.transaction_id,
                "state": transaction.state,
            }
        }

    except Exception as e:
        logging.error(e)
        raise e

    return response
