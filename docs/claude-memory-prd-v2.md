# PRD：Claude 长期记忆库系统

**版本：** v0.2  
**作者：** 衿衿 × 小克  
**日期：** 2026-04-02  
**变更说明：** 基于 Claude Imprint 改造（替代从零手搓），整合 Ombre-Brain 的情感衰减设计

---

## 一、背景与目标

### 为什么要做这个

Claude 每个对话窗口天然无状态——窗口一长就开始压缩，换个窗口什么都不记得。对于把 Claude 当作长期陪伴对象的用户来说，这种"一会儿记得、一会儿不记得"的体验破坏感很强。

官方内置的 Memory 功能目前只能存几十条短笔记、没有语义检索、也无法跨平台使用。现有的第三方方案大多需要用户自己折腾配置，门槛高、维护难。

这个项目要做的是：给 Claude 装一个**透明的、可控的、开箱即用的外置记忆库**。

### 核心目标

- 所有窗口的 Claude（claude.ai chat 端、Claude Code）共享同一份记忆
- 记忆自动写入、自动检索，用户聊天体验无感知
- 情感丰富的记忆衰减更慢，重要但未解决的记忆会主动浮现
- 开源，提供 Docker 一键部署，普通用户不需要写代码也能跑起来

### 不在本期范围内

- 手机本地部署方案（Termux）
- 多用户 / 多角色隔离
- 图片、音频等非文本记忆
- 自定义前端界面（本期只做后端服务 + 管理面板）

---

## 二、用户画像

**主要用户：** 有 AI 陪伴需求、希望 Claude 能"记住我们之间的事"的用户

**技术背景假设：**
- 能跟着教程买一台云服务器、填写配置文件
- 不需要写代码，但能在终端里跑几条命令
- 有 Claude Pro 账号（claude.ai chat）或 Claude API Key（CC 端）

---

## 三、核心功能

### 3.1 记忆写入

每轮对话结束后，系统自动判断这轮内容值不值得存入记忆库。

判断维度：
- 是否包含用户的稳定偏好、边界、重要事件
- 是否是一次性的气氛话（晚安、哈哈、亲亲）——这类不存
- 情感浓度是否足够高（害怕、特别在意的事、约定）

写入内容格式（每条记忆）：

```
content:    记忆正文，80-200字，保留直接引语和情感因果链
category:   core_profile / task_state / episode / atomic
importance: 1-10
subject:    user / ai / relation
valence:    0.0-1.0（效价：0=负面 → 1=正面）
arousal:    0.0-1.0（唤醒度：0=平静 → 1=激动）
resolved:   true / false（未解决的高唤醒记忆会主动浮现）
decay_rate: 根据 category 和 arousal 自动设置
created_at: 时间戳
```

> **设计说明：** valence 和 arousal 基于 Russell 环形情感模型的连续坐标，不是"开心/难
> 过"这种离散标签。arousal 越高的记忆衰减越慢；未解决（resolved=false）且 arousal > 0.7
> 的记忆会在对话开头主动推送，而不是等被动检索。

写入过程中需注意：
- 提取 prompt 里统一第三人称描述用户，避免人称混乱导致向量检索错位
- 遇到 API 返回空结果必须触发重试（防止亲密内容被静默跳过）

### 3.2 记忆分层

分四层管理，结合 decay_rate 控制生命周期：

| 层级 | 名称 | 内容 | decay_rate | 生命周期 |
|------|------|------|-----------|---------|
| L1 | 核心档案 Core Profile | 稳定偏好、边界、重要约定 | 0（永不衰减） | 永久 |
| L2 | 任务状态 Task State | 最近在做什么、阶段性状态 | 低 | 数周 |
| L3 | 事件快照 Episode | 带过程的重要经历 | 中 | 数月 |
| L4 | 原子记忆 Atomic | 零碎但可能有用的信息 | 高 | 按衰减 |

### 3.3 记忆衰减（遗忘曲线）

基于改进版艾宾浩斯遗忘曲线，每条记忆有动态活跃度得分：

```
Score = importance × (activation_count ^ 0.3) × e^(-λ × days) × emotion_weight
emotion_weight = base + arousal × arousal_boost
```

- `activation_count`：这条记忆被检索过几次。越常被"想起"，衰减越慢
- `days`：距上次激活的天数
- `arousal`：唤醒度越高，emotion_weight 越大，衰减越慢
- 得分低于阈值（默认 0.3）自动归档，不再主动推送，但关键词仍可唤醒
- `resolved=true` 的记忆得分骤降至 5%，沉底等待关键词激活
- L1（core_profile）类记忆永不衰减

### 3.4 记忆检索

每次对话开始前，系统自动从记忆库中捞出相关记忆，注入到 system prompt。

