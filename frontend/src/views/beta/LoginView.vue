<template>
  <div class="ref-app sa-page">
    <div class="login-shell sa-page-surface">
      <div class="login-card sa-card" data-animate style="--delay: 0.05s">
        <div class="login-header">
          <div>
            <p class="eyebrow">Semantic Atlas</p>
            <h1>统一入口 · 全角色协同</h1>
          </div>
          <div class="login-brand">
            <span class="login-mark">Semantic</span>
            <span class="login-sub">Atlas</span>
          </div>
        </div>
        <div class="login-grid">
          <section class="login-panel">
            <h2>选择角色</h2>
            <p class="login-caption">已预设所有角色与流程入口</p>
            <div class="role-grid">
              <button
                v-for="role in roles"
                :key="role.value"
                type="button"
                class="role-card sa-card sa-card--interactive sa-card--selectable"
                :class="{ active: selectedRole === role.value }"
                :aria-pressed="selectedRole === role.value ? 'true' : 'false'"
                @click="selectedRole = role.value"
              >
                <div>
                  <h3>{{ role.title }}</h3>
                </div>
                <span class="chip chip-neutral">{{ role.tag }}</span>
              </button>
            </div>
          </section>
          <form class="login-form" @submit.prevent="handleEnter">
            <div class="login-field">
              <label for="account">账号</label>
              <input
                id="account"
                v-model="account"
                type="text"
                class="sa-input"
                placeholder="工号 / 学号 / 手机号"
              />
            </div>
            <div class="login-field">
              <label for="password">密码</label>
              <input
                id="password"
                v-model="password"
                type="password"
                class="sa-input"
                placeholder="请输入密码"
              />
            </div>
            <div class="login-field">
              <label for="role">当前角色</label>
              <select id="role" v-model="selectedRole" class="sa-input">
                <option v-for="role in roles" :key="role.value" :value="role.value">
                  {{ role.title }}
                </option>
              </select>
            </div>
            <div class="login-actions">
              <button type="submit" class="primary sa-button sa-button--primary" :disabled="loading">
                {{ loading ? "登录中..." : "进入系统" }}
              </button>
              <button type="button" class="ghost sa-button sa-button--secondary">找回密码</button>
              <button type="button" class="ghost sa-button sa-button--secondary" @click="handleRegister">
                注册账号
              </button>
            </div>
            <div v-if="message" class="login-hint" :class="{ error: messageType === 'error' }">
              {{ message }}
            </div>
            <div class="login-hint">
              提示：超级管理员 admin / admin；测试账号 test / test
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const props = defineProps({
  defaultRole: {
    type: String,
    default: "",
  },
});

const roles = [
  {
    value: "super_admin",
    title: "高级管理员 (SUPER_ADMIN)",
    tag: "全平台最高权限",
  },
  {
    value: "admin",
    title: "管理员 (ADMIN)",
    tag: "平台管理",
  },
  {
    value: "member",
    title: "项目成员 (MEMBER)",
    tag: "内部员工",
  },
  {
    value: "viewer",
    title: "访客 (VIEWER)",
    tag: "只读权限",
  },
];

const selectedRole = ref(
  props.defaultRole || roles.find((role) => role.value === "member")?.value || roles[0].value
);
const account = ref("");
const password = ref("");
const loading = ref(false);
const message = ref("");
const messageType = ref("success");

const emit = defineEmits(["enter", "register"]);

const showMessage = (text, type = "success") => {
  message.value = text;
  messageType.value = type;
};

const getRedirectTarget = () => {
  const candidate = typeof route.query.redirect === "string" ? route.query.redirect : "";
  if (!candidate.startsWith("/") || candidate.startsWith("//")) {
    return null;
  }
  return candidate;
};

const handleEnter = async () => {
  message.value = "";
  const trimmedAccount = account.value.trim();
  const trimmedPassword = password.value;

  if (!trimmedAccount) {
    showMessage("请输入账号", "error");
    return;
  }

  if (!trimmedPassword) {
    showMessage("请输入密码", "error");
    return;
  }

  loading.value = true;
  try {
    // 使用 Pinia Store 登录
    const result = await authStore.login(trimmedAccount, trimmedPassword, selectedRole.value);

    showMessage("登录成功", "success");

    const redirectTarget = getRedirectTarget();

    if (redirectTarget) {
      router.push(redirectTarget);
    } else {
      router.push({ name: 'beta-dashboard' });
    }

    emit("enter", {
      role: result.role || selectedRole.value,
      user: result
    });
  } catch (error) {
    console.error("Login error:", error);
    const errorMsg = error.response?.data?.error || error.message || "登录失败，请检查账号和密码";
    showMessage(errorMsg, "error");
  } finally {
    loading.value = false;
  }
};

const handleRegister = () => {
  // 跳转到注册页面
  router.push({ name: 'beta-register' });
  // 保留 emit 以兼容可能的父组件调用
  emit("register", selectedRole.value);
};

watch(
  () => props.defaultRole,
  (value) => {
    if (value) {
      selectedRole.value = value;
    }
  }
);
</script>
