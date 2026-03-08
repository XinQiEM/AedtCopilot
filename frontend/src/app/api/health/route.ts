import { NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/health`, { cache: "no-store" });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json(
      {
        hfss_connected: false,
        llm_provider: "—",
        llm_model: "—",
        rag_ready: false,
        rag_chunks: 0,
      },
      { status: 200 }   // return 200 so front-end doesn't throw
    );
  }
}
