<template>
  <div class="ref-app">
    <div class="login-shell">
      <div class="login-card" data-animate style="--delay: 0.05s">
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
                class="role-card"
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
                placeholder="工号 / 学号 / 手机号"
              />
            </div>
            <div class="login-field">
              <label for="password">密码</label>
              <input
                id="password"
                v-model="password"
                type="password"
                placeholder="请输入密码"
              />
            </div>
            <div class="login-field">
              <label for="role">当前角色</label>
              <select id="role" v-model="selectedRole">
                <option v-for="role in roles" :key="role.value" :value="role.value">
                  {{ role.title }}
                </option>
              </select>
            </div>
            <div class="login-actions">
              <button type="submit" class="primary" :disabled="loading">
                {{ loading ? "登录中..." : "进入系统" }}
              </button>
              <button type="button" class="ghost">找回密码</button>
              <button type="button" class="ghost" @click="handleRegister">
                注册账号
              </button>
            </div>
            <div v-if="message" class="login-hint" :class="{ error: messageType === 'error' }">
              {{ message }}
            </div>
            <div class="login-hint">
              提示：测试账号 test / 密码 test
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { authApi } from "@/utils/api.js";

const router = useRouter();

const props = defineProps({
  defaultRole: {
    type: String,
    default: "",
  },
});

const roles = [
  {
    value: "admin",
    title: "管理员（Project Admin）",
    tag: "管理人员",
  },
  {
    value: "member",
    title: "成员（Contributor）",
    tag: "项目成员",
  },
  {
    value: "viewer",
    title: "访客（Viewer）",
    tag: "只读权限",
  },
];

const selectedRole = ref(props.defaultRole || roles[1].value); // 默认选择 member
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

const clearAuthStorage = () => {
  try {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  } catch (_) {
    // ignore
  }
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
    // 调用真实登录 API
    const result = await authApi.login(trimmedAccount, trimmedPassword, selectedRole.value);

    // 保存 token 和用户信息到 localStorage
    try {
      localStorage.setItem("token", result.token);
      localStorage.setItem("user", JSON.stringify(result));
      // 兼容旧的 actor/role 字段
      localStorage.setItem("actor", result.username || trimmedAccount);
      localStorage.setItem("role", result.role || selectedRole.value);
    } catch (e) {
      console.error("Failed to save auth data:", e);
    }

    showMessage("登录成功", "success");

    // Navigate to dashboard
    router.push({ name: 'main-dashboard' });

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
  router.push({ name: 'main-register' });
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
