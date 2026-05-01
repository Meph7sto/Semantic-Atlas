<template>
  <div class="ref-app sa-page">
    <div class="login-shell sa-page-surface">
      <div class="login-card sa-card" data-animate style="--delay: 0.05s">
        <div class="login-header">
          <div>
            <p class="eyebrow">Semantic Atlas</p>
            <h1>用户注册</h1>
          </div>
          <div class="login-brand">
            <span class="login-mark">Semantic</span>
            <span class="login-sub">Atlas</span>
          </div>
        </div>
        <form class="login-form" @submit.prevent="handleRegister">
          <div class="login-field">
            <label for="username">用户名</label>
            <input
              id="username"
              v-model="username"
              type="text"
              class="sa-input"
              placeholder="请输入用户名"
              @input="usernameError = ''"
            />
            <p v-if="usernameError" class="field-error">{{ usernameError }}</p>
            <p class="field-hint">用户名只能包含字母、数字、下划线和中划线</p>
          </div>
          <div class="login-field">
            <label for="displayName">显示名称</label>
            <input
              id="displayName"
              v-model="displayName"
              type="text"
              class="sa-input"
              placeholder="请输入显示名称"
              @input="displayNameError = ''"
            />
            <p v-if="displayNameError" class="field-error">{{ displayNameError }}</p>
          </div>
          <div class="login-field">
            <label for="password">密码</label>
            <input
              id="password"
              v-model="password"
              type="password"
              class="sa-input"
              placeholder="请输入密码（至少 6 位）"
              @input="passwordError = ''"
            />
            <p v-if="passwordError" class="field-error">{{ passwordError }}</p>
          </div>
          <div class="login-field">
            <label for="confirmPassword">确认密码</label>
            <input
              id="confirmPassword"
              v-model="confirmPassword"
              type="password"
              class="sa-input"
              placeholder="请再次输入密码"
              @input="confirmPasswordError = ''"
            />
            <p v-if="confirmPasswordError" class="field-error">{{ confirmPasswordError }}</p>
          </div>
          <div class="login-actions">
            <button type="submit" class="primary sa-button sa-button--primary" :disabled="loading">
              {{ loading ? "注册中..." : "注册账号" }}
            </button>
            <button type="button" class="ghost sa-button sa-button--secondary" @click="handleBack">
              返回登录
            </button>
          </div>
          <div v-if="message" class="login-hint" :class="{ error: messageType === 'error' }">
            {{ message }}
          </div>
          <div v-if="!message" class="login-hint">
            提交注册申请后需管理员审批，审批通过后才能登录
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { authApi } from "@/api/auth";

const router = useRouter();

const username = ref("");
const displayName = ref("");
const password = ref("");
const confirmPassword = ref("");
const loading = ref(false);
const message = ref("");
const messageType = ref("success");

// 字段错误
const usernameError = ref("");
const displayNameError = ref("");
const passwordError = ref("");
const confirmPasswordError = ref("");

const showMessage = (text, type = "success") => {
  message.value = text;
  messageType.value = type;
};

const clearMessage = () => {
  message.value = "";
};

const validateForm = () => {
  let isValid = true;

  // 验证用户名
  if (!username.value.trim()) {
    usernameError.value = "请输入用户名";
    isValid = false;
  } else if (!/^[a-zA-Z0-9_-]+$/.test(username.value)) {
    usernameError.value = "用户名只能包含字母、数字、下划线和中划线";
    isValid = false;
  }

  // 验证显示名称
  if (!displayName.value.trim()) {
    displayNameError.value = "请输入显示名称";
    isValid = false;
  }

  // 验证密码
  if (!password.value) {
    passwordError.value = "请输入密码";
    isValid = false;
  } else if (password.value.length < 6) {
    passwordError.value = "密码长度不能少于 6 位";
    isValid = false;
  }

  // 验证确认密码
  if (!confirmPassword.value) {
    confirmPasswordError.value = "请再次输入密码";
    isValid = false;
  } else if (password.value !== confirmPassword.value) {
    confirmPasswordError.value = "两次输入的密码不一致";
    isValid = false;
  }

  return isValid;
};

const handleRegister = async () => {
  clearMessage();

  if (!validateForm()) {
    return;
  }

  loading.value = true;
  try {
    await authApi.register(
      username.value.trim(),
      password.value,
      displayName.value.trim(),
      "viewer"
    );

    showMessage("注册申请已提交，请等待管理员审批，正在返回登录页面...", "success");

    // 延迟后跳转到登录页面
    setTimeout(() => {
      router.push({ name: 'beta-login' });
    }, 1500);
  } catch (error) {
    console.error("Register error:", error);
    const errorMsg =
      error.response?.data?.detail ||
      error.response?.data?.error ||
      error.message ||
      "注册失败，请稍后重试";
    showMessage(errorMsg, "error");

    // 如果是用户名已存在的错误，显示在字段下方
    if (errorMsg.includes("用户名已存在")) {
      usernameError.value = errorMsg;
    }
  } finally {
    loading.value = false;
  }
};

const handleBack = () => {
  router.push({ name: 'beta-login' });
};
</script>

<style scoped>
.field-error {
  color: #ef4444;
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.field-hint {
  color: #6b7280;
  font-size: 0.75rem;
  margin-top: 0.25rem;
}
</style>
