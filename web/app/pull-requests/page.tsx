"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Filter, GitPullRequest, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { MetricCard, Panel, StatusBadge } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

type PullRequest = { id: string; number: number; title: string; author: string; state: string; source_confidence: number; repository?: { full_name?: string } | string; decision?: string; risk_level?: string; created_at?: string };

export default function Page() {
  const [rows, setRows] = useState<PullRequest[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() { setBusy(true); const result = await apiFetch<PullRequest[]>("/api/governance/pull-requests"); setRows(result.data ?? []); setBusy(false); }
  useEffect(() => { void load(); }, []);
  const filtered = useMemo(() => rows.filter((row) => !query || `${row.title} ${row.author} ${row.number}`.toLowerCase().includes(query.toLowerCase())), [rows, query]);
  const highRisk = rows.filter((row) => row.risk_level === "high" || row.risk_level === "critical" || row.decision === "block").length;
  const review = rows.filter((row) => row.decision === "review" || row.state === "open").length;
  const confidence = rows.length ? rows.reduce((sum, row) => sum + (row.source_confidence ?? 0), 0) / rows.length : 0;
  const repoName = (row: PullRequest) => typeof row.repository === "string" ? row.repository : row.repository?.full_name ?? "GitHub";

  return <AppLayout title="变更控制" subtitle="统一评估 AI 代码变更的安全、质量、成本与来源可信度。">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="纳管变更" value={rows.length} description="当前工作区全部 Pull Request" tone="blue" />
      <MetricCard label="高风险变更" value={highRisk} description="严重风险或已触发策略阻断" tone={highRisk ? "red" : "emerald"} />
      <MetricCard label="待复核" value={review} description="需要研发负责人确认的变更" tone={review ? "amber" : "emerald"} />
      <MetricCard label="平均来源可信度" value={`${(confidence * 100).toFixed(0)}%`} description="Agent、CI 与 Gateway 证据综合评分" tone={confidence >= .8 ? "emerald" : "amber"} />
    </div>

    <Panel className="mt-5 overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center">
        <div><h2 className="text-[15px] font-semibold">变更队列</h2><p className="mt-1 text-xs text-slate-500">按风险优先级处理阻断、审批与合并决策</p></div>
        <div className="ml-auto flex items-center gap-2">
          <label className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3"><Search className="h-3.5 w-3.5 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="w-44 bg-transparent text-xs outline-none" placeholder="搜索 PR 或提交人" /></label>
          <button className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs text-slate-600"><Filter className="h-3.5 w-3.5" />筛选</button>
          <button onClick={load} className="rounded-lg border border-slate-200 p-2 text-slate-500"><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /></button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="bg-slate-50/80 text-[10px] font-semibold uppercase tracking-[.08em] text-slate-400"><tr><th className="px-5 py-3">变更</th><th className="px-4 py-3">代码资产</th><th className="px-4 py-3">提交人</th><th className="px-4 py-3">风险决策</th><th className="px-4 py-3">来源可信度</th><th className="px-4 py-3 text-right">操作</th></tr></thead>
          <tbody>{filtered.map((row) => <tr key={row.id} className="border-t border-slate-100 hover:bg-blue-50/30">
            <td className="px-5 py-4"><div className="flex items-start gap-3"><span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600"><GitPullRequest className="h-4 w-4" /></span><div><Link className="font-semibold text-slate-900 hover:text-blue-600" href={`/pull-requests/${row.id}`}>{row.title}</Link><div className="mt-1 text-[11px] text-slate-400">PR #{row.number} · {row.state === "open" ? "开放中" : row.state}</div></div></div></td>
            <td className="px-4 py-4 font-medium text-slate-600">{repoName(row)}</td><td className="px-4 py-4 text-slate-600">{row.author}</td>
            <td className="px-4 py-4"><div className="flex items-center gap-2"><StatusBadge value={row.decision ?? row.risk_level ?? "review"} />{(row.decision === "block" || row.risk_level === "critical") && <ShieldAlert className="h-4 w-4 text-red-500" />}</div></td>
            <td className="px-4 py-4"><div className="flex items-center gap-3"><div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${row.source_confidence >= .8 ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: `${row.source_confidence * 100}%` }} /></div><span className="font-semibold text-slate-700">{(row.source_confidence * 100).toFixed(0)}%</span></div></td>
            <td className="px-4 py-4 text-right"><Link href={`/pull-requests/${row.id}`} className="inline-flex items-center gap-1 font-medium text-blue-600">查看证据<ArrowUpRight className="h-3.5 w-3.5" /></Link></td>
          </tr>)}{!filtered.length && <tr><td colSpan={6} className="px-6 py-16 text-center text-xs text-slate-500">暂无匹配变更。创建 GitHub PR 后，风险评估会自动进入此队列。</td></tr>}</tbody>
        </table>
      </div>
    </Panel>
  </AppLayout>;
}
