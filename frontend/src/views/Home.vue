<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { RefreshCw, Rocket, ShieldCheck, ShoppingCart } from 'lucide-vue-next'
import { useFlashSale } from '../hooks/useFlashSale'
import ProductCard from '../components/ProductCard.vue'

const router = useRouter()
const {
  products,
  activeOrder,
  isLoading,
  isRefreshingOrder,
  isMutatingOrder,
  fetchProducts,
  placeOrder,
  refreshOrderStatus,
  payOrder,
  cancelOrder,
  restoreLatestOrder,
  clearActiveOrder
} = useFlashSale()

const username = ref(localStorage.getItem('username'))
const pageError = ref('')

const currentOrderStatusTone = computed(() => {
  const status = activeOrder.value?.status
  if (status === 'PENDING_PAYMENT') return 'text-amber-600'
  if (status === 'PAID') return 'text-green-600'
  if (status === 'CANCELLED' || status === 'FAILED') return 'text-apple-red'
  return 'text-apple-blue'
})

const currentOrderCanPay = computed(() => activeOrder.value?.status === 'PENDING_PAYMENT')
const currentOrderCanCancel = computed(() => activeOrder.value?.status === 'PENDING_PAYMENT')

const loadPageData = async () => {
  pageError.value = ''
  try {
    await fetchProducts()
  } catch (e) {
    pageError.value = e.message || '商品服务暂时不可用'
  }
}

onMounted(async () => {
  await Promise.all([loadPageData(), restoreLatestOrder()])
})

const handleLogout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('username')
  username.value = null
  clearActiveOrder()
}

const handleBuyClick = async (productId, callback) => {
  if (!localStorage.getItem('access_token')) {
    router.push('/login')
    return
  }

  const result = await placeOrder(productId)
  callback(result)
  await loadPageData()
}

const handleRefreshOrder = async () => {
  if (!activeOrder.value?.order_id) return
  try {
    await refreshOrderStatus(activeOrder.value.order_id)
    await loadPageData()
  } catch (e) {
    pageError.value = e.message || '刷新订单状态失败'
  }
}

const handlePayOrder = async () => {
  if (!activeOrder.value?.order_id) return
  try {
    await payOrder(activeOrder.value.order_id)
    await loadPageData()
  } catch (e) {
    pageError.value = e.message || '订单支付失败'
  }
}

const handleCancelOrder = async () => {
  if (!activeOrder.value?.order_id) return
  try {
    await cancelOrder(activeOrder.value.order_id)
    await loadPageData()
  } catch (e) {
    pageError.value = e.message || '取消订单失败'
  }
}
</script>

