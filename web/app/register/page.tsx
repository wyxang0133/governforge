"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";

export default function Page() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = await apiFetch("/api/auth/register", {method: "POST", body: JSON.stringify({username, password, tenant_id: "ai_platform"})});
    if (result.error) { setError(result.error.message); return; }
    router.push("/");
  }
  return <main className="grid min-h-screen place-items-center bg-slate-950 p-5"><form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-7"><h1 className="text-2xl font-semibold">创建演示账号</h1>{error&&<div className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>}<label className="mt-5 block text-sm">用户名<input minLength={3} value={username} onChange={e=>setUsername(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" required/></label><label className="mt-4 block text-sm">密码<input type="password" minLength={8} value={password} onChange={e=>setPassword(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" required/></label><button className="mt-6 w-full rounded-lg bg-blue-600 py-2.5 text-white">创建并进入</button><p className="mt-4 text-center text-sm"><Link href="/login" className="text-blue-600">返回登录</Link></p></form></main>;
}
