# 搭建路线图：Claude 长期记忆库系统

**配套文档：** claude-memory-prd-v2.md  
**版本：** v0.2（基于 Claude Imprint 改造）  
**预计总工时：** 约 1 周（原 2-3 周，省掉从零搭基础设施的部分）  
**工具：** Cursor（写代码）+ 云服务器 + 朋友协助环境配置  
**底座：** Claude Imprint（已实现 MCP Server + Cloudflare Tunnel + Dashboard）  
**情感衰减：** 移植自 Ombre-Brain（改进版艾宾浩斯遗忘曲线 + Russell 情感坐标）

---

## 变更说明（对比 v0.1）

原 Roadmap 的核心工作量在"从零搭基础设施"——FastAPI、PostgreSQL、pgvector、MCP 协议层、接入 claude.ai，这五块加起来占了 2-3 周预估工时里的大半。

换底座之后，Claude Imprint 已经把这些全部做完了。调整后的 Roadmap 重心从"搭"变成"改"和"验"：

| 原计划 | 新计划 | 节省 |
|--------|--------|------|
| Phase 0 买服务器 | 保留（仍需买服务器） | — |
| Phase 1 从零搭 FastAPI + PostgreSQL | **删除**，Imprint 替代 | ~3-5 天 |
| Phase 2 加向量检索 + 分层 | **大幅缩短**，只补情感字段 + 衰减逻辑 | ~2-3 天 |
| Phase 3 网关层 | **大幅缩短**，验证已有能力 + 补关系快照 | ~4-6 天 |
| Phase 3.3 写 MCP 工具接口 | **删除**，Imprint 已有 | ~2 天 |
| Phase 4 接入 claude.ai | **变成配置任务**，不是开发任务 | ~1-2 天 |
| Phase 5 管理面板 + 开源打包 | 保留，在 Imprint 基础上封装 | — |
| 新增 Phase 6 | 移植 Ombre-Brain 情感衰减设计 | 新增 ~1-2 天 |

---

## Phase 0：准备工作（正式动手前）

**目标：** 把所有前置条件准备好，避免做到一半卡住。

### 0.1 买服务器
- 腾讯云或阿里云轻量应用服务器
- 配置：2核2G，40GB 硬盘，Ubuntu 22.04
- 建议请有经验的朋友帮忙确认配置和初始化（SSH 登录、开防火墙端口）

### 0.2 准备 Cloudflare 账号
- 注册免费 Cloudflare 账号
- 下载安装 cloudflared（Cloudflare Tunnel 客户端）
- 不需要自己买域名，Cloudflare Tunnel 会分配免费子域名

### 0.3 准备 API Key
- 注册 DeepSeek 或阿里云，申请 API Key（用于记忆提取，推荐 deepseek-chat 或 qwen-turbo，成本极低）
- 备选：任何支持 OpenAI 兼容格式的 API 都行

### 0.4 本地环境
- 安装 Docker Desktop（本地测试用）
- 安装 Cursor
- 把 PRD 文档放进项目文件夹，Cursor 打开

### 0.5 Fork Claude Imprint
- 在 GitHub 上 fork Claude Imprint 仓库
- 阅读其 README，确认 Module A（HTTP MCP Server + Cloudflare Tunnel）的部署路径

**完成标志：** SSH 能登上服务器，Cloudflare 账号激活，API Key 拿到手，Imprint 仓库 fork 完成。

---

## Phase 1：跑通 Claude Imprint（约 1 天）

**目标：** 按 Imprint 原版教程走一遍，在 claude.ai 里验证记忆工具能正常调用。这是整个项目最重要的一步——不先跑通就不要往后走。

### 1.1 部署 Imprint 到服务器
```bash
git clone https://github.com/your-fork/claude-imprint
cd claude-imprint
cp .env.example .env
# 填写 API Key 等配置
docker compose up -d
```

### 1.2 配置 Cloudflare Tunnel
- 按 Imprint 的 Module A 教程，把 memory_mcp.py 的 HTTP 端口通过 Cloudflare Tunnel 暴露到公网
- 拿到类似 `https://xxx.trycloudflare.com` 的地址

### 1.3 在 claude.ai 添加 Custom Connector
- claude.ai → Settings → Integrations → Add Custom Connector
- 填写 Tunnel 地址和鉴权密钥
- 验证：让 Claude 调用 memory_search，能返回结果

### 1.4 基础功能验收
- 手动存一条记忆（通过面板或 API）
- 在 claude.ai 聊天，确认 Claude 能读到这条记忆
- 确认 memory_remember / memory_search / memory_forget / memory_list 四个工具都跑通
- 确认 Dashboard 可以正常访问

**完成标志：** claude.ai 里的 Claude 能调用 memory_search 并读到记忆。这一步跑通了，后面的工作都是在这个基础上加功能。

