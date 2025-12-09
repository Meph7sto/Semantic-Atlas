<template>
  <div id="app">
    <el-container class="app-container">
      <!-- 顶部导航 -->
      <el-header class="app-header">
        <div class="header-content">
          <div class="logo">
            <el-icon size="28"><Document /></el-icon>
            <span class="logo-text">需求追溯系统</span>
          </div>
          <el-menu
            :default-active="$route.path"
            mode="horizontal"
            class="nav-menu"
            router
          >
            <el-menu-item index="/">
              <el-icon><EditPen /></el-icon>
              需求分析
            </el-menu-item>
            <el-menu-item index="/history">
              <el-icon><Clock /></el-icon>
              分析历史
            </el-menu-item>
            <el-menu-item index="/statistics">
              <el-icon><DataAnalysis /></el-icon>
              统计数据
            </el-menu-item>
          </el-menu>
        </div>
      </el-header>

      <!-- 主要内容区域 -->
      <el-main class="app-main">
        <router-view />
      </el-main>

      <!-- 底部 -->
      <el-footer class="app-footer">
        <div class="footer-content">
          <span>&copy; 2025 需求追溯系统 - 基于AI的需求全生命周期追溯分析</span>
        </div>
      </el-footer>
    </el-container>
  </div>
</template>

<script>
import { Document, EditPen, Clock, DataAnalysis } from '@element-plus/icons-vue'

export default {
  name: 'App',
  components: {
    Document,
    EditPen,
    Clock,
    DataAnalysis
  }
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
  color: #2c3e50;
  min-height: 100vh;
  background-color: #f5f7fa;
}

.app-container {
  min-height: 100vh;
}

.app-header {
  background: #fff;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 0;
  height: 60px !important;
  line-height: 60px;
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 0 20px;
}

.logo {
  display: flex;
  align-items: center;
  font-size: 20px;
  font-weight: bold;
  color: #409eff;
}

.logo .el-icon {
  margin-right: 8px;
}

.logo-text {
  background: linear-gradient(135deg, #409eff, #67c23a);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.nav-menu {
  border-bottom: none;
  background: transparent;
}

.nav-menu .el-menu-item {
  border-bottom: 2px solid transparent;
  color: #606266;
}

.nav-menu .el-menu-item:hover,
.nav-menu .el-menu-item.is-active {
  color: #409eff;
  border-bottom-color: #409eff;
  background: transparent;
}

.app-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  min-height: calc(100vh - 120px);
}

.app-footer {
  background: #fff;
  border-top: 1px solid #e4e7ed;
  height: 60px !important;
  line-height: 60px;
}

.footer-content {
  text-align: center;
  color: #909399;
  font-size: 14px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    height: auto;
    padding: 10px;
  }
  
  .logo {
    margin-bottom: 10px;
  }
  
  .app-header {
    height: auto !important;
  }
  
  .app-main {
    padding: 10px;
  }
}
</style>
