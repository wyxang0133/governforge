/**
 * AI 接口错误码映射
 *
 * 后端通过 X-Error-Code Header 传递结构化错误码，
 * 前端根据错误码显示对应的 UI 状态和操作。
 */

export interface ErrorMeta {
  /** HTTP 状态码 */
  httpStatus: number;
  /** 展示给用户的友好提示 */
  uiMessage: string;
  /** 建议用户采取的操作 */
  action: "retry" | "dismiss" | "countdown";
}

/** 6 个结构化错误码 → UI 映射 */
export const ERROR_CODE_MAP: Record<string, ErrorMeta> = {
  MODEL_UNAVAILABLE: {
    httpStatus: 503,
    uiMessage: "模型服务异常，正在重试...",
    action: "retry",
  },
  GUARDRAIL_BLOCKED: {
    httpStatus: 400,
    uiMessage: "您的输入不符合安全规范",
    action: "dismiss",
  },
  RAG_NO_RESULT: {
    httpStatus: 200,
    uiMessage: "未找到相关文档，请换个问题试试",
    action: "dismiss",
  },
  RATE_LIMIT_EXCEEDED: {
    httpStatus: 429,
    uiMessage: "请求过于频繁，请稍后再试",
    action: "countdown",
  },
  CONTEXT_WINDOW_EXCEEDED: {
    httpStatus: 400,
    uiMessage: "输入内容过长，请删减后重试",
    action: "dismiss",
  },
  INTERNAL_TIMEOUT: {
    httpStatus: 504,
    uiMessage: "响应超时，请重新提问",
    action: "retry",
  },
};

/**
 * 从响应头解析错误码
 */
export function parseErrorCode(headers: Headers): string | null {
  return headers.get("X-Error-Code");
}

/**
 * 从响应头解析 Trace ID
 */
export function parseTraceId(headers: Headers): string | null {
  return headers.get("X-Trace-Id");
}
