"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BadgeDollarSign,
  BellRing,
  BookOpenCheck,
  Bot,
  Boxes,
  ChevronDown,
  CircleUserRound,
  GitBranch,
  GitPullRequest,
  LayoutDashboard,
  LogOut,
  Plug,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

const groups = [
  {
    label: "运营工作台",
    items: [
      { href: "/", label: "运营总览", icon: LayoutDashboard },
      { href: "/agent-runs", label: "Agent 运行", icon: Boxes },
    ],
  },
  {
    label: "交付治理",
    items: [
      { href: "/pull-requests", label: "变更控制", icon: GitPullRequest },
      { href: "/approvals", label: "人工审批", icon: BookOpenCheck },
      { href: "/policies", label: "策略中心", icon: ShieldCheck },
      { href: "/governance", label: "效能洞察", icon: Activity },
    ],
  },
  {
    label: "平台能力",
    items: [
      { href: "/knowledge", label: "企业知识助手", icon: Bot },
      { href: "/costs", label: "模型与成本", icon: BadgeDollarSign },
      { href: "/repositories", label: "代码资产", icon: GitBranch },
      { href: "/integrations", label: "连接器", icon: Plug },
    ],
  },
  {
    label: "安全与管理",
    items: [
      { href: "/audit", label: "审计追踪", icon: BellRing },
      { href: "/settings", label: "系统设置", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar-shell flex h-screen w-[272px] flex-col text-slate-300">
      <div className="px-5 pb-4 pt-5">
        <div className="flex items-center gap-3">
          <div className="brand-mark">DP</div>
          <div>
            <div className="text-[17px] font-semibold tracking-tight text-white">DevPilot</div>
            <div className="mt-0.5 text-[11px] font-medium tracking-wide text-slate-500">AI CONTROL PLANE</div>
          </div>
        </div>
      </div>

      <button className="mx-3 mb-3 flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.055] px-3 py-2.5 text-left">
        <span className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/20 text-xs font-semibold text-blue-300">AI</span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-slate-200">AI Platform</span>
            <span className="block text-[10px] text-emerald-400">● 生产控制面在线</span>
          </span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
      </button>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4 pt-2">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">{group.label}</div>
            <div className="space-y-0.5">
              {group.items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition",
                      active ? "bg-white/[0.1] text-white" : "text-slate-400 hover:bg-white/[0.055] hover:text-slate-100",
                    )}
                  >
                    {active && <span className="absolute -left-3 h-5 w-0.5 rounded-r bg-blue-400" />}
                    <Icon className={cn("h-4 w-4", active ? "text-blue-400" : "text-slate-500 group-hover:text-slate-300")} />
                    <span>{label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-white/[0.07] p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800"><CircleUserRound className="h-4 w-4" /></div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium text-slate-200">demo1784260019</div>
            <div className="text-[10px] text-slate-500">平台管理员</div>
          </div>
          <button
            aria-label="退出登录"
            onClick={async () => {
              await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
              location.href = "/login";
            }}
            className="rounded-lg p-2 text-slate-500 hover:bg-white/[0.06] hover:text-white"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
