import axios from 'axios'

// 约定：
// - 开发环境通过 Vite 代理 /api/v2 到业务后端 (5002)
// - 业务接口统一走 /api/v2/*
// - 生产环境由 Nginx 反代 /api/v2 到后端
export const api = axios.create({
    baseURL: '/api/v2',
    timeout: 1800000, // 30分钟超时，批量分析需要较长时间
    headers: { 'Content-Type': 'application/json' },
})

export const inferenceAxios = axios.create({
    baseURL: '/inference',
    timeout: 1800000, // 30分钟超时，模型推理可能需要较长时间
    headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
    (resp) => resp,
    (err) => {
        // 处理 401 未授权错误，清除本地存储的认证信息
        if (err.response?.status === 401) {
            // 清除认证信息
            localStorage.removeItem('token')
            localStorage.removeItem('user')
            // 如果不是在登录页面，可以重定向到登录页
            if (window.location.pathname !== '/beta/login' && !window.location.pathname.startsWith('/guide')) {
                window.location.href = '/beta/login'
            }
        }
        return Promise.reject(err)
    }
)

api.interceptors.request.use((config) => {
    try {
        // 优先使用 JWT Token 认证
        const token = localStorage.getItem('token')
        if (token) {
            config.headers = config.headers || {}
            config.headers['Authorization'] = `Bearer ${token}`
        }

        // 兼容旧的 X-Actor / X-Role 头
        const actor = localStorage.getItem('actor') || ''
        const role = localStorage.getItem('role') || ''
        if (actor) {
            config.headers = config.headers || {}
            config.headers['X-Actor'] = actor
        }
        if (role) {
            config.headers = config.headers || {}
            config.headers['X-Role'] = role
        }
    } catch (_) {
        // ignore
    }
    return config
})

inferenceAxios.interceptors.response.use(
    (resp) => resp,
    (err) => Promise.reject(err)
)

export default api
