from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint

from database import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # 为什么要把 (user_id, product_id) 设成唯一约束：
        # Redis 幂等标记负责挡住大多数重复请求，但真正能兜底“缓存丢失、服务重启、消息重复投递”的，
        # 仍然必须是数据库这一层的最终约束。否则只要上游有一个环节漏掉检查，业务规则就会被绕过去。
        UniqueConstraint("user_id", "product_id", name="uk_orders_user_product"),
    )

    # 订单号由雪花算法在接收请求时提前生成：
    # 这样前端在“异步排队中”阶段就已经拿到了稳定的查询凭证，不需要等数据库真正落单后再返回结果。
    id = Column(String(32), primary_key=True, index=True)

    # 核心关联字段：买家ID 和 商品ID
    user_id = Column(String(32), index=True, nullable=False)
    product_id = Column(String(32), index=True, nullable=False)

    # 订单快照数据：下单时的真实成交价 (极其重要！因为商品价格以后可能会变)
    amount = Column(Numeric(10, 2), nullable=False)

    # 秒杀单默认 quantity=1：
    # 课程场景里“一个用户抢一个名额”比“购物车批量购买”更贴近秒杀本质，也能显著降低幂等和库存一致性的复杂度。
    quantity = Column(Integer, nullable=False, default=1)

    # 订单状态分成 PROCESSING / PENDING_PAYMENT / PAID / CANCELLED / FAILED：
    # 这样我们才能把“请求已接收但异步消费者还没真正落库完成”的中间态表达清楚，方便演示 MQ 削峰过程。
    status = Column(String(20), default="PROCESSING")

    # 失败原因单独落库，不只是在日志里打印：
    # 因为秒杀链路最难排查的往往不是“有没有失败”，而是“失败发生在商品查询、库存确认还是消息消费哪一层”。
    failure_reason = Column(String(255), nullable=True)

    # 创建时间
    create_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 更新时间能帮助我们判断消息消费是否卡在某个中间态。
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