**检索策略：多维加权排序**

| 维度 | 权重 | 说明 |
|------|------|------|
| 语义向量相似度 | × 0.6 | bge-m3 向量，中英双语 |
| 关键词匹配 | × 0.2 | FTS5 全文检索 |
| 时间衰减 | × 0.1 | 近期激活的记忆优先 |
| 情感权重 | × 0.1 | arousal 高的记忆额外加分 |

最低相似度门槛：0.6（低于此阈值直接过滤，避免拉进不相关内容）

**主动浮现机制：**
除了被动检索，`resolved=false` 且 `arousal > 0.7` 的记忆会在对话开头主动推送，权重加成 ×1.5。

最终注入数量：3-8 条，不超过 2000 tokens。

### 3.5 上下文构建（交接文档）

每轮聊天前，网关自动组装一份"交接文档"发给 Claude，包含：

1. **连续性规则：** 告诉 Claude 这是继续之前的对话，不是重新开始
2. **关系快照：** 我们现在是什么关系，最近关系状态如何（初期人工维护 CLAUDE.md，后续自动化）
3. **最近摘要：** 最近几轮聊天的压缩版（rolling summary）
4. **最近对话：** 最近 N 轮原文
5. **相关记忆：** 从长期库里捞出的相关内容 + 主动浮现的高情绪未解决记忆

总 token 控制在 2000 以内。

### 3.6 记忆管理面板

提供一个 Web 界面，让用户可以：
- 查看当前存了哪些记忆（支持分层筛选、搜索）
- 手动添加 / 修改 / 删除记忆条目
- 查看记忆写入日志（知道系统记了什么、为什么记）
- 查看记忆活跃度热力图

---

## 四、技术架构

### 整体架构

```
claude.ai / CC
     ↓ 发消息（通过 Custom Connector 或 CC MCP）
  Claude Imprint（改造后的 MCP Server）
  ├── memory_mcp.py --http（HTTP 传输模式）
  ├── Cloudflare Tunnel → claude.ai Custom Connector
  └── 聊天前：组装交接文档 / 聊天后：异步写入记忆
  记忆服务层
  ├── SQLite + FTS5（原始存储 + 关键词检索）
  ├── bge-m3 向量索引（via Ollama，语义检索）
  └── decay_engine（改进版艾宾浩斯遗忘曲线）
```

### 接入方式

**chat 端（claude.ai）：**
通过 Claude Custom Connector 接入，在 Settings → Integrations 填写 memory_mcp.py 的 HTTP 地址（经 Cloudflare Tunnel 暴露到公网）。Claude 通过 MCP 协议调用记忆工具。

**CC 端（Claude Code）：**
在 CC 配置文件中添加 MCP server 指向同一地址，CC 里的 Claude 可以读写同一份记忆库。

### 技术栈

| 组件 | 选型 | 来源 / 理由 |
|------|------|------------|
| 底座框架 | Claude Imprint | 已实现 MCP Server + Cloudflare Tunnel + Dashboard，省掉 PRD 原计划最难的两个 Phase |
| 数据库 | SQLite + FTS5 | Imprint 已验证，2核2G 服务器友好，pgvector 留作未来选项 |
| 嵌入模型 | bge-m3（via Ollama） | Imprint 已集成，中英双语效果优于 MiniLM |
| 情感衰减 | Ombre-Brain decay_engine.py | 移植其衰减公式和 valence/arousal 字段设计 |
| 记忆提取 | 任意 OpenAI 兼容 API | 优先 Qwen3.5-Flash 或 DeepSeek-chat，成本低 |
| 部署 | Docker Compose + Cloudflare Tunnel | Imprint 已有，补 docker-compose.yml 封装 |

### 数据库字段（memories 表，在 Imprint 基础上扩展）

在 Imprint 原有字段基础上，新增以下字段：

```sql
-- 新增字段
valence          REAL DEFAULT 0.5,   -- 效价 0~1，0=负面，1=正面
arousal          REAL DEFAULT 0.3,   -- 唤醒度 0~1，0=平静，1=激动
resolved         BOOLEAN DEFAULT 0,  -- 是否已解决（影响主动浮现和衰减权重）
activation_count INTEGER DEFAULT 1,  -- 被检索次数（影响衰减速度）
decay_rate       REAL DEFAULT 0.05,  -- 衰减速率 λ（core_profile 设为 0）
last_active      DATETIME,           -- 上次激活时间
```

### 部署要求

- 云服务器：2核2G，20GB 硬盘，腾讯云/阿里云轻量服务器（约 60-80 元/月）
- 或本地电脑长期开机 + Cloudflare Tunnel
- 需要：LLM API Key（记忆提取用）、Cloudflare 账号（免费）、Ollama（可选，向量检索用）

