from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    # redis_url 设置默认值
    redis_url: str = "redis://127.0.0.1:6379/0"
    # 正常商品详情缓存 TTL
    product_cache_ttl_seconds: int = 3600
    # 为正常缓存增加随机抖动
    product_cache_ttl_jitter_seconds: int = 600
    # 不存在商品的空值缓存 TTL 通常应该更短
    product_null_cache_ttl_seconds: int = 120
    # 空值缓存同样做抖动，避免大量恶意请求命中的空 Key 在同一秒失效后重新冲击数据库
    product_null_cache_ttl_jitter_seconds: int = 60
    # 分布式锁过期时间
    product_cache_lock_seconds: int = 10
    # 等待其他请求回填缓存的最长时间
    product_cache_lock_wait_ms: int = 1500
    # 等待期间的轮询间隔
    product_cache_lock_retry_ms: int = 50
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
