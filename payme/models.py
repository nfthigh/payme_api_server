from datetime import datetime
from typing import Optional

from uuid import uuid4, UUID
from .config import settings
from .errors import IncorrectAmount, OrderDoesNotExist

from pydantic import BaseModel, Field




class MerchantTransactionsModel(BaseModel):
    id: str
    transaction_id: UUID = Field(default_factory=uuid4, alias="transaction_id")
    order_id: Optional[int]
    amount: Optional[float]
    time: Optional[int] = None
    perform_time: Optional[int] = None
    cancel_time: Optional[int] = None
    state: Optional[int] = 0
    reason: Optional[str] = None
    created_at_ms: Optional[int] = None
    created_at: datetime = None
    updated_at: Optional[datetime] = None

    async def verify(self, db: Database):
        query = "SELECT price*session_quantity FROM orders WHERE order_id = $1"
        res_price = await db.execute(query, self.order_id, fetchval=True)
        if res_price:
            if res_price*100 != self.amount or settings.payme_min_amount > res_price * 100:
                raise IncorrectAmount('incorrect amount')
            return True
        raise OrderDoesNotExist(error_message={'account': {'order_id': self.order_id}})


class Orders(BaseModel):
    order_id: Optional[int] = None
    user_id: int
    price: float
    session_quantity: Optional[int] = 10
    created_at: datetime = datetime.now()
    updated_at: Optional[datetime] = None

    async def verify(self, db: 'Database'):
        query = "SELECT price * session_quantity FROM orders WHERE order_id = $1"
        res_sum = await db.execute(query, self.order_id, fetchval=True)
        if res_sum:
            if res_sum != self.price*self.session_quantity:
                raise IncorrectAmount('incorrect amount')
            return True
        raise OrderDoesNotExist(error_message={'account': {'order_id': self.order_id}})
