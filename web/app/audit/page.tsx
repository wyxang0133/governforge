"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, Filter, GitBranch, Search, ShieldCheck, Workflow } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { MetricCard, Panel } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

type AuditEvent = { id: string; event_type: string; actor_id: string; entity_type: string; entity_id: string; trace_id?: string; created_at: string; payload: unknown };
const eventNames: Record<string, string> = { "integration.github.received": "收到 GitHub 事件", "integration.github.repositories.synced": "同步 GitHub 仓库", "integration.github.installation.registered": "绑定 GitHub Installation", "knowledge.seeded": "初始化企业知识" };

export default function Page() {
  const [rows, setRows] = useState<AuditEvent[]>([]); const [query, setQuery] = useState("");
  useEffect(() => { apiFetch<AuditEvent[]>("/api/governance/audit?limit=300").then((result) => setRows(result.data ?? [])); }, []);
  const filtered = useMemo(() => rows.filter((row) => !query || JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows, query]);
  const githubEvents = rows.filter((row) => row.event_type.includes("github")).length; const traces = new Set(rows.map((row) => row.trace_id).filter(Boolean)).size; const today = rows.filter((row) => new Date(row.created_at).toDateString() === new Date().toDateString()).length;
  const iconFor = (type: string) => type.includes("github") ? GitBranch : type.includes("policy") || type.includes("approval") ? ShieldCheck : Workflow;
  return <AppLayout title="审计追踪" subtitle="以不可变事件和 Trace ID 还原 Agent、策略、审批与外部系统行为。">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="审计事件" value={rows.length} description="当前查询窗口内的不可变记录" /><MetricCard label="今日新增" value={today} description="过去自然日写入事件" tone="emerald" /><MetricCard label="GitHub 事件" value={githubEvents} description="Webhook、安装与仓库同步" /><MetricCard label="独立 Trace" value={traces} description="可端到端还原的业务链路" tone="amber" /></div>
    <Panel className="mt-5 overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 md:flex-row md:items-center"><div><h2 className="text-[15px] font-semibold">事件时间线</h2><p className="mt-1 text-xs text-slate-500">{filtered.length} 条事件 · 点击展开原始证据</p></div><div className="ml-auto flex gap-2"><label className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3"><Search className="h-3.5 w-3.5 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Actor、实体或 Trace ID" className="w-52 bg-transparent text-xs outline-none" /></label><button className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 text-xs text-slate-600"><Filter className="h-3.5 w-3.5" />事件类型</button></div></div>
      <div className="divide-y divide-slate-100">{filtered.map((row) => { const Icon = iconFor(row.event_type); return <details key={row.id} className="group"><summary className="flex cursor-pointer list-none items-center gap-4 px-5 py-4 hover:bg-slate-50/70"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600"><Icon className="h-4 w-4" /></div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-xs font-semibold text-slate-900">{eventNames[row.event_type] ?? row.event_type}</span><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /></div><div className="mt-1 flex flex-wrap items-center gap-x-2 text-[10px] text-slate-400"><span>{row.actor_id}</span><span>·</span><span>{row.entity_type}/{row.entity_id}</span>{row.trace_id && <><span>·</span><span className="font-mono text-blue-600">Trace {row.trace_id.slice(0, 12)}…</span></>}</div></div><time className="hidden whitespace-nowrap text-[10px] text-slate-400 sm:block">{new Date(row.created_at).toLocaleString()}</time><ChevronRight className="h-4 w-4 text-slate-300 transition group-open:rotate-90" /></summary><div className="border-t border-slate-100 bg-slate-950 px-5 py-4"><pre className="overflow-auto text-[11px] leading-5 text-slate-300">{JSON.stringify(row.payload, null, 2)}</pre></div></details>; })}</div>
    </Panel>
  </AppLayout>;
}
