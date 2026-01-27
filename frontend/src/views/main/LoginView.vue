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
              提示：借用人员需提前 1-7 天预约，校外借用需缴费确认后生效。
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
    value: "teacher",
    title: "成员（Contributor）",
    tag: "项目成员",
  },
  {
    value: "external",
    title: "访客（Viewer）",
    tag: "只读权限",
  },
];

const selectedRole = ref(props.defaultRole || roles[0].value);
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

const handleEnter = async () => {
  message.value = "";
  const trimmedAccount = account.value.trim();

  loading.value = true;
  try {
    // Prototyping Mode: Bypass actual login
    await new Promise(resolve => setTimeout(resolve, 600)); // Simulate delay

    // Navigate to dashboard
    router.push({ name: 'main-dashboard' });

    emit("enter", {
      role: selectedRole.value,
      user: {
        name: "Test User",
        role: selectedRole.value,
        token: "mock-token"
      }
    });
  } catch (error) {
    console.error(error);
    // Even on error, for prototype, just enter
    router.push({ name: 'main-dashboard' });
    emit("enter", { role: selectedRole.value, user: { role: selectedRole.value } });
  } finally {
    loading.value = false;
  }
};

const handleRegister = () => {
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
