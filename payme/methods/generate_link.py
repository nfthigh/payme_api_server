import base64
from payme.config import settings
import logging

PAYME_ID = settings.payme_id

PAYME_ACCOUNT = settings.payme_account
PAYME_URL = settings.payme_url


async def generate_link(order_id: int, amount: float, fake: bool = False) -> str:
    """
            GeneratePayLink for each order.
            :param order_id: order_id
            :param amount: amount of order
            :param fake: fake or not
            :return: link string

    """

    PAYME_URL = settings.payme_url
    logging.info(f'generate_link: {order_id}, {amount}, fake={fake}')
    if fake:
        PAYME_URL = settings.payme_test_url
    GENERATED_PAY_LINK: str = "{payme_url}/{encode_params}"
    PARAMS: str = 'm={payme_id};ac.{payme_account}={order_id};a={amount};c={callback}'

    PARAMS = PARAMS.format(
        payme_id=PAYME_ID,
        payme_account=PAYME_ACCOUNT,
        order_id=order_id,
        amount=amount * 100,
        callback='' # callback url for your convience
    )

   

    encode_params = base64.b64encode(PARAMS.encode("utf-8"))

    return GENERATED_PAY_LINK.format(
        payme_url=PAYME_URL,
        encode_params=str(encode_params, 'utf-8')
    )