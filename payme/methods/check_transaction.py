from payme.errors import  TransactionDoesNotExist
from payme.models import MerchantTransactionsModel
from payme.loader import db
import logging


async def CheckTransaction(params: dict) -> dict:
    try:
        transaction: MerchantTransactionsModel = await db.get_transaction_by_id(params.get('id'))
        if transaction is None:
            raise TransactionDoesNotExist()
        if transaction.cancel_time is None:
            transaction.cancel_time = 0

        if transaction.perform_time is None:
            transaction.perform_time = 0
        response = {
            "result": {
                "create_time": transaction.created_at_ms,
                "perform_time": transaction.perform_time,
                "cancel_time": transaction.cancel_time,
                "transaction": transaction.transaction_id,
                "state": transaction.state,
                "reason": None,
            }
        }
        if transaction.reason is not None:
            response["result"]["reason"] = int(transaction.reason)

    except TransactionDoesNotExist:
        raise TransactionDoesNotExist('transaction does not exist with %s' % params.get('id'))

    except Exception as e:
        logging.info('error during check transaction in db %s %s' % (e, params.get('id')))
        return {}
    return response
