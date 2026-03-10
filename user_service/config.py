from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440 # 默认一天

    # 告诉 Pydantic 去当前目录下找 .env 文件
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# 实例化配置对象，后续所有文件都引入这个 settings
settings = Settings()