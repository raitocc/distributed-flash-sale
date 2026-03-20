<script setup>
import { computed, ref } from 'vue'
import StockProgressBar from './StockProgressBar.vue'
import { ShoppingBag, Loader2, CheckCircle, XCircle } from 'lucide-vue-next'

const props = defineProps({
  product: { type: Object, required: true },
  delayIndex: { type: Number, default: 0 }
})

const emit = defineEmits(['buy'])

const isBuying = ref(false)
const purchaseState = ref('idle') // idle, loading, success, fail
const purchaseMessage = ref('')

const handleBuy = async () => {
  if (isBuying.value) return 

  isBuying.value = true
  purchaseState.value = 'loading'
  
  // 向上抛出秒杀事件
  emit('buy', props.product.id, (result) => {
    isBuying.value = false
    if (result.success) {
      purchaseState.value = 'success'
      purchaseMessage.value = '抢下成功！'
    } else {
      purchaseState.value = 'fail'
      purchaseMessage.value = result.message || '已被秒光'
    }
    
    // 3秒后还原按钮状态
    setTimeout(() => {
      purchaseState.value = 'idle'
      purchaseMessage.value = ''
    }, 3000)
  })
}

const mockTotal = computed(() => props.product.total_stock || 0)
const mockAvailable = computed(() => props.product.available_stock || 0)
const isSoldOut = computed(() => mockAvailable.value <= 0 && mockTotal.value > 0)
</script>

<template>
  <div 
    v-motion
    :initial="{ opacity: 0, y: 30, scale: 0.95 }"
    :enter="{ opacity: 1, y: 0, scale: 1, transition: { type: 'spring', stiffness: 200, damping: 20, delay: delayIndex * 100 } }"
    class="group relative flex flex-col justify-between p-6 sm:p-8 rounded-[2rem] bg-apple-card shadow-[0_2px_10px_rgba(0,0,0,0.03)] hover:shadow-[0_12px_24px_rgba(0,0,0,0.08)] transition-shadow duration-500 overflow-hidden isolating"
  >
    <!-- 极简高雅的背景光晕 -->
    <div class="absolute -top-24 -right-24 w-48 h-48 bg-apple-blue/5 rounded-full blur-3xl group-hover:bg-apple-blue/10 transition-colors duration-700 pointer-events-none"></div>

    <div>
      <h3 class="text-xl sm:text-2xl font-bold tracking-tight text-apple-text">
        {{ product.name }}
      </h3>
      <p class="mt-2 text-sm text-apple-subtext leading-relaxed line-clamp-2">
        {{ product.description || '高端精密制造，颠覆行业格局的先锋性能。' }}
      </p>

      <div class="mt-8 flex items-baseline gap-3">
        <span class="text-3xl font-medium tracking-tighter text-apple-text">¥{{ product.flash_price || 9.9 }}</span>
        <span class="text-sm tracking-wide text-apple-subtext line-through" v-if="product.original_price">
          ¥{{ product.original_price }}
        </span>
      </div>
      
      <StockProgressBar :total="mockTotal" :available="mockAvailable" />
    </div>

    <!-- 交互专区 -->
    <div class="mt-8 pt-6 border-t border-black/5 flex justify-end">
      <button 
        @click="handleBuy"
        :disabled="isBuying || isSoldOut"
        class="relative flex items-center justify-center h-10 px-6 rounded-full font-medium text-sm transition-all duration-300"
        :class="[
          isSoldOut && purchaseState === 'idle'
            ? 'bg-black/5 text-apple-subtext cursor-not-allowed' 
            : purchaseState === 'idle' 
              ? 'bg-apple-blue text-white hover:bg-[#0071E3]/90 hover:scale-105 active:scale-95 shadow-md shadow-apple-blue/20' 
              : purchaseState === 'loading'
                ? 'bg-apple-blue/80 text-white cursor-wait'
                : purchaseState === 'success'
                  ? 'bg-green-500 text-white shadow-md shadow-green-500/20'
                  : 'bg-apple-red text-white shadow-md shadow-apple-red/20'
        ]"
      >
        <span v-if="purchaseState === 'idle'" class="flex items-center gap-2">
          {{ isSoldOut ? '已售罄' : '极限点击抢购' }} <ShoppingBag v-if="!isSoldOut" class="w-4 h-4"/>
        </span>
        <Loader2 v-else-if="purchaseState === 'loading'" class="w-4 h-4 animate-spin" />
        <span v-else-if="purchaseState === 'success'" class="flex items-center gap-1">
          <CheckCircle class="w-4 h-4"/> {{ purchaseMessage }}
        </span>
        <span v-else-if="purchaseState === 'fail'" class="flex items-center gap-1">
          <XCircle class="w-4 h-4"/> {{ purchaseMessage }}
        </span>
      </button>
    </div>
  </div>
</template>
