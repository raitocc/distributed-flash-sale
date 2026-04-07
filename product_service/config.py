from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 保留历史的 DATABASE_URL 作为兼容兜底：
    # 真正启用读写分离时，会优先读取 WRITE_DATABASE_URL / READ_DATABASE_URL。
    database_url: str = ""
    # 写库连接串：创建商品等写操作必须命中主库，否则无法保证数据源权威性。
    write_database_url: Optional[str] = None
    # 读库连接串：商品列表、详情查询等读操作走从库，用来分担主库压力并演示读写分离。
    read_database_url: Optional[str] = None
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

    @property
    def effective_write_database_url(self) -> str:
        # 为什么通过 property 做“最终生效配置”：
        # 读写分离是新能力，但项目里已经有单库模式、测试模式和 Docker 模式。
        # 统一在配置层做兼容收敛，可以避免业务代码四处判断“到底该读哪个变量”。
        if self.write_database_url:
            return self.write_database_url
        if self.database_url:
            return self.database_url
        raise ValueError("未配置写库连接串：请提供 WRITE_DATABASE_URL 或 DATABASE_URL")

    @property
    def effective_read_database_url(self) -> str:
        # 为什么读库默认回退到写库：
        # 这样本地开发、SQLite 测试、或者尚未部署从库的环境仍然可以跑通。
        # 这是一种渐进式改造思路：先让代码支持读写分离，再逐步切换基础设施。
        if self.read_database_url:
            return self.read_database_url
        if self.write_database_url:
            return self.write_database_url
        if self.database_url:
            return self.database_url
        raise ValueError("未配置读库连接串：请提供 READ_DATABASE_URL、WRITE_DATABASE_URL 或 DATABASE_URL")

settings = Settings()
