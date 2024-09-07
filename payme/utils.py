import base64
import binascii
import logging
from payme.config import settings
from payme.errors import PermissionDenied



def get_params(params: dict) -> dict:
    """
    Use this function to get the parameters from the payme.
    """
    account: dict = params.get("account")

    clean_params: dict = {}
    clean_params["id"] = params.get("id")
    clean_params["time"] = params.get("time")
    clean_params["amount"] = params.get("amount")
    clean_params["reason"] = params.get("reason")
    clean_params['from'] = params.get('from')
    clean_params['to'] = params.get('to')

    if params.get("reason") is not None:
        clean_params["reason"] = params.get("reason")

    if account is not None:
        account_name: str = settings.payme_account
        clean_params[settings.payme_account] = account[account_name]

    return clean_params


def authorize(password: str) -> bool:
    """
    Authorize the Merchant.
    :param password: string -> Merchant authorization password
    """
    is_payme: bool = False
    error_message: str = ""

    if not isinstance(password, str):
        error_message = "Request from an unauthorized source!"

        raise PermissionDenied(error_message)

    password = password.split()[-1]

    try:
        password = base64.b64decode(password).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError):
        error_message = "Error when authorize request to merchant, unable to decode!"

        raise PermissionDenied(error_message=error_message)

    merchant_key = password.split(':')[-1]

    if merchant_key == settings.payme_key or merchant_key == settings.payme_test_key\
            or merchant_key == settings.speaklish_payme_key or merchant_key == settings.speaklish_payme_test_key:
        is_payme = True

    if is_payme is False:
        raise PermissionDenied(
            error_message="Unavailable data for unauthorized users!"
        )

    return is_payme




logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s]  %(filename)s -> %(funcName)s:%(lineno)d - %(levelname)s \n---> %(message)s',
    datefmt='%d-%m-%Y %H:%M:%S')
