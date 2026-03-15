# RequirementActor 设计方案 (专属需求条目)

## 1. 定位与核心职责

`RequirementActor` 是系统架构领域层（Domain Layer）的核心组件。它的唯一目标是：**作为单条需求记录（Requirement）生命周期与状态变更的绝对权威持有者。**

* **防并发冲突**：在成百上千个 Agent 和 Worker 并发执行时，它是单点串行化的“内存漏斗”，彻底避免多线程覆盖写或死锁。
* **业务一致性网关**：负责前置校验所有对需求状态的修改请求（如：已被基线的需求不允许被 Worker 静默修改）。
* **追溯与审计基石**：结合事件溯源（Event Sourcing），将所有变更转化为不可变事件持久化。

---

## 2. 核心架构原理：虚拟 Actor 模式

`RequirementActor` 采用虚拟 Actor（Virtual Actor）模式，对调用方屏蔽其物理内存的装载和销毁细节。

### 2.1 寻址与通信机制
* **唯一标识**：全局唯一定位符 `requirement_id`。
* **消息驱动**：外界与之交互的唯一手段是发送**命令（Command）**。Actor 不暴露直接修改内部属性的 Setter 方法。
* **单线程信箱（Mailbox queue）**：每个加载到内存的 Actor 实例都有一个专属的异步信箱（如 Python 的 `asyncio.Queue`）。发送给它的 Command 必须在信箱排队，**Actor 每次只出队一条消息处理**，天然实现读写安全。

### 2.2 透明生命周期管理 (Actor Manager)
* **透明唤醒（Activation）**：当关于 `req-123` 的命令到达时，Manager 检查其是否在内存。若不在，Manager 负责实例化空对象 -> 从数据库拉取状态或重放历史事件 -> 重建完毕 -> 开始处理信箱中的命令。
* **安全性休眠（Passivation）**：系统不长期驻留非活跃需求。Manager 定时扫描，如果某个 Actor 超过 `10分钟` 没有收到新命令，将启动休眠回收程序。**休眠必须满足两个绝对前提**：
  1. **Mailbox 必须彻底排空**：如果 Actor 正在处理积压消息，即便距离上一条已过去 10 分钟，定时器也**静默跳过**，打断休眠流程。
  2. **快照写入必须幂等确认**：在销毁内存对象前，必须成功将快照（Snapshot）落库。如果写库失败（网络抖动等），Actor 内存**绝对不能丢弃**，重置闲置计时器，等待下一个周期重试，确保状态不丢。

### 2.3 分布式场景下的绝对唯一性约束
需求条目在整个业务集群中是唯一的，因此 **同一个 `requirement_id` 对应的 Actor 实例在整个分布式集群中必须且只能存在一个**。如果允许两个节点各自激活了一个同样的 Actor 实例，串行化保证将立即崩溃。
为了守住这条底线，系统必须采用以下两种路由机制之一：
* **一致性哈希路由（推荐）**：API 网关或微服务 RPC 层通过 `Hash(requirement_id)`，将涉及同一条需求的所有请求强制路由到同一台物理节点 / Pod 身上。
* **分布式锁（保底方案）**：如果做不到精细路由，Actor 在 Activation（唤醒）的第一步，必须向 Redis 申请一把排他锁（如 `lock:actor:req-123`）。拿不到锁的节点必须将请求代理转发给持有该锁的节点。

---

## 3. 数据模型定义

### 3.1 Actor 内部状态快照 (State)
```python
class RequirementState:
    requirement_id: str        # 唯一标识
    version: int               # 单调递增版本号 (用于 Version Fencing)
    content: dict              # 结构化需求内容 (L1-L4, 验收标准等)
    status: str                # 阶段 (Draft, UnderReview, Baselined)
    quality_markers: dict      # 质检标签 (冲突、歧义标记)
    evidence_links: list       # 关联的会议纪要、截图等溯源信息
```

### 3.2 命令 (Command) 与 事件 (Event) 字典
Actor 遵循的生命周期律即为：`f(State, Command) -> Event(s)` 然后 `g(State, Event) -> State`

