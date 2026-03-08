"use client";

import { useHfssStatus } from "@/hooks/useHfssStatus";
import { LLMSettingsDrawer } from "@/components/LLMSettingsDrawer";
import { Badge } from "@/components/ui/badge";
import { Cpu, Database } from "lucide-react";

export function HfssStatusBar() {
  const status = useHfssStatus();

  return (
    <header className="flex items-center gap-3 px-4 py-2.5 border-b-2 border-border bg-muted/10 backdrop-blur shrink-0">
      {/* Brand */}
      <span className="font-semibold text-sm tracking-tight mr-1">
        ⚡ AedtCopilot
      </span>

      {/* HFSS connection */}
      <Badge
        variant="outline"
        className={`h-5 text-[10px] gap-1 font-mono ${
          status.hfss_connected
            ? "border-green-500/50 text-green-400"
            : "border-red-500/50 text-red-400"
        }`}
      >
        <Cpu size={10} />
        {status.hfss_connected ? `HFSS ${status.version ?? ""}` : "HFSS 未连接"}
      </Badge>

      {/* LLM info */}
      <Badge variant="outline" className="h-5 text-[10px] gap-1 font-mono border-blue-500/40 text-blue-400">
        🤖 {status.llm_model}
      </Badge>

      {/* RAG status */}
      <Badge
        variant="outline"
        className={`h-5 text-[10px] gap-1 font-mono ${
          status.rag_ready
            ? "border-teal-500/40 text-teal-400"
            : "border-zinc-500/30 text-zinc-500"
        }`}
      >
        <Database size={10} />
        {status.rag_ready ? `RAG ${status.rag_chunks}块` : "RAG 未就绪"}
      </Badge>

      {/* Spacer */}
      <div className="flex-1" />

      {/* LLM settings */}
      <LLMSettingsDrawer />
    </header>
  );
}
