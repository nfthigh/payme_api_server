from payme.loader import db


async def GetStatement(params: dict) -> dict:
    time_from = params['from']
    time_to = params['to']
    transactions: list = await db.range_transactions(time_from, time_to)
    trans = []
    if len(transactions) == 0:
        return {"result": {"transactions": []}}
    for row in transactions:
        res = {
            'id': row['id'],
            'time': row['time'],
            'amount': row['amount'],
            'account': {
                'order_id': row['order_id']
            },
            'create_time': int(row['created_at'].timestamp() * 1000),
            'perform_time': row['perform_time'],
            'cancel_time': row['cancel_time'],
            "transaction": "",
            "state": row['state'],
            "reason": row['reason']
        }
        if row['perform_time'] is None:
            res['perform_time'] = 0
        if row['cancel_time'] is None:
            res['cancel_time'] = 0
        if row['reason'] is not None:
            res['reason'] = int(row['reason'])
        trans.append(res)

    return {
        "result": {
            "transactions": trans
        }
    }
