import { ref } from 'vue'
import request from '../api/request'

const ORDER_PENDING_STATES = new Set(['QUEUED', 'PROCESSING'])

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export function useFlashSale() {
  const products = ref([])
  const isLoading = ref(false)
  const activeOrder = ref(null)
  const isSubmittingOrder = ref(false)
  const isRefreshingOrder = ref(false)
  const isMutatingOrder = ref(false)

  const fetchProducts = async () => {
    isLoading.value = true
    try {
      const res = await request.get('/api/products?skip=0&limit=50')
      let items = res.data || []

      // 为什么这里保留“商品列表 + 库存列表”双查询：
      // 当前后端仍然保持微服务边界，商品服务负责商品信息，库存服务负责库存状态。
      // 前端把它们聚合成一个卡片视图，是为了让测试秒杀时能直观看到“这个商品能不能抢”，
      // 而不是让用户自己对着两个接口做脑补。
      items = await Promise.all(items.map(async (prod) => {
        try {
          const invRes = await request.get(`/api/inventory/${prod.id}`)
          const invData = invRes.data || { total_stock: 0, locked_stock: 0 }
          return {
            ...prod,
            total_stock: invData.total_stock,
            available_stock: Math.max(0, invData.total_stock - invData.locked_stock)
          }
        } catch (e) {
          return {
            ...prod,
            total_stock: 0,
            available_stock: 0
          }
        }
      }))

      products.value = items
    } catch (e) {
      console.error('加载商品/库存失败', e.message)
      products.value = []
      throw e
    } finally {
      isLoading.value = false
    }
  }

  const getOrderStatus = async (orderId) => {
    const res = await request.get(`/api/orders/${orderId}`)
    const status = res.data || null
    if (status) {
      activeOrder.value = status
      localStorage.setItem('latest_order_id', orderId)
    }
    return status
  }

  const pollOrderStatus = async (orderId, maxAttempts = 12, intervalMs = 1000) => {
    let latestStatus = null

    // 为什么轮询而不是在前端假设“下单成功就等于已创建订单”：
    // 现在订单服务已经切成 Kafka 异步建单，请求返回成功只代表“消息成功入队”，
    // 不代表数据库里的订单已经准备好付款。前端如果继续沿用旧版同步心智，
    // 就会在队列尚未消费完成时立刻调用支付接口，最终把正确的异步架构误判成 bug。
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        latestStatus = await getOrderStatus(orderId)
        if (!latestStatus || !ORDER_PENDING_STATES.has(latestStatus.status)) {
          return latestStatus
        }
      } catch (e) {
        // WARNING:
        // 异步订单在极短时间窗口内可能还没来得及写入 Redis 状态缓存或数据库。
        // 这里不因为单次查询失败就立刻把整次秒杀判死，而是给消费者一点追平时间。
        if (attempt === maxAttempts) {
          throw e
        }
      }

      await sleep(intervalMs)
    }

    return latestStatus
  }

  const placeOrder = async (productId) => {
    isSubmittingOrder.value = true
    try {
      const res = await request.post('/api/orders', { product_id: productId })
      const orderData = res.data
      activeOrder.value = {
        order_id: orderData.order_id,
        status: orderData.status,
        message: orderData.message
      }
      localStorage.setItem('latest_order_id', orderData.order_id)

      const finalStatus = await pollOrderStatus(orderData.order_id)
      return {
        success: true,
        order: finalStatus || activeOrder.value,
        message: finalStatus?.message || orderData.message || '秒杀请求已提交'
      }
    } catch (e) {
      return { success: false, message: e.message }
    } finally {
      isSubmittingOrder.value = false
    }
  }

  const refreshOrderStatus = async (orderId) => {
    if (!orderId) {
      return null
    }
    isRefreshingOrder.value = true
    try {
      return await getOrderStatus(orderId)
    } finally {
      isRefreshingOrder.value = false
    }
  }

  const payOrder = async (orderId) => {
    isMutatingOrder.value = true
    try {
      await request.post(`/api/orders/${orderId}/pay`)
      return await refreshOrderStatus(orderId)
    } finally {
      isMutatingOrder.value = false
    }
  }

  const cancelOrder = async (orderId) => {
    isMutatingOrder.value = true
    try {
      await request.post(`/api/orders/${orderId}/cancel`)
      return await refreshOrderStatus(orderId)
    } finally {
      isMutatingOrder.value = false
    }
  }

  const restoreLatestOrder = async () => {
    const latestOrderId = localStorage.getItem('latest_order_id')
    if (!latestOrderId) {
      return null
    }

    try {
      return await refreshOrderStatus(latestOrderId)
    } catch (e) {
      localStorage.removeItem('latest_order_id')
      activeOrder.value = null
      return null
    }
  }

  const clearActiveOrder = () => {
    activeOrder.value = null
    localStorage.removeItem('latest_order_id')
  }

  return {
    products,
    activeOrder,
    isLoading,
    isSubmittingOrder,
    isRefreshingOrder,
    isMutatingOrder,
    fetchProducts,
    placeOrder,
    refreshOrderStatus,
    payOrder,
    cancelOrder,
    restoreLatestOrder,
    clearActiveOrder
  }
}
