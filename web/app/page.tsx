"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { BarList, EmptyState, MetricCard, Panel, PanelHeader } from "@/components/ui/Console";
import { apiFetch } from "@/lib/api-client";

type Dashboard={kpis:{repositories:number;pull_requests:number;risk_pull_requests:number;blocked_pull_requests:number;agent_runs:number;high_risk_agent_runs:number;pending_approvals:number;approval_sla_minutes:number;total_cost_usd:number;average_agent_score:number};cost_trend:{date:string;cost_usd:number}[];model_distribution:{model:string;calls:number;tokens:number;cost_usd:number}[];risk_distribution:{type:string;label:string;count:number}[];agent_status:{status:string;count:number}[]};
const statusNames:Record<string,string>={running:"执行中",waiting_approval:"等待审批",completed:"已完成",blocked:"已阻断",failed:"失败"};

export default function HomePage(){
  const [data,setData]=useState<Dashboard>();const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function load(){setBusy(true);const response=await apiFetch<Dashboard>("/api/dashboard/overview");if(response.error)setError(response.error.message);else{setData(response.data!);setError("")}setBusy(false)}
  useEffect(()=>{void load()},[]);
  const maxCost=useMemo(()=>Math.max(.001,...(data?.cost_trend??[]).map(item=>item.cost_usd)),[data]);
  const k=data?.kpis;
  return <AppLayout title="企业 AI Agent 管理驾驶舱" subtitle="从管理视角统一观察 Agent 使用规模、交付风险、审批效率、模型成本和治理效果。">
    <div className="mb-5 flex justify-end"><button onClick={load} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm"><RefreshCw className={`h-4 w-4 ${busy?"animate-spin":""}`}/>刷新数据</button></div>
    {error&&<div className="mb-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Agent 任务" value={k?.agent_runs??0} description={`${k?.high_risk_agent_runs??0} 个高风险任务`} tone={(k?.high_risk_agent_runs??0)>0?"amber":"blue"}/>
      <MetricCard label="风险变更" value={k?.risk_pull_requests??0} description={`${k?.blocked_pull_requests??0} 个 PR 被策略阻断`} tone={(k?.blocked_pull_requests??0)>0?"red":"emerald"}/>
      <MetricCard label="待处理审批" value={k?.pending_approvals??0} description={`平均处理 ${k?.approval_sla_minutes??0} 分钟`} tone={(k?.pending_approvals??0)>0?"amber":"emerald"}/>
      <MetricCard label="累计模型成本" value={`$${(k?.total_cost_usd??0).toFixed(2)}`} description={`Agent 平均评分 ${k?.average_agent_score??0}`} tone="blue"/>
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-[1.5fr_1fr]">
      <Panel><PanelHeader title="近 30 天 AI 成本趋势" description="统一统计 Coding Agent、知识助手和模型网关产生的费用"/>
        <div className="flex h-64 items-end gap-1 px-5 pb-5 pt-8">{(data?.cost_trend??[]).map(item=><div key={item.date} className="group relative flex h-full flex-1 items-end"><div className="w-full rounded-t bg-blue-500/80 transition hover:bg-blue-600" style={{height:`${Math.max(3,item.cost_usd/maxCost*100)}%`}}/><div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-slate-950 px-2 py-1 text-xs text-white group-hover:block">{item.date} · ${item.cost_usd.toFixed(4)}</div></div>)}</div>
      </Panel>
      <Panel><PanelHeader title="Agent 运行状态" description="执行、审批与阻断状态分布"/><div className="p-5"><BarList items={(data?.agent_status??[]).map(item=>({label:statusNames[item.status]??item.status,value:item.count}))}/>{!data?.agent_status.some(item=>item.count)&&<EmptyState title="暂无 Agent 任务" description="生成演示任务或接入 Codex、Claude Code、Cursor 行为事件后显示。" action={<Link href="/agent-runs" className="text-sm text-blue-600">进入 Agent 任务中心</Link>}/>}</div></Panel>
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-2">
      <Panel><PanelHeader title="AI Coding 风险分布" description="密钥、权限、敏感文件、破坏性命令和测试风险" action={<Link href="/agent-runs" className="inline-flex items-center gap-1 text-sm text-blue-600">查看任务<ArrowRight className="h-4 w-4"/></Link>}/><div className="p-5">{data?.risk_distribution.length?<BarList items={data.risk_distribution.map(item=>({label:item.label,value:item.count}))}/>:<EmptyState title="暂未发现 Agent 风险" description="Agent Action 接入后，风险引擎会在这里汇总行为风险。"/>}</div></Panel>
      <Panel><PanelHeader title="模型使用分布" description="按 Provider/Model 汇总调用次数、Token 和成本" action={<Link href="/costs" className="inline-flex items-center gap-1 text-sm text-blue-600">成本明细<ArrowRight className="h-4 w-4"/></Link>}/><div className="p-5">{data?.model_distribution.length?<BarList items={data.model_distribution.slice(0,8).map(item=>({label:item.model,value:item.calls,display:`${item.calls} 次 · $${item.cost_usd.toFixed(2)}`}))}/>:<EmptyState title="暂无模型调用" description="接入 LLM Gateway 或使用企业知识助手后显示模型分布。"/>}</div></Panel>
    </div>
  </AppLayout>
}
