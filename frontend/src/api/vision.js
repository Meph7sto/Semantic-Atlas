import { api } from './request'

export const visionApi = {
    async captionImage(
        file,
        {
            prompt = '请详细描述图片内容，并总结关键信息。',
            speaker = 'vision_agent',
            maxNewTokens = null,
        } = {}
    ) {
        if (!file) {
            throw new Error('请选择图片')
        }
        const formData = new FormData()
        formData.append('file', file)
        formData.append('prompt', String(prompt || '').trim())
        formData.append('speaker', String(speaker || '').trim())
        if (maxNewTokens != null && Number(maxNewTokens) > 0) {
            formData.append('max_new_tokens', String(Number(maxNewTokens)))
        }
        const resp = await api.post('/vision/caption', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '图生文生成失败')
        }
        return resp.data?.data ?? resp.data
    },

    async listPreviews() {
        const resp = await api.get('/vision/previews')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载图生文预览失败')
        }
        return resp.data?.data ?? []
    },

    async confirmPreview(
        previewId,
        {
            sessionId = null,
            estimateTimestampsIfMissing = true,
            defaultSpanMs = 8000,
            maxSpansReturned = 200,
        } = {}
    ) {
        const payload = {
            estimate_timestamps_if_missing: estimateTimestampsIfMissing,
            default_span_ms: defaultSpanMs,
            max_spans_returned: maxSpansReturned,
        }
        if (sessionId && String(sessionId).trim()) {
            payload.session_id = String(sessionId).trim()
        }

        const resp = await api.post(`/vision/previews/${encodeURIComponent(previewId)}/confirm`, payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '确认入库失败')
        }
        return resp.data?.data ?? resp.data
    },
}
