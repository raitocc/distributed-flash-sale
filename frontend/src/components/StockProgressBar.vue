<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: Number, required: true },
  available: { type: Number, required: true }
})

const percentage = computed(() => {
  if (props.total <= 0) return 0
  return Math.min(100, Math.max(0, (props.available / props.total) * 100))
})

const progressColor = computed(() => {
  if (percentage.value > 50) return 'bg-apple-blue'   // 蓝色健康
  if (percentage.value > 10) return 'bg-orange-400'  // 橙色吃紧
  return 'bg-apple-red'                              // 红色殆尽
})
</script>

<template>
  <div class="flex flex-col gap-2 mt-4">
    <div class="flex justify-between items-end text-xs font-semibold tracking-wider">
      <span class="text-apple-subtext">极鲜货源余量</span>
      <span :class="{'text-apple-red': percentage <= 10, 'text-apple-text': percentage > 10}">
        {{ available }} / {{ total }}
      </span>
    </div>
    
    <!-- 极细果味进度条，底色非常淡 -->
    <div class="h-1.5 w-full bg-black/5 rounded-full overflow-hidden">
      <div 
        class="h-full transition-all duration-700 ease-[cubic-bezier(0.34,1.56,0.64,1)] rounded-full"
        :class="progressColor"
        :style="{ width: percentage + '%' }"
      ></div>
    </div>
  </div>
</template>
