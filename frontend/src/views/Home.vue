<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useFlashSale } from '../hooks/useFlashSale'
import ProductCard from '../components/ProductCard.vue'

const router = useRouter()
const { products, isLoading, fetchProducts, placeOrder } = useFlashSale()
const username = ref(localStorage.getItem('username'))

onMounted(async () => {
  await fetchProducts()
  if (products.value.length === 0) {
    products.value = [
      { id: '1', name: 'iPhone 15 Pro', description: '钛金属工艺，坚固轻盈，A17 Pro 芯片引擎。', flash_price: 6999, original_price: 7999, total_stock: 100, available_stock: 45 },
      { id: '2', name: 'MacBook Air M2', description: '不要小看它，M2芯片驱动，身如羽毛。', flash_price: 7899, original_price: 8999, total_stock: 50, available_stock: 5 },
      { id: '3', name: 'AirPods Pro 2', description: '妙不可言，为你带来最纯粹的主动降噪。', flash_price: 1399, original_price: 1899, total_stock: 500, available_stock: 0 },
      { id: '4', name: 'Apple Watch Ultra', description: '准备去探险吧，钛合金表盘极致防护。', flash_price: 4999, original_price: 6299, total_stock: 30, available_stock: 28 },
    ]
  }
})

const handleLogout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('username')
  username.value = null
}

const handleBuyClick = async (productId, callback) => {
  if (!localStorage.getItem('access_token')) {
    router.push('/login')
    return
  }
  
  const result = await placeOrder(productId)
  callback(result)
  setTimeout(() => fetchProducts(), 500)
}
</script>

<template>
  <main class="min-h-screen bg-apple-bg px-6 sm:px-12 md:px-24 flex flex-col pt-6 pb-32">
    <!-- 顶部状态栏提取出来，避免绝对定位重叠 -->
    <nav class="flex justify-end items-center gap-6 mb-12 h-10 w-full z-10">
      <router-link to="/admin" class="text-xs font-semibold text-apple-subtext hover:text-apple-text transition-colors tracking-widest">管理后台</router-link>
      <div v-if="username" class="flex items-center gap-4">
        <span class="text-xs font-bold text-apple-text tracking-widest bg-black/5 px-3 py-1 rounded-full">{{ username }}</span>
        <button @click="handleLogout" class="text-xs font-semibold text-apple-red hover:text-red-700 transition-colors tracking-widest">退出登录</button>
      </div>
      <router-link v-else to="/login" class="text-xs font-semibold text-apple-blue hover:underline transition-colors tracking-widest">账号登录</router-link>
    </nav>

    <!-- Header Hero Section with Spring Entrance -->
    <header 
      v-motion
      :initial="{ opacity: 0, y: 50 }"
      :enter="{ opacity: 1, y: 0, transition: { type: 'spring', stiffness: 250, damping: 25 } }"
      class="max-w-4xl mx-auto text-center"
    >
      <h1 class="text-4xl md:text-6xl font-bold tracking-tighter text-apple-text">
        分布式极速秒杀
      </h1>
      <p class="mt-6 text-xl md:text-2xl font-normal text-apple-subtext tracking-tight max-w-2xl mx-auto leading-relaxed">
        支持百万级高并发请求。<br/>基于严苛物理隔离与绝对幂等性架构设计。
      </p>
    </header>

    <!-- Content Area -->
    <div class="mt-24 max-w-7xl mx-auto w-full">
      <div v-if="isLoading" class="flex justify-center items-center h-64">
        <div class="w-12 h-12 border-4 border-black/10 border-t-apple-text rounded-full animate-spin"></div>
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
    </div>
  </main>
</template>
