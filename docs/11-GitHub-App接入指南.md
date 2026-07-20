# GitHub App 接入指南

## 创建 GitHub App

建议权限：

- Repository metadata：Read-only
- Pull requests：Read-only
- Checks：Read & write
- Actions：Read-only（如需采集 Workflow Run）

订阅 `pull_request`、`check_run`、`workflow_run` 和安装/仓库范围相关事件。Webhook URL 设置为：

```text
https://<your-domain>/api/integrations/github/webhook
```

Setup URL 指向：

```text
https://<your-domain>/integrations
```

## 配置

```text
GITHUB_APP_ID=<app id>
GITHUB_APP_SLUG=<app slug>
GITHUB_APP_PRIVATE_KEY=<PEM private key>
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/devpilot/github-app.pem
GITHUB_WEBHOOK_SECRET=<strong webhook secret>
GITHUB_CHECKS_ENABLED=true
```

私钥和 Webhook Secret 必须从企业密钥系统注入，不能进入 Git、镜像或 ConfigMap。

## 前端接入流程

1. 打开“集成中心”，检查 App ID、Private Key、Webhook Secret 和 Checks 状态。
2. 点击“安装 GitHub App”，在 GitHub 选择组织和授权仓库。
3. 返回后确认 Installation ID 并绑定到当前 Workspace。
4. 点击“同步仓库”；服务端使用短期 Installation Token 获取授权仓库。
5. 创建真实 PR，验证 Webhook、Scorecard、Policy、Approval、Audit 和 Check 回写。

Installation ID 在全平台只能绑定一个 Workspace，防止伪造 Header 造成跨租户事件注入。

## 当前本地状态

本地环境已经运行完整连接器代码，但没有用户的真实 GitHub App ID、Slug 和私钥，因此集成中心会显示“待配置”。这不是代码缺失；填入真实凭据后才可完成 GitHub 侧验收。
