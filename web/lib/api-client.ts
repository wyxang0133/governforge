export interface ApiResponseMeta { traceId:string|null; }

export async function apiFetch<T>(url:string, options:RequestInit={}):Promise<{data:T|null;meta:ApiResponseMeta;error:Error|null}>{
  const headers=new Headers(options.headers);
  if(!(options.body instanceof FormData)) headers.set("Content-Type","application/json");
  headers.set("X-Trace-ID",crypto.randomUUID());
  // The backend derives workspace scope from the signed session. A browser-controlled
  // tenant header would be redundant and made non-default workspaces unusable.
  let response=await fetch(url,{...options,headers,credentials:"same-origin"});
  if(response.status===401&&!url.includes("/api/auth/")){
    const refreshed=await fetch("/api/auth/refresh",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin"});
    if(refreshed.ok) response=await fetch(url,{...options,headers,credentials:"same-origin"});
  }
  const traceId=response.headers.get("X-Trace-ID");
  let payload:any=null;
  if((response.headers.get("content-type")??"").includes("application/json")) payload=await response.json();
  if(!response.ok){const error=new Error(payload?.detail??`请求失败 (${response.status})`);return {data:null,meta:{traceId},error};}
  return {data:payload as T,meta:{traceId},error:null};
}
