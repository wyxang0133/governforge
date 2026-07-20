import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";

test("enterprise governance flow works through the browser and BFF", async ({page}) => {
  const username = `e2e-${Date.now()}`;
  const existingAdmin = process.env.E2E_ADMIN_USERNAME;
  await page.goto(existingAdmin ? "/login" : "/register");
  await page.getByLabel("用户名").fill(existingAdmin || username);
  await page.getByLabel("密码").fill(process.env.E2E_ADMIN_PASSWORD || "E2ePass!2026");
  await page.getByRole("button", {name: existingAdmin ? "登录" : "创建并进入"}).click();
  await expect(page).toHaveURL(/\/$/);

  const payload = {number: 88, repository: {id: 8800, full_name: "acme/e2e", default_branch: "main"}, pull_request: {number: 88, title: "Enterprise delivery gate", state: "open", user: {login: "e2e"}, head: {sha: "e2esha"}, additions: 12, deletions: 2, changed_files: 1, labels: [{name: "ai-assisted"}]}};
  const raw = JSON.stringify(payload); const secret = process.env.E2E_GITHUB_WEBHOOK_SECRET || "";
  const headers: Record<string,string> = {"Content-Type": "application/json", "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": `e2e-${Date.now()}`};
  if (secret) headers["X-Hub-Signature-256"] = `sha256=${createHmac("sha256", secret).update(raw).digest("hex")}`;
  const webhook = await page.request.post("/api/integrations/github/webhook", {headers, data: raw});
  expect(webhook.ok()).toBeTruthy();

  await page.goto("/repositories");
  await expect(page.getByText("acme/e2e")).toBeVisible();
  await page.goto("/pull-requests");
  await expect(page.getByText("Enterprise delivery gate")).toBeVisible();
  await page.getByRole("link", {name: "#88"}).click();
  await expect(page.getByText("Enterprise delivery gate")).toBeVisible();

  await page.goto("/policies");
  await page.getByRole("button", {name: "创建企业策略"}).click();
  await expect(page.getByText(/企业高风险变更策略/).first()).toBeVisible();
  await page.getByRole("button", {name: "导出策略代码"}).click();
  await expect(page.locator("textarea")).toContainText("kind: PolicyBundle");

  await page.goto("/costs");
  await page.waitForLoadState("networkidle");
  const createBudget = page.getByRole("button", {name: /创建 \$100 月度预算/});
  if (await createBudget.isVisible().catch(() => false)) await createBudget.click({force: true});
  await expect(page.getByText("预算进度")).toBeVisible();

  await page.goto("/agent-runs");
  const demoCreated = page.waitForResponse(response => response.url().includes("/api/agents/demo") && response.request().method() === "POST");
  await page.getByRole("button", {name: "生成演示任务"}).first().click();
  const demoPayload = await (await demoCreated).json();
  await page.goto(`/agent-runs/${demoPayload.run_id}`);
  await expect(page.getByText("Agent 行为时间线")).toBeVisible();
  await page.getByRole("button", {name: "批准继续"}).click();
  await page.getByRole("button", {name: "完成任务并执行评估"}).click();
  await expect(page.getByText("需复核")).toBeVisible();

  await page.goto("/integrations");
  await expect(page.getByText("GitHub App", {exact: true})).toBeVisible();

  await page.goto("/knowledge");
  await page.getByRole("button", {name: "初始化"}).click();
  await page.getByRole("button", {name: "发送"}).click();
  await expect(page.getByText(/问题分类：risk/)).toBeVisible();
  await expect(page.getByText("AI 编码安全与权限边界").last()).toBeVisible();
  await page.getByTitle("回答有帮助").click();
  await page.getByRole("button", {name: "转人工专家"}).click();
  await expect(page.getByText(/已转交 knowledge-experts/)).toBeVisible();

  await page.getByRole("button", {name: "退出登录"}).click();
  await expect(page).toHaveURL(/\/login$/);
});