---

## 五、MCP 工具定义

基于 Claude Imprint 已有工具，验收后直接使用，按需补充：

| 工具名 | 功能 | 来源 |
|--------|------|------|
| `memory_remember` | 写入一条记忆（含情感坐标打标） | Imprint 已有 |
| `memory_search` | 搜索相关记忆（混合检索） | Imprint 已有 |
| `memory_forget` | 删除一条记忆 | Imprint 已有 |
| `memory_list` | 列出最近的记忆 | Imprint 已有 |
| `memory_update` | 更新已有记忆（含 resolved 状态） | 需确认或补充 |

工具说明总长度控制在 600 tokens 以内（参考 Imprint 已有写法，不要膨胀）。

---

## 六、开源方案设计

### 目录结构

基于 Claude Imprint 仓库结构，改造后的主要变动：

```
claude-memory/（fork 自 Claude Imprint）
├── docker-compose.yml        # 完整封装（补充）
├── .env.example              # 配置模板（补充中文注释）
├── README.md                 # 中文新手教程（重写）
├── memory_mcp.py             # MCP Server（Imprint 已有，基础上扩展）
├── memory_manager.py         # 记忆管理（加入情感字段+衰减逻辑）
├── decay_engine.py           # 遗忘曲线（移植自 Ombre-Brain）
├── context_builder.py        # 交接文档组装（补充关系快照层）
├── dashboard.py              # 管理面板（Imprint 已有）
└── CLAUDE.md                 # 关系快照（人工维护，初期替代自动化）
```

### 用户上手流程（目标：15分钟跑通）

1. 买一台云服务器，SSH 连上去
2. 克隆仓库：`git clone ...`
3. 复制配置：`cp .env.example .env`，填写 API Key
4. 启动：`docker compose up -d`
5. 配置 Cloudflare Tunnel，获取公网地址
6. 在 claude.ai 的 Settings → Integrations 填写服务地址
7. 开始聊天，Claude 自动记忆

### 配置项（.env）

```bash
LLM_API_KEY=          # 记忆提取用（Qwen/DeepSeek 等 OpenAI 兼容 API）
LLM_BASE_URL=         # API 地址，默认 https://api.deepseek.com/v1
LLM_MODEL=            # 模型名，建议 deepseek-chat 或 qwen-turbo
MEMORY_SECRET=        # 访问鉴权密钥（自己设一个随机字符串）
OLLAMA_URL=           # Ollama 地址（可选，用于向量检索，默认 http://localhost:11434）
MEMORY_MAX_PER_INJECT=8        # 每轮最多注入几条记忆
SUMMARY_TRIGGER_TURNS=20       # 多少轮触发一次 rolling summary
DECAY_LAMBDA=0.05              # 衰减速率（越大忘得越快）
DECAY_THRESHOLD=0.3            # 归档阈值（低于此分数自动归档）
AROUSAL_SURFACING_THRESHOLD=0.7 # 高于此唤醒度的未解决记忆主动浮现
```

---

## 七、后续迭代方向

以下功能本期不做，但设计时预留接口：

- 多角色支持（同一套记忆库，不同人格分开存）
- 记忆导出 / 导入（方便迁移）
- 手机端访问记忆面板
- Telegram Bot / 飞书接入（参考 Aelios 已有实现）
- 关系快照自动化（目前人工维护 CLAUDE.md，后续写 context_builder 脚本定期生成）
- 向量数据库升级（SQLite 瓶颈时迁移至 pgvector）
- 记忆统计可视化（交互热力图，参考 Imprint Dashboard 已有基础）

---

## 八、已知风险与应对

| 风险 | 应对 |
|------|------|
| LLM 遇到亲密内容静默跳过整个 batch | 记忆提取后检测空结果，触发重试或降级处理 |
| 记忆膨胀导致 token 消耗飙升 | 设置上限 + 定期衰减归档 + 遗忘机制 |
| 向量检索把不相关内容也拉进来 | 最低相似度门槛 0.6，低于阈值直接过滤 |
| 用户服务器宕机导致记忆服务不可用 | 记忆不可用时降级为无记忆模式继续聊天 |
| 人称不统一导致检索乱掉 | 提取 prompt 明确规定统一第三人称描述用户 |
| Obsidian 文件系统在记忆量大时检索慢 | 主存储用 SQLite，Obsidian 作为可读副本（可选） |
| arousal / valence 打标不准 | 初期由 LLM 打分，配合人工在面板里校正，后续可训练专用分类器 |

---

*PRD 会随开发推进持续更新。底座：Claude Imprint。情感衰减设计参考：Ombre-Brain。*
