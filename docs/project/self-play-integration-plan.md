> **Implementation tracker (sprints, tasks, status):** [self-play-pipeline-implementation.md](self-play-pipeline-implementation.md)

## 分析：Pipeline Service API 与当前仓库的对应关系

### 现有架构概览

你的仓库实现了一个"自我进化"框架，核心是：

| 层 | 组件 | 当前状态 |
|----|------|----------|
| **SelfCoachingClient** | 统一接口 (`client.py`) | `learn()`, `self_play()`, `evaluate()`, `train()`, `run_all()` |
| **Mock self-play** | `mock-services/mock_self_play.py` | 从失败轨迹生成对抗性评测用例，注册为 AgentEvals suite |
| **Coach scheduler** | `modes/coach/scheduler.py` | 定时 tick → `handle_post_body` → 路由(learn/play/tune/full_tick) |
| **Backend 切换** | env-driven in `LoopConfig` | `ORCHESTRATOR_EVAL_BACKEND`, `ORCHESTRATOR_TRAIN_BACKEND`，但 **self-play 没有独立的 backend flag** |

### Pipeline Service API 与 Mock Self-Play 的语义差异

| 维度 | Mock Self-Play (`/self-play/generate`) | Real Pipeline Service (`/api/pipeline/submit`) |
|------|---------------------------------------|-----------------------------------------------|
| **输入** | `{capability, n, coaching_root}` | `{start_stage, train_eval_flag, generate_tasks_limit, n, num_explore_threads, ...}` |
| **执行** | 同步、in-process 生成用例 | 异步 3 阶段：DB消息→任务 → Agent探索 → JSONL导入 |
| **输出** | `{status, count, case_ids, suite_id, curation}` | `{job_id, status, stage_results, error, logs_preview}` |
| **数据流** | 本地 JSONL → curation → suite 注册 | Supabase messages → LLM生成tasks → 环境探索 → Supabase query_bank |
| **状态模型** | 无状态（同步返回） | 有状态（pending → running → success/failed） |

关键对应关系：
- **Stage 1** (generate_tasks_from_messages) ≈ mock 的"从 learning_events 中选种子"
- **Stage 2** (task_manager explore) ≈ mock 的 `_build_case_from_failure` + 多变体生成
- **Stage 3** (import_synthetic_jsonl) ≈ mock 的 curation + `append_jsonl` 到 staging

---

## 可用性测试方案

### Phase 1: 连通性验证（无破坏性）

```python
# test_pipeline_service_availability.py
"""
对真实 Pipeline Service (10.110.158.146:8001) 执行非破坏性探测。
不提交任何真实任务，仅验证：网络可达、API 合规、dry_run 工作。
"""
import pytest
import requests

BASE_URL = "http://10.110.158.146:8001"
TIMEOUT = 10


class TestPipelineServiceHealth:
    """P0: 网络可达 + 服务存活"""

    def test_health_endpoint(self):
        resp = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_openapi_docs_available(self):
        resp = requests.get(f"{BASE_URL}/docs", timeout=TIMEOUT)
        assert resp.status_code == 200


class TestPipelineServiceContract:
    """P1: API 合规性 — 验证请求/响应 schema 匹配文档"""

    def test_submit_dry_run(self):
        """dry_run=true 不执行实际工作，验证请求被接受"""
        payload = {"dry_run": True, "generate_tasks_limit": 1, "train_eval_flag": "eval"}
        resp = requests.post(f"{BASE_URL}/api/pipeline/submit", json=payload, timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] in ("pending", "running", "success", "failed")
        return data["job_id"]

    def test_status_poll(self):
        """提交 dry_run 后轮询状态"""
        payload = {"dry_run": True, "generate_tasks_limit": 1, "train_eval_flag": "eval"}
        resp = requests.post(f"{BASE_URL}/api/pipeline/submit", json=payload, timeout=TIMEOUT)
        job_id = resp.json()["job_id"]

        resp = requests.get(f"{BASE_URL}/api/pipeline/status/{job_id}", timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "stage_results" in data

    def test_tasks_list(self):
        resp = requests.get(f"{BASE_URL}/api/pipeline/tasks", timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "total" in data

    def test_invalid_job_returns_404(self):
        resp = requests.get(f"{BASE_URL}/api/pipeline/status/nonexistent_id", timeout=TIMEOUT)
        assert resp.status_code == 404

    def test_validation_error_returns_422(self):
        payload = {"start_stage": 99}  # out of range
        resp = requests.post(f"{BASE_URL}/api/pipeline/submit", json=payload, timeout=TIMEOUT)
        assert resp.status_code == 422


class TestPipelineServiceSmoke:
    """P2: 真实执行烟雾测试 — 仅在有信心时启用"""

    @pytest.mark.skipif(True, reason="enable manually after P0/P1 pass")
    def test_sync_single_message(self):
        """执行 1 条消息的完整流水线，验证端到端可工作"""
        payload = {
            "generate_tasks_limit": 1,
            "train_eval_flag": "eval",
            "n": 2,
            "num_explore_threads": 2,
            "fail_fast": True,
        }
        resp = requests.post(f"{BASE_URL}/api/pipeline/run_sync", json=payload, timeout=600)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("success", "failed")
        if data["status"] == "success":
            assert data["stage_results"]["1"] is True
```

