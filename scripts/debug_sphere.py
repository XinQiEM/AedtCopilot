"""Debug: send sphere creation command via WebSocket and log all events."""
import asyncio
import json
import websockets


async def test():
    uri = "ws://127.0.0.1:8000/ws/chat"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"message": "创建一个半径1m的金属球", "history": []}))
        for _ in range(60):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                ev = json.loads(msg)
                etype = ev.get("type", "?")
                print(f"[{etype}]", json.dumps(ev, ensure_ascii=False)[:200])
                if etype in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                print("TIMEOUT")
                break


asyncio.run(test())
