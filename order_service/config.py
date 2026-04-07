from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    product_service_url: str
    inventory_service_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_flash_sale_topic: str = "flash-sale-orders"
    kafka_consumer_group_id: str = "flash-sale-order-service"
    internal_service_timeout_seconds: int = 5
    flash_sale_order_status_ttl_seconds: int = 86400
    flash_sale_user_mark_ttl_seconds: int = 86400
    flash_sale_consumer_max_retries: int = 3
    flash_sale_consumer_retry_interval_seconds: int = 2
    order_id_worker_id: int = 1

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def kafka_bootstrap_server_list(self) -> list[str]:
        # 为什么把字符串拆分逻辑收口在配置层：
        # 业务代码真正关心的是“有哪些 broker 可以连接”，而不是环境变量到底是逗号分隔还是单个值。
        # 把兼容性细节放在配置对象里，能避免 producer / consumer 两边重复做同一份解析。
        return [item.strip() for item in self.kafka_bootstrap_servers.split(",") if item.strip()]


settings = Settings()
