"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatMessage,
  ChartStreamEvent,
  FarFieldData,
  HistoryItem,
  SParamData,
  SimStatusData,
  StreamEvent,
  ToolCall,
} from "@/lib/types";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";
const WS_URL = BACKEND.replace(/^http/, "ws") + "/ws/chat";

const LS_KEY = "aedtcopilot_chat_history";
const LS_MAX = 200; // keep last N messages to cap storage usage

let _msgId = 0;
function nextId() {
  return String(++_msgId);
}

/** Read persisted messages from localStorage (SSR-safe). */
function loadPersistedMessages(): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    const parsed: ChatMessage[] = JSON.parse(raw);
    // Strip any in-progress streaming state from a previous session
    return parsed.map((m) => ({ ...m, streaming: false }));
  } catch {
    return [];
  }
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadPersistedMessages);
  const [connected, setConnected] = useState(false);
  const [sending, setSending] = useState(false);

  // ── Chart / sim state exposed to consumers ──────────────────────────────
  const [sparamData, setSparamData] = useState<SParamData | null>(null);
  const [farFieldData, setFarFieldData] = useState<FarFieldData | null>(null);
  const [simStatus, setSimStatus] = useState<SimStatusData | null>(null);
  const [simLogs, setSimLogs] = useState<string[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentReplyIdRef = useRef<string | null>(null);
  const inRunSimRef = useRef(false);

  // ── Persist messages to localStorage (skip while a message is streaming) ──
  useEffect(() => {
    const hasStreaming = messages.some((m) => m.streaming);
    if (hasStreaming) return;
    try {
      if (messages.length === 0) {
        localStorage.removeItem(LS_KEY);
      } else {
        const toSave = messages.slice(-LS_MAX);
        localStorage.setItem(LS_KEY, JSON.stringify(toSave));
      }
    } catch {
      // Quota exceeded or private-browsing restriction — silently ignore
    }
  }, [messages]);

  // ── helpers ──────────────────────────────────────────────────────────────

  const appendChunk = useCallback((id: string, chunk: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + chunk } : m))
    );
  }, []);

  const patchMessage = useCallback((id: string, patch: Partial<ChatMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...patch } : m))
    );
  }, []);

  /** Append a ToolCall placeholder to the current reply message. */
  const appendToolCall = useCallback((id: string, tc: ToolCall) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] } : m
      )
    );
  }, []);

  /** Patch the last ToolCall in the current reply message with ok/message. */
  const patchLastToolCall = useCallback(
    (id: string, patch: Pick<ToolCall, "ok" | "message">) => {
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== id || !m.toolCalls?.length) return m;
          const updated = [...m.toolCalls];
          updated[updated.length - 1] = { ...updated[updated.length - 1], ...patch };
          return { ...m, toolCalls: updated };
        })
      );
    },
    []
  );

  // ── WebSocket lifecycle ───────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (ev) => {
      let event: StreamEvent;
      try {
        event = JSON.parse(ev.data as string) as StreamEvent;
      } catch {
        return;
      }

      const replyId = currentReplyIdRef.current;
      if (!replyId) return;

      switch (event.type) {
        case "intent":
          patchMessage(replyId, { intent: event.content });
          break;

        case "rag":
          if (event.content) patchMessage(replyId, { ragHint: event.content.slice(0, 80) });
          break;

        case "token":
          appendChunk(replyId, event.content);
          break;

        case "tool_call":
          appendToolCall(replyId, { tool: event.tool, params: event.params });
          if (event.tool === "run_simulation") {
            inRunSimRef.current = true;
            setSimLogs((prev) => [
              ...prev,
              `[${new Date().toLocaleTimeString()}] ▶ 开始运行仿真...`,
            ]);
          }
          break;

        case "tool_result":
          patchLastToolCall(replyId, { ok: event.ok, message: event.message });
          if (inRunSimRef.current) {
            inRunSimRef.current = false;
            setSimLogs((prev) => [
              ...prev,
              `[${new Date().toLocaleTimeString()}] ${
                event.ok ? `✓ ${event.message}` : `✗ ${event.message}`
              }`,
            ]);
          }
          break;

        case "chart": {
          const ce = event as ChartStreamEvent;
          if (ce.chart_type === "s_params") {
            setSparamData(ce.plotly_json as SParamData);
          } else if (ce.chart_type === "far_field") {
            setFarFieldData(ce.plotly_json as FarFieldData);
          }
          break;
        }

        case "sim_status": {
          const s = event;
          setSimStatus({
            pass: s.pass,
            delta_s: s.delta_s,
            max_passes: s.max_passes,
            converged: s.converged,
          });
          setSimLogs((prev) => [
            ...prev,
            `[${new Date().toLocaleTimeString()}]   Pass ${s.pass}/${s.max_passes}  ΔS = ${
              s.delta_s.toFixed(4)
            }${s.converged ? "  ✓ 已收敛" : ""}`,
          ]);
          break;
        }

        case "done":
          patchMessage(replyId, { streaming: false });
          currentReplyIdRef.current = null;
          setSending(false);
          break;

        case "error":
          patchMessage(replyId, {
            content: `⚠️ ${event.content}`,
            streaming: false,
          });
          currentReplyIdRef.current = null;
          setSending(false);
          break;
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // ── send ─────────────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    (text: string) => {
      if (
        !text.trim() ||
        sending ||
        !wsRef.current ||
        wsRef.current.readyState !== WebSocket.OPEN
      )
        return;

      const history: HistoryItem[] = messages
        .filter((m) => m.role !== "system" && !m.streaming)
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content: text,
        ts: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);

      const replyId = nextId();
      currentReplyIdRef.current = replyId;
      const replyMsg: ChatMessage = {
        id: replyId,
        role: "assistant",
        content: "",
        streaming: true,
        ts: Date.now(),
      };
      setMessages((prev) => [...prev, replyMsg]);

      setSending(true);

      wsRef.current.send(JSON.stringify({ message: text, history }));
    },
    [messages, sending]
  );

  const clearMessages = useCallback(() => {
    // Reset all chat state synchronously so the UI clears immediately
    setMessages([]);
    setSending(false);
    currentReplyIdRef.current = null;
    setSparamData(null);
    setFarFieldData(null);
    setSimStatus(null);
    setSimLogs([]);
    inRunSimRef.current = false;
    try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ }
  }, []);

  return {
    messages,
    connected,
    sending,
    sendMessage,
    clearMessages,
    sparamData,
    farFieldData,
    simStatus,
    simLogs,
    clearSimLogs: () => setSimLogs([]),
  };
}
