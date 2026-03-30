import { api } from './request'

// 需求管理监控 API
export const manageApi = {
    async createProject(payload) {
        const resp = await api.post('/manage/projects', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listProjects() {
        const resp = await api.get('/manage/projects')
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getProject(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateProject(projectId, payload) {
        const resp = await api.patch(`/manage/projects/${encodeURIComponent(projectId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async setProjectSession(projectId, sessionId) {
        return this.updateProject(projectId, { current_session_id: sessionId })
    },

    async deleteProject(projectId) {
        const resp = await api.delete(`/manage/projects/${encodeURIComponent(projectId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listRequirements(projectId, { tree = false } = {}) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/requirements`, {
            params: tree ? { tree: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createRequirement(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/requirements`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateRequirement(reqId, payload) {
        const resp = await api.patch(`/manage/requirements/${encodeURIComponent(reqId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async bulkUpdateRequirementStatus(payload) {
        const resp = await api.post('/manage/requirements/bulk-status', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listDefects(projectId, { requirementId } = {}) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/defects`, {
            params: requirementId ? { requirement_id: requirementId } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listRequirementDefects(reqId) {
        const resp = await api.get(`/manage/requirements/${encodeURIComponent(reqId)}/defects`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createDefect(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/defects`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateDefect(defectId, payload) {
        const resp = await api.patch(`/manage/defects/${encodeURIComponent(defectId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async deleteDefect(defectId) {
        const resp = await api.delete(`/manage/defects/${encodeURIComponent(defectId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async moveRequirement(reqId, payload) {
        const resp = await api.post(`/manage/requirements/${encodeURIComponent(reqId)}/move`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async deleteRequirement(reqId, { cascade = false } = {}) {
        const resp = await api.delete(`/manage/requirements/${encodeURIComponent(reqId)}`, {
            params: cascade ? { cascade: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async importFromSession(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/requirements/import`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // Backward-compatible alias (old naming).
    async importFromL123(projectId, payload) {
        return this.importFromSession(projectId, payload)
    },

    async createMilestone(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/milestones`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMilestones(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/milestones`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getMilestone(milestoneId) {
        const resp = await api.get(`/manage/milestones/${encodeURIComponent(milestoneId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async setBaseline(milestoneId) {
        const resp = await api.post(`/manage/milestones/${encodeURIComponent(milestoneId)}/baseline`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async compareMilestones(payload) {
        const resp = await api.post('/manage/milestones/compare', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMilestoneGraph(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/milestone-graph`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createBranch(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/branches`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async mergeBranches(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/branches/merge`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listBranches(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/branches`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async addChangeSet(branchId, payload) {
        const resp = await api.post(`/manage/branches/${encodeURIComponent(branchId)}/changes`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listChangeSets(branchId) {
        const resp = await api.get(`/manage/branches/${encodeURIComponent(branchId)}/changes`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createImpactReport(branchId) {
        const resp = await api.post(`/manage/branches/${encodeURIComponent(branchId)}/impact`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createMergeRequest(branchId, payload) {
        const resp = await api.post(`/manage/branches/${encodeURIComponent(branchId)}/merge`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listAudits(projectId, limit = 100) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/audits`, {
            params: { limit },
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getTraceabilityOverview(projectId, branchId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/traceability/overview`, {
            params: branchId ? { branch_id: branchId } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getTraceabilityMatrix(projectId, branchId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/traceability/matrix`, {
            params: branchId ? { branch_id: branchId } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getTraceabilityCoverage(projectId, branchId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/traceability/coverage`, {
            params: branchId ? { branch_id: branchId } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createTraceabilityImpact(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/traceability/impact`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getTraceabilityRisk(projectId, branchId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/traceability/risk`, {
            params: branchId ? { branch_id: branchId } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },
}
