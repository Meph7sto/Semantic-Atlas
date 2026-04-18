import { api } from './request'

// 认证 API
export const authApi = {
    // 登录
    async login(username, password, role = 'member') {
        const resp = await api.post('/auth/login', {
            username,
            password,
            role,
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '登录失败')
        }
        return resp.data.data
    },

    // 注册
    async register(username, password, displayName, role = 'viewer') {
        const resp = await api.post('/auth/register', {
            username,
            password,
            display_name: displayName,
            role,
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '注册失败')
        }
        return resp.data.data
    },

    // 验证 Token
    async verify() {
        const resp = await api.get('/auth/verify', { skipAuthRedirect: true })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || 'Token 无效')
        }
        return resp.data.data
    },

    // 获取当前用户信息
    async getCurrentUser() {
        const resp = await api.get('/auth/me')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取用户信息失败')
        }
        return resp.data.data
    },

    // 登出
    async logout() {
        const resp = await api.post('/auth/logout', null, { skipAuthRedirect: true })
        return resp.data
    },

    // 列出用户目录（任意已登录用户可访问）
    async listUserDirectory({ role, limit = 500, offset = 0 } = {}) {
        const params = { limit, offset }
        if (role) params.role = role
        const resp = await api.get('/auth/user-directory', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取用户目录失败')
        }
        return resp.data.data
    },

    // 列出用户（仅管理员）
    async listUsers({ role, limit = 100, offset = 0 } = {}) {
        const params = { limit, offset }
        if (role) params.role = role
        const resp = await api.get('/auth/users', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取用户列表失败')
        }
        return resp.data.data
    },

    // 创建用户（仅管理员）
    async createUser(data) {
        const resp = await api.post('/auth/users', data)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '创建用户失败')
        }
        return resp.data.data
    },

    // 更新用户（仅管理员）
    async updateUser(userId, data) {
        const resp = await api.patch(`/auth/users/${userId}`, data)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新用户失败')
        }
        return resp.data.data
    },

    // 获取范围授权可选项（产品/项目）
    async getScopeOptions() {
        const resp = await api.get('/auth/scope-options')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取范围选项失败')
        }
        return resp.data.data
    },

    // 获取用户范围授权
    async getUserScopes(userId) {
        const resp = await api.get(`/auth/users/${encodeURIComponent(userId)}/scopes`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取用户范围失败')
        }
        return resp.data.data
    },

    // 更新用户范围授权（全量替换）
    async updateUserScopes(userId, payload) {
        const resp = await api.put(`/auth/users/${encodeURIComponent(userId)}/scopes`, payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新用户范围失败')
        }
        return resp.data.data
    },

    // 列出注册申请（仅管理员）
    async listRegistrations({ status = 'pending', limit = 100, offset = 0 } = {}) {
        const resp = await api.get('/auth/registrations', {
            params: { status, limit, offset },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取注册申请列表失败')
        }
        return resp.data?.data ?? resp.data
    },

    // 获取注册申请详情（仅管理员）
    async getRegistration(userId) {
        const resp = await api.get(`/auth/registrations/${encodeURIComponent(userId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取注册申请详情失败')
        }
        return resp.data?.data ?? resp.data
    },

    // 批准注册申请（仅管理员）
    async approveRegistration(userId, { role, external_type = undefined } = {}) {
        const payload = { role }
        if (external_type !== undefined && external_type !== '') {
            payload.external_type = external_type
        }
        const resp = await api.post(`/auth/registrations/${encodeURIComponent(userId)}/approve`, payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '批准注册申请失败')
        }
        return resp.data?.data ?? resp.data
    },

    // 拒绝注册申请（仅管理员）
    async rejectRegistration(userId, reason) {
        const resp = await api.post(`/auth/registrations/${encodeURIComponent(userId)}/reject`, { reason })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '拒绝注册申请失败')
        }
        return resp.data?.data ?? resp.data
    },

    // 获取待审批注册申请数量（仅管理员）
    async getPendingRegistrationCount() {
        const resp = await api.get('/auth/registrations/pending/count')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取待审批注册数量失败')
        }
        if (typeof resp.data?.count === 'number') {
            return resp.data.count
        }
        return resp.data?.data?.count ?? 0
    },

    // 获取当前用户个人资料
    async getProfile() {
        const resp = await api.get('/auth/profile')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取个人资料失败')
        }
        return resp.data.data
    },

    // 更新当前用户个人资料（display_name, avatar_url）
    async updateProfile({ display_name, avatar_url } = {}) {
        const body = {}
        if (display_name !== undefined) body.display_name = display_name
        if (avatar_url !== undefined) body.avatar_url = avatar_url
        const resp = await api.patch('/auth/profile', body)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新个人资料失败')
        }
        return resp.data.data
    },

    // 修改当前用户密码
    async changePassword(oldPassword, newPassword) {
        const resp = await api.post('/auth/profile/change-password', {
            old_password: oldPassword,
            new_password: newPassword,
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '修改密码失败')
        }
        return resp.data
    },
}
