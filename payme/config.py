from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()


class Config(BaseModel):
    postgres_url: str = os.getenv('DB_URL')
    payme_account: str = 'order_id'
    payme_min_amount: int = os.getenv('PAYME_MIN_AMOUNT') # in tyiyn
    payme_url: str = 'https://checkout.paycom.uz'
    payme_test_url: str = 'https://test.paycom.uz'
    payme_id: str = os.getenv('PAYME_ID')
    payme_test_key: str = os.getenv('PAYME_TEST_KEY')
    payme_key: str = os.getenv('PAYME_KEY')

settings = Config()
