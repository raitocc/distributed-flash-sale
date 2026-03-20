<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import request from '../api/request'
import { PlusCircle, Save, Layers, PackagePlus } from 'lucide-vue-next'

const router = useRouter()
const products = ref([])
const newProduct = ref({ name: '', description: '', original_price: 1999, flash_price: 999 })
const inventoryForm = ref({ product_id: '', total_stock: 100 })
const isLoading = ref(false)
const username = ref(localStorage.getItem('username'))

const handleLogout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('username')
  router.push('/login')
}

const fetchAdminData = async () => {
  isLoading.value = true
  try {
    const res = await request.get('/api/products?skip=0&limit=50')
    const items = res.data || []
    
    // Fetch inventory
    products.value = await Promise.all(items.map(async (prod) => {
      try {
        const invRes = await request.get(`/api/inventory/${prod.id}`)
        const invData = invRes.data || { total_stock: 0, locked_stock: 0 }
        return { 
          ...prod, 
          total_stock: invData.total_stock, 
          available_stock: Math.max(0, invData.total_stock - invData.locked_stock) 
        }
      } catch(e) {
        return { ...prod, total_stock: 0, available_stock: 0 }
      }
    }))
  } finally {
    isLoading.value = false
  }
}

const handleAddProduct = async () => {
  try {
    if (!localStorage.getItem('access_token')) {
      alert('权限不足：需登录后方可操作。')
      return router.push('/login')
    }
    
    const res = await request.post('/api/products', newProduct.value)
    if (res.code === 200) {
      alert('商品发布成功')
      newProduct.value = { name: '', description: '', original_price: 1999, flash_price: 999 }
      await fetchAdminData()
    }
  } catch (e) {
    alert('发布失败: ' + e.message)
  }
}

const handleSetInventory = async () => {
  try {
    const res = await request.post('/api/inventory', inventoryForm.value)
    if (res.code === 200) {
      alert('库存储备已更新')
      inventoryForm.value.total_stock = 100
      await fetchAdminData()
    }
  } catch (e) {
    alert('更新库存失败: ' + e.message)
  }
}

onMounted(() => {
  if (!localStorage.getItem('access_token')) {
    router.push('/login')
    return
  }
  fetchAdminData()
})
</script>

<template>
  <div class="min-h-screen bg-apple-bg p-6 sm:p-12">
    <div class="max-w-5xl mx-auto">
      <!-- 提取出的独立导航外壳，保证不重叠 -->
      <nav class="flex justify-between items-center w-full mb-10 h-10">
        <router-link to="/" class="text-sm font-medium text-apple-blue hover:underline">← 返回商城</router-link>
        <div v-if="username" class="flex items-center gap-3">
          <span class="text-xs font-bold text-apple-text tracking-widest bg-black/5 px-3 py-1 rounded-full">{{ username }}</span>
          <button @click="handleLogout" class="text-xs font-semibold text-apple-red hover:text-red-700 transition-colors tracking-widest">退出登录</button>
        </div>
      </nav>

      <div class="mb-12">
        <h1 class="text-3xl font-bold tracking-tight text-apple-text">秒杀控制台</h1>
        <p class="text-sm text-apple-subtext mt-1">全局管控分布式的商品货架与底层库存资源池。</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
        <!-- Add Product -->
        <div class="bg-apple-card rounded-[2rem] p-8 shadow-sm">
          <h2 class="text-lg font-semibold mb-6 flex items-center gap-2"><PackagePlus class="w-5 h-5"/> 上架新商品</h2>
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-semibold text-apple-subtext tracking-wider mb-2">商品名称</label>
              <input v-model="newProduct.name" type="text" class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20" placeholder="例如：Vision Pro">
            </div>
            <div>
              <label class="block text-xs font-semibold text-apple-subtext tracking-wider mb-2">详情描述</label>
              <input v-model="newProduct.description" type="text" class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20" placeholder="空间计算设备新纪元。">
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-semibold text-apple-subtext tracking-wider mb-2">专柜原价(元)</label>
                <input v-model.number="newProduct.original_price" type="number" class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20">
              </div>
              <div>
                <label class="block text-xs font-semibold text-apple-subtext tracking-wider mb-2">超低秒杀价</label>
                <input v-model.number="newProduct.flash_price" type="number" class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20">
              </div>
            </div>
            <button @click="handleAddProduct" class="mt-4 w-full bg-apple-blue text-white rounded-full py-3 text-sm font-medium hover:bg-[#0071E3]/90 transition-colors flex items-center justify-center gap-2">
              <PlusCircle class="w-4 h-4"/> 确认发布上架
            </button>
          </div>
        </div>

        <!-- Set Inventory -->
        <div class="bg-apple-card rounded-[2rem] p-8 shadow-sm">
          <h2 class="text-lg font-semibold mb-6 flex items-center gap-2"><Layers class="w-5 h-5"/> 注入后备箱库存</h2>
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-semibold text-apple-subtext tracking-wider mb-2">选择商品</label>
              <select v-model="inventoryForm.product_id" class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20">
                <option value="" disabled>请选择要注水的商品...</option>
                <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} ({{ p.id }})</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold text-apple-subtext tracking-wider mb-2">总库存池配置 (件)</label>
              <input v-model.number="inventoryForm.total_stock" type="number" class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20">
            </div>
            <button @click="handleSetInventory" :disabled="!inventoryForm.product_id" class="mt-4 w-full bg-apple-text text-white rounded-full py-3 text-sm font-medium hover:bg-black transition-colors flex items-center justify-center gap-2 disabled:opacity-50">
              <Save class="w-4 h-4"/> 生效库存配置
            </button>
          </div>
        </div>
      </div>

      <!-- Live Data Table -->
      <div class="bg-apple-card rounded-[2rem] p-8 shadow-sm overflow-hidden">
        <h2 class="text-lg font-semibold mb-6">实时物理数据全景</h2>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="text-apple-subtext border-b border-black/5 whitespace-nowrap">
                <th class="pb-3 font-medium">全局流水 ID</th>
                <th class="pb-3 font-medium">商品名称</th>
                <th class="pb-3 font-medium">击穿底价</th>
                <th class="pb-3 font-medium">投放总件数</th>
                <th class="pb-3 font-medium">实物可卖</th>
              </tr>
            </thead>
            <tbody v-if="!isLoading">
              <tr v-for="p in products" :key="p.id" class="border-b border-black/5 last:border-0 hover:bg-black/[0.02]">
                <td class="py-4 font-mono text-xs text-apple-subtext">{{ p.id }}</td>
                <td class="py-4 font-medium">{{ p.name }}</td>
                <td class="py-4 font-medium text-apple-red">¥{{ p.flash_price }}</td>
                <td class="py-4">{{ p.total_stock }}</td>
                <td class="py-4 font-bold text-lg">
                  <span :class="p.available_stock > 0 ? 'text-green-600' : 'text-apple-red'">
                    {{ p.available_stock }}
                  </span>
                </td>
              </tr>
            </tbody>
            <tbody v-else>
              <tr><td colspan="5" class="py-8 text-center text-apple-subtext animate-pulse">正在底层服务聚合查询数据...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
