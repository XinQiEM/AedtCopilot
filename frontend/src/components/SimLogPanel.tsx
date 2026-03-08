"use client";

import { useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface SimLogPanelProps {
  logs: string[];
  onClear: () => void;
}

export function SimLogPanel({ logs, onClear }: SimLogPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever a new log entry arrives
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="flex flex-col border-t-2 border-border bg-muted/5" style={{ height: "160px" }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/60 bg-muted/10 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-muted-foreground tracking-wide uppercase">
            HFSS 仿真进度
          </span>
          {logs.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono">
              {logs.length} 条
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5"
          onClick={onClear}
          title="清空日志"
          disabled={logs.length === 0}
        >
          <Trash2 size={11} />
        </Button>
      </div>

      {/* Log body */}
      <div className="flex-1 overflow-y-auto overflow-x-auto px-3 py-2 font-mono text-[11px] leading-5">
        {logs.length === 0 ? (
          <p className="text-muted-foreground/50 select-none text-center mt-4 text-xs">
            运行仿真后进度将在此显示
          </p>
        ) : (
          <>
            {logs.map((line, i) => {
              const isSuccess = line.includes("✓");
              const isError = line.includes("✗");
              const isStart = line.includes("▶");
              const color = isSuccess
                ? "text-green-400"
                : isError
                ? "text-red-400"
                : isStart
                ? "text-sky-300"
                : "text-muted-foreground";
              return (
                <div key={i} className={`whitespace-pre ${color}`}>
                  {line}
                </div>
              );
            })}
            <div ref={bottomRef} />
          </>
        )}
      </div>
    </div>
  );
}