* **Command (外界的意图，可能被拒绝)**：
  * `UpdateRequirementContentCommand(l4_text="...")` -> 尝试填写大模型生成的 L4 正文。
  * `ChangeStatusToReviewCommand()` -> 将状态推向评审。
* **Event (已发生的不可变事实，必须被接受)**：
  * `RequirementContentUpdatedEvent(l4_text="...", timestamp="...")`
  * `RequirementStatusChangedEvent(old_status="Draft", new_status="UnderReview")`

---

## 4. 核心工作流：Command 处理引擎

当一个 Actor 出队获取到一条 Command（例如：`UpdateRequirementContentCommand`）时，执行以下严密流转：

1. **前置业务校验 (Validation)**：
   Actor 查看自己的内存状态。例如：当前 `status == 'Baselined'`，拒绝修改，抛出 `DomainException("禁止修改已基线需求")`。
2. **生成事件 (Event Generation)**：
   校验通过后，构造 `RequirementContentUpdatedEvent`。
3. **持久化事件 (Append Event Store)**：
   首要动作是将 Event **仅追加 (Append-Only)** 写入底层数据库（如 PostgreSQL 的 `events_table`）。
4. **状态突变 (Mutate State)**：
   数据库写入确认后，Actor 立刻把该 Event 应用于自己的内存变量，并将 `self.version += 1`。
5. **返回成功反馈 (Ack Response)**：
   向外部调用方返回：`{"status": "success", "new_version": self.version}`。

---

## 5. 高维特性支持：写后即读（Read-Your-Writes）

由于异步读模型的建立存在延迟，为了保证 Agent 或前台操作能够“所见即查”，需要提供专属查询通道机制：

### 5.1 Actor Ask (内部特权穿透查询)
对内提供的特权 RPC。如果计划 Agent 要马上利用 Actor 算出的结果，允许它发 `QueryStateCommand` 到 Actor 的信箱。Actor 处理到该命令时，直接将自己内存中最新的 `RequirementState` 返回，免除一切入库和拉库的开销与延迟。

### 5.2 Version Fencing (按版本阻塞式外部查询)
对外提供的接口防护。Worker 修改了需求并返回 `version=42` 给主控程序，前端页面或外部服务读取查询模型时附带 `min_version=42`，查库服务会在读库未赶上该版本时轮询阻塞等待。**如果等待超过设定的超时时间（例如 5 秒），必须中断轮询并返回 503 Service Unavailable**，让调用方决定是否重试，绝不允许查询端无脑无限期挂起消耗服务器连接池。

---

## 6. Python 极简落地示例（FastAPI / asyncio）

不借助沉重的第三方中间件，手写 Manager 也是完全可控的：

