from pydantic import BaseSettings

class Settings(BaseSettings):
    app_name: str = "ShopSense API"
    database_url: str = "sqlite:///./shop_sense.db"

settings = Settings()
