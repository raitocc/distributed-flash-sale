import { ref, computed } from 'vue'
import request from '../api/request'

export function useFlashSale() {
    const products = ref([])
    const isLoading = ref(false)

    // 查询商品，并行拉取每个商品的真实库存
    const fetchProducts = async () => {
        isLoading.value = true
        try {
            const res = await request.get('/api/products?skip=0&limit=50')
            let items = res.data || []

            // 遍历列表查询库存 (模拟 BFF 聚合)
            items = await Promise.all(items.map(async (prod) => {
                try {
                    const invRes = await request.get(`/api/inventory/${prod.id}`)
                    // Inventory 结构：{ total_stock, locked_stock, ... }
                    const invData = invRes.data || { total_stock: 0, locked_stock: 0 }
                    return {
                        ...prod,
                        total_stock: invData.total_stock,
                        available_stock: Math.max(0, invData.total_stock - invData.locked_stock)
                    }
                } catch (e) {
                    return { ...prod, total_stock: 0, available_stock: 0 }
                }
            }))
            products.value = items
        } catch (e) {
            console.error("加载商品/库存失败", e.message)
        } finally {
            isLoading.value = false
        }
    }

    // 下单与扣减
    const placeOrder = async (productId) => {
        try {
            // 1. 下单
            const res = await request.post('/api/orders', { product_id: productId })
            const orderData = res.data

            // 2. 模拟自动付款
            if (orderData && orderData.id) {
                await request.post(`/api/orders/${orderData.id}/pay`)
            }
            return { success: true, order: orderData }
        } catch (e) {
            return { success: false, message: e.message }
        }
    }

    return {
        products,
        isLoading,
        fetchProducts,
        placeOrder
    }
}