```python
import asyncio
import time
from typing import Dict

class RequirementActor:
    def __init__(self, req_id: str):
        self.req_id = req_id
        self.state = {} # 重建的内部状态
        self.mailbox = asyncio.Queue()
        self.last_accessed = time.time()
        self.is_faulted = False # 熔断标记
        
        # 启动消费协程
        self._consumer_task = asyncio.create_task(self._process_mailbox())

    async def _handle_command(self, command):
        """核心业务逻辑伪代码示范"""
        # 1. 业务校验 (Validation)
        if getattr(command, "type", "") == "UpdateRequirementContent":
            if self.state.get("status") == "Baselined":
                raise DomainException("禁止修改已基线需求")
        
        # 2. 构造事件 (Generate Event)
        event = {"event_type": "RequirementContentUpdated", "payload": getattr(command, "payload", {})}
        
        # 3. 落库持久化 (Append Event Store)
        # 此处若数据库网络抖动超时，应向外抛出 InfrastructureException
        # await self.event_store.append(self.req_id, event) 
        
        # 4. 更新内存 (Mutate State) - [警告] 必须在落库成功确认后才能执行内存突变！
        # self.state = apply_event(self.state, event)
        self.state["version"] = self.state.get("version", 0) + 1
        return {"status": "success", "new_version": self.state["version"]}

    async def _process_mailbox(self):
        MAX_RETRIES = 3
        while True:
            if self.is_faulted:
                # 若 Actor 已触发熔断，拒绝消费新消息
                # [Fix] 主动清空信箱中所有由于熔断前已经积压进去的命令，给每个调用方明确错误，防止被连带挂起
                while not self.mailbox.empty():
                    try:
                        cmd, fut = self.mailbox.get_nowait()
                        if not fut.done():
                            fut.set_exception(Exception(f"ActorFaultedException: Actor {self.req_id} 已熔断，旧有积压命令连带取消。"))
                        self.mailbox.task_done()
                    except asyncio.QueueEmpty:
                        break
                await asyncio.sleep(5)
                continue

            # 单线程串行出队
            command, future = await self.mailbox.get()
            self.last_accessed = time.time()
            
            retry_count = 0
            is_resolved = False
            
            # 使用内部循环保障基建异常可重试，同时确保此 Command 绝对不被重入队导致“插队”或乱序
            while not is_resolved and not self.is_faulted:
                try:
                    # 1.校验 -> 2.造事件 -> 3.落库 -> 4.改内存
                    result = await self._handle_command(command)
                    future.set_result(result)
                    is_resolved = True
                except DomainException as e:
                    # 业务拒绝规则（如：修改已基线需求）
                    # 明确的拒绝语义，无需物理重试，直接向客户端返回 4xx
                    future.set_exception(e)
                    is_resolved = True
                except InfrastructureException as e:
                    # 基建故障（如：数据库宕机）
                    retry_count += 1
                    if retry_count >= MAX_RETRIES:
                        self.is_faulted = True  # 最大重试耗尽，彻底熔断该 Actor
                        future.set_exception(e) 
                        is_resolved = True
                        # logger.critical(f"Actor {self.req_id} 突破最大重试失败并被熔断！")
                    else:
                        await asyncio.sleep(2 ** retry_count) # 指数避让，下一轮继续原样处理该指令
                except Exception as e:
                    # 兜底：未知的代码 Bug，为了防止无限死循环，抛出 500 而不重试
                    future.set_exception(e)
                    is_resolved = True

            self.mailbox.task_done()

# 全局 Actor 管理器，屏蔽物理存在细节
class ActorManager:
    _actors: Dict[str, RequirementActor] = {}

    @classmethod
    async def send_command(cls, req_id: str, command):
        if req_id not in cls._actors:
            # 激活（初始化并加载历史事件重建状态）
            cls._actors[req_id] = RequirementActor(req_id)
            # await cls._actors[req_id].load_history()

        actor = cls._actors[req_id]
        
        if actor.is_faulted:
            raise Exception(f"ActorFaultedException: Actor {req_id} 已熔断，由于底层状态异常，拒绝接受新命令")

        future = asyncio.get_running_loop().create_future()
        # 将命令连同 future 放入信箱排队，然后 await 获取结果
        await actor.mailbox.put((command, future))
        return await future

    @classmethod
    async def deactivate_actor(cls, req_id: str):
        """生命周期释放 (Passivation): 确保关闭协程与清除内存记录，防止协程泄露"""
        if req_id in cls._actors:
            actor = cls._actors[req_id]
            # [Fix] 显式取消协程并析构字典键值，防止资源泄露
            if actor._consumer_task and not actor._consumer_task.done():
                actor._consumer_task.cancel()
            del cls._actors[req_id]
```

## 7. 前端 Alpha 独立分支：Actor 可视化监控与测试专区设计

为了在上线前确保这套自定义 Actor 模式真正经得起并发风暴及异常情形的考验，特建议在前端单独开辟一个 `actor-visual-tester` 界面，专门用于研发自测与调试。

### 7.1 建立独立的测试页面（Actor Dashboard）
该页面完全游离于正常的用户业务界面之外，扮演控制台（Cockpit）的角色。

#### 页面布局（三分屏设计）

