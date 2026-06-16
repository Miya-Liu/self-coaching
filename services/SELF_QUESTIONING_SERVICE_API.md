# Pipeline Service API 调用指南

## 概述

[`pipeline_service.py`](pipeline_service.py:1) 是一个基于 FastAPI + Uvicorn 的 HTTP 服务，将自提问智能体（Self-Questioning Agent）的三段式流水线暴露为 REST API。服务默认启动在 `0.0.0.0:8001`。

### 启动服务

```bash
# 默认启动（0.0.0.0:8001）
python pipeline_service.py

# 自定义端口和主机
python pipeline_service.py --port 8001 --host 0.0.0.0

# 开发模式（自动重载）
python pipeline_service.py --port 8001 --reload
```

---

## API 端点一览

| 方法   | 端点                              | 说明                         |
|--------|-----------------------------------|------------------------------|
| `GET`  | `/health`                         | 健康检查                     |
| `POST` | `/api/pipeline/submit`            | 异步提交流水线任务（立即返回 job_id） |
| `POST` | `/api/pipeline/run_sync`          | 同步执行流水线（阻塞直到完成）     |
| `GET`  | `/api/pipeline/status/{job_id}`   | 查询任务状态 + 日志预览         |
| `GET`  | `/api/pipeline/tasks`             | 列出所有任务（可选 `?status=running`） |
| `GET`  | `/api/pipeline/logs/{job_id}`     | 获取完整日志（可选 `?lines=100`）  |

---

## 输入：PipelineRequest

所有 `POST` 端点接收相同的 JSON 请求体，对应 Pydantic 模型 [`PipelineRequest`](pipeline_service.py:63)。

> **注意**：所有字段均为可选（有默认值），最小请求体为 `{}`。

### 全局可选选项

| 字段名          | 类型    | 默认值  | 约束          | 说明                                                                                                           |
|-----------------|---------|---------|---------------|----------------------------------------------------------------------------------------------------------------|
| `start_stage`   | `int`   | `1`     | `1 ≤ v ≤ 3`   | 流水线起始阶段。`1` = 从生成任务开始（完整流程）；`2` = 跳过 Stage 1，直接从任务探索开始；`3` = 仅执行数据库导入       |
| `dry_run`       | `bool`  | `false` | —             | 干跑模式。`true` 时仅打印各阶段将执行的命令而不实际运行，用于预览和调试；`false` 时正常执行所有阶段                     |
| `fail_fast`     | `bool`  | `true`  | —             | 快速失败策略。`true` 时任一阶段失败立即终止后续阶段；`false` 时即使某阶段失败也继续尝试执行后续阶段                     |

### Stage 1 必须选项（生成任务）

| 字段名                   | 类型    | 默认值    | 约束                    | 说明                                                                                                                   |
|--------------------------|---------|-----------|-------------------------|------------------------------------------------------------------------------------------------------------------------|
| `generate_tasks_limit`   | `int`   | `0`       | `v ≥ 0`                 | 限制 Stage 1 处理的消息数量。`0` = 不限制，处理数据库中所有符合条件的消息；`>0` 时仅处理前 N 条（用于测试或小批量运行）     |
| `train_eval_flag`        | `str`   | `"eval"`  | 枚举：`"train"` / `"eval"` | 指定 Stage 1 的数据来源。`"train"` = 从用户训练消息（user messages）生成任务；`"eval"` = 从评估消息（eval messages）生成任务 |

### Stage 2 可选选项（任务探索）

| 字段名                  | 类型            | 默认值                                     | 约束          | 说明                                                                                                                   |
|-------------------------|-----------------|--------------------------------------------|---------------|------------------------------------------------------------------------------------------------------------------------|
| `n`                     | `int \| null`   | `8`                                        | `v ≥ 1`       | 每个种子任务生成的探索分支数。值越大，探索越深入，但耗时越长。建议范围：`1–32`                                            |
| `num_explore_threads`   | `int \| null`   | `8`                                        | `v ≥ 1`       | 并行探索的线程数。值越大并发越高，但会占用更多 CPU/内存资源。建议根据机器核心数设置                                        |

### Stage 3 可选选项（数据导入）

| 字段名             | 类型     | 默认值    | 约束  | 说明                                                                                                         |
|--------------------|----------|-----------|-------|--------------------------------------------------------------------------------------------------------------|
| `dry_run_import`   | `bool`   | `false`   | —     | 导入预览模式。`true` 时仅打印将要导入的数据条目而不实际写入数据库，用于确认数据正确性；`false` 时执行真实导入（upsert 到 Supabase `query_bank` 表） |

### 额外选项

| 字段名        | 类型            | 默认值   | 约束  | 说明                                                                                                         |
|---------------|-----------------|----------|-------|--------------------------------------------------------------------------------------------------------------|
| `extra_env`   | `dict \| null`  | `null`   | —     | 额外环境变量，键值对均为字符串。用于传递 LLM API Key、数据库连接串等敏感配置，避免硬编码。例：`{"OPENAI_API_KEY": "sk-xxx"}` |

