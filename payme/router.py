import logging

from payme.methods import (
    CheckTransaction,
    CreateTransaction,
    CancelTransaction,
    PerformTransaction,
    CheckPerformTransaction,
    GetStatement,
    generate_link
)
from payme.errors import MethodNotFound
from fastapi import APIRouter, Request
from payme.utils import get_params, authorize
from payme.loader import db
from typing import Callable


payme_router = APIRouter()
payment_router = APIRouter(prefix="/payment")

available_methods: dict = {
    "CheckTransaction": CheckTransaction,
    "CreateTransaction": CreateTransaction,
    "CancelTransaction": CancelTransaction,
    "PerformTransaction": PerformTransaction,
    "CheckPerformTransaction": CheckPerformTransaction,
    'GetStatement': GetStatement,
}


@payme_router.post("/payme", tags=["merchant"])
async def merchant(request: Request) -> dict:
    try:
        password = request.headers.get('Authorization')
        if authorize(password):
            incoming_data = await request.json()
            incoming_method: Callable = available_methods[incoming_data.get("method", 'Not found')]
            logging.info(f"Incoming {incoming_data}")
            params = incoming_data.get("params")
            return await incoming_method(get_params(params))
    except KeyError as e:
        logging.error(e)
        raise MethodNotFound()


@payment_router.post("/generate_link", tags=["merchant"],
                     include_in_schema=False)
async def generate_link_func(request: Request, order_id: int, amount: int) -> dict:
    """send data to generate link for payment for payme speaklish
    body: {
        "order_id": 1,
        "amount": 10000
    }

    """
    try:
        links = await generate_link(order_id=order_id, amount=amount)
        return {
            "payme_link": links[0]
        }

    except Exception as e:
        raise e


@payment_router.get("/create_order", tags=["merchant"], name="create_order", description="Create order")
async def create_order_func(user_id: int, price: float, quantity: int = 10) -> dict:
    try:
        new_order = await db.create_order(user_id=user_id, amount=price,
                                          session_quantity=quantity)
        checkout_url = await generate_link(order_id=new_order.order_id, amount=new_order.price * quantity)
        return {**new_order.model_dump(), "amount": new_order.price* new_order.session_quantity,"url": checkout_url[0], }
    except Exception as e:
        raise e
