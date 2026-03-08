"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizonal, Trash2, Wifi, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import type { ChatMessage, ToolCall } from "@/lib/types";
import SyntaxHighlighter from "react-syntax-highlighter";
import { atomOneDark } from "react-syntax-highlighter/dist/esm/styles/hljs";

const INTENT_COLOR: Record<string, string> = {
  geometry: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  simulation: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  postprocess: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  array: "bg-green-500/20 text-green-300 border-green-500/30",
  general: "bg-zinc-500/20 text-zinc-300 border-zinc-500/30",
};

const TOOL_LABEL: Record<string, string> = {
  create_box: "创建长方体",
  create_cylinder: "创建圆柱体",
  create_sphere: "创建球体",
  subtract_objects: "布尔减运算",
  assign_material: "赋材料",
  list_objects: "列举对象",
  import_cad_file: "导入 CAD",
  assign_radiation_boundary: "辐射边界",
  assign_lumped_port: "集总端口",
  assign_plane_wave: "平面波激励",
  create_solution_setup: "新建 Setup",
  create_frequency_sweep: "频率扫描",
  run_simulation: "运行仿真",
  get_convergence_info: "收敛查询",
  get_s_parameters: "S 参数提取",
  get_vswr: "VSWR 提取",
  get_far_field: "远场方向图",
  compute_array_weights: "阵列权值",
  apply_array_excitation: "阵列激励",
};

// ─── Tool call/result bubble ──────────────────────────────────────────────────
function ToolCallBubble({ tc }: { tc: ToolCall }) {
  const label = TOOL_LABEL[tc.tool] ?? tc.tool;
  const pending = tc.ok === undefined;
  const statusColor = pending
    ? "text-amber-400"
    : tc.ok
    ? "text-green-400"
    : "text-red-400";
  const statusIcon = pending ? "⋯" : tc.ok ? "✓" : "✗";

  return (
    <div className="my-1 rounded-lg border border-border/40 bg-muted/30 px-3 py-1.5 text-xs font-mono">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">🔧</span>
        <span className="text-sky-300 font-semibold">{label}</span>
        <span className={`ml-auto font-bold ${statusColor}`}>{statusIcon}</span>
      </div>
      {tc.message && !pending && (
        <p className={`mt-0.5 whitespace-nowrap ${tc.ok ? "text-muted-foreground" : "text-red-300"}`}>
          {tc.message}
        </p>
      )}
    </div>
  );
}

// ─── Code / text content parser ───────────────────────────────────────────────
function parseContent(text: string) {
  const parts: { type: "text" | "code"; content: string; lang?: string }[] = [];
  const codeRe = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = codeRe.exec(text)) !== null) {
    if (m.index > lastIdx) parts.push({ type: "text", content: text.slice(lastIdx, m.index) });
    parts.push({ type: "code", lang: m[1] || "python", content: m[2] });
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) parts.push({ type: "text", content: text.slice(lastIdx) });
  return parts;
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const parts = parseContent(msg.content);

  return (
    <div className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      {/* Meta badges */}
      {!isUser && (msg.intent || msg.ragHint) && (
        <div className="flex gap-1 flex-wrap ml-1">
          {msg.intent && (
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full border font-mono ${
                INTENT_COLOR[msg.intent] ?? INTENT_COLOR.general
              }`}
            >
              {msg.intent}
            </span>
          )}
          {msg.ragHint && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border bg-teal-500/20 text-teal-300 border-teal-500/30 font-mono truncate max-w-[200px]">
              📚 RAG
            </span>
          )}
        </div>
      )}

      {/* Tool calls (assistant only, shown above the reply bubble) */}
      {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
        <div className="w-full max-w-[90%] ml-1">
          {msg.toolCalls.map((tc, i) => (
            <ToolCallBubble key={i} tc={tc} />
          ))}
        </div>
      )}

      {/* Main bubble */}
      {(msg.content || msg.streaming) && (
        <div
          className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed break-words ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted/50 text-foreground border border-border/40"
          }`}
        >
          {parts.map((p, i) =>
            p.type === "code" ? (
              <div key={i} className="my-1 rounded-lg overflow-x-auto text-xs">
                <SyntaxHighlighter
                  language={p.lang}
                  style={atomOneDark}
                  customStyle={{ margin: 0, borderRadius: "8px", padding: "10px" }}
                >
                  {p.content.trimEnd()}
                </SyntaxHighlighter>
              </div>
            ) : (
              <span key={i} style={{ whiteSpace: "pre-wrap" }}>
                {p.content}
              </span>
            )
          )}
          {msg.streaming && (
            <span className="inline-block w-1.5 h-3.5 bg-current ml-0.5 animate-pulse rounded-sm" />
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main export (props-based — state lives in page.tsx via useChat) ──────────
export interface ChatPanelProps {
  messages: ChatMessage[];
  connected: boolean;
  sending: boolean;
  sendMessage: (text: string) => void;
  clearMessages: () => void;
}

export function ChatPanel({
  messages,
  connected,
  sending,
  sendMessage,
  clearMessages,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b-2 border-border bg-muted/10">
        <span className="text-sm font-medium text-muted-foreground">对话</span>
        <div className="flex items-center gap-2">
          {connected ? (
            <Wifi size={14} className="text-green-400" />
          ) : (
            <WifiOff size={14} className="text-red-400 animate-pulse" />
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={clearMessages}
            title="清空对话"
          >
            <Trash2 size={13} />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-auto px-3 py-3">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground py-16 gap-2">
            <p className="text-2xl">⚡</p>
            <p className="text-sm font-medium">AedtCopilot</p>
            <p className="text-xs max-w-[200px]">
              用自然语言操控 HFSS 仿真，例如：
              "在原点创建一个 10×5×2mm 的 PEC 贴片"
            </p>
          </div>
        ) : (
          <div className="flex flex-col">
            {messages.map((msg, idx) => (
              <div key={msg.id}>
                {idx > 0 && (
                  <div className="my-2 flex items-center gap-2">
                    <Separator className="flex-1 opacity-25" />
                  </div>
                )}
                <MessageBubble msg={msg} />
              </div>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t-2 border-border" />

      {/* Input */}
      <div className="px-3 py-2.5 flex gap-2 items-end bg-muted/10">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入 HFSS 指令… (Enter 发送, Shift+Enter 换行)"
          rows={2}
          wrap="off"
          className="resize-none text-sm min-h-[60px] flex-1"
          style={{ overflowX: "auto", whiteSpace: "pre" }}
          disabled={sending || !connected}
        />
        <Button
          size="icon"
          className="h-[60px] w-10 shrink-0"
          onClick={handleSend}
          disabled={sending || !connected || !input.trim()}
        >
          <SendHorizonal size={16} />
        </Button>
      </div>
    </div>
  );
}
