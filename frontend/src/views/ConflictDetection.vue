<script setup>
import { ref, onMounted, nextTick } from 'vue';
import axios from 'axios';

// State
const reqA = ref('');
const reqB = ref('');
const messages = ref([]);
const isLoading = ref(false);
const chatContainer = ref(null);
const showWelcome = ref(true);

// Methods
const clearChat = () => {
    messages.value = [];
    reqA.value = '';
    reqB.value = '';
    showWelcome.value = true;
};

const scrollToBottom = async () => {
    await nextTick();
    if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
    }
};

const checkConflict = async () => {
    if (!reqA.value.trim() || !reqB.value.trim()) {
        alert("Please enter both Requirement A and Requirement B.");
        return;
    }

    showWelcome.value = false;
    isLoading.value = true;

    // 1. Add User Message
    const userMsg = {
        role: 'user',
        content: `**Requirement A:**\n${reqA.value}\n\n**Requirement B:**\n${reqB.value}`
    };
    messages.value.push(userMsg);
    await scrollToBottom();

    try {
        // Use relative path which is proxied by Vite to Flask backend
        const response = await axios.post('/api/conflict/check', {
            requirement_a: reqA.value,
            requirement_b: reqB.value
        });

        // 2. Add AI Response
        const data = response.data;
        const statusHtml = data.is_conflict 
            ? '<span class="status-indicator status-conflict">CONFLICT DETECTED</span>'
            : '<span class="status-indicator status-ok">NO CONFLICT</span>';
            
        const aiMsg = {
            role: 'ai',
            content: `${statusHtml}\n\n${data.raw_response}`,
            type: 'html' // Custom flag to render HTML
        };
        messages.value.push(aiMsg);

    } catch (error) {
        console.error(error);
        messages.value.push({
            role: 'ai',
            content: `<span style="color: #ff6b6b">Error: ${error.message}</span>`,
            type: 'html'
        });
    } finally {
        isLoading.value = false;
        await scrollToBottom();
    }
};

// Handle Ctrl+Enter
const handleKeydown = (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        checkConflict();
    }
};
</script>

<template>
    <div class="layout">
        <!-- Sidebar -->
        <aside class="sidebar">
            <button class="new-chat-btn" @click="clearChat">
                <span>+</span> New Check
            </button>
            <div class="history-list">
                <div class="feature-item" style="text-align: left; color: var(--text-secondary);">
                    Previous Checks
                </div>
                <!-- Future history items -->
            </div>
            <div class="footer-info">
                Semantic Atlas v1.0
            </div>
        </aside>

        <!-- Main Content -->
        <main class="main-content">
            <div class="chat-container" ref="chatContainer" :class="{ 'has-messages': messages.length > 0 }">
                <!-- Welcome Screen -->
                <div v-if="showWelcome" class="welcome-screen">
                    <h1>Conflict Detection</h1>
                    <div class="feature-columns">
                        <div class="feature-col">
                            <div class="feature-icon">⚡</div>
                            <div class="feature-title">Fast Analysis</div>
                            <div class="feature-item">Instantly detects logical contradictions between requirements</div>
                        </div>
                        <div class="feature-col">
                            <div class="feature-icon">🧠</div>
                            <div class="feature-title">AI Powered</div>
                            <div class="feature-item">Uses DeepSeek-LLM to understand semantic nuances</div>
                        </div>
                        <div class="feature-col">
                            <div class="feature-icon">🛡️</div>
                            <div class="feature-title">Safety Focused</div>
                            <div class="feature-item">Identifies critical safety constraints and violations</div>
                        </div>
                    </div>
                </div>

                <!-- Chat Messages -->
                <div v-else class="messages-list">
                    <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
                        <div class="message-content">
                            <div class="avatar" :class="msg.role">
                                {{ msg.role === 'user' ? 'U' : 'AI' }}
                            </div>
                            <div class="text-content">
                                <div v-if="msg.type === 'html'" v-html="msg.content"></div>
                                <div v-else style="white-space: pre-wrap;">{{ msg.content }}</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Loading Indicator -->
                    <div v-if="isLoading" class="message ai">
                        <div class="message-content">
                            <div class="avatar ai">AI</div>
                            <div class="text-content">
                                <span class="loading-dots">Analyzing</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Input Area -->
            <div class="input-area">
                <div class="input-container">
                    <div class="input-row">
                        <div class="textarea-wrapper">
                            <label class="textarea-label">Requirement A</label>
                            <textarea 
                                v-model="reqA" 
                                placeholder="Enter the first requirement description..."
                                @keydown="handleKeydown"
                            ></textarea>
                        </div>
                        <div class="textarea-wrapper">
                            <label class="textarea-label">Requirement B</label>
                            <textarea 
                                v-model="reqB" 
                                placeholder="Enter the second requirement description..."
                                @keydown="handleKeydown"
                            ></textarea>
                        </div>
                    </div>
                    <button class="send-btn" @click="checkConflict" :disabled="isLoading || !reqA || !reqB">
                        <svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height="1em" width="1em" xmlns="http://www.w3.org/2000/svg"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                        Check
                    </button>
                </div>
                <div class="disclaimer">
                    AI can make mistakes. Consider checking important information.
                </div>
            </div>
        </main>
    </div>
</template>

<style scoped>
/* Scoped styles can override global or add component specific styles */
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background-color: var(--bg-color);
  color: var(--text-primary);
}

.footer-info {
    border-top: 1px solid rgba(255,255,255,0.1);
    padding-top: 10px;
    font-size: 0.8em;
    color: var(--text-secondary);
}

.messages-list {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.disclaimer {
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.75rem;
    margin-top: 10px;
    position: absolute;
    bottom: 10px;
}
</style>
