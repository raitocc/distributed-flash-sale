from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    product_service_url: str  # 新增：商品服务的通信地址

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()