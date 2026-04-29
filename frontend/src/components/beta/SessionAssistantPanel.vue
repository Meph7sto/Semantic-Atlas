<script setup>
import { ref, nextTick, watch } from 'vue'
import { Bot, Plus, RefreshCw, Send, Sparkles, X } from 'lucide-vue-next'
import { useSessionAssistant } from '@/composables/useSessionAssistant'

const isAssistantOpen = ref(false)
const messagesContainerRef = ref(null)

const {
  projects,
  sessions,
  selectedProjectId,
  sessionId,
  messages,
  inputMessage,
  selectedModel,
  useThinkingMode,
  isSending,
  isLoadingProjects,
  isLoadingSessions,
  isCreatingSession,
  errorMessage,
  lastDispatchedAgents,
  sessionTitle,
  refreshWorkspace,
  createSession,
  handleSelectSession,
  sendMessage,
} = useSessionAssistant()

// 自动滚动到最新消息
watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    if (messagesContainerRef.value) {
      messagesContainerRef.value.scrollTop =
        messagesContainerRef.value.scrollHeight
    }
  },
)

const handleKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <!-- 悬浮球按钮 -->
  <button
    v-if="!isAssistantOpen"
    class="assistant-fab"
    @click="isAssistantOpen = true"
    title="打开小助手"
  >
    <Bot class="fab-icon" />
  </button>

  <!-- 悬浮对话面板 -->
  <Transition
    enter-active-class="panel-enter-active"
    enter-from-class="panel-enter-from"
    enter-to-class="panel-enter-to"
    leave-active-class="panel-leave-active"
    leave-from-class="panel-leave-from"
    leave-to-class="panel-leave-to"
  >
    <section v-if="isAssistantOpen" class="assistant-panel">
      <!-- 头部 -->
      <header class="panel-header">
        <div class="header-top">
          <div class="header-title-group">
            <Bot class="header-icon" />
            <h2 class="header-title">会话总控 Agent</h2>
          </div>
          <div class="header-actions">
            <button
              class="icon-btn"
              @click="refreshWorkspace"
              title="刷新"
            >
              <RefreshCw
                class="icon-sm"
                :class="isLoadingProjects || isLoadingSessions ? 'animate-spin' : ''"
              />
            </button>
            <button
              class="icon-btn"
              @click="isAssistantOpen = false"
              title="收起助手"
            >
              <X class="icon-sm" />
            </button>
          </div>
        </div>

        <!-- 项目和会话选择 -->
        <div class="header-controls">
          <div class="control-row">
            <select
              v-model="selectedProjectId"
              class="control-select"
            >
              <option value="">选择项目 ({{ projects.length }})</option>
              <option
                v-for="project in projects"
                :key="project.project_id"
                :value="project.project_id"
              >
                {{ project.name }}
              </option>
            </select>
            <button
              class="btn-primary-sm"
              :disabled="!selectedProjectId || isCreatingSession"
              @click="createSession"
            >
              <Plus class="icon-xs" />
              新建
            </button>
          </div>

          <div class="control-row">
            <select
              v-model="sessionId"
              class="control-select"
              @change="(e) => handleSelectSession(sessions.find(s => s.session_id === e.target.value))"
            >
              <option value="">未选择会话</option>
              <option
                v-for="(session, index) in sessions"
                :key="session.session_id"
                :value="session.session_id"
              >
                {{ sessionTitle(session, index) }} ({{ session.message_count || 0 }}条)
              </option>
            </select>
          </div>

          <!-- 已调度的子Agent -->
          <div v-if="lastDispatchedAgents.length" class="dispatched-agents">
            <span class="dispatched-label">已调度：</span>
            <span
              v-for="agent in lastDispatchedAgents"
              :key="agent"
              class="agent-badge"
            >
              {{ agent }}
            </span>
          </div>
        </div>
      </header>

      <!-- 消息区 -->
      <div class="panel-body">
        <div
          v-if="sessionId"
          ref="messagesContainerRef"
          class="messages-container"
        >
          <article
            v-for="message in messages"
            :key="message.message_id"
            class="message-bubble"
            :class="message.role === 'user' ? 'message-user' : 'message-assistant'"
          >
            <div class="message-role">
              <Bot v-if="message.role !== 'user'" class="role-icon" />
              <Sparkles v-else class="role-icon" />
              {{ message.role === 'user' ? 'User' : '会话总控' }}
            </div>
            <div class="message-content">{{ message.content }}</div>
          </article>
          <div v-if="messages.length === 0" class="messages-empty">
            暂无消息记录
          </div>
        </div>

        <div v-else class="panel-placeholder">
          <p>先选择或新建一个项目会话</p>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="panel-footer">
        <div v-if="errorMessage" class="error-bar">
          {{ errorMessage }}
        </div>
        <div class="footer-toolbar">
          <select v-model="selectedModel" class="control-select model-select">
            <option value="deepseek-v4-pro">V4 Pro</option>
            <option value="deepseek-v4-flash">V4 Flash</option>
          </select>
          <label class="thinking-toggle">
            <input
              v-model="useThinkingMode"
              type="checkbox"
              class="thinking-toggle-input"
            />
            <span class="thinking-toggle-track">
              <span class="thinking-toggle-thumb" />
            </span>
            <span class="thinking-toggle-label">
              思考
            </span>
          </label>
        </div>
        <div class="input-wrapper">
          <textarea
            v-model="inputMessage"
            class="message-input"
            :disabled="!sessionId || isSending"
            placeholder="向会话总控发送指令…"
            @keydown="handleKeydown"
          />
          <div class="input-actions">
            <button
              class="btn-send"
              :disabled="isSending || !inputMessage.trim() || !sessionId"
              @click="sendMessage"
            >
              <Send class="icon-xs" />
              {{ isSending ? '处理中' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </section>
  </Transition>
</template>

<style scoped>
/* ---- 悬浮球 ---- */
.assistant-fab {
  position: fixed;
  bottom: 32px;
  right: 32px;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, #1b2730 0%, #2f8f89 100%);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.22);
  transition: transform 0.2s, box-shadow 0.2s;
}

.assistant-fab:hover {
  transform: scale(1.08);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.32);
}

.fab-icon {
  width: 26px;
  height: 26px;
}

/* ---- 面板 ---- */
.assistant-panel {
  position: fixed;
  bottom: 32px;
  right: 32px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  width: 440px;
  max-width: calc(100vw - 2rem);
  height: 80vh;
  max-height: 860px;
  border: 1px solid rgba(47, 143, 137, 0.15);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(20px);
  overflow: hidden;
}

/* ---- 过渡动画 ---- */
.panel-enter-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.panel-leave-active {
  transition: all 0.2s ease-in;
}

.panel-enter-from,
.panel-leave-to {
  transform: translateY(16px) scale(0.96);
  opacity: 0;
}

.panel-enter-to,
.panel-leave-from {
  transform: translateY(0) scale(1);
  opacity: 1;
}

/* ---- 头部 ---- */
.panel-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(47, 143, 137, 0.1);
  background: linear-gradient(180deg, rgba(47, 143, 137, 0.06) 0%, transparent 100%);
  padding: 16px 20px;
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  width: 20px;
  height: 20px;
  color: #2f8f89;
}

