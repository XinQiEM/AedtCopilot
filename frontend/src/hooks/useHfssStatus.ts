"use client";

import { useEffect, useState } from "react";
import type { HealthStatus } from "@/lib/types";

const DEFAULT: HealthStatus = {
  hfss_connected: false,
  llm_provider: "—",
  llm_model: "—",
  rag_ready: false,
  rag_chunks: 0,
};

export function useHfssStatus(intervalMs = 5000) {
  const [status, setStatus] = useState<HealthStatus>(DEFAULT);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch("/api/health");
        if (res.ok && !cancelled) {
          const data = await res.json();
          setStatus(data as HealthStatus);
        }
      } catch {
        // Silently ignore — UI shows "disconnected" via default state
      }
    };

    poll();
    const timer = setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return status;
}
