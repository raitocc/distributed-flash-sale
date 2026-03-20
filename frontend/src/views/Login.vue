<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import request from '../api/request'
import { Loader2 } from 'lucide-vue-next'

const router = useRouter()

const isRegister = ref(false)
const username = ref('')
const password = ref('')
const isLoading = ref(false)
const errorMessage = ref('')

const handleAuth = async () => {
  if (!username.value || !password.value) {
    errorMessage.value = '您好，请输入账号与密码。'
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    if (isRegister.value) {
      await request.post('/api/users/register', { username: username.value, password: password.value })
      // Auto switch to login
      isRegister.value = false
      errorMessage.value = '通行证创建成功，请立即登录以体验。'
    } else {
      const res = await request.post('/api/users/login', { username: username.value, password: password.value })
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('username', username.value)
      router.push('/')
    }
  } catch (e) {
    errorMessage.value = e.message || '身份验证受阻，请检查。'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-apple-bg flex items-center justify-center p-6 sm:p-12">
    <div 
      v-motion
      :initial="{ opacity: 0, y: 20 }"
      :enter="{ opacity: 1, y: 0, transition: { type: 'spring', stiffness: 200, damping: 20 } }"
      class="w-full max-w-sm bg-apple-card p-10 rounded-[2rem] shadow-[0_12px_24px_rgba(0,0,0,0.06)]"
    >
      <div class="text-center mb-10">
        <h1 class="text-2xl font-bold tracking-tight text-apple-text">
          {{ isRegister ? '注册通行证' : '验证您的身份' }}
        </h1>
        <p class="text-sm text-apple-subtext mt-2">
          持有有效凭据即可接入极速秒杀底层。
        </p>
      </div>

      <div class="space-y-4">
        <div>
          <input 
            v-model="username" 
            type="text" 
            placeholder="账户名" 
            class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
            @keyup.enter="handleAuth"
          >
        </div>
        <div>
          <input 
            v-model="password" 
            type="password" 
            placeholder="密钥密码" 
            class="w-full bg-apple-bg rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
            @keyup.enter="handleAuth"
          >
        </div>
      </div>

      <div v-if="errorMessage" class="mt-4 text-xs font-semibold text-center" :class="isRegister && errorMessage.includes('创建成功') ? 'text-green-500' : 'text-apple-red'">
        {{ errorMessage }}
      </div>

      <button 
        @click="handleAuth"
        :disabled="isLoading"
        class="mt-8 w-full flex items-center justify-center h-12 bg-apple-blue text-white rounded-full text-sm font-medium hover:bg-[#0071E3]/90 transition-all active:scale-95 shadow-md shadow-apple-blue/20 disabled:bg-apple-blue/50 tracking-wide"
      >
        <Loader2 v-if="isLoading" class="w-4 h-4 animate-spin" />
        <span v-else>{{ isRegister ? '确认注册身份 →' : '安全联机介入 →' }}</span>
      </button>

      <div class="mt-8 text-center text-sm text-apple-subtext">
        {{ isRegister ? '已经手握通行证了？' : '首次探索这一领域？' }}
        <button @click="isRegister = !isRegister; errorMessage = ''" class="text-apple-blue font-medium hover:underline focus:outline-none ml-1">
          {{ isRegister ? '直接前往核心登录' : '立即免费创建' }}
        </button>
      </div>
    </div>
  </div>
</template>