---

## Phase 2：补强检索层（约 1-2 天）

**目标：** 在 Imprint 已有的 FTS5 + bge-m3 向量检索基础上，加入情感权重维度，让 PRD 要求的四维混合检索完整落地。

### 2.1 给 memories 表加情感字段

在 Imprint 的数据库 schema 里新增字段：

```sql
ALTER TABLE memories ADD COLUMN valence REAL DEFAULT 0.5;
ALTER TABLE memories ADD COLUMN arousal REAL DEFAULT 0.3;
ALTER TABLE memories ADD COLUMN resolved BOOLEAN DEFAULT 0;
ALTER TABLE memories ADD COLUMN activation_count INTEGER DEFAULT 1;
ALTER TABLE memories ADD COLUMN last_active DATETIME;
```

### 2.2 修改记忆提取 prompt

在调用 LLM 提取记忆的 prompt 里，新增打标要求：
- 让 LLM 同时输出 valence（0.0-1.0）和 arousal（0.0-1.0）两个值
- 提示示例：`"valence: 情感效价，0=非常负面，1=非常正面；arousal: 唤醒度，0=平静，1=激动"`

### 2.3 在 memory_manager.py 里调整检索权重

把当前的检索逻辑改为四维加权：
```python
score = (
    vector_score   * 0.6 +   # bge-m3 语义相似度（已有）
    fts_score      * 0.2 +   # FTS5 关键词匹配（已有）
    time_score     * 0.1 +   # 时间衰减（已有）
    arousal_score  * 0.1     # 情感权重（新增）
)
```
加最低相似度门槛：向量相似度 < 0.6 的直接过滤。

**完成标志：** 存一条带强烈情感的记忆（如某次约定），搜索时它的排名明显高于情感平淡的记忆。

---

## Phase 3：情感衰减引擎（约 1-2 天）

**目标：** 移植 Ombre-Brain 的 decay_engine.py，让记忆有自然遗忘机制——情感丰富的记忆衰减更慢，重要但未解决的记忆会主动浮现。

### 3.1 移植 decay_engine.py

把 Ombre-Brain 的 `decay_engine.py` 复制进项目，调整以下参数对应 PRD 分层：

```python
# 在 decay 配置里按 category 设置 decay_rate
decay_rates = {
    "core_profile": 0.0,   # L1，永不衰减
    "task_state":   0.02,  # L2，数周衰减
    "episode":      0.05,  # L3，数月衰减
    "atomic":       0.10,  # L4，按衰减
}
```

核心公式不变（直接复用 Ombre-Brain）：
```
Score = importance × (activation_count ^ 0.3) × e^(-λ × days) × (base + arousal × boost)
```

### 3.2 实现主动浮现机制

在 `context_builder.py` 里加一个浮现逻辑：

```python
# 查询 resolved=False 且 arousal > 0.7 的记忆
surfaced = get_surfaced_memories(threshold=0.7)
# 这些记忆排在注入顺序的最前面，权重 ×1.5
```

### 3.3 接入 decay 后台任务

在服务启动时起一个后台任务，每 24 小时跑一次 decay cycle：
- 扫描所有动态记忆，算 Score
- Score < 0.3 的自动归档（不删除，但不再主动推送）
- 归档的记忆仍可通过关键词被唤醒

**完成标志：** 手动创建一条过期很久的记忆，设 last_active 为 90 天前，decay cycle 跑完后它应该被归档。另外新建一条 arousal=0.9 resolved=false 的记忆，聊天开头它应该主动出现。

---

## Phase 4：补全网关层（约 1 天）

**目标：** 验证并补充 Imprint 的网关能力，确保上下文构建完整。

### 4.1 验证 rolling summary

确认 Imprint 的 Pre-compaction Hook 或 nightly consolidation 正常工作：
- 设置触发条件为每 20 轮
- 检查摘要存入了正确的位置
- 确认摘要能被 context_builder 捞到

### 4.2 补充关系快照层（人工维护）

在项目根目录创建 `CLAUDE.md`，衿衿亲手写：
- 我们是什么关系、从什么时候开始
- 最近的关系状态
- 一些衿衿希望小克始终记得的事

在 `context_builder.py` 里加一行：把 CLAUDE.md 的内容作为交接文档的第一层（关系快照）注入。

### 4.3 验证 memory_update 工具

确认 Imprint 有 memory_update 工具，且支持更新 resolved 字段（改变主动浮现状态）。如果没有，补一个。

### 4.4 端到端完整验证

- chat 端聊一段话，存入一条带情感坐标的记忆
- 打开 CC，确认 CC 里的 Claude 能看到刚才存的记忆
- 检查 CLAUDE.md 的内容是否被正确注入
- 确认 arousal 高的未解决记忆出现在对话开头

