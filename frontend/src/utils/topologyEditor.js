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
  const config = parseJsonInput(formData.config_json, {
    fallback: {},
    label: '节点配置'
  })
  if (!config.ok) return config
  if (!isPlainObject(config.value)) {
    return { ok: false, error: '节点配置必须是 JSON 对象' }
  }

  const inputSchema = parseJsonInput(formData.input_schema_json, {
    fallback: [],
    label: '输入 Schema'
  })
  if (!inputSchema.ok) return inputSchema
  if (!Array.isArray(inputSchema.value)) {
    return { ok: false, error: '输入 Schema 必须是 JSON 数组' }
  }

  const outputSchema = parseJsonInput(formData.output_schema_json, {
    fallback: [],
    label: '输出 Schema'
  })
  if (!outputSchema.ok) return outputSchema
  if (!Array.isArray(outputSchema.value)) {
    return { ok: false, error: '输出 Schema 必须是 JSON 数组' }
  }

  const stagePrompt = typeof formData.stage_prompt === 'string'
    ? formData.stage_prompt.trim()
    : ''
  const configValue = { ...config.value }
  if (stagePrompt) {
    configValue.stage_prompt = stagePrompt
  } else if (Object.prototype.hasOwnProperty.call(configValue, 'stage_prompt')) {
    delete configValue.stage_prompt
  }

  return {
    ok: true,
    value: {
      container_id: formData.container_id || null,
      subgraph_id: formData.subgraph_id || null,
      node_key: formData.node_key?.trim(),
      label: formData.label?.trim(),
      node_type: formData.node_type || 'node',
      role_type: formData.role_type || 'human',
      order_index: normalizeInteger(formData.order_index, 0),
      config_json: configValue,
      input_schema_json: inputSchema.value,
      output_schema_json: outputSchema.value
    }
  }
}

export const normalizeSubgraphPayload = (formData) => {
  return {
    ok: true,
    value: {
      label: formData.label?.trim(),
      task_description: formData.task_description?.trim() || '',
      order_index: normalizeInteger(formData.order_index, 0)
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

  if (objectType === 'subgraph') {
    const payload = normalizeSubgraphPayload(formData)
    if (!payload.ok) return payload
    return {
      ok: true,
      value: {
        label: payload.value.label,
        task_description: payload.value.task_description,
        order_index: payload.value.order_index
      }
    }
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
        role_type: payload.value.role_type,
        order_index: payload.value.order_index,
        config_json: payload.value.config_json,
        input_schema_json: payload.value.input_schema_json,
        output_schema_json: payload.value.output_schema_json
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
