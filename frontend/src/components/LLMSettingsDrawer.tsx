"use client";

import { useState } from "react";
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { LLMConfig } from "@/lib/types";

// ── Provider presets ───────────────────────────────────────────────────────────
interface Preset {
  base_url: string;
  model: string;
}
const PRESETS: Record<string, Preset> = {
  modelscope: { base_url: "https://api-inference.modelscope.cn/v1",            model: "Qwen/Qwen3-32B" },
  dashscope:  { base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  moonshot:   { base_url: "https://api.moonshot.cn/v1",                         model: "moonshot-v1-8k" },
  minimax:    { base_url: "https://api.minimaxi.com/v1",                         model: "MiniMax-Text-01" },
  deepseek:   { base_url: "https://api.deepseek.com/v1",                         model: "deepseek-chat" },
  zhipuai:    { base_url: "https://open.bigmodel.cn/api/paas/v4",               model: "glm-4-flash" },
  qianfan:    { base_url: "https://qianfan.baidubce.com/v2",                    model: "ernie-speed-128k" },
  ollama:     { base_url: "http://localhost:11434/v1",                           model: "qwen2.5:7b" },
};

const PROVIDERS = [
  // International
  { value: "openai",           label: "OpenAI (GPT-4o / GPT-4.1)" },
  { value: "azure_openai",     label: "Azure OpenAI" },
  { value: "anthropic",        label: "Anthropic Claude" },
  // Domestic (auto-fill base_url)
  { value: "modelscope",       label: "魔塔社区 ModelScope（免费额度）" },
  { value: "dashscope",        label: "通义千问 DashScope（阿里云）" },
  { value: "moonshot",         label: "Kimi（月之暗面）" },
  { value: "minimax",          label: "MiniMax（海螺 AI）" },
  { value: "deepseek",         label: "DeepSeek" },
  { value: "zhipuai",          label: "智谱 AI（glm-4-flash 永久免费）" },
  { value: "qianfan",          label: "百度千帆（文心系列）" },
  // Local / custom
  { value: "ollama",           label: "本地 Ollama / LM Studio" },
  { value: "openai_compatible",label: "自定义 OpenAI 兼容接口" },
];

/** Map UI provider value to backend provider string */
function resolveBackendProvider(v: string): LLMConfig["provider"] {
  if (["openai", "azure_openai", "anthropic"].includes(v)) return v as LLMConfig["provider"];
  return "openai_compatible";
}

// ── Component ─────────────────────────────────────────────────────────────────

export function LLMSettingsDrawer() {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("dashscope");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(PRESETS.dashscope.model);
  const [baseUrl, setBaseUrl] = useState(PRESETS.dashscope.base_url);
  const [azureEndpoint, setAzureEndpoint] = useState("");
  const [azureDeployment, setAzureDeployment] = useState("");
  const [azureApiVersion, setAzureApiVersion] = useState("2024-02-01");
  const [temperature, setTemperature] = useState("0.0");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleProviderChange = (v: string) => {
    setProvider(v);
    if (PRESETS[v]) {
      setBaseUrl(PRESETS[v].base_url);
      setModel(PRESETS[v].model);
    } else if (v === "openai") {
      setBaseUrl("");
      setModel("gpt-4o");
    } else if (v === "anthropic") {
      setBaseUrl("");
      setModel("claude-3-5-sonnet-20241022");
    }
    setTestResult(null);
  };

  const buildConfig = (): LLMConfig => ({
    provider: resolveBackendProvider(provider),
    api_key: apiKey,
    model,
    base_url: baseUrl || null,
    azure_endpoint: azureEndpoint || null,
    azure_deployment: azureDeployment || null,
    azure_api_version: azureApiVersion,
    temperature: parseFloat(temperature) || 0,
    max_tokens: parseInt(maxTokens, 10) || 4096,
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch("/api/llm/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildConfig()),
      });
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const t0 = Date.now();
      const res = await fetch("/api/llm/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildConfig()),
      });
      const data = await res.json();
      const latency = Date.now() - t0;
      setTestResult(data.ok ? `✓ ${latency}ms` : `✗ ${data.error}`);
    } catch (e) {
      setTestResult(`✗ ${String(e)}`);
    } finally {
      setTesting(false);
    }
  };

  const showBaseUrl = !!PRESETS[provider] || provider === "openai_compatible" || provider === "ollama";
  const showAzure = provider === "azure_openai";

  return (
    <Drawer open={open} onOpenChange={setOpen}>
      <DrawerTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
          <Settings size={13} />
          LLM 设置
        </Button>
      </DrawerTrigger>

      <DrawerContent className="max-h-[90vh]">
        <div className="mx-auto w-full max-w-md pb-6">
          <DrawerHeader>
            <DrawerTitle>LLM 接口配置</DrawerTitle>
          </DrawerHeader>

          <div className="space-y-3 px-4">
            {/* Provider */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">接口提供商</label>
              <Select value={provider} onValueChange={handleProviderChange}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p.value} value={p.value} className="text-sm">
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* API Key */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">API Key</label>
              <Input
                type="password"
                placeholder="sk-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="h-8 text-sm"
              />
            </div>

            {/* Model */}
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">模型名称</label>
              <Input
                placeholder="模型名称"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="h-8 text-sm"
              />
            </div>

            {/* Base URL */}
            {showBaseUrl && (
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Base URL</label>
                <Input
                  placeholder="https://..."
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="h-8 text-sm"
                />
              </div>
            )}

            {/* Azure-specific */}
            {showAzure && (
              <>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Azure Endpoint</label>
                  <Input
                    placeholder="https://xxx.openai.azure.com"
                    value={azureEndpoint}
                    onChange={(e) => setAzureEndpoint(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Deployment Name</label>
                  <Input
                    placeholder="gpt-4o-deploy"
                    value={azureDeployment}
                    onChange={(e) => setAzureDeployment(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">API 版本</label>
                  <Input
                    placeholder="2024-02-01"
                    value={azureApiVersion}
                    onChange={(e) => setAzureApiVersion(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
              </>
            )}

            {/* Temperature + Max tokens */}
            <div className="flex gap-2">
              <div className="space-y-1 flex-1">
                <label className="text-xs text-muted-foreground">温度</label>
                <Input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={temperature}
                  onChange={(e) => setTemperature(e.target.value)}
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1 flex-1">
                <label className="text-xs text-muted-foreground">最大 Token</label>
                <Input
                  type="number"
                  min="256"
                  max="128000"
                  step="256"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(e.target.value)}
                  className="h-8 text-sm"
                />
              </div>
            </div>

            {/* Test result */}
            {testResult && (
              <p
                className={`text-xs font-mono px-2 py-1 rounded ${
                  testResult.startsWith("✓")
                    ? "bg-green-500/10 text-green-400"
                    : "bg-red-500/10 text-red-400"
                }`}
              >
                {testResult}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleTest}
                disabled={testing || !apiKey}
                className="flex-1"
              >
                {testing ? "测试中…" : "测试连接"}
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving} className="flex-1">
                {saving ? "保存中…" : "保存并热切换"}
              </Button>
              <DrawerClose asChild>
                <Button variant="ghost" size="sm">
                  取消
                </Button>
              </DrawerClose>
            </div>
          </div>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