### 请求体示例

```json
{
//   "start_stage": 1,
//   "dry_run": false,
//   "fail_fast": true,
  "generate_tasks_limit": 0,
  "train_eval_flag": "eval"
//   "n": 8,
//   "num_explore_threads": 8,
//   "cpu_only": true,
//   "dry_run_import": false
}
```

---

## 输出：PipelineTaskInfo

所有端点返回统一的结构，对应 Pydantic 模型 [`PipelineTaskInfo`](pipeline_service.py:89)。

| 字段名            | 类型                     | 说明                                                                                                                   |
|-------------------|--------------------------|------------------------------------------------------------------------------------------------------------------------|
| `job_id`          | `str`                    | 任务唯一标识，16 位小写十六进制字符串（由 `uuid.uuid4().hex[:16]` 生成）。用于后续查询状态和日志时作为路径参数               |
| `status`          | `PipelineStatus`         | 任务当前状态，枚举值见下表                                                                                               |
| `created_at`      | `str`                    | 任务创建时间，ISO 8601 格式（如 `"2026-06-16T16:00:00.123456"`），表示请求被服务接收的时刻                                |
| `started_at`      | `str \| null`            | 任务开始执行时间。提交后为 `null`，后台线程启动后更新为实际时间                                                                 |
| `finished_at`     | `str \| null`            | 任务完成时间。未完成时为 `null`，成功或失败后更新为实际时间                                                                   |
| `config`          | `dict[str, any]`         | 提交时使用的完整请求配置（去除 `null` 值）。可用于核对任务参数                                                                 |
| `stage_results`   | `dict[int, bool]`        | 各阶段执行结果。键为阶段号（1/2/3），值为 `true`（成功）或 `false`（失败）。未执行的阶段也会出现在字典中                       |
| `error`           | `str \| null`            | 错误信息。成功时为 `null`；失败时包含异常类名和异常消息（如 `"Pipeline execution error: Connection refused"`）               |
| `logs_preview`    | `str \| null`            | 最近 50 行日志的文本预览（仅 `GET /api/pipeline/status/{job_id}` 端点返回）。每行带时间戳，格式为 `"[HH:MM:SS] message"` |

### `status` 枚举值（[`PipelineStatus`](pipeline_service.py:56)）

| 值           | 说明                                                                                           |
|--------------|------------------------------------------------------------------------------------------------|
| `"pending"`  | 任务已提交但尚未开始执行。此时 `started_at` 为 `null`，后台线程正在排队等待                          |
| `"running"`  | 任务正在执行中。此时 `started_at` 已有值，`finished_at` 为 `null`。可通过 `/status` 端点持续轮询      |
| `"success"`  | 流水线所有阶段执行成功。此时 `finished_at` 已有值，`stage_results` 中所有阶段均为 `true`              |
| `"failed"`   | 流水线执行失败（任一阶段出错或异常）。此时 `finished_at` 已有值，`error` 字段包含失败原因               |

### `stage_results` 结构说明

```json
{
  "stage_results": {
    "1": true,   // Stage 1（生成任务）执行成功
    "2": true,   // Stage 2（任务探索）执行成功
    "3": false   // Stage 3（数据导入）执行失败
  }
}
```

- 键为阶段号（`1`、`2`、`3`），值为布尔型
- 如果 `start_stage=2`，则 Stage 1 的结果为 `false`（未执行），Stage 2 和 Stage 3 反映实际执行情况
- 如果 `fail_fast=true` 且 Stage 2 失败，则 Stage 3 的结果为 `false`（被跳过）

### 响应体示例

```json
{
  "job_id": "a1b2c3d4e5f67890",
  "status": "success",
  "created_at": "2026-06-16T16:00:00.000000",
  "started_at": "2026-06-16T16:00:01.000000",
  "finished_at": "2026-06-16T16:05:30.000000",
  "config": {
    "start_stage": 1,
    "n": 8,
    "env_type": "openworld"
  },
  "stage_results": {
    "1": true,
    "2": true,
    "3": true
  },
  "error": null
}
```

---

## Python 调用示例

### 1. 使用 `requests` 库

