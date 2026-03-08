import { HfssStatusBar } from "@/components/HfssStatusBar";
import { ChatPageClient } from "./_client";

export default function Home() {
  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">
      {/* Top nav */}
      <HfssStatusBar />
      {/* Split panels — state lives in ChatPageClient */}
      <ChatPageClient />
    </div>
  );
}
