import asyncio
import json
import websockets

API_KEY = "eecbc989b2a944a6c7462016941249cc"
WS_URL = "wss://api.solanastreaming.com/"

async def listen_stream():
    async with websockets.connect(
        WS_URL,
        ping_interval=20,
        ping_timeout=20,
        extra_headers={"X-API-KEY": API_KEY}   # ✅ Auth comme en JS
    ) as ws:
        print("📡 Connecté à SolanaStreaming")

        # Exemple : newPairSubscribe (nouveaux pools)
        await ws.send(json.dumps({
            "id": 1,
            "method": "newPairSubscribe",
            "params": {
                "include_pumpfun": True
            }
        }))

        # Boucle de lecture
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                print("🔔", json.dumps(data, indent=2))
            except Exception as e:
                print("⚠️ Erreur WS:", e)
                break

if __name__ == "__main__":
    asyncio.run(listen_stream())
