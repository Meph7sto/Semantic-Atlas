import { api } from './request'

export const requirementChangeApi = {
    async analyzeRequirementChange({ projectId, requirementId, changes } = {}) {
        const resp = await api.post('/requirement-change/analyze', {
            project_id: projectId,
            requirement_id: requirementId,
            changes: changes || {},
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },
}
