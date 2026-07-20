# Coding Agent 原生接入指南

## 稳定合同

连接器统一上报 `schema_version=v1` 事件：`run.started`、`run.heartbeat`、`action.pre`、`action.completed`、`run.completed`。事件必须携带 `event_id`、`run_external_id`、provider、时间、Trace 和幂等序号。

- 同一 Run ID 或 Action sequence 重放相同负载：返回 `duplicate`。
- 同一幂等键上报不同负载：返回 `409 EVIDENCE_CONFLICT`。
- 高风险 `action.pre`：创建中心审批，Hook 暂停轮询，超时 fail-closed。
- Run 超过心跳窗口：Worker 标记 `timed_out`，不伪造完成。

## 1. 签发服务凭据

在“连接器 → Coding Agent 服务身份”点击签发。Token 只显示一次，服务端只保存 SHA-256 摘要。

```powershell
$env:GOVERNFORGE_URL="http://localhost:8000"
$env:GOVERNFORGE_AGENT_TOKEN="<gf_agent_...>"
$env:GOVERNFORGE_WORKSPACE="ai_platform"
$env:GOVERNFORGE_ACTOR="developer@example.com"
```

## 2. Codex 接入

Codex 当前稳定 lifecycle hooks 包含 `SessionStart`、`PreToolUse`、`PermissionRequest`、`PostToolUse` 和 `Stop`；项目级 Hook 只会在项目被信任后加载。

```powershell
cd D:\path\to\target-repository
governforge-agent-hook install --provider codex --root .
```

命令生成 `.codex/hooks.json`，不会覆盖已有文件。启动 Codex 后使用 `/hooks` 检查、信任新 Hook。对企业强制策略，应通过托管 `requirements.toml`/MDM 发布，不仅依赖仓库内配置。

## 3. Claude Code 接入

```powershell
cd D:\path\to\target-repository
governforge-agent-hook install --provider claude-code --root .
```

命令生成 `.claude/settings.json`，映射 `SessionStart`、`PreToolUse`、`PostToolUse` 和 `Stop`。中心审批超时默认 300 秒，可用 `GOVERNFORGE_APPROVAL_WAIT_SECONDS` 调整。

## 4. 降级策略

- 写文件、命令、未登记工具和敏感操作：GovernForge 不可用时默认 deny。
- 只读操作：仅当显式设置 `GOVERNFORGE_FAIL_OPEN_READS=true` 才可 fail-open，并在 Hook 输出中标记降级。
- 不得将个人 Web 登录 JWT 写入 Hook；机器凭据应设置到期时间并定期轮换。

## 5. 验收用例

1. 读取普通源文件：`allow`，形成 Action 审计。
2. 修改 `auth`/迁移/部署文件：进入 Owner/Security 审批，未批准不执行。
3. 执行删除、`git reset --hard` 或越权命令：critical，拒绝或等待 Security。
4. 执行测试并停止任务：自动生成 Agent Evaluation。
5. 中断 Hook 网络：写操作 fail-closed；恢复后相同事件幂等重放。
