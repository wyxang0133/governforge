"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, BookOpen, ChevronRight, CircleHelp, Menu, Search, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";

const destinations = [
  ["运营总览", "/"], ["Agent 运行", "/agent-runs"], ["变更控制", "/pull-requests"], ["人工审批", "/approvals"],
  ["策略中心", "/policies"], ["效能洞察", "/governance"], ["企业知识助手", "/knowledge"], ["模型与成本", "/costs"],
  ["代码资产", "/repositories"], ["连接器", "/integrations"], ["审计追踪", "/audit"], ["系统设置", "/settings"],
] as const;

type Dashboard = { kpis?: { risk_pull_requests?: number; pending_approvals?: number; high_risk_agent_runs?: number } };

export function AppLayout({ children, title, subtitle }: { children: React.ReactNode; title: string; subtitle?: string }) {
  const [open, setOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard>();
  const searchInput = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "same-origin" }).then((response) => { if (!response.ok) router.replace("/login"); });
    apiFetch<Dashboard>("/api/dashboard/overview").then((response) => setDashboard(response.data ?? undefined));
  }, [router]);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setSearchOpen(true); }
      if (event.key === "Escape") { setSearchOpen(false); setHelpOpen(false); setNotificationsOpen(false); }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  useEffect(() => { if (searchOpen) setTimeout(() => searchInput.current?.focus(), 0); }, [searchOpen]);
  const results = useMemo(() => destinations.filter(([label]) => !query || label.toLowerCase().includes(query.toLowerCase())), [query]);
  const kpis = dashboard?.kpis;
  const alerts = [
    { label: "风险变更待处理", value: kpis?.risk_pull_requests ?? 0, href: "/pull-requests", tone: "text-red-600 bg-red-50" },
    { label: "人工审批待处理", value: kpis?.pending_approvals ?? 0, href: "/approvals", tone: "text-amber-600 bg-amber-50" },
    { label: "高风险 Agent 任务", value: kpis?.high_risk_agent_runs ?? 0, href: "/agent-runs", tone: "text-orange-600 bg-orange-50" },
  ];
  const alertCount = alerts.reduce((sum, item) => sum + item.value, 0);
  function navigate(href: string) { setSearchOpen(false); setQuery(""); router.push(href); }

  return <div className="flex min-h-screen bg-[#f4f6fa]">
    <div className="sticky top-0 hidden h-screen lg:flex"><Sidebar /></div>
    {open && <div className="fixed inset-0 z-50 flex lg:hidden"><Sidebar /><button aria-label="关闭导航" className="flex-1 bg-slate-950/60 backdrop-blur-sm" onClick={() => setOpen(false)} /></div>}
    <div className="min-w-0 flex-1">
      <header className="sticky top-0 z-30 flex h-16 items-center border-b border-slate-200/80 bg-white/90 px-5 backdrop-blur-xl lg:px-7">
        <button aria-label="打开导航" className="mr-4 lg:hidden" onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button>
        <div className="hidden items-center gap-2 text-xs text-slate-500 md:flex"><ShieldCheck className="h-4 w-4 text-emerald-600" /><span>治理控制面</span><span className="text-slate-300">/</span><span className="font-medium text-slate-800">{title}</span></div>
        <div className="relative ml-auto flex items-center gap-1.5">
          <button onClick={() => setSearchOpen(true)} className="hidden h-9 w-64 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs text-slate-400 hover:border-slate-300 xl:flex"><Search className="h-3.5 w-3.5" /><span>搜索功能与页面</span><kbd className="ml-auto rounded border bg-white px-1.5 py-0.5 text-[10px]">Ctrl K</kbd></button>
          <button aria-label="帮助" onClick={() => { setHelpOpen(!helpOpen); setNotificationsOpen(false); }} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><CircleHelp className="h-4 w-4" /></button>
          <button aria-label="通知" onClick={() => { setNotificationsOpen(!notificationsOpen); setHelpOpen(false); }} className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100"><Bell className="h-4 w-4" />{alertCount > 0 && <span className="absolute right-1 top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-red-500 px-1 text-[8px] font-semibold text-white">{alertCount > 9 ? "9+" : alertCount}</span>}</button>
          {helpOpen && <div className="absolute right-9 top-11 w-72 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"><div className="border-b border-slate-100 px-4 py-3"><div className="text-xs font-semibold">帮助与文档</div><p className="mt-1 text-[10px] text-slate-400">快速进入配置和排障入口</p></div><div className="p-2"><Link href="/integrations" onClick={() => setHelpOpen(false)} className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-slate-50"><BookOpen className="h-4 w-4 text-blue-600" /><div className="flex-1"><div className="text-xs font-medium">接入指南</div><div className="mt-0.5 text-[10px] text-slate-400">GitHub App、Agent 与模型网关</div></div><ChevronRight className="h-3.5 w-3.5 text-slate-300" /></Link><Link href="/audit" onClick={() => setHelpOpen(false)} className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-slate-50"><ShieldAlert className="h-4 w-4 text-amber-600" /><div className="flex-1"><div className="text-xs font-medium">链路排障</div><div className="mt-0.5 text-[10px] text-slate-400">通过 Trace ID 检查事件处理</div></div><ChevronRight className="h-3.5 w-3.5 text-slate-300" /></Link></div></div>}
          {notificationsOpen && <div className="absolute right-0 top-11 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"><div className="flex items-center justify-between border-b border-slate-100 px-4 py-3"><div className="text-xs font-semibold">治理待办</div><span className="text-[10px] text-slate-400">实时汇总</span></div><div className="divide-y divide-slate-100">{alerts.map((item) => <Link key={item.label} href={item.href} onClick={() => setNotificationsOpen(false)} className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50"><span className={`flex h-8 w-8 items-center justify-center rounded-lg text-xs font-semibold ${item.tone}`}>{item.value}</span><span className="flex-1 text-xs text-slate-700">{item.label}</span><ChevronRight className="h-3.5 w-3.5 text-slate-300" /></Link>)}</div>{alertCount === 0 && <div className="px-4 py-5 text-center text-xs text-slate-400">当前没有待处理治理事项</div>}</div>}
        </div>
      </header>
      <main className="mx-auto max-w-[1560px] p-5 lg:p-7 xl:p-8"><div className="mb-6 flex items-end justify-between gap-4"><div><h1 className="text-[26px] font-semibold tracking-[-0.02em] text-slate-950">{title}</h1>{subtitle && <p className="mt-1.5 max-w-4xl text-[13px] leading-5 text-slate-500">{subtitle}</p>}</div><div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[11px] font-medium text-emerald-700 sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> 实时数据</div></div>{children}</main>
    </div>
    {searchOpen && <div className="fixed inset-0 z-[80] flex justify-center bg-slate-950/45 px-4 pt-[12vh] backdrop-blur-sm" onMouseDown={() => setSearchOpen(false)}><div className="h-fit w-full max-w-xl overflow-hidden rounded-2xl border border-white/30 bg-white shadow-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-center gap-3 border-b border-slate-100 px-4"><Search className="h-4 w-4 text-slate-400" /><input ref={searchInput} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && results[0]) navigate(results[0][1]); }} placeholder="输入功能名称，例如：审批、成本、审计" className="h-14 flex-1 text-sm outline-none" /><kbd className="rounded border bg-slate-50 px-2 py-1 text-[10px] text-slate-400">ESC</kbd></div><div className="max-h-80 overflow-y-auto p-2">{results.map(([label, href]) => <button key={href} onClick={() => navigate(href)} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-slate-50"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-blue-600"><ChevronRight className="h-3.5 w-3.5" /></span><span className="text-xs font-medium text-slate-700">{label}</span><span className="ml-auto font-mono text-[10px] text-slate-300">{href}</span></button>)}{!results.length && <div className="px-4 py-10 text-center text-xs text-slate-400">没有匹配的功能</div>}</div></div></div>}
  </div>;
}
