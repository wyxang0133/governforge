# Agent 行为接入指南

## 标准事件模型

一次编码任务映射为一个 `AgentRun`，每个行为按递增 `sequence` 上报为 `AgentAction`：

- `plan`：计划与任务拆解。
- `file_read/file_write/file_delete`：文件操作。
- `command`：终端命令。
- `tool_call`：MCP、浏览器或外部系统工具。
- `dependency`：依赖变更和漏洞结果。
- `test`：测试名称、结论和覆盖率。
- `pull_request`：PR 创建或更新。

服务端对敏感文件、凭据、破坏性命令、权限扩大、未批准工具、依赖和测试行为分类。高风险 Action 返回 `waiting_approval`，调用方必须暂停 Agent，直到审批结果变为 approved/rejected。

## 通用 Hook CLI

```powershell
$env:DEVPILOT_URL="http://localhost:8000"
$env:DEVPILOT_TOKEN="<access-token>"
$env:DEVPILOT_WORKSPACE="ai_platform"

devpilot-agent-hook start --external-id codex-20260719-001 --provider codex --agent-name Codex --task "升级登录会话" --plan "分析认证模块" --plan "修改并测试"

devpilot-agent-hook action --run-id <run-id> --sequence 1 --type file_write --target "src/auth/session.py"
devpilot-agent-hook action --run-id <run-id> --sequence 2 --type test --target "tests/test_auth.py" --detail '{"conclusion":"passed"}'
devpilot-agent-hook complete --run-id <run-id>
```

CLI 的 `--type` 使用下划线形式，例如 `file_write`。返回体包含 `requires_approval` 和 `approval_id`；高风险操作不能在未批准时继续执行。

## 工具映射

- Claude Code Hooks：在 PreToolUse/PostToolUse 中调用 action；`waiting_approval` 时退出非零并等待审批。
- Codex/自研 Agent：在工具执行器外包一层 Hook，在执行文件/命令前上报。
- Cursor/IDE Agent：通过扩展或 CI 汇总事件；无法做前置拦截时标记为检测模式。

不同工具的原始事件先在连接器侧转换成标准 Action，策略和评估内核不绑定供应商。

## 风险分类

`secret_exposure`、`privilege_escalation`、`dependency_risk`、`test_bypass`、`sensitive_file_change`、`cost_anomaly`、`unapproved_tool`、`destructive_operation`、`data_exfiltration`、`policy_bypass`。

生产接入必须使用短期服务身份或企业 OIDC Token，禁止把个人长期 Token 写进仓库。
