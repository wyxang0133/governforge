"use client";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Bot, Database, FileText, Loader2, Plus, Send, Sparkles, ThumbsDown, ThumbsUp, Upload, UserRoundCheck } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { apiFetch } from "@/lib/api-client";

type Article = { id:string; title:string; category:string; tags:string[]; source_uri?:string|null; chunk_count:number; updated_at:string };
type Citation = { article_id:string; title:string; category:string; score:number; snippet:string };
type ChatResult = { conversation_id:string; message_id:string; answer:string; category:string; confidence:number; citations:Citation[]; provider:string; model:string; cost_usd:number };
type Message = { role:"user"|"assistant"; content:string; messageId?:string; category?:string; confidence?:number; citations?:Citation[]; model?:string; feedback?:string };

const categoryLabels:Record<string,string> = {
  general:"通用",
  hr:"人力",
  risk:"风控合规",
  finance:"财务成本",
  engineering:"研发运维",
  customer:"客户服务",
};

export default function KnowledgePage(){
  const [articles,setArticles]=useState<Article[]>([]);
  const [messages,setMessages]=useState<Message[]>([]);
  const [conversationId,setConversationId]=useState<string>();
  const [question,setQuestion]=useState("AI 编码工具可以修改认证和数据库迁移吗？");
  const [busy,setBusy]=useState(false);
  const [articleBusy,setArticleBusy]=useState(false);
  const [form,setForm]=useState({title:"",category:"risk",tags:"",content:""});
  const [error,setError]=useState<string>();
  const [notice,setNotice]=useState<string>();
  const [uploadFile,setUploadFile]=useState<File>();
  const [analytics,setAnalytics]=useState<any>();
  const grouped=useMemo(()=>articles.reduce<Record<string,Article[]>>((acc,item)=>{(acc[item.category]??=[]).push(item);return acc;},{}),[articles]);

  async function loadArticles(){
    const response=await apiFetch<Article[]>("/api/knowledge/articles");
    if(response.error)setError(response.error.message); else setArticles(response.data??[]);
  }

  async function loadAnalytics(){const response=await apiFetch("/api/knowledge/analytics");if(!response.error)setAnalytics(response.data)}

  useEffect(()=>{loadArticles();loadAnalytics()},[]);

  async function seed(){
    setArticleBusy(true); setError(undefined);
    const response=await apiFetch<{created:number}>("/api/knowledge/seed",{method:"POST",body:JSON.stringify({})});
    if(response.error)setError(response.error.message);
    await loadArticles();
    await loadAnalytics();
    setArticleBusy(false);
  }

  async function uploadDocument(){
    if(!uploadFile)return;
    setArticleBusy(true);setError(undefined);
    const body=new FormData();body.set("file",uploadFile);body.set("category",form.category);body.set("tags",form.tags);
    const response=await apiFetch("/api/knowledge/documents",{method:"POST",body});
    if(response.error)setError(response.error.message);else setUploadFile(undefined);
    await loadArticles();await loadAnalytics();setArticleBusy(false);
  }

  async function createArticle(event:FormEvent){
    event.preventDefault(); setArticleBusy(true); setError(undefined);
    const response=await apiFetch("/api/knowledge/articles",{method:"POST",body:JSON.stringify({
      title:form.title,
      category:form.category,
      tags:form.tags.split(",").map(item=>item.trim()).filter(Boolean),
      content:form.content,
    })});
    if(response.error)setError(response.error.message); else setForm({title:"",category:"risk",tags:"",content:""});
    await loadArticles();
    setArticleBusy(false);
  }

  async function ask(event:FormEvent){
    event.preventDefault();
    const text=question.trim();
    if(!text)return;
    setBusy(true); setError(undefined); setQuestion("");
    setMessages(prev=>[...prev,{role:"user",content:text}]);
    const response=await apiFetch<ChatResult>("/api/knowledge/chat",{method:"POST",body:JSON.stringify({message:text,conversation_id:conversationId})});
    if(response.error){
      setError(response.error.message);
    }else if(response.data){
      setConversationId(response.data.conversation_id);
      setMessages(prev=>[...prev,{role:"assistant",messageId:response.data!.message_id,content:response.data!.answer,category:response.data!.category,confidence:response.data!.confidence,citations:response.data!.citations,model:response.data!.model}]);
    }
    setBusy(false);
  }

  async function feedback(messageId:string,index:number,rating:"helpful"|"unhelpful"){
    const response=await apiFetch("/api/knowledge/feedback",{method:"POST",body:JSON.stringify({message_id:messageId,rating})});
    if(response.error)setError(response.error.message);else setMessages(items=>items.map((item,i)=>i===index?{...item,feedback:rating}:item));
  }

  async function escalate(messageId?:string){
    if(!conversationId)return;
    const response=await apiFetch<any>("/api/knowledge/escalations",{method:"POST",body:JSON.stringify({conversation_id:conversationId,message_id:messageId,reason:"用户请求由业务专家复核当前知识回答"})});
    if(response.error)setError(response.error.message);else{setError(undefined);setNotice(`已转交 ${response.data.queue}，工单 ${response.data.id}`)}
  }

  return <AppLayout title="知识服务" subtitle="把制度、流程、FAQ 和专家经验沉淀成可检索、有引用、可反馈、可升级的企业知识 Agent。">
    <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
      <section className="space-y-5">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <div><h2 className="font-semibold text-slate-950">知识库</h2><p className="mt-1 text-sm text-slate-500">{analytics?`${analytics.articles} 篇 · ${analytics.chunks} 个检索分块`:"按业务域分类沉淀企业知识"}</p></div>
            <button onClick={seed} disabled={articleBusy} className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"><Database className="h-4 w-4"/>初始化</button>
          </div>
          <div className="mt-4 space-y-3">
            {Object.entries(grouped).map(([category,items])=><div key={category}>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">{categoryLabels[category]??category}</div>
              <div className="space-y-2">{items.map(item=><div key={item.id} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-start gap-2"><FileText className="mt-0.5 h-4 w-4 text-blue-600"/><div className="min-w-0"><div className="truncate text-sm font-medium text-slate-900">{item.title}</div><div className="mt-1 text-xs text-slate-500">{(item.tags??[]).join(" / ")||"无标签"} · {item.chunk_count} 块</div></div></div>
              </div>)}</div>
            </div>)}
            {!articles.length&&<div className="rounded-md border border-dashed border-slate-300 p-4 text-sm text-slate-500">还没有知识条目，先点初始化生成一组企业样例。</div>}
          </div>
        </div>
        <form onSubmit={createArticle} className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-slate-950">新增知识</h2>
          <div className="mt-4 space-y-3">
            <input value={form.title} onChange={e=>setForm({...form,title:e.target.value})} placeholder="标题，例如：资金类问题升级规则" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"/>
            <div className="grid grid-cols-2 gap-3">
              <select value={form.category} onChange={e=>setForm({...form,category:e.target.value})} className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500">
                {Object.entries(categoryLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}
              </select>
              <input value={form.tags} onChange={e=>setForm({...form,tags:e.target.value})} placeholder="标签，逗号分隔" className="rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"/>
            </div>
            <textarea value={form.content} onChange={e=>setForm({...form,content:e.target.value})} placeholder="输入制度、流程、FAQ 或专家经验" rows={5} className="w-full resize-none rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"/>
            <button disabled={articleBusy||!form.title||form.content.length<10} className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"><Plus className="h-4 w-4"/>保存知识</button>
          </div>
        </form>
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-slate-950">导入企业文档</h2><p className="mt-1 text-xs text-slate-500">支持 PDF、Markdown、UTF-8 文本，最大 5 MB；服务端自动解析和分块。</p>
          <input type="file" accept=".pdf,.md,.markdown,.txt" onChange={e=>setUploadFile(e.target.files?.[0])} className="mt-4 block w-full text-sm"/>
          <button onClick={uploadDocument} disabled={!uploadFile||articleBusy} className="mt-3 inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"><Upload className="h-4 w-4"/>上传并索引</button>
        </div>
      </section>
      <section className="flex min-h-[720px] flex-col rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3"><div className="rounded-md bg-blue-50 p-2 text-blue-600"><Bot className="h-5 w-5"/></div><div><h2 className="font-semibold text-slate-950">AI 业务助手</h2><p className="text-sm text-slate-500">先分类，再检索，再基于来源回答</p></div></div>
          <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-700"><Sparkles className="h-3.5 w-3.5"/>可审计</div>
        </div>
        {error&&<div className="mx-5 mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        {notice&&<div className="mx-5 mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</div>}
        <div className="flex-1 space-y-4 overflow-auto p-5">
          {!messages.length&&<div className="rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-500">试着问：“AI 编码工具可以修改认证和数据库迁移吗？”、“生产发布故障怎么处理？”、“AI 成本超预算怎么办？”</div>}
          {messages.map((message,index)=><div key={index} className={message.role==="user"?"ml-auto max-w-2xl rounded-lg bg-blue-600 px-4 py-3 text-sm text-white":"max-w-3xl rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800"}>
            <div className="whitespace-pre-wrap leading-6">{message.content}</div>
            {message.role==="assistant"&&<div className="mt-4 space-y-3">
              <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-white px-2.5 py-1 text-slate-600">分类：{categoryLabels[message.category??"general"]??message.category}</span><span className="rounded-full bg-white px-2.5 py-1 text-slate-600">置信度：{Math.round((message.confidence??0)*100)}%</span><span className="rounded-full bg-white px-2.5 py-1 text-slate-600">引擎：{message.model}</span></div>
              {!!message.citations?.length&&<div className="space-y-2">{message.citations.map(citation=><div key={citation.article_id} className="rounded-md bg-white p-3 text-xs text-slate-600"><div className="font-medium text-slate-900">{citation.title}</div><div className="mt-1">{citation.snippet}</div></div>)}</div>}
              {message.messageId&&<div className="flex gap-2 border-t border-slate-200 pt-3"><button onClick={()=>feedback(message.messageId!,index,"helpful")} className={`rounded p-1.5 ${message.feedback==="helpful"?"bg-emerald-100 text-emerald-700":"bg-white text-slate-500"}`} title="回答有帮助"><ThumbsUp className="h-4 w-4"/></button><button onClick={()=>feedback(message.messageId!,index,"unhelpful")} className={`rounded p-1.5 ${message.feedback==="unhelpful"?"bg-red-100 text-red-700":"bg-white text-slate-500"}`} title="回答无帮助"><ThumbsDown className="h-4 w-4"/></button><button onClick={()=>escalate(message.messageId)} className="inline-flex items-center gap-1.5 rounded bg-white px-2.5 py-1.5 text-xs text-slate-600"><UserRoundCheck className="h-4 w-4"/>转人工专家</button></div>}
            </div>}
          </div>)}
        </div>
        <form onSubmit={ask} className="flex gap-3 border-t border-slate-200 p-4">
          <input value={question} onChange={e=>setQuestion(e.target.value)} placeholder="输入企业制度、流程、风控、研发运维问题" className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"/>
          <button disabled={busy||!question.trim()} className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">{busy?<Loader2 className="h-4 w-4 animate-spin"/>:<Send className="h-4 w-4"/>}发送</button>
        </form>
      </section>
    </div>
  </AppLayout>;
}
