"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, GitBranch, Github, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { MetricCard, Panel, StatusBadge } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

type Repository = { id: string; full_name: string; provider: string; default_branch: string; installation_id?: string; active: boolean; html_url?: string; auto_merge_enabled:boolean; merge_method:string };

export default function Page() {
  const [rows, setRows] = useState<Repository[]>([]); const [error, setError] = useState(""); const [query, setQuery] = useState(""); const [showAll, setShowAll] = useState(false);
  async function load() { const result = await apiFetch<Repository[]>("/api/governance/repositories"); result.error ? setError(result.error.message) : setRows(result.data ?? []); }
  useEffect(() => { void load(); }, []);
  async function toggleAutoMerge(row:Repository){
    const next=!row.auto_merge_enabled;
    if(next&&!confirm("启用受控自动合并？仅当最新策略允许、审批完成、SHA 未变化且 GitHub 检查全部通过时才会合并。"))return;
    const result=await apiFetch(`/api/governance/repositories/${row.id}/governance`,{method:"PATCH",body:JSON.stringify({auto_merge_enabled:next,merge_method:row.merge_method||"squash"})});
    result.error?setError(result.error.message):await load();
  }
  const managed = rows.filter((row) => row.active && row.installation_id);
  const visible = useMemo(() => rows.filter((row) => (showAll || Boolean(row.installation_id)) && (!query || row.full_name.toLowerCase().includes(query.toLowerCase()))), [rows, query, showAll]);
  return <AppLayout title="代码资产" subtitle="管理 GitHub 授权范围、治理覆盖与仓库连接健康度。">
    {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div>}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="已授权仓库" value={managed.length} description="来自有效 GitHub Installation" /><MetricCard label="治理覆盖" value={rows.length ? `${Math.round(managed.length / rows.length * 100)}%` : "0%"} description="已接入真实事件链路" tone="emerald" /><MetricCard label="连接异常" value={rows.filter((row) => !row.active).length} description="需要重新授权或同步" tone={rows.some((row) => !row.active) ? "red" : "emerald"} /><MetricCard label="GitHub Installation" value={new Set(managed.map((row) => row.installation_id)).size} description="当前工作区授权主体" /></div>
    <Panel className="mt-5 overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 md:flex-row md:items-center"><div><h2 className="text-[15px] font-semibold">资产目录</h2><p className="mt-1 text-xs text-slate-500">默认仅显示已通过 GitHub App 纳管的真实仓库</p></div><div className="ml-auto flex gap-2"><div className="flex rounded-lg bg-slate-100 p-1 text-[11px]"><button onClick={() => setShowAll(false)} className={`rounded-md px-3 py-1.5 ${!showAll ? "bg-white font-medium text-slate-900 shadow-sm" : "text-slate-500"}`}>已纳管</button><button onClick={() => setShowAll(true)} className={`rounded-md px-3 py-1.5 ${showAll ? "bg-white font-medium text-slate-900 shadow-sm" : "text-slate-500"}`}>全部资产</button></div><label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3"><Search className="h-3.5 w-3.5 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索仓库" className="w-36 text-xs outline-none" /></label><button onClick={load} className="rounded-lg border border-slate-200 p-2 text-slate-500"><RefreshCw className="h-4 w-4" /></button></div></div>
      <div className="grid gap-4 p-5 lg:grid-cols-2 2xl:grid-cols-3">{visible.map((row) => <article key={row.id} className="group rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-300 hover:shadow-md"><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white"><Github className="h-5 w-5" /></div><div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-900">{row.full_name}</div><div className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-400"><GitBranch className="h-3 w-3" />{row.default_branch}</div></div></div><StatusBadge value={row.installation_id && row.active ? "active" : "pending"} /></div><div className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-[11px]"><div><span className="block text-slate-400">治理状态</span><span className="mt-1 flex items-center gap-1 font-medium text-slate-700"><ShieldCheck className="h-3 w-3 text-emerald-500" />{row.installation_id ? "策略已生效" : "历史种子数据"}</span></div><div><span className="block text-slate-400">Installation</span><span className="mt-1 block truncate font-mono text-slate-700">{row.installation_id ?? "未绑定"}</span></div></div><div className="mt-4 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2"><div><div className="text-xs font-medium text-slate-700">受控自动合并</div><div className="text-[10px] text-slate-400">{row.auto_merge_enabled?`${row.merge_method} · 全部门禁通过后执行`:"默认关闭"}</div></div><button onClick={()=>toggleAutoMerge(row)} disabled={!row.installation_id} className={`relative h-6 w-11 rounded-full transition ${row.auto_merge_enabled?"bg-emerald-500":"bg-slate-300"} disabled:opacity-40`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${row.auto_merge_enabled?"left-6":"left-1"}`}/></button></div>{row.html_url && <a href={row.html_url} target="_blank" className="mt-4 inline-flex items-center gap-1 text-[11px] font-medium text-blue-600">打开 GitHub <ExternalLink className="h-3 w-3" /></a>}</article>)}{!visible.length && <div className="col-span-full py-16 text-center text-xs text-slate-500">暂无已纳管仓库，请在“连接器”中同步 GitHub Installation。</div>}</div>
    </Panel>
  </AppLayout>;
}