```python
import requests
import time

BASE_URL = "http://10.110.158.146:8001"

# ---------- 健康检查 ----------
resp = requests.get(f"{BASE_URL}/health")
print(resp.json())
# {"status": "ok", "timestamp": "...", "version": "1.0.0"}


# ---------- 异步提交任务 ----------
payload = {
    "generate_tasks_limit": 5,
    "train_eval_flag": "eval"
}

resp = requests.post(f"{BASE_URL}/api/pipeline/submit", json=payload)
job_info = resp.json()
job_id = job_info["job_id"]
print(f"Submitted job: {job_id}")

# ---------- 轮询任务状态 ----------
while True:
    resp = requests.get(f"{BASE_URL}/api/pipeline/status/{job_id}")
    status = resp.json()
    print(f"Status: {status['status']}")

    if status["status"] in ("success", "failed"):
        break
    if status.get("error"):
        print(f"Error: {status['error']}")
        break

    time.sleep(5)

# ---------- 获取完整日志 ----------
resp = requests.get(f"{BASE_URL}/api/pipeline/logs/{job_id}", params={"lines": 200})
logs = resp.json()
for line in logs["logs"]:
    print(line)


# ---------- 列出所有任务 ----------
resp = requests.get(f"{BASE_URL}/api/pipeline/tasks", params={"limit": 10})
tasks = resp.json()
print(f"Total tasks: {tasks['total']}")
for t in tasks["tasks"]:
    print(f"  {t['job_id']}: {t['status']}")


# ---------- 按状态筛选 ----------
resp = requests.get(f"{BASE_URL}/api/pipeline/tasks", params={"status": "running"})
print(resp.json())
```

### 2. 使用 `httpx`（异步调用）

```python
import httpx
import asyncio

BASE_URL = "http://10.110.158.146:8001"

async def submit_and_wait(payload: dict, poll_interval: float = 5.0):
    async with httpx.AsyncClient() as client:
        # 提交任务
        resp = await client.post(f"{BASE_URL}/api/pipeline/submit", json=payload)
        job_id = resp.json()["job_id"]
        print(f"Submitted job: {job_id}")

        # 轮询状态
        while True:
            resp = await client.get(f"{BASE_URL}/api/pipeline/status/{job_id}")
            status = resp.json()["status"]
            print(f"  Status: {status}")

            if status in ("success", "failed"):
                return resp.json()

            await asyncio.sleep(poll_interval)

# 使用
result = asyncio.run(submit_and_wait({
    "start_stage": 2,
    "n": 4,
    "num_explore_threads": 4,
}))
print(f"Final status: {result['status']}")
```

### 3. 同步执行（阻塞模式）

适用于需要立即获得结果的场景，但会占用服务器工作线程。

```python
import requests

BASE_URL = "http://10.110.158.146:8001"

payload = {
    "generate_tasks_limit": 5,
    "train_eval_flag": "eval"
}

# 注意：此调用会阻塞直到流水线完成
resp = requests.post(f"{BASE_URL}/api/pipeline/run_sync", json=payload, timeout=600)
result = resp.json()

print(f"Job: {result['job_id']}")
print(f"Status: {result['status']}")
print(f"Stage results: {result['stage_results']}")
if result.get("error"):
    print(f"Error: {result['error']}")
```

### 4. 使用 `curl` 命令行

#### 同步执行（阻塞直到完成）

```bash
curl -X POST http://10.110.158.146:8001/api/pipeline/run_sync \
  -H "Content-Type: application/json" \
  -d '{ "train_eval_flag": "train", "generate_tasks_limit": 1 }'
```

该命令使用默认参数执行完整流水线（Stage 1 → 2 → 3），仅覆盖 `train_eval_flag` 为 `"train"`（从训练消息生成任务）和 `generate_tasks_limit` 为 `1`（仅处理 1 条消息）。请求会阻塞直到流水线执行完毕，然后返回完整结果。

#### 异步提交（立即返回 job_id）

```bash
curl -X POST http://10.110.158.146:8001/api/pipeline/submit \
  -H "Content-Type: application/json" \
  -d '{
    "train_eval_flag": "eval",
    "generate_tasks_limit": 0
  }'
```

#### 查询任务状态

```bash
curl http://10.110.158.146:8001/api/pipeline/status/<job_id>
```

#### 获取任务日志

```bash
curl "http://10.110.158.146:8001/api/pipeline/logs/<job_id>?lines=200"
```

---

## 流水线三阶段说明

| 阶段 | 功能 | 执行脚本 |
|------|------|----------|
| Stage 1 | 从数据库消息生成任务 | [`frontdata/generate_tasks_from_messages.py`](frontdata/generate_tasks_from_messages.py:1) |
| Stage 2 | 任务管理器探索（调用环境服务） | `agentevolver.module.task_manager` |
| Stage 3 | 将合成 JSONL 数据导入数据库 | [`backend/import_synthetic_jsonl.py`](backend/import_synthetic_jsonl.py:1) |

通过 `start_stage` 参数可以指定从哪个阶段开始执行，方便跳过已完成的阶段。

---

## 错误处理

| HTTP 状态码 | 说明 |
|------------|------|
| `200` | 请求成功 |
| `400` | 请求参数无效（如 `status` 过滤值不合法） |
| `404` | 指定的 `job_id` 不存在 |
| `422` | 请求体校验失败（字段类型/范围不正确） |

当任务执行失败时，`status` 字段为 `"failed"`，`error` 字段包含异常信息。可通过 `/api/pipeline/logs/{job_id}` 获取详细日志。

---

## 交互式 API 文档

服务启动后，浏览器打开以下地址可在线调试：

- **Swagger UI**: `http://10.110.158.146:8001/docs`
- **ReDoc**: `http://10.110.158.146:8001/redoc`
