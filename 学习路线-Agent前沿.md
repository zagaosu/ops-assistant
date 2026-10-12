# Agent 前沿课程地图

**设计原则**：每一课都用**你自己写的代码**当教材。
你缺的不是"没做过"，是"做过但不知道行业里管它叫什么"。

**每课固定四段：**

| 段 | 内容 |
|---|---|
| ① **你已有的** | 指到你项目里的具体文件和行数 |
| ② **术语** | 行业里管这个东西叫什么（面试要用的词） |
| ③ **前沿** | 2026 年这块在往哪走 |
| ④ **面试句** | 一句话，能直接说出口的那种 |

---

## 课程列表

### 第一课 · Agent 循环与设计模式
- **已有**：`agent.py` 的四步循环、四种终止条件、trace 记录
- **术语**：ReAct、agent loop、harness、termination conditions
- **前沿**：Plan-and-Execute、Reflexion、Orchestrator-Worker；**什么时候不该用 Agent**
- **目标**：能画出循环图并说清"为什么要限步和超时"

### 第二课 · Context Engineering（上下文工程）
- **已有**：`top_k=3`、最近 6 条历史、`MIN_SCORE=0.55` 拒答、工具结果回填
- **术语**：context window、context budget、retrieval、compaction
- **前沿**：context rot（上下文腐化）、子 agent 隔离上下文、**这个领域已取代 prompt engineering 成为核心议题**
- **目标**：把你在做的三件事装进这套术语

### 第三课 · 工具设计与 MCP 协议
- **已有**：`TOOL_REGISTRY` 白名单、Pydantic 三层校验、错误即数据、`not_closed` 别名
- **术语**：tool schema、function calling、constrained decoding、tool error contract
- **前沿**：**MCP（Model Context Protocol）**、工具数量与选择准确率的权衡、并行工具调用
- **目标**：能讲清"工具描述怎么设计"和"MCP 解决了什么问题"

### 第四课 · Agent 评测（轨迹评测）⭐ 你最接近前沿的一块
- **已有**：24 题冻结集、mock/real 分离、人工判分、`steps`/`tools_used`/`error_codes` 断言
- **术语**：trajectory evaluation、LLM-as-judge、rubrics、pass@k
- **前沿**：只判结果的 LLM 评委会漏掉轨迹问题；长程任务评测；评测本身的成本
- **目标**：能说出"我的评测脚本其实就是轨迹评测的雏形"

### 第五课 · Memory 架构
- **已有**：最近 6 条历史（最原始的做法）
- **术语**：short/long-term memory、working memory、summarization、episodic memory
- **前沿**：MemGPT/Letta 式的外部记忆、压缩策略、什么该记住什么该忘
- **目标**：能说出你现在的做法缺什么

### 第六课 · RAG 进阶
- **已有**：分块 + bge-m3 + 余弦 + 阈值拒答
- **术语**：hybrid retrieval（混合检索）、reranking（重排）、query rewriting、chunking strategy
- **前沿**：contextual retrieval、late chunking、GraphRAG
- **目标**：能说出"下一步该补什么、为什么"

### 第七课 · 框架与生态（工具篇）
- **已有**：一个手写的 while 循环
- **要认识的**：LangChain / LangGraph / LangSmith / OpenAI Agents SDK / Claude Agent SDK / CrewAI / Google ADK / Vercel AI SDK
- **前沿**：**反框架趋势**——"框架 vs 一个简单的 while 循环"被当成严肃对比；新词 **harness engineering**
- **目标**：能说清 LangChain 和 LangGraph 的区别，以及"我为什么手写循环"

---

## 建议顺序与理由

**1 → 2 → 3 → 4 → 5 → 6 → 7**

- **从 1 开始**：这是所有东西的地基，也是你项目的心脏
- **4 往前排**（原本想放后面）：你的评测**已经接近前沿**，补齐理论马上能讲，性价比最高
- **7 放最后**：工具是"知道就行"，先把概念立住
- **5、6 是补短板**，可以按兴趣调换

**预计**：每课 1–1.5 小时（讲 + 你复述 + 追问）

---

## 每课结束的标志

不是"听懂了"，而是：**能不看笔记，用自己的话讲 60 秒**。

讲不出来 = 没学会 = 重来。这是唯一标准。
