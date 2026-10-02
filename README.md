# Ops Assistant（设备运维知识库与工单助手）

面向设备运维场景的 AI 助手：**能查内部 SOP 文档回答问题、能查工单、能把口头报的故障转成规范工单。**

全部模型跑在本地（Ollama），数据不出本机。

## 能做什么

| 功能 | 说明 |
|---|---|
| **知识问答** | 问"电池冒烟起火了怎么处置"，从 10 份运维 SOP 里检索相关片段，**带来源**回答；资料里没有的直接拒答，不编造 |
| **工单查询** | Agent 自主决定调用工具查工单，且**只查得到自己名下的** |
| **草稿转工单** | 口语描述的故障 → 生成草稿 → 用户确认才真正落库；**重复确认不会重复建单**（幂等） |
| **会话记忆** | 会话与历史存数据库，刷新不丢；每次提问只带最近 6 条（上下文预算） |
| **多用户隔离** | 工单、会话、草稿、私有文档都按用户隔离；访问别人的资源一律返回 404 |
| **检索缓存** | 同一问题第二次问，跳过 embedding 计算（实测 2.2 秒 → 3 毫秒） |
| **后台任务** | 文档重新入库走 RQ 队列，接口立刻返回 job_id，可查进度、失败可见、有限重试 |

## 技术栈

| 层 | 用了什么 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 18 |
| 前端 | React + TypeScript + Vite |
| 模型 | 本地 Ollama：`qwen3:8b`（对话决策）+ `bge-m3`（embedding，1024 维） |
| 缓存 / 队列 | Redis（缓存） + RQ（后台任务） |
| 测试 | pytest，**35 个用例**（接口、工具契约、Agent 循环、鉴权、草稿事务、检索权限） |

设计取舍（为什么选本地模型、为什么不用 pgvector、缓存键怎么设计）：见 [技术取舍记录.md](技术取舍记录.md)。
5 分钟演示脚本：见 [演示脚本.md](演示脚本.md)。

## 目录

```
ops-assistant/
├── backend/          FastAPI 后端（Python 3.13）
│   ├── main.py       接口定义
│   ├── agent.py      有限步 Agent 循环
│   ├── tools.py      工具注册表与契约
│   ├── rag.py        检索与生成
│   ├── cache.py      检索缓存（Redis）
│   ├── jobs.py       后台任务（RQ）
│   ├── auth.py       登录与鉴权
│   ├── models.py     数据表模型
│   ├── migrations/   Alembic 迁移
│   └── tests/        pytest 用例
├── frontend/         React + TypeScript（Vite）
├── eval/             冻结评测集与跑批脚本
├── docs/sop/         10 份运维文档（知识库源文件）
└── scripts/          服务启停脚本
```

## 环境要求

- Python：conda 环境 `spider_env`，依赖版本锁在 `backend/requirements.txt`
- Node.js 24 / npm 11
- PostgreSQL 18、Redis 7
- Ollama，需要 `qwen3:8b` 和 `bge-m3` 两个模型

## 启动（五步）

**① 数据库**：

```bat
scripts\db-start.cmd
```

**② Redis**（需要 Docker Desktop 在运行）：

```bat
scripts\redis-start.cmd
```

**③ 后端**：

```bat
cd backend
D:/anaconda/envs/spider_env/python.exe -m uvicorn main:app --reload --port 8000
```

打开 <http://localhost:8000/docs> 可以在网页上直接调接口（Swagger）。
数据库连接串在 `backend/.env`（格式见 `.env.example`，`.env` 不进仓库）。

**④ 前端**：

```bat
cd frontend
npm run dev
```

打开 <http://localhost:5173>。前端的 `/api` 请求由 Vite 代理转发到 8000 端口。

**⑤ 后台任务 worker**（可选，只在要用"重新入库"时启动）：

```bat
scripts\worker-start.cmd
```

这个窗口要一直开着。不开也能用其它功能，只是入库任务会一直排队。

**测试账号**：`user1` / `ops123`，`user2` / `ops123`

## 数据库操作速查（在 backend 目录下）

```bat
:: 改过 models.py 之后：生成迁移 + 应用迁移（两条都要跑）
python -m alembic revision --autogenerate -m "这次改了什么"
python -m alembic upgrade head

:: 写入示例数据
python -X utf8 seed.py
```

用 psql 连数据库（密码 postgres）：

```bat
D:\anaconda\envs\spider_env\Library\bin\psql.exe -h localhost -U postgres -d ops_assistant
```

## 运行测试（在 backend 目录下）

```bat
D:/anaconda/envs/spider_env/python.exe -m pytest tests/ -v
```

测试连独立的测试数据库 `ops_assistant_test`（每个用例前重建表），不碰开发数据。

## 跑评测（在 ops-assistant 目录下）

题目冻结在 `eval/cases_rag.json`（检索命中 / 该拒答）和 `eval/cases_agent.json`（工具与 Agent 循环）。

```bat
:: 检索质量（真 embedding，14 题：10 该命中 + 4 该拒答）
D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite rag

:: Agent 循环逻辑（脚本 Fake，秒出，不调用模型）
D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite agent --mode mock

:: Agent 决策质量（真模型，慢，部分题需人工判分）
D:/anaconda/envs/spider_env/python.exe -X utf8 eval/run_eval.py --suite agent --mode real
```

最近一次结果：**检索 14/14**（命中 10/10、拒答 4/4）；**Agent 循环 6/6**（假模型）；
**Agent 决策**：机械断言 4/4，人工判分 3 PASS / 1 PARTIAL。

每次运行都把逐题原始输出写进 `eval/reports/<时间>_<套件>-<模式>.json`。
**脚本 Fake（mock）和真模型（real）的数字分开统计，不合并**——假模型只能证明代码逻辑对，证明不了模型答得好。

## 常见问题

- **改了后端代码，接口行为却没变**：uvicorn 的自动 reload 偶尔失灵（日志喊了 "Reloading..." 但进程没重启）。手动重启后端。
- **端口被占用（8000 / 5173 / 6379）**：`netstat -ano | findstr :8000` 找最后一列的 PID，`taskkill /PID <PID> /F`。
- **数据库连不上**：确认 PostgreSQL 在跑（`scripts\db-start.cmd`）。
- **后台任务一直排队**：worker 没启动（`scripts\worker-start.cmd`）。
- **检索结果没更新**：文档改动后要重新入库（跑 `ingest_docs.py` + `embed_chunks.py`，或提交后台任务）。
