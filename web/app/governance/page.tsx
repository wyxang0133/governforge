"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Download, Target } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { BarList, MetricCard, Panel, PanelHeader, SegmentedBar } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

type Metrics = { ai_assisted_pr_rate: number; source_confidence: number; first_ci_pass_rate: number; rework_rate: number; cycle_time_hours: number; cost_per_merged_pr_usd: number; counts: { pull_requests: number; merged: number; ai_usage_events: number } };

export default function Page() {
  const [data, setData] = useState<Metrics>();
  useEffect(() => { apiFetch<{ metrics: Metrics }>("/api/governance/scorecard").then((result) => result.data && setData(result.data.metrics)); }, []);
  const percent = (value = 0) => `${(value * 100).toFixed(1)}%`;
  const bars = [52, 61, 48, 68, 72, 70, 78, 81, 76, 85, 88, Math.round((data?.first_ci_pass_rate ?? .9) * 100)];
  return <AppLayout title="效能洞察" subtitle="量化 AI Coding 对交付速度、质量、成本与可信度的实际影响。">
    <div className="mb-4 flex justify-end gap-2"><button className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"><CalendarDays className="h-3.5 w-3.5" />近 30 天</button><button className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"><Download className="h-3.5 w-3.5" />导出报告</button></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="AI 辅助变更占比" value={percent(data?.ai_assisted_pr_rate)} description="具有可信 Agent / Gateway 证据" trend={12.4} />
      <MetricCard label="首次 CI 通过率" value={percent(data?.first_ci_pass_rate)} description="衡量一次性交付质量" tone="emerald" trend={4.8} />
      <MetricCard label="平均交付周期" value={`${(data?.cycle_time_hours ?? 0).toFixed(1)}h`} description="从 PR 创建到合并" tone="blue" trend={-8.2} />
      <MetricCard label="单位交付成本" value={`$${(data?.cost_per_merged_pr_usd ?? 0).toFixed(2)}`} description="每个已合并 AI 变更" tone="amber" trend={-3.6} />
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-[1.55fr_1fr]">
      <Panel><PanelHeader title="交付质量趋势" description="首次 CI 通过率 · 12 个周期" action={<span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600"><Target className="h-3.5 w-3.5" />目标 85%</span>} /><div className="px-5 pb-5 pt-6"><div className="relative flex h-56 items-end gap-2 border-b border-slate-200">{bars.map((value, index) => <div key={index} className="group relative flex h-full flex-1 items-end"><div className="w-full rounded-t-md bg-gradient-to-t from-blue-600 to-blue-400 opacity-90" style={{ height: `${value}%` }} /><span className="absolute bottom-[calc(100%+6px)] left-1/2 hidden -translate-x-1/2 rounded bg-slate-900 px-2 py-1 text-[10px] text-white group-hover:block">{value}%</span></div>)}</div><div className="mt-3 flex justify-between text-[10px] text-slate-400"><span>第 1 周</span><span>第 6 周</span><span>本周</span></div></div></Panel>
      <Panel><PanelHeader title="质量与返工" description="交付结果构成" /><div className="p-5"><SegmentedBar items={[{ label: "首次通过", value: Math.round((data?.first_ci_pass_rate ?? 0) * 100), color: "bg-emerald-500" }, { label: "返工", value: Math.round((data?.rework_rate ?? 0) * 100), color: "bg-amber-500" }, { label: "其他", value: Math.max(0, 100 - Math.round(((data?.first_ci_pass_rate ?? 0) + (data?.rework_rate ?? 0)) * 100)), color: "bg-slate-300" }]} /><div className="mt-8"><BarList items={[{ label: "来源可信度", value: Math.round((data?.source_confidence ?? 0) * 100), display: percent(data?.source_confidence), tone: "blue" }, { label: "首次 CI 通过", value: Math.round((data?.first_ci_pass_rate ?? 0) * 100), display: percent(data?.first_ci_pass_rate), tone: "emerald" }, { label: "返工率", value: Math.round((data?.rework_rate ?? 0) * 100), display: percent(data?.rework_rate), tone: "amber" }]} /></div></div></Panel>
    </div>
    <Panel className="mt-5"><PanelHeader title="治理证据覆盖" description="当前指标的数据完整度与可解释性" /><div className="grid gap-px overflow-hidden rounded-b-[14px] bg-slate-100 sm:grid-cols-3">{[["Pull Request", data?.counts.pull_requests ?? 0, "GitHub App"], ["已合并变更", data?.counts.merged ?? 0, "交付结果"], ["模型用量事件", data?.counts.ai_usage_events ?? 0, "LLM Gateway"]].map(([label, value, source]) => <div key={String(label)} className="bg-white p-5"><div className="text-xs text-slate-500">{label}</div><div className="mt-2 text-2xl font-semibold">{value}</div><div className="mt-2 text-[10px] text-slate-400">数据源 · {source}</div></div>)}</div></Panel>
  </AppLayout>;
}
