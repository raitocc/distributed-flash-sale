import axios from 'axios'

// Create axios instance pointing to the proxy or remote gateway
const request = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '',  // 留空则走 vite.config.js 的 proxy 代理到 8000
    timeout: 10000
})

// Request interceptor
request.interceptors.request.use(
    config => {
        // Attempt to inject token if exists
        const token = localStorage.getItem('access_token')
        if (token) {
            config.headers.Authorization = `Bearer ${token}`
        }
        return config
    },
    error => Promise.reject(error)
)

// Response interceptor
request.interceptors.response.use(
    response => {
        const res = response.data
        // 如果后端的统一返回值为 code !== 200，将直接走异常流程方便前端在 hook 中捕获
        if (res.code && res.code !== 200) {
            if (res.code === 401) {
                localStorage.removeItem('access_token')
            }
            return Promise.reject(new Error(res.message || 'Error'))
        }
        return res
    },
    error => {
        let msg = '服务异常，请稍候再试'
        if (error.response && error.response.data && error.response.data.message) {
            msg = error.response.data.message
        }
        return Promise.reject(new Error(msg))
    }
)

export default request
