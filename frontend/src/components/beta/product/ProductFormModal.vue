<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <h3>{{ mode === 'create' ? '新建产品' : '编辑产品' }}</h3>
      <div class="form-group">
        <label>产品名称 *</label>
        <input type="text" v-model="form.name" placeholder="输入产品名称" />
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea v-model="form.description" placeholder="输入产品描述" rows="3"></textarea>
      </div>
      <div class="form-group">
        <label>版本</label>
        <input type="text" v-model="form.version" placeholder="如: v1.0.0" />
      </div>
      <div class="form-group">
        <label>路线图</label>
        <input type="text" v-model="form.roadmap" placeholder="产品路线图说明" />
      </div>
      <div class="form-group">
        <label>标签 (逗号分隔)</label>
        <input type="text" v-model="form.tagsInput" placeholder="tag1, tag2, tag3" />
      </div>
      <div class="modal-actions">
        <button type="button" class="action-btn white sa-button sa-button--secondary" @click="$emit('close')">取消</button>
        <button
          type="button"
          class="action-btn brown sa-button sa-button--primary"
          @click="handleSubmit"
          :disabled="!form.name.trim()"
        >
          {{ mode === 'create' ? '创建' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  mode: { type: String, required: true }, // 'create' | 'edit'
  initial: { type: Object, default: null },
})

const emit = defineEmits(['submit', 'close'])

const form = ref({
  name: '',
  description: '',
  version: '',
  roadmap: '',
  tagsInput: '',
})

watch(
  () => props.initial,
  (val) => {
    if (val) {
      form.value = {
        name: val.name || '',
        description: val.description || '',
        version: val.version || '',
        roadmap: val.roadmap || '',
        tagsInput: (val.tags || []).join(', '),
      }
    } else {
      form.value = { name: '', description: '', version: '', roadmap: '', tagsInput: '' }
    }
  },
  { immediate: true }
)

const handleSubmit = () => {
  emit('submit', { ...form.value })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-content h3 {
  margin: 0 0 1.5rem 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  margin-bottom: 0.5rem;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  font-size: 0.875rem;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--primary-color, #c4692f);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.action-btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.2s;
}

.action-btn.brown {
  background: var(--primary-color, #c4692f);
  color: white;
}

.action-btn.brown:hover {
  background: #b35d28;
}

.action-btn.brown:disabled {
  background: #d1d5db;
  cursor: not-allowed;
}

.action-btn.white {
  background: white;
  border-color: var(--border-color, #e5e7eb);
  color: var(--text-primary, #1f2937);
}

.action-btn.white:hover {
  background: var(--surface-secondary, #f9fafb);
}
</style>