.header-title {
  font-size: 15px;
  font-weight: 700;
  color: #1b2730;
  margin: 0;
  letter-spacing: 0.01em;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #5d6b76;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.icon-btn:hover {
  background: rgba(47, 143, 137, 0.1);
  color: #2f8f89;
}

.icon-sm {
  width: 16px;
  height: 16px;
}

.icon-xs {
  width: 14px;
  height: 14px;
}

/* ---- 控制区 ---- */
.header-controls {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.control-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-select {
  flex: 1;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  padding: 7px 10px;
  font-size: 13px;
  color: #1b2730;
  outline: none;
  transition: border-color 0.15s;
}

.control-select:focus {
  border-color: #2f8f89;
}

.btn-primary-sm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 7px 12px;
  border: none;
  border-radius: 8px;
  background: #1b2730;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-primary-sm:hover:not(:disabled) {
  background: #2f8f89;
}

.btn-primary-sm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ---- 已调度 ---- */
.dispatched-agents {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.dispatched-label {
  font-size: 11px;
  color: #9eabb4;
}

.agent-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  background: #1b2730;
  color: #fff;
}

/* ---- 消息区 ---- */
.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-bubble {
  max-width: 88%;
  padding: 12px 16px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.message-user {
  align-self: flex-end;
  background: linear-gradient(135deg, #1b2730, #2a3a45);
  color: #fff;
}

.message-assistant {
  align-self: flex-start;
  background: #f4f7f6;
  color: #1b2730;
  border: 1px solid rgba(47, 143, 137, 0.1);
}

.message-role {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  opacity: 0.6;
  margin-bottom: 6px;
}

.role-icon {
  width: 12px;
  height: 12px;
}

.message-content {
  font-size: 13.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.messages-empty {
  padding: 48px 0;
  text-align: center;
  font-size: 13px;
  color: #9eabb4;
}

.panel-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  color: #9eabb4;
  font-size: 13px;
}

/* ---- 输入区 ---- */
.panel-footer {
  flex-shrink: 0;
  border-top: 1px solid rgba(47, 143, 137, 0.1);
  background: rgba(247, 250, 249, 0.8);
  padding: 12px 16px;
}

.error-bar {
  margin-bottom: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(220, 38, 38, 0.2);
  border-radius: 8px;
  background: rgba(254, 242, 242, 0.9);
  font-size: 12px;
  color: #b91c1c;
}

.input-wrapper {
  border: 1px solid #d1d5db;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  transition: border-color 0.15s;
}

.input-wrapper:focus-within {
  border-color: #2f8f89;
}

.footer-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin-bottom: 8px;
}

.thinking-toggle {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.thinking-toggle-input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.thinking-toggle-track {
  position: relative;
  width: 38px;
  height: 22px;
  border-radius: 999px;
  background: #d1d5db;
  transition: background 0.15s ease;
}

.thinking-toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.2);
  transition: transform 0.15s ease;
}

.thinking-toggle-input:checked + .thinking-toggle-track {
  background: #2f8f89;
}

.thinking-toggle-input:checked + .thinking-toggle-track .thinking-toggle-thumb {
  transform: translateX(16px);
}

.thinking-toggle-label {
  font-size: 12px;
  font-weight: 600;
  color: #5d6b76;
  letter-spacing: 0.02em;
}

.message-input {
  display: block;
  width: 100%;
  height: 72px;
  resize: none;
  border: none;
  outline: none;
  padding: 10px 14px;
  font-size: 13.5px;
  line-height: 1.6;
  color: #1b2730;
  background: transparent;
}

.message-input::placeholder {
  color: #9eabb4;
}

.message-input:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px 8px;
}

.btn-send {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: none;
  border-radius: 8px;
  background: #2f8f89;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}

.btn-send:hover:not(:disabled) {
  background: #1b2730;
}

.btn-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
