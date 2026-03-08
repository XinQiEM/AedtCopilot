"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import dynamic from "next/dynamic";
import type { FarFieldData, SimStatusData, SParamData } from "@/lib/types";

// Plotly is large — load it client-side only
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false, loading: () => <PlotPlaceholder text="加载图表中…" /> });

function PlotPlaceholder({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
      {text}
    </div>
  );
}

// ─── Empty state placeholder ──────────────────────────────────────────────────
function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
      <p className="text-3xl opacity-30">📊</p>
      <p className="text-sm">{label}</p>
      <p className="text-xs opacity-60">运行仿真后结果将在此显示</p>
    </div>
  );
}

// ─── S-param chart ────────────────────────────────────────────────────────────
function SParamChart({ data }: { data: SParamData | null }) {
  if (!data) return <EmptyChart label="S 参数 / VSWR" />;
  const traces = Object.entries(data.traces).map(([name, values]) => ({
    x: data.freq_ghz,
    y: values,
    mode: "lines" as const,
    name,
    line: { width: 2 },
  }));
  return (
    <Plot
      data={traces}
      layout={{
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#e4e4e7", size: 12 },
        xaxis: { title: { text: "Frequency (GHz)" }, gridcolor: "#3f3f46", color: "#a1a1aa" },
        yaxis: { title: { text: "dB" }, gridcolor: "#3f3f46", color: "#a1a1aa" },
        margin: { t: 20, b: 60, l: 55, r: 20 },
        legend: { x: 0.01, y: 0.98, font: { size: 10 } },
      }}
      config={{ displayModeBar: true, displaylogo: false }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

// ─── Smith chart ──────────────────────────────────────────────────────────────
function SmithChart() {
  return <EmptyChart label="Smith 圆图（需仿真数据）" />;
}

// ─── Far-field pattern ────────────────────────────────────────────────────────
function FarFieldChart({ data }: { data: FarFieldData | null }) {
  if (!data) return <EmptyChart label="远场方向图" />;
  return (
    <Plot
      data={[
        {
          type: "scatterpolar" as const,
          r: data.gain_dbi,
          theta: data.theta_deg,
          mode: "lines" as const,
          name: "GainTotal (dBi)",
          line: { color: "#6366f1", width: 2 },
        },
      ]}
      layout={{
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        polar: {
          bgcolor: "transparent",
          angularaxis: { color: "#a1a1aa" },
          radialaxis: { color: "#a1a1aa", gridcolor: "#3f3f46" },
        },
        font: { color: "#e4e4e7", size: 12 },
        margin: { t: 20, b: 20, l: 20, r: 20 },
      }}
      config={{ displayModeBar: true, displaylogo: false }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}

// ─── Simulation progress ──────────────────────────────────────────────────────
function SimProgressBar({ sim }: { sim: SimStatusData | null }) {
  if (!sim) return null;
  const pct = Math.round((sim.pass / sim.max_passes) * 100);
  const color = sim.converged ? "bg-green-500" : "bg-amber-500";
  return (
    <div className="px-4 py-2 border-t-2 border-border bg-muted/10">
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>
          Pass {sim.pass}/{sim.max_passes}
        </span>
        <div className="flex-1 bg-muted/60 rounded-full h-1.5">
          <div className={`${color} h-1.5 rounded-full transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span>ΔS = {sim.delta_s.toFixed(4)}</span>
        {sim.converged && <span className="text-green-400 font-medium">✓ 已收敛</span>}
      </div>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export interface ResultPanelProps {
  sparamData: SParamData | null;
  farFieldData: FarFieldData | null;
  simStatus: SimStatusData | null;
}

export function ResultPanel({ sparamData, farFieldData, simStatus }: ResultPanelProps) {
  return (
    <div className="flex flex-col h-full bg-background">
      <Tabs defaultValue="sparam" className="flex flex-col h-full">
        {/* Tab bar */}
        <div className="px-3 pt-2 border-b-2 border-border bg-muted/10">
          <TabsList className="h-8 bg-transparent p-0 gap-1">
            {[
              { value: "sparam", label: "S 参数" },
              { value: "smith", label: "Smith 圆图" },
              { value: "farfield", label: "方向图" },
            ].map(({ value, label }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="h-7 text-xs px-3 data-[state=active]:bg-muted"
              >
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        {/* Chart areas */}
        <div className="flex-1 overflow-hidden">
          <TabsContent value="sparam" className="h-full m-0 p-3">
            <SParamChart data={sparamData} />
          </TabsContent>
          <TabsContent value="smith" className="h-full m-0 p-3">
            <SmithChart />
          </TabsContent>
          <TabsContent value="farfield" className="h-full m-0 p-3">
            <FarFieldChart data={farFieldData} />
          </TabsContent>
        </div>

        {/* Simulation progress */}
        <SimProgressBar sim={simStatus} />
      </Tabs>
    </div>
  );
}
