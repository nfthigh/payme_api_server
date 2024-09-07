from payme.postgres import Database
from payme.config import settings

db = Database(settings.postgres_url)
