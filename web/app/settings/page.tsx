"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Database, KeyRound, LockKeyhole, RotateCcw, ServerCog, Users } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Panel, PanelHeader, StatusBadge } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

export default function Page() {
  const [status, setStatus] = useState<any>(); const [me, setMe] = useState<any>(); const [dead, setDead] = useState<any[]>([]);
  useEffect(() => { apiFetch("/api/system/status").then((r) => setStatus(r.data)); apiFetch("/api/auth/me").then((r) => setMe(r.data)); apiFetch<any[]>("/api/system/outbox/dead-letters").then((r) => setDead(r.data || [])); }, []);
  async function requeue(id: string) { await apiFetch(`/api/system/outbox/${id}/requeue`, { method: "POST" }); setDead((items) => items.filter((item) => item.id !== id)); }
  const health = [
    { label: "API 服务", value: "正常", detail: status?.environment ?? "development", icon: ServerCog },
    { label: "事务消息", value: status ? `${status.outbox.pending} 待处理` : "检查中", detail: status ? `${status.outbox.failed} 失败` : "", icon: Database },
    { label: "身份与权限", value: me?.role ?? "检查中", detail: me?.username ?? "", icon: Users },
    { label: "知识服务", value: status?.knowledge?.model ?? "检查中", detail: "私有知识边界", icon: KeyRound },
  ];
  const boundaries = [
    { title: "Workspace 数据隔离", detail: "租户数据按 workspace_id 强制隔离", icon: LockKeyhole },
    { title: "审计事件只追加", detail: "关键决策不可覆盖或静默删除", icon: Database },
    { title: "敏感凭据脱敏", detail: "Token、Cookie 与私钥禁止写入日志", icon: KeyRound },
    { title: "人工审批兜底", detail: "高风险 Agent 操作执行前必须授权", icon: Users },
  ];
  return <AppLayout title="系统设置" subtitle="管理工作区身份、运行健康、数据边界与故障恢复。">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{health.map(({ label, value, detail, icon: Icon }) => <Panel key={label} className="p-4"><div className="flex items-center justify-between"><div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><Icon className="h-4 w-4" /></div><StatusBadge value="active" /></div><div className="mt-4 text-xs text-slate-400">{label}</div><div className="mt-1 truncate text-sm font-semibold text-slate-900">{value}</div><div className="mt-1 truncate text-[10px] text-slate-400">{detail}</div></Panel>)}</div>
    <div className="mt-5 grid gap-5 xl:grid-cols-[1.35fr_1fr]">
      <Panel><PanelHeader title="安全与数据边界" description="平台默认执行最小采集与工作区隔离" /><div className="grid gap-3 p-5 sm:grid-cols-2">{boundaries.map(({ title, detail, icon: Icon }) => <div key={title} className="rounded-xl border border-slate-200 p-4"><div className="flex items-start gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600"><Icon className="h-4 w-4" /></span><div><div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800">{title}<CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /></div><p className="mt-1 text-[10px] leading-4 text-slate-400">{detail}</p></div></div></div>)}</div></Panel>
      <Panel><PanelHeader title="管理入口" description="平台级配置集中维护" /><div className="divide-y divide-slate-100">{[["连接器", "GitHub App 与模型网关", "/integrations"], ["策略中心", "版本化治理规则", "/policies"], ["模型与成本", "预算、限额与用量", "/costs"], ["审计追踪", "查询不可变事件", "/audit"]].map(([title, detail, href]) => <Link key={href} href={href} className="flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50"><div className="flex-1"><div className="text-xs font-medium text-slate-800">{title}</div><div className="mt-1 text-[10px] text-slate-400">{detail}</div></div><ArrowRight className="h-4 w-4 text-slate-300" /></Link>)}</div></Panel>
    </div>
    {dead.length > 0 && <Panel className="mt-5"><PanelHeader title="Outbox 故障恢复" description="外部依赖恢复后由管理员受控重放，原始审计记录保持不变" /><div className="divide-y divide-slate-100">{dead.map((item) => <div key={item.id} className="flex items-center justify-between p-5 text-xs"><div><div className="font-medium">{item.event_type}</div><div className="mt-1 text-slate-500">失败 {item.attempts} 次 · {item.last_error}</div></div><button onClick={() => requeue(item.id)} className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-3 py-2 text-white"><RotateCcw className="h-3.5 w-3.5" />重新入队</button></div>)}</div></Panel>}
  </AppLayout>;
}
