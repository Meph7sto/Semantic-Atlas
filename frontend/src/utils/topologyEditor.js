const isPlainObject = (value) => Object.prototype.toString.call(value) === '[object Object]'

export const stringifyJsonForEditor = (value, fallback = '') => {
  if (value === null || value === undefined || value === '') {
    return fallback
  }

  if (typeof value === 'string') {
    return value
  }

  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return fallback
  }
}

export const parseJsonInput = (value, options = {}) => {
  const { fallback = null, label = 'JSON' } = options

  if (value === null || value === undefined) {
    return { ok: true, value: fallback }
  }

  if (typeof value !== 'string') {
    return { ok: true, value }
  }

  const trimmed = value.trim()
  if (!trimmed) {
    return { ok: true, value: fallback }
  }

  try {
    return { ok: true, value: JSON.parse(trimmed) }
  } catch {
    return { ok: false, error: `${label} 不是合法 JSON` }
  }
}

export const normalizeInteger = (value, fallback = 0) => {
  if (value === '' || value === null || value === undefined) {
    return fallback
  }

  const num = Number(value)
  return Number.isInteger(num) ? num : fallback
}

export const isBlank = (value) => {
  return typeof value !== 'string' || value.trim() === ''
}

export const normalizeGraphPayload = (formData) => {
  return {
    name: formData.name?.trim(),
    description: formData.description?.trim() || '',
    status: formData.status || 'draft'
  }
}

export const normalizeContainerPayload = (formData) => {
  const config = parseJsonInput(formData.config_json, {
    fallback: {},
    label: '容器配置'
  })
  if (!config.ok) return config
  if (!isPlainObject(config.value)) {
    return { ok: false, error: '容器配置必须是 JSON 对象' }
  }

  return {
    ok: true,
    value: {
      container_key: formData.container_key?.trim(),
      label: formData.label?.trim(),
      role_type: formData.role_type || 'agent',
      order_index: normalizeInteger(formData.order_index, 0),
      config_json: config.value
    }
  }
}

export const normalizeNodePayload = (formData) => {
  const conditionalEdges = parseJsonInput(formData.conditional_edges, {
    fallback: [],
    label: '条件出边'
  })
  if (!conditionalEdges.ok) return conditionalEdges
  if (!Array.isArray(conditionalEdges.value)) {
    return { ok: false, error: '条件出边必须是 JSON 数组' }
  }

  return {
    ok: true,
    value: {
      container_id: formData.container_id || null,
      node_key: formData.node_key?.trim(),
      label: formData.label?.trim(),
      node_type: formData.node_type || 'llm',
      phase_label: formData.phase_label?.trim() || '',
      task_prompt: formData.task_prompt?.trim() || '',
      conditional_edges: conditionalEdges.value
    }
  }
}


export const normalizeEdgePayload = (formData) => {
  const config = parseJsonInput(formData.config_json, {
    fallback: {},
    label: '边配置'
  })
  if (!config.ok) return config
  if (!isPlainObject(config.value)) {
    return { ok: false, error: '边配置必须是 JSON 对象' }
  }

  return {
    ok: true,
    value: {
      source_node_id: formData.source_node_id || '',
      target_node_id: formData.target_node_id || '',
      edge_type: formData.edge_type || 'call',
      label: formData.label?.trim() || '',
      condition_expr: formData.condition_expr?.trim() || '',
      order_index: normalizeInteger(formData.order_index, 0),
      config_json: config.value
    }
  }
}

export const normalizeInspectorPayload = (objectType, formData) => {
  if (objectType === 'graph') {
    return { ok: true, value: normalizeGraphPayload(formData) }
  }

  if (objectType === 'container') {
    const payload = normalizeContainerPayload(formData)
    if (!payload.ok) return payload
    return {
      ok: true,
      value: {
        label: payload.value.label,
        role_type: payload.value.role_type,
        order_index: payload.value.order_index,
        config_json: payload.value.config_json
      }
    }
  }

  if (objectType === 'node') {
    const payload = normalizeNodePayload(formData)
    if (!payload.ok) return payload
    return {
      ok: true,
      value: {
        container_id: payload.value.container_id,
        label: payload.value.label,
        node_type: payload.value.node_type,
        phase_label: payload.value.phase_label,
        task_prompt: payload.value.task_prompt,
        conditional_edges: payload.value.conditional_edges
      }
    }
  }

  if (objectType === 'edge') {
    const payload = normalizeEdgePayload(formData)
    if (!payload.ok) return payload
    return {
      ok: true,
      value: {
        label: payload.value.label || null,
        edge_type: payload.value.edge_type,
        condition_expr: payload.value.condition_expr || null,
        order_index: payload.value.order_index,
        config_json: payload.value.config_json
      }
    }
  }

  return { ok: true, value: {} }
}