**左侧栏：物理大盘（全局状态）**
*   **Actor 存活监控**：展示当前 Python 内存中的 `ActorManager._actors` 列表（按 ID、当前 `version`、闲置时长降序排列）。
*   **全局仪表盘**：活体数（Active）、重试耗尽熔断数（Faulted）、历史累积落库事件总条数。提供一个红色的“一键强制刷库并卸载所有内存 Actor（清场）”按钮。

**中栏：焦点靶向控制器（打靶单个Actor）**
该区域必须绑定一个具体的 `requirement_id`。**强烈建议直接调用后端已有的 `RequirementsManageService.list_requirements(project_id)` 接口，加载测试库中某个真实存在的项目及其下属的所有真实需求条目，从下拉列表中选择一个真实的 `req_id` 作为靶标进行模拟（而非随便乱编的假 ID）**。
锁定真实的靶标需求后，你可以对它模拟各种恶劣的操作：
*   **断网重放测试 (Event Sourcing Replay)**：从页面手动踢掉内存中已经缓存的 Actor。随后发送新命令，观测系统是否如期触发了从真实数据库中（Event Store）提取历史变动事件、并在 0.1 秒内逐个 `apply()` 完毕重建成最新快照全过程。这是检验虚拟 Actor 透明唤醒机制（Activation）的最硬核测试。
*   **手动发令枪**：表单提供各类命令的极简下拉框：发送普通修改、发送修改（故意伪造缺少必填项以触犯 DomainException）、发送变更（但后台主动拔掉数据库网线或停止数据库引擎以此触发 InfrastructureException）。
*   **高并发压力泵**：设置并发数（如 `100 次 / 1秒`），向这个 Actor 疯狂发射相同或不同的 Command，模拟 Worker 风暴，用来验证哪怕被调用多少次，它的自增版本号 `version` 也一定是顺次累加，绝不出现 `Dirty Read`。

**右栏：实时心电图与时序日志（X光机）**
*   **Mailbox 排队漏斗动画**：以纵向队列的 UI 组件，实时展示该 Actor 当前 `asyncio.Queue` 里的积压深度，队列中的卡片出队就伴随一个 UI 闪烁，证明它是被“一条条单次执行的”。
*   **生命周期轨迹打点（Live Log River）**：一条从上滚下的黑底绿字日志流。展示前端通过 WebSocket 订阅到的 Actor 内部心跳：
    > `[10:00:01] 唤醒激活 req-123，耗时 13ms`
    > `[10:00:01] 开始消费 Command: UpdateTitle`
    > `[10:00:03] 遭遇基建网络跌落 正在进行第 1 次指数退避 (sleep 2)`
    > `[10:00:05] 第 2 次重试成功，发生状态突变 (version 41->42)`
    > `[10:10:05] 闲置超时 10min... 正在排空队列... 快照已安全落库。`
    > `[10:10:06] Actor req-123 销毁完毕，释放物理内存。`

### 7.2 联调与技术实现要点
如果要在这套 Alpha 专属的控制中心达到上述极致的观测体验，后端必须做两件事的配合：
1. **暴露特权巡检接口**：如 `GET /_internals/actors/stats`，直接透出 `ActorManager` 的字典及各个对象的 `queue.qsize()` 等内部物理指标。
2. **埋点 WebSocket 广播**：在上述单机方案的伪代码里，`_process_mailbox` 的生命周期关键节点上（如重试、丢出异常、成功出队），均通过如 `socketio.emit('actor_dev_trace', {...})` 将日志以广播形式发布，前端通过特定的专用频道接收渲染。

## 8. 方案总结

该 `RequirementActor` 设计实现了：
1. **隔离复杂度**：剥离并发锁等传统数据库防冲突技术细节，专注于需求对象生命周期的自身状态校验。
2. **天生护航高并发**：面对大模型（LLM）等异步 Worker 的并行请求和海量短时间回调风暴，通过 Queue 单一串行出口实现稳定接单。
3. **弹性内存管理**：不活跃的记录被自动卸载下线，不再占据内存；通过快照（Snapshot）和事件溯源（Event Sourcing），随时能从休眠状态复苏并复核。
