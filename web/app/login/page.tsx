"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";

export default function Page() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [authConfig, setAuthConfig] = useState({local_auth_enabled: true, self_registration_enabled: true, oidc_enabled: false});
  useEffect(() => { fetch("/api/auth/config").then(r => r.json()).then(setAuthConfig).catch(() => undefined); }, []);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = await apiFetch("/api/auth/login", {method: "POST", body: JSON.stringify({username, password})});
    if (result.error) { setError(result.error.message); return; }
    router.push("/");
  }
  return <main className="grid min-h-screen place-items-center bg-slate-950 p-5"><form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-7 shadow-xl"><h1 className="text-2xl font-semibold">登录 GovernForge</h1><p className="mt-1 text-sm text-slate-500">进入 AI Coding 治理控制台</p>{error&&<div className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>}{authConfig.oidc_enabled&&<a href="/api/auth/oidc/login" className="mt-5 block rounded-lg border border-blue-600 py-2.5 text-center text-blue-700">使用企业 SSO 登录</a>}{authConfig.local_auth_enabled&&<><label className="mt-5 block text-sm">用户名<input value={username} onChange={e=>setUsername(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" required/></label><label className="mt-4 block text-sm">密码<input type="password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5" required/></label><button className="mt-6 w-full rounded-lg bg-blue-600 py-2.5 text-white">登录</button></>}{authConfig.self_registration_enabled&&<p className="mt-4 text-center text-sm text-slate-500">没有账号？ <Link className="text-blue-600" href="/register">创建演示账号</Link></p>}</form></main>;
}
