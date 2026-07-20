# DevPilot

DevPilot 是面向研发组织的企业 AI 工程平台，包含两条互相打通的业务主线：

1. **AI Agent 行为控制平面**：接入 Codex、Claude Code、Cursor 等工具的任务、文件、命令、测试与工具调用，执行操作前风险判断、人工审批和 Agent Evaluation。
2. **AI Coding 交付控制平面**：汇聚 GitHub PR、CI 和 LLM Gateway 证据，执行评分、策略门禁、审批、成本归因与审计。
3. **企业知识 Agent**：导入 PDF/Markdown/文本，自动分块检索，完成问题分类、基于证据回答、引用、反馈与人工专家升级。

它不是另一个 Codex/Claude Code，而是企业采用多种 AI Agent 后所需的治理、知识、成本和审计基础设施。

## 核心链路

```text
GitHub / CI / LLM Gateway → Evidence → Scorecard → Policy → Approval → Audit / Check
Coding Agent → Agent Run → Action Risk → Pre-action Approval → Evaluation → Audit
Enterprise Documents → Parse / Chunk → Retrieve → Guardrail → Answer → Feedback / Escalation
                                                        └→ Usage / Cost / Trace / Audit
```

## 已实现

- GitHub App/Webhook HMAC、Delivery 幂等、可信安装映射、Installation Token 和 Check 回写 Outbox。
- GitHub 集成中心、安装状态诊断、Installation 绑定、真实授权仓库同步和断开审计。
- Agent Run/Action、十类 AI Coding 风险、操作前审批、行为时间线与自动 Evaluation。
- 通用 `devpilot-agent-hook` CLI，可用于 Codex、Claude Code、Cursor 和自研 Agent 的 hooks。
- 企业管理驾驶舱：风险、审批 SLA、Agent 状态、模型分布和成本趋势可视化。
- 六维 Scorecard、Workspace/Team/Repository 策略继承、Policy-as-Code、审批和预算硬门禁。
- OIDC PKCE/JWKS/JIT、SCIM、Refresh Token 轮换/重放吊销、团队与仓库 RBAC。
- 文档上传解析、分块索引、中文/英文混合检索、引用、低置信度拒答、Prompt Injection 拦截。
- OpenAI-compatible 模型适配器；未配置或调用失败时自动使用零成本 extractive RAG。
- 知识回答反馈、人工升级、对话历史、用量成本、Prometheus 指标和不可变审计。
- PostgreSQL/Alembic、事务 Outbox、Trace ID、结构化日志、OTLP、Kubernetes、SBOM/provenance/Cosign。
- Python `uv.lock` 与 npm lockfile 固定依赖，CI/镜像使用 frozen 安装保证可复现构建。

## 一键运行

```powershell
Copy-Item .env.example .env
# 修改 POSTGRES_PASSWORD、JWT_SECRET_KEY、GITHUB_WEBHOOK_SECRET
docker compose up -d --build
```

- 控制台：<http://localhost:3000>
- 企业知识助手：<http://localhost:3000/knowledge>
- OpenAPI（开发环境）：<http://localhost:8000/docs>
- 就绪/指标：<http://localhost:8000/health>、<http://localhost:8000/metrics>

空库可注册演示管理员。生产必须关闭 `ALLOW_SELF_REGISTRATION` 和 `ALLOW_LOCAL_AUTH`，使用 OIDC/SCIM。知识模型默认关闭，开启前配置 `KNOWLEDGE_LLM_*`、企业密钥系统和实际合同价格。

## 验证

```powershell
Set-Location devpilot
python -m pytest -q
python -m alembic upgrade head

Set-Location ..\web
npm ci
npm run build
npm run test:e2e

Set-Location ..
docker compose config --quiet
kubectl kustomize deploy/kubernetes
```

项目结构、验收证据、生产门禁、演示脚本和面试拆解见 [docs](./docs/)。本地自动化通过代表代码达到 Release Candidate，不代表某个企业环境已经 Production Approved。
