import { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={cn("enterprise-panel", className)}>{children}</section>;
}

export function PanelHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4"><div><h2 className="text-[15px] font-semibold text-slate-950">{title}</h2>{description && <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>}</div>{action}</div>;
}

export function MetricCard({ label, value, description, tone = "blue", trend }: { label: string; value: string | number; description?: string; tone?: "blue" | "red" | "amber" | "emerald"; trend?: number }) {
  const accents = { blue: "bg-blue-500", red: "bg-red-500", amber: "bg-amber-500", emerald: "bg-emerald-500" };
  return <Panel className="relative overflow-hidden p-5"><span className={cn("absolute left-0 top-5 h-8 w-[3px] rounded-r", accents[tone])} /><div className="text-xs font-medium text-slate-500">{label}</div><div className="mt-2 flex items-end justify-between gap-3"><div className="text-[30px] font-semibold leading-none tracking-[-0.035em] text-slate-950">{value}</div>{trend !== undefined && <span className={cn("flex items-center gap-0.5 text-[11px] font-medium", trend >= 0 ? "text-emerald-600" : "text-red-600")}>{trend >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}{Math.abs(trend)}%</span>}</div>{description && <p className="mt-3 text-[11px] leading-4 text-slate-400">{description}</p>}</Panel>;
}

export function StatusBadge({ value }: { value: string }) {
  const map: Record<string, string> = { completed: "bg-emerald-50 text-emerald-700 ring-emerald-200", allow: "bg-emerald-50 text-emerald-700 ring-emerald-200", approved: "bg-emerald-50 text-emerald-700 ring-emerald-200", active: "bg-emerald-50 text-emerald-700 ring-emerald-200", open: "bg-blue-50 text-blue-700 ring-blue-200", running: "bg-blue-50 text-blue-700 ring-blue-200", pending: "bg-amber-50 text-amber-700 ring-amber-200", waiting_approval: "bg-amber-50 text-amber-700 ring-amber-200", review: "bg-amber-50 text-amber-700 ring-amber-200", high: "bg-orange-50 text-orange-700 ring-orange-200", critical: "bg-red-50 text-red-700 ring-red-200", blocked: "bg-red-50 text-red-700 ring-red-200", block: "bg-red-50 text-red-700 ring-red-200", rejected: "bg-red-50 text-red-700 ring-red-200", failed: "bg-red-50 text-red-700 ring-red-200", low: "bg-slate-100 text-slate-600 ring-slate-200", medium: "bg-yellow-50 text-yellow-700 ring-yellow-200" };
  const labels: Record<string, string> = { completed: "已完成", allow: "通过", approved: "已批准", active: "已连接", open: "开放", running: "执行中", pending: "待处理", waiting_approval: "等待审批", review: "需复核", high: "高风险", critical: "严重风险", blocked: "已阻断", block: "阻断", rejected: "已拒绝", failed: "失败", low: "低风险", medium: "中风险" };
  return <span className={cn("inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset", map[value] ?? "bg-slate-100 text-slate-600 ring-slate-200")}>{labels[value] ?? value}</span>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) { return <div className="px-6 py-14 text-center"><div className="text-sm font-medium text-slate-700">{title}</div><p className="mx-auto mt-2 max-w-md text-xs leading-5 text-slate-500">{description}</p>{action && <div className="mt-5">{action}</div>}</div>; }

export function BarList({ items }: { items: { label: string; value: number; display?: string; tone?: "blue" | "red" | "amber" | "emerald" }[] }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  const tones = { blue: "bg-blue-500", red: "bg-red-500", amber: "bg-amber-500", emerald: "bg-emerald-500" };
  return <div className="space-y-4">{items.map((item) => <div key={item.label}><div className="mb-1.5 flex justify-between text-xs"><span className="text-slate-600">{item.label}</span><span className="font-medium text-slate-900">{item.display ?? item.value}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className={cn("h-full rounded-full", tones[item.tone ?? "blue"])} style={{ width: `${Math.max(3, item.value / max * 100)}%` }} /></div></div>)}</div>;
}

export function SegmentedBar({ items }: { items: { label: string; value: number; color: string }[] }) {
  const total = Math.max(1, items.reduce((sum, item) => sum + item.value, 0));
  return <><div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">{items.map((item) => <div key={item.label} className={item.color} style={{ width: `${item.value / total * 100}%` }} />)}</div><div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">{items.map((item) => <div key={item.label} className="flex items-center gap-2 text-[11px] text-slate-500"><span className={cn("h-2 w-2 rounded-full", item.color)} />{item.label}<b className="text-slate-800">{item.value}</b></div>)}</div></>;
}