<template>
  <main class="min-h-screen bg-apple-bg px-6 sm:px-12 md:px-24 flex flex-col pt-6 pb-24">
    <nav class="flex justify-end items-center gap-6 mb-12 h-10 w-full z-10">
      <router-link to="/admin" class="text-xs font-semibold text-apple-subtext hover:text-apple-text transition-colors tracking-widest">管理后台</router-link>
      <div v-if="username" class="flex items-center gap-4">
        <span class="text-xs font-bold text-apple-text tracking-widest bg-black/5 px-3 py-1 rounded-full">{{ username }}</span>
        <button @click="handleLogout" class="text-xs font-semibold text-apple-red hover:text-red-700 transition-colors tracking-widest">退出登录</button>
      </div>
      <router-link v-else to="/login" class="text-xs font-semibold text-apple-blue hover:underline transition-colors tracking-widest">账号登录</router-link>
    </nav>

    <header
      v-motion
      :initial="{ opacity: 0, y: 50 }"
      :enter="{ opacity: 1, y: 0, transition: { type: 'spring', stiffness: 250, damping: 25 } }"
      class="max-w-5xl mx-auto text-center"
    >
      <h1 class="text-4xl md:text-6xl font-bold tracking-tighter text-apple-text">
        分布式极速秒杀
      </h1>
      <p class="mt-6 text-xl md:text-2xl font-normal text-apple-subtext tracking-tight max-w-3xl mx-auto leading-relaxed">
        现在前端已经接入真实的异步秒杀链路。<br>点击抢购后，会经历 Redis 预扣、Kafka 排队、订单状态轮询与支付确认。
      </p>
    </header>

    <section class="mt-12 max-w-6xl mx-auto w-full grid grid-cols-1 xl:grid-cols-[1.4fr_1fr] gap-6">
      <div class="bg-apple-card rounded-[2rem] p-8 shadow-[0_12px_24px_rgba(0,0,0,0.04)]">
        <div class="flex items-center gap-3">
          <Rocket class="w-5 h-5 text-apple-blue" />
          <h2 class="text-lg font-semibold text-apple-text">前端完整测试链路</h2>
        </div>
        <div class="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-apple-subtext leading-7">
          <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
            <p class="font-semibold text-apple-text">1. 登录或注册用户</p>
            <p>如果还没有 token，先去登录页创建账号。秒杀接口要求 JWT 鉴权。</p>
          </div>
          <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
            <p class="font-semibold text-apple-text">2. 去管理后台创建商品并加库存</p>
            <p>首页不再伪造商品 ID，必须先用真实商品和真实库存，才能打通秒杀。</p>
          </div>
          <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
            <p class="font-semibold text-apple-text">3. 回到首页点击抢购</p>
            <p>前端会提交真实商品 ID，然后自动轮询订单状态，而不是假设同步下单成功。</p>
          </div>
          <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
            <p class="font-semibold text-apple-text">4. 在右侧观察订单状态</p>
            <p>可以看到 `QUEUED`、`PROCESSING`、`PENDING_PAYMENT`，再继续测试支付或取消。</p>
          </div>
        </div>
      </div>

      <div class="bg-apple-card rounded-[2rem] p-8 shadow-[0_12px_24px_rgba(0,0,0,0.04)]">
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <ShieldCheck class="w-5 h-5 text-green-600" />
            <h2 class="text-lg font-semibold text-apple-text">订单状态面板</h2>
          </div>
          <button
            v-if="activeOrder?.order_id"
            @click="handleRefreshOrder"
            :disabled="isRefreshingOrder"
            class="text-xs font-semibold text-apple-blue hover:underline disabled:opacity-50"
          >
            {{ isRefreshingOrder ? '刷新中...' : '手动刷新' }}
          </button>
        </div>

        <div v-if="activeOrder" class="mt-5 space-y-4 text-sm">
          <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
            <p class="text-xs font-semibold tracking-[0.24em] text-apple-subtext">LATEST ORDER</p>
            <p class="mt-2 font-mono text-xs break-all text-apple-text">{{ activeOrder.order_id }}</p>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
              <p class="text-xs font-semibold tracking-[0.18em] text-apple-subtext">状态</p>
              <p class="mt-2 text-lg font-bold" :class="currentOrderStatusTone">{{ activeOrder.status }}</p>
            </div>
            <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
              <p class="text-xs font-semibold tracking-[0.18em] text-apple-subtext">金额</p>
              <p class="mt-2 text-lg font-bold text-apple-text">
                {{ activeOrder.amount ? `¥${activeOrder.amount}` : '待生成' }}
              </p>
            </div>
          </div>
          <div class="bg-black/[0.03] rounded-2xl px-5 py-4">
            <p class="text-xs font-semibold tracking-[0.18em] text-apple-subtext">当前阶段说明</p>
            <p class="mt-2 text-apple-text leading-6">{{ activeOrder.message || '等待订单服务返回状态描述' }}</p>
            <p v-if="activeOrder.failure_reason" class="mt-2 text-apple-red leading-6">{{ activeOrder.failure_reason }}</p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button
              @click="handlePayOrder"
              :disabled="!currentOrderCanPay || isMutatingOrder"
              class="h-11 px-5 rounded-full bg-apple-blue text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isMutatingOrder && currentOrderCanPay ? '支付中...' : '测试支付链路' }}
            </button>
            <button
              @click="handleCancelOrder"
              :disabled="!currentOrderCanCancel || isMutatingOrder"
              class="h-11 px-5 rounded-full bg-black text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isMutatingOrder && currentOrderCanCancel ? '取消中...' : '测试取消回补' }}
            </button>
            <button
              @click="clearActiveOrder"
              class="h-11 px-5 rounded-full bg-black/5 text-apple-subtext text-sm font-medium"
            >
              清空当前面板
            </button>
          </div>
        </div>

        <div v-else class="mt-5 bg-black/[0.03] rounded-2xl px-5 py-6 text-sm leading-7 text-apple-subtext">
          <p>这里会展示最近一次真实秒杀请求的状态流转。</p>
          <p>当你点击商品卡片后，前端会自动记录订单 ID，并持续轮询直到订单进入终态或待支付态。</p>
        </div>
      </div>
    </section>

    <p v-if="pageError" class="mt-8 max-w-6xl mx-auto w-full text-sm text-apple-red bg-red-50 border border-red-100 rounded-2xl px-5 py-4">
      {{ pageError }}
    </p>

    <div class="mt-16 max-w-7xl mx-auto w-full">
      <div class="flex items-center justify-between gap-4 mb-6">
        <div>
          <h2 class="text-2xl font-bold tracking-tight text-apple-text">真实商品货架</h2>
          <p class="mt-1 text-sm text-apple-subtext">这里只显示后端实际存在的商品，不再使用前端假数据冒充秒杀链路。</p>
        </div>
        <button
          @click="loadPageData"
          :disabled="isLoading"
          class="inline-flex items-center gap-2 h-10 px-4 rounded-full bg-black text-white text-sm font-medium disabled:opacity-50"
        >
          <RefreshCw class="w-4 h-4" :class="isLoading ? 'animate-spin' : ''" />
          刷新商品
        </button>
      </div>

      <div v-if="isLoading" class="flex justify-center items-center h-64">
        <div class="w-12 h-12 border-4 border-black/10 border-t-apple-text rounded-full animate-spin"></div>
      </div>

      <div v-else-if="products.length === 0" class="bg-apple-card rounded-[2rem] px-8 py-12 text-center shadow-[0_12px_24px_rgba(0,0,0,0.04)]">
        <p class="text-xl font-semibold text-apple-text">当前还没有可测试的真实商品</p>
        <p class="mt-3 text-sm text-apple-subtext leading-7">
          请先去管理后台创建商品，并为商品写入库存。<br>
          只有真实商品 ID 和库存就绪后，首页秒杀按钮才会打到正确接口。
        </p>
        <router-link to="/admin" class="inline-flex mt-6 h-11 items-center justify-center px-5 rounded-full bg-apple-blue text-white text-sm font-medium">
          前往管理后台准备测试数据
        </router-link>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
        <ProductCard
          v-for="(product, index) in products"
          :key="product.id"
          :product="product"
          :delay-index="index"
          @buy="handleBuyClick"
        />
      </div>

      <div class="mt-10 bg-apple-card rounded-[2rem] px-8 py-6 shadow-[0_12px_24px_rgba(0,0,0,0.04)]">
        <div class="flex items-center gap-3">
          <ShoppingCart class="w-5 h-5 text-apple-blue" />
          <h3 class="text-lg font-semibold text-apple-text">你现在可以这样完整验证一次</h3>
        </div>
        <div class="mt-4 text-sm text-apple-subtext leading-7">
          <p>1. 在管理后台创建一个商品，并给它设置库存，比如 20 件。</p>
          <p>2. 回到首页点击该商品的“极限点击抢购”。</p>
          <p>3. 右侧面板会先出现 `QUEUED / PROCESSING`，随后进入 `PENDING_PAYMENT`。</p>
          <p>4. 点击“测试支付链路”，可以把订单推进到 `PAID`；点击“测试取消回补”，可以验证库存回补。</p>
          <p>5. 若想验证幂等，再用同一账号重复抢同一商品，应收到“同一用户同一商品只能秒杀一次”。</p>
        </div>
      </div>
    </div>
  </main>
</template>
