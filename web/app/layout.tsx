import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevPilot · AI Governance Platform",
  description: "企业 AI Coding 治理、知识助手与交付门禁平台",
};

export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="zh-CN"><body>{children}</body></html>;
}
