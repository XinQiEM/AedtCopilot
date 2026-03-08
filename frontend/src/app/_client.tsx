"use client";

import { useChat } from "@/hooks/useChat";
import { ChatPanel } from "@/components/ChatPanel";
import { ResultPanel } from "@/components/ResultPanel";
import { SimLogPanel } from "@/components/SimLogPanel";

/**
 * Client boundary: owns the useChat hook so that chart/sim state
 * can flow from ChatPanel down to ResultPanel without prop drilling through
 * the server component root.
 */
export function ChatPageClient() {
  const {
    messages,
    connected,
    sending,
    sendMessage,
    clearMessages,
    sparamData,
    farFieldData,
    simStatus,
    simLogs,
    clearSimLogs,
  } = useChat();

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Chat — 40% */}
      <div className="w-[40%] min-w-[320px] flex flex-col overflow-hidden border-r-2 border-border">
        <ChatPanel
          messages={messages}
          connected={connected}
          sending={sending}
          sendMessage={sendMessage}
          clearMessages={clearMessages}
        />
      </div>

      {/* Result — 60% */}
      <div className="flex-1 flex flex-col overflow-hidden bg-muted/5">
        <div className="flex-1 min-h-0 overflow-hidden">
          <ResultPanel
            sparamData={sparamData}
            farFieldData={farFieldData}
            simStatus={simStatus}
          />
        </div>
        <SimLogPanel logs={simLogs} onClear={clearSimLogs} />
      </div>
    </div>
  );
}
