from typing import Union

import asyncpg
from asyncpg import Connection, Record
from asyncpg.pool import Pool
from .models import MerchantTransactionsModel, Orders


class Database:
    def __init__(self, dsn: str):
        self.pool: Pool | None = None
        self.dsn = dsn

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            # dsn=config.Config.postgres_url
            dsn=self.dsn
        )

    async def execute(self, command: str, *args: object,
                      fetch: bool = False,
                      fetchval: bool = False,
                      fetchrow: bool = False,
                      execute: bool = False
                      ) -> object | Record | list[Record] | None:
        async with self.pool.acquire() as connection:
            connection: Connection
            async with connection.transaction():
                if fetch:
                    result = await connection.fetch(command, *args)
                elif fetchval:
                    result = await connection.fetchval(command, *args)
                elif fetchrow:
                    result = await connection.fetchrow(command, *args)
                elif execute:
                    result = await connection.execute(command, *args)
            return result

    """    class MerchantTransactionsModel(BaseModel):
        id: str
        transaction_id: Optional[str] = Field(default_factory=uuid.uuid4, alias="transaction_id")
        order_id: Optional[int] = None
        amount: Optional[float] = None
        time: Optional[int] = None
        perform_time: Optional[int] = None
        cancel_time: Optional[int] = None
        state: Optional[int] = 1
        reason: Optional[str] = None
        created_at_ms: Optional[str] = None
        created_at: datetime = datetime.now()
        updated_at: Optional[datetime] = None"""

    async def get_transaction(self, order_id):
        query = "SELECT * FROM payme_transactions WHERE order_id = $1"
        res = await self.execute(query, order_id, fetchrow=True)
        if res:
            return MerchantTransactionsModel(**res)

    async def get_transaction_by_id(self, _id: str):
        query = "SELECT * FROM payme_transactions WHERE id = $1"
        res = await self.execute(query, _id, fetchrow=True)
        if res:
            return MerchantTransactionsModel(**res)

    async def update_transaction(self, transaction: MerchantTransactionsModel) -> None:
        query = """UPDATE payme_transactions SET transaction_id = $1,\
                    order_id = $2, amount = $3, 
                    time = $4, perform_time = $5,
                    cancel_time = $6, state = $7, reason = $8,
                    created_at_ms = $9, created_at = $10, updated_at = $11 \
                    where id = $12"""
        await self.execute(query, str(transaction.transaction_id), transaction.order_id, transaction.amount,
                           transaction.time, transaction.perform_time, transaction.cancel_time, transaction.state,
                           transaction.reason, transaction.created_at_ms, transaction.created_at,
                           transaction.updated_at,
                           transaction.id, execute=True)

    async def get_order(self, order_id: int) -> Union[Orders, None]:
        query = "SELECT * FROM orders WHERE order_id = $1"
        res = await self.execute(query, order_id, fetchrow=True)
        if res:
            return Orders(**res)

    async def create_transaction(self, transaction: MerchantTransactionsModel) -> MerchantTransactionsModel:
        query = ("INSERT INTO payme_transactions (id,transaction_id, order_id, amount, created_at_ms"
                 ",time, state, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, now()) RETURNING *")

        res = await self.execute(query, transaction.id,
                                 str(transaction.transaction_id),
                                 transaction.order_id,
                                 transaction.amount,
                                 transaction.created_at_ms,
                                 transaction.time,
                                 transaction.state,
                                 fetchrow=True)
        return MerchantTransactionsModel(**res)

    async def range_transactions(self, _from: int, _to: int):
        query = "SELECT * FROM payme_transactions WHERE created_at_ms BETWEEN $1 AND $2"
        return await self.execute(query, _from, _to, fetch=True)

    async def create_order(self, user_id: int, amount: float, session_quantity) -> Orders:
        query = ("INSERT INTO orders (user_id, price, session_quantity, created_at) VALUES ($1, $2, $3, "
                 "now()) RETURNING *")
        res = await self.execute(query, user_id, amount, session_quantity, fetchrow=True)
        return Orders(**res)
