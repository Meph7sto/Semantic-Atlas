import axios from 'axios'

export const AUTH_CLEARED_EVENT = 'semantic-atlas:auth-cleared'

export function clearAuthStorage() {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    localStorage.removeItem('actor')
    localStorage.removeItem('role')

    if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(AUTH_CLEARED_EVENT))
    }
}

function buildUnauthorizedRedirectTarget() {
    const { pathname, search } = window.location
    const currentTarget = `${pathname}${search || ''}`
    const query = new URLSearchParams({ redirect: currentTarget }).toString()

    if (pathname === '/beta/login' || pathname.startsWith('/guide')) {
        return null
    }

    if (pathname === '/alpha' || pathname.startsWith('/alpha/')) {
        return `/guide?${query}`
    }

    return `/beta/login?${query}`
}

export function handleUnauthorized({ redirect = true } = {}) {
    clearAuthStorage()

    if (!redirect) {
        return
    }

    const target = buildUnauthorizedRedirectTarget()
    if (target) {
        window.location.assign(target)
    }
}

export function extractErrorMessage(detail) {
    if (typeof detail === 'string' && detail.trim()) {
        return detail
    }

    if (Array.isArray(detail) && detail.length > 0) {
        return detail.map((item) => item?.msg || JSON.stringify(item)).join('; ')
    }

    return ''
}

export function extractErrorMessageFromPayload(payload) {
    return (
        extractErrorMessage(payload?.detail) ||
        (typeof payload?.error === 'string' && payload.error.trim() ? payload.error : '')
    )
}

export async function readErrorPayload(response) {
    try {
        return await response.json()
    } catch {
        return null
    }
}

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
            handleUnauthorized({ redirect: err.config?.skipAuthRedirect !== true })
        }
        const detail = err.response?.data?.detail
        const message = extractErrorMessage(detail)
        if (message) {
            err.message = message
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
