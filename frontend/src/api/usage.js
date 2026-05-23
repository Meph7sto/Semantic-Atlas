import { api } from './request'

export const usageApi = {
    async getLeaderboard({ period = 'day', limit = 50, timezone } = {}) {
        const params = {
            period,
            limit,
            timezone: timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        }
        const resp = await api.get('/usage/leaderboard', { params })
        return resp.data?.data ?? resp.data
    },
}
