import time
from payme.errors import PerformTransactionDoesNotExist
from payme.models import MerchantTransactionsModel
from payme.loader import db


async def CancelTransaction(params: dict) -> dict:
    try:
        transaction: MerchantTransactionsModel = await db.get_transaction_by_id(params.get('id'))
        if transaction is None:
            raise PerformTransactionDoesNotExist()
        if transaction.cancel_time == 0 or transaction.cancel_time is None:
            transaction.cancel_time = int(time.time() * 1000)
        if transaction.perform_time is None:
            transaction.state = -1
        if transaction.perform_time != 0 and transaction.perform_time is not None:
            transaction.state = -2
        transaction.reason = str(params.get("reason"))
        await db.update_transaction(transaction)
    except PerformTransactionDoesNotExist:
        raise PerformTransactionDoesNotExist('transaction does not exist')

    response: dict = {
        "result": {
            "state": transaction.state,
            "cancel_time": transaction.cancel_time,
            "transaction": transaction.transaction_id,
            "reason": int(transaction.reason),
        }
    }
    return response

