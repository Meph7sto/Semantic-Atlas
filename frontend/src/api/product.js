import { api } from './request'

// 产品管理 API
export const productApi = {
    // ----------------------
    // Products CRUD
    // ----------------------
    async createProduct(payload) {
        const resp = await api.post('/product/products', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listProducts({ includeArchived = false } = {}) {
        const resp = await api.get('/product/products', {
            params: includeArchived ? { include_archived: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateProduct(productId, payload) {
        const resp = await api.patch(`/product/products/${encodeURIComponent(productId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async deleteProduct(productId) {
        const resp = await api.delete(`/product/products/${encodeURIComponent(productId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // ----------------------
    // Product Members
    // ----------------------
    async addMember(productId, payload) {
        const resp = await api.post(`/product/products/${encodeURIComponent(productId)}/members`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async removeMember(productId, userId) {
        const resp = await api.delete(`/product/products/${encodeURIComponent(productId)}/members/${encodeURIComponent(userId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMembers(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/members`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // ----------------------
    // Product-Project Relations
    // ----------------------
    async listProjectsByProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/projects`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createProjectUnderProduct(productId, payload) {
        const resp = await api.post(`/product/products/${encodeURIComponent(productId)}/projects`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async bindProjectToProduct(projectId, productId) {
        const resp = await api.post(`/product/projects/${encodeURIComponent(projectId)}/bind`, {
            product_id: productId,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // ----------------------
    // Product Overview
    // ----------------------
    async getProductOverview(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/overview`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listRequirementsByProduct(productId, { includeDeleted = false } = {}) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/requirements`, {
            params: includeDeleted ? { include_deleted: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMilestonesByProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/milestones`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listBaselinesByProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/baselines`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },
}