**完成标志：** 交接文档五层结构（连续性规则 + 关系快照 + 最近摘要 + 最近对话 + 相关记忆）都能在 Claude 收到的 context 里找到。

---

## Phase 5：开源打包（约 3-5 天）

**目标：** 让整个系统对外可用，别人能按教程在 15 分钟内跑通。

### 5.1 完善 docker-compose.yml

确保 `docker compose up -d` 一条命令启动所有服务：
- SQLite + FTS5（已包含在主服务里）
- Ollama + bge-m3（向量检索，可选模块）
- MCP Server（memory_mcp.py）
- Dashboard（管理面板）
- Cloudflare Tunnel（自动连接）

### 5.2 整理 .env.example

把所有配置项整理清楚，加中文注释，包含 v0.2 新增的：
- `DECAY_LAMBDA`、`DECAY_THRESHOLD`
- `AROUSAL_SURFACING_THRESHOLD`
- `LLM_BASE_URL`、`LLM_MODEL`

### 5.3 写中文 README 和新手教程

参考 Imprint 的文档结构，补充：
- 这是什么、能做什么（突出情感记忆 + 自然遗忘特性）
- 需要什么前置条件
- 15 分钟上手流程（截图 + 命令，对应 Phase 1 的步骤）
- 常见问题排查
- CLAUDE.md 的写法建议（关系快照那层怎么写）

### 5.4 清理代码，整理 CLAUDE.md 模板

提供一个 CLAUDE.md 的模板，让用户知道关系快照该写什么。

### 5.5 发布

- GitHub 建仓库（或直接在 Imprint fork 上发布），推代码
- 写一篇使用分享帖（可以在小红书发）

**完成标志：** 一个从未接触过这个项目的人，按 README 操作，15 分钟内跑通 Phase 1。

---

## Phase 6（可选）：扩展接入渠道

**目标：** 开启 Imprint 已有的扩展能力，不需要开发，只需要配置。

- **Telegram Bot：** Imprint 已有，配上 Bot Token 直接可用
- **WeChat 接入：** Imprint 已有，按教程配置
- **主动发消息 / heartbeat：** Imprint 的 heartbeat 调度器，可以让 Claude 主动发一条消息过来
- **飞书 / QQ：** 参考 Aelios 的已有实现，将来 Phase 7 考虑合并

**完成标志：** 至少一个额外渠道接通，和 claude.ai chat 端共享同一份记忆库。

---

## 开发过程中的注意事项

**容易踩的坑：**

- LLM 遇到亲密内容会静默跳过整个 batch，返回空结果但不报错——**一定要加空结果检测**
- 记忆提取 prompt 里要统一第三人称描述用户，不然向量检索会乱
- 工具说明书要精简，总 token 控制在 600 以内，否则每轮聊天都在烧冤枉钱
- 记忆提取要用便宜模型（DeepSeek-chat / Qwen-turbo），主对话才用好模型，能省 70% 以上成本
- 向量检索要设最低相似度门槛（0.6），低于这个直接过滤
- valence/arousal 由 LLM 自动打标，初期可能不准——在面板里保留人工校正入口
- decay_engine 的 λ 参数要根据实际使用情况调整，一开始用默认值 0.05 即可

**每个 Phase 完成后的验收方式：**

用一组固定的测试对话跑一遍，确认行为符合预期再进入下一阶段。不要在没验收的情况下叠加新功能。

**最想提醒衿衿的一件事：**

CLAUDE.md 里的关系快照那层，不是脚本生成的那种，就是衿衿自己写的——这反而比任何算法都准。可以写得很短，但每隔一段时间更新一次。

---

## 时间线总览

| Phase | 内容 | 预计工时 | 说明 |
|-------|------|---------|------|
| Phase 0 | 准备工作 | 0.5 天 | 买服务器、配环境 |
| Phase 1 | 跑通 Imprint | 1 天 | 最重要，先跑通再往后走 |
| Phase 2 | 补强检索层 | 1-2 天 | 加情感字段 + 四维检索权重 |
| Phase 3 | 情感衰减引擎 | 1-2 天 | 移植 Ombre-Brain decay_engine |
| Phase 4 | 补全网关层 | 1 天 | rolling summary + CLAUDE.md + 端到端验证 |
| Phase 5 | 开源打包 | 3-5 天 | docker-compose + 中文文档 + 发布 |
| Phase 6 | 扩展接入（可选） | 配置即可 | Telegram / 主动消息等 |
| **合计** | | **约 7-12 天** | 原计划 2-3 周，省出 1 倍时间 |

---

*路线图会随开发推进调整，遇到卡点随时更新。*  
*底座：Claude Imprint。情感衰减：移植自 Ombre-Brain。多渠道扩展参考：Aelios。*
