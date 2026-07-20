"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, CircleDollarSign, ExternalLink, GitBranch, Play, RefreshCw, ShieldAlert, Workflow } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { EmptyState, MetricCard, Panel, PanelHeader, StatusBadge } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<any>();
  const [busy, setBusy] = useState(false);
  const load = () => apiFetch<any>(`/api/governance/pull-requests/${id}`).then((response) => setData(response.data));
  useEffect(() => { void load(); }, [id]);
  async function evaluate() { setBusy(true); await apiFetch(`/api/governance/pull-requests/${id}/evaluate`, { method: "POST" }); await load(); setBusy(false); }
  const cost = useMemo(() => data?.usage?.reduce((sum: number, item: any) => sum + item.cost_usd, 0) ?? 0, [data]);
  const latest = data?.evaluations?.[0];
  const decisionTone = latest?.decision === "block" ? "red" : latest?.decision === "review" ? "amber" : "emerald";

  return <AppLayout title={data ? `PR #${data.number} · ${data.title}` : "Pull Request"} subtitle={data?.repository?.full_name ?? "正在加载变更证据"}>
    {!data ? <Panel><div className="flex items-center justify-center gap-2 p-16 text-xs text-slate-400"><RefreshCw className="h-4 w-4 animate-spin" />加载变更证据</div></Panel> : <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Link href="/pull-requests" className="inline-flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-slate-900"><ArrowLeft className="h-3.5 w-3.5" />返回变更队列</Link>
        <div className="flex items-center gap-2">{latest && <StatusBadge value={latest.decision} />}{data.repository?.html_url && <a href={`${data.repository.html_url}/pull/${data.number}`} target="_blank" className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">打开 GitHub <ExternalLink className="h-3.5 w-3.5" /></a>}<button onClick={evaluate} disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3.5 py-2 text-xs font-medium text-white shadow-sm shadow-blue-200 hover:bg-blue-700 disabled:opacity-50">{busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}运行最新策略</button></div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="来源可信度" value={`${(data.source_confidence * 100).toFixed(0)}%`} description={`${data.source_signals.length} 条来源证据`} tone={data.source_confidence >= .8 ? "emerald" : "amber"} />
        <MetricCard label="CI 检查" value={data.ci_runs.length} description={`${data.ci_runs.filter((item: any) => item.conclusion === "success").length} 条检查通过`} tone={data.ci_runs.every((item: any) => item.conclusion === "success") ? "emerald" : "red"} />
        <MetricCard label="模型成本" value={`$${cost.toFixed(4)}`} description={`${data.usage.length} 条模型用量事件`} tone="blue" />
        <MetricCard label="策略决策" value={data.evaluations.length} description={latest ? `最新结果 · ${latest.decision}` : "尚未执行策略"} tone={decisionTone} />
      </div>
      {latest && <Panel className={`overflow-hidden border-l-4 ${latest.decision === "block" ? "border-l-red-500" : latest.decision === "review" ? "border-l-amber-500" : "border-l-emerald-500"}`}><div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center"><span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${latest.decision === "block" ? "bg-red-50 text-red-600" : latest.decision === "review" ? "bg-amber-50 text-amber-600" : "bg-emerald-50 text-emerald-600"}`}>{latest.decision === "allow" ? <CheckCircle2 className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}</span><div className="flex-1"><div className="flex items-center gap-2"><h2 className="text-sm font-semibold">策略结论：{latest.decision === "block" ? "阻断合并" : latest.decision === "review" ? "等待人工复核" : "允许交付"}</h2><StatusBadge value={latest.decision} /></div><p className="mt-1.5 text-xs leading-5 text-slate-500">{latest.reasons.join("；") || "全部检查通过"}</p></div><div className="text-right text-[10px] text-slate-400"><div>{latest.policy_version}</div><div className="mt-1">{new Date(latest.created_at).toLocaleString()}</div></div></div></Panel>}
      <div className="grid gap-5 xl:grid-cols-[1.25fr_.85fr]">
        <Panel><PanelHeader title="策略决策时间线" description="每次评估均保留版本、证据和最终决策" /><div className="divide-y divide-slate-100">{data.evaluations.length ? data.evaluations.map((evaluation: any, index: number) => <div key={evaluation.id} className="flex gap-4 px-5 py-4"><div className="relative flex flex-col items-center"><span className={`flex h-8 w-8 items-center justify-center rounded-full ${evaluation.decision === "block" ? "bg-red-50 text-red-600" : evaluation.decision === "review" ? "bg-amber-50 text-amber-600" : "bg-emerald-50 text-emerald-600"}`}><Workflow className="h-3.5 w-3.5" /></span>{index < data.evaluations.length - 1 && <span className="mt-2 h-full w-px bg-slate-200" />}</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-xs font-semibold">{evaluation.policy_version}</span><StatusBadge value={evaluation.decision} /></div><p className="mt-2 text-xs leading-5 text-slate-500">{evaluation.reasons.join("；") || "全部检查通过"}</p><div className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(evaluation.checks ?? {}).map(([name, result]) => <div key={name} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-[10px]"><span className="text-slate-500">{name}</span><StatusBadge value={String(result)} /></div>)}</div></div><time className="hidden whitespace-nowrap text-[10px] text-slate-400 sm:block">{new Date(evaluation.created_at).toLocaleString()}</time></div>) : <EmptyState title="尚未执行治理策略" description="运行最新策略后，这里会显示可审计的策略决策链。" />}</div></Panel>
        <div className="space-y-5">
          <Panel><PanelHeader title="交付证据" description="来自 GitHub、CI 与模型网关" /><div className="divide-y divide-slate-100">{data.ci_runs.map((run: any) => <div key={run.id} className="flex items-center gap-3 px-5 py-3.5"><span className={`flex h-8 w-8 items-center justify-center rounded-lg ${run.conclusion === "success" ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}><CheckCircle2 className="h-4 w-4" /></span><div className="min-w-0 flex-1"><div className="truncate text-xs font-medium">{run.name}</div><div className="mt-0.5 text-[10px] text-slate-400">尝试 #{run.attempt} · {run.status}</div></div><StatusBadge value={run.conclusion ?? run.status} /></div>)}{data.usage.map((item: any) => <div key={item.id} className="flex items-center gap-3 px-5 py-3.5"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600"><CircleDollarSign className="h-4 w-4" /></span><div className="min-w-0 flex-1"><div className="truncate text-xs font-medium">{item.provider} / {item.model}</div><div className="mt-0.5 text-[10px] text-slate-400">{item.tokens} tokens</div></div><span className="text-xs font-medium">${item.cost_usd.toFixed(4)}</span></div>)}{!data.ci_runs.length && !data.usage.length && <EmptyState title="暂无交付证据" description="等待 CI 或模型网关事件进入当前 PR。" />}</div></Panel>
          <Panel><PanelHeader title="变更范围" description="GitHub Pull Request 元数据" /><div className="grid grid-cols-3 gap-px overflow-hidden rounded-b-[14px] bg-slate-100 text-center"><div className="bg-white p-4"><div className="text-lg font-semibold text-emerald-600">+{data.changes.additions}</div><div className="mt-1 text-[10px] text-slate-400">新增</div></div><div className="bg-white p-4"><div className="text-lg font-semibold text-red-600">-{data.changes.deletions}</div><div className="mt-1 text-[10px] text-slate-400">删除</div></div><div className="bg-white p-4"><div className="flex items-center justify-center gap-1 text-lg font-semibold"><GitBranch className="h-4 w-4" />{data.changes.files}</div><div className="mt-1 text-[10px] text-slate-400">文件</div></div></div></Panel>
        </div>
      </div>
    </div>}
  </AppLayout>;
}