---

## 迁移方案：在 Pipeline Service 之上构建 self-play skill

### 架构图

```
Coach Scheduler tick
       │
       ▼
SelfCoachingClient.self_play()
       │
       ├─ ORCHESTRATOR_SELFPLAY_BACKEND=mock      → MockSelfPlayEngine (现有)
       └─ ORCHESTRATOR_SELFPLAY_BACKEND=pipeline  → PipelineServiceAdapter (新建)
                                                        │
                                                        ▼
                                               POST /api/pipeline/submit
                                               GET  /api/pipeline/status/{job_id}
                                               GET  /api/pipeline/logs/{job_id}
```

### 实施步骤

**Step 1: 新建 `services/adapters/pipeline_service_client.py`**

```python
"""Pipeline Service HTTP adapter — wraps the Self-Questioning pipeline as a self-play backend."""

class PipelineServiceClient:
    def __init__(self, base_url: str, *, timeout_s=30, poll_interval_s=5, poll_timeout_s=3600): ...
    def health(self) -> dict: ...
    def submit(self, request: PipelineRequest) -> PipelineTaskInfo: ...
    def status(self, job_id: str) -> PipelineTaskInfo: ...
    def wait_for_job(self, job_id: str) -> PipelineTaskInfo: ...  # poll loop
    def logs(self, job_id: str, lines=200) -> list[str]: ...
    def run_sync(self, request: PipelineRequest, timeout=600) -> PipelineTaskInfo: ...
```

遵循 `TrainingClient` 同样的模式（poll + timeout + error raise）。

**Step 2: 构建转换层 `services/adapters/selfplay_pipeline_adapter.py`**

将 `SelfCoachingClient.self_play()` 的语义映射到 Pipeline Service：

```python
class SelfPlayPipelineAdapter:
    """Adapts the SelfCoachingClient.self_play() interface to the real Pipeline Service."""

    def __init__(self, client: PipelineServiceClient, *, default_train_eval_flag="eval"):
        self._client = client
        self._default_flag = default_train_eval_flag

    def self_play(self, *, capability="tool_use", n=3, coaching_root=None) -> dict:
        """Submit a pipeline job, wait, return results in mock-compatible format."""
        request = {
            "start_stage": 1,           # full pipeline
            "train_eval_flag": self._default_flag,
            "generate_tasks_limit": n,  # limit to N messages → roughly N tasks
            "n": n,                     # exploration branches per task
            "num_explore_threads": min(n, 8),
            "dry_run_import": False,
        }
        result = self._client.run_sync(request)

        if result["status"] == "failed":
            return {"status": "error", "error": result["error"], "count": 0}

        return {
            "status": "generated",
            "count": n,
            "job_id": result["job_id"],
            "stage_results": result["stage_results"],
            "pipeline_service": True,  # flag indicating real backend
        }
```

**Step 3: 注册到 `LoopConfig` + `loop_env.py`**

在 `LoopConfig` 中添加：
```python
# 新字段
selfplay_backend: str = "mock"      # mock | pipeline
pipeline_service_url: str | None = None
```

在 `from_env()` 中读取：
```python
selfplay_be = os.environ.get("ORCHESTRATOR_SELFPLAY_BACKEND", "mock").lower()
pipeline_url = os.environ.get("PIPELINE_SERVICE_URL") or os.environ.get("SELF_QUESTIONING_URL")
```

在 `build_loop_client()` 中，当 `selfplay_backend == "pipeline"` 时注入 adapter。

**Step 4: Coach Clock 集成**

在 `trigger.py` 的 self-play 路由分支中，通过 composite client 调用 `self_play()`。由于 adapter 内部处理了异步 poll，对 caller 来说依然是阻塞调用，无需改动 scheduler 逻辑。

**Step 5: 环境变量示例**

```env
ORCHESTRATOR_SELFPLAY_BACKEND=pipeline
PIPELINE_SERVICE_URL=http://10.110.158.146:8001
PIPELINE_POLL_INTERVAL_S=5
PIPELINE_POLL_TIMEOUT_S=3600
```

### 关键考量

| 问题 | 建议 |
|------|------|
| Pipeline Service 的输出是导入到 Supabase，不是返回 case_ids | adapter 的 `self_play()` 返回 job 元数据即可；实际数据已在 DB 中，后续 eval 直接从 DB 读取 |
| 异步 job 可能跑很久（5–30 分钟） | `poll_timeout_s` 配合 scheduler 的 per-agent lock 可防止重复提交 |
| `dry_run` 模式可用于 CI 测试 | 在 CI 里用 `dry_run=True` 跑连通性，不消耗 GPU/LLM 配额 |
| Mock 路径保留 | `ORCHESTRATOR_SELFPLAY_BACKEND=mock` 仍走 MockSelfPlayEngine，保障本地开发和 CI |
| stage 粒度控制 | adapter 可暴露 `start_stage` 参数给高级调用方，用于 partial re-run |

---
