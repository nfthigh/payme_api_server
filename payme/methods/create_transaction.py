import time

from payme.errors import TooManyRequests
from payme.models import MerchantTransactionsModel
from payme.loader import db
import logging


async def CreateTransaction(params: dict) -> dict:
    logging.debug('create transaction %s' % params)
    transaction_model: MerchantTransactionsModel = MerchantTransactionsModel(id=params.get('id'),
                                                                             amount=params.get('amount'),
                                                                             order_id=params.get('order_id'),
                                                                             time=params.get('time'),
                                                                             created_at_ms=int(time.time() * 1000), # in milliseconds
                                                                             state=1)

    transaction_exists = await db.get_transaction(transaction_model.order_id)
    if transaction_exists:
        if transaction_exists.id != transaction_model.id:
            raise TooManyRequests()

    await transaction_model.verify(db=db)

    transaction = await db.get_transaction_by_id(transaction_model.id)
    if not transaction:
        transaction = await db.create_transaction(transaction_model)
    response: dict = {
        "result": {
            "create_time": transaction.created_at_ms,
            "transaction": transaction.transaction_id,
            "state": transaction.state,
        }
    }

    return response
