import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './style.css'
import './assets/ref-styles.css'
import './assets/theme-components.css'
import { hasPermission, hasRole } from './directives/permission.js'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 注册权限指令
app.directive('has-permission', hasPermission)
app.directive('has-role', hasRole)

app.mount('#app')
