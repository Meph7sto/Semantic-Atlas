# 需求追溯系统

基于大语言模型的智能需求追溯关系分析系统，专注于顶层需求与底层需求之间的追溯关系识别。

## 🚀 功能特性

- **AI智能分析**: 基于大语言模型的需求关系智能分析
- **关系追溯**: 自动识别顶层需求与底层需求之间的追溯关系
- **批量分析**: 支持多对需求的批量关系分析
- **可视化展示**: 直观的追溯网络图和关系统计
- **灵活输入**: 支持动态添加/删除需求项
- **响应式设计**: 支持PC和移动设备访问

## 🏗️ 项目结构

```
requirement-trace-local/
├── backend/                 # Flask后端
│   ├── app/
│   │   ├── __init__.py      # Flask应用初始化
│   │   ├── models.py        # 数据模型
│   │   ├── routes.py        # API路由
│   │   └── services.py      # 业务逻辑服务
│   ├── requirements.txt     # Python依赖
│   ├── config.py           # 配置文件
│   ├── run.py              # 启动脚本
│   └── app.env             # 环境变量
├── frontend/               # Vue.js前端
│   ├── src/
│   │   ├── components/     # 组件
│   │   ├── views/          # 页面
│   │   ├── api/            # API服务
│   │   └── router/         # 路由配置
│   ├── package.json        # 前端依赖
│   └── vue.config.js       # Vue配置
└── README.md
```

## 🛠️ 技术栈

### 后端
- **Flask**: Python Web框架
- **FastAPI**: AI推理服务框架
- **Flask-SQLAlchemy**: ORM数据库操作
- **Flask-CORS**: 跨域资源共享
- **SQLite**: 轻量级数据库

### AI推理
- **Transformers**: Hugging Face模型库
- **DeepSeek-7B**: 大语言模型
- **Safetensors**: 模型权重格式
- **BitsAndBytes**: 模型量化

### 前端
- **Vue 3**: 渐进式JavaScript框架
- **Element Plus**: 企业级UI组件库
- **ECharts**: 数据可视化图表库
- **Axios**: HTTP客户端
- **Vue Router**: 前端路由

## 📦 安装部署

### 环境要求
- Python 3.8+
- Node.js 16+
- npm 或 yarn

### 后端部署

1. **进入后端目录**
   ```bash
   cd backend
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   ```bash
   # 复制环境变量文件
   copy app.env .env  # Windows
   cp app.env .env    # macOS/Linux
   ```

5. **启动后端服务**
   ```bash
   python run.py
   ```

   后端服务将在 `http://localhost:5000` 启动

### 前端部署

1. **进入前端目录**
   ```bash
   cd frontend
   ```

2. **安装依赖**
   ```bash
   npm install
   # 或者
   yarn install
   ```

3. **启动开发服务器**
   ```bash
   npm run serve
   # 或者
   yarn serve
   ```

   前端服务将在 `http://localhost:8080` 启动

4. **构建生产版本**
   ```bash
   npm run build
   # 或者
   yarn build
   ```

## 🎯 使用指南

### 关系追溯分析
1. 访问系统首页
2. 选择"关系追溯"模式（默认）
3. 在顶层需求区域输入一个或多个顶层需求
4. 在底层需求区域输入一个或多个底层需求
5. 点击"分析追溯关系"按钮
6. 查看分析结果，包括关系类型、置信度等

### 批量分析
1. 选择"批量分析"模式
2. 在顶层需求列表中输入多个顶层需求（每行一个）
3. 在底层需求列表中输入多个底层需求（每行一个）
4. 点击"批量分析追溯关系"按钮
5. 查看批量分析结果和关系统计

### 需求管理
1. 使用"添加"按钮动态增加需求项
2. 使用"删除"按钮移除不需要的需求项
3. 系统自动过滤空的需求项
4. 支持快速示例填充

## 🔧 开发指南

### API接口

#### 健康检查
```
GET /api/health
```

#### 关系追溯分析
```
POST /api/trace-relation
{
  "high_level_requirement": "顶层需求描述",
  "low_level_requirement": "底层需求描述",
  "save_to_db": false
}
```

#### 批量关系分析
```
POST /api/batch-trace-relation
{
  "high_level_requirements": ["顶层需求1", "顶层需求2"],
  "low_level_requirements": ["底层需求1", "底层需求2"],
  "save_to_db": false
}
```

#### AI推理服务
```
POST /ai/analyze-relation
{
  "high_level_requirement": "顶层需求描述",
  "low_level_requirement": "底层需求描述",
  "max_tokens": 1000,
  "temperature": 0.1
}
```

#### 获取统计数据
```
GET /api/statistics
```

### 数据模型

#### 需求模型 (Requirement)
- `id`: 主键
- `title`: 需求标题
- `description`: 需求描述
- `created_at`: 创建时间
- `updated_at`: 更新时间

#### 追溯记录模型 (TraceRecord)
- `id`: 主键
- `requirement_id`: 关联需求ID
- `stage`: 阶段名称
- `stage_type`: 阶段状态 (success/warning/error/info)
- `description`: 阶段描述

#### 风险模型 (Risk)
- `id`: 主键
- `requirement_id`: 关联需求ID
- `title`: 风险标题
- `description`: 风险描述
- `level`: 风险等级 (high/warning/info/low)

#### 建议模型 (Suggestion)
- `id`: 主键
- `requirement_id`: 关联需求ID
- `content`: 建议内容
- `priority`: 优先级 (high/medium/low)

## 🐛 常见问题

### Q: 后端启动失败
A: 请检查Python版本和依赖安装，确保使用Python 3.8+

### Q: 前端编译错误
A: 请检查Node.js版本，建议使用Node.js 16+

### Q: 数据库连接失败
A: 系统使用SQLite数据库，会自动创建，无需额外配置

### Q: 跨域问题
A: 后端已配置CORS，如有问题请检查前后端端口配置

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交Issue和Pull Request来帮助改进项目！

## 📞 联系方式

如有问题，请通过以下方式联系：
- 提交GitHub Issue
- 发送邮件至开发团队
