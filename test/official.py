import asyncio
import json
import websockets
import aiohttp
from collections import deque
from datetime import datetime

# ✅ RPC WebSocket & HTTP de Solana mainnet
RPC_WS = "wss://api.mainnet-beta.solana.com"
RPC_HTTP = "https://api.mainnet-beta.solana.com"

# ✅ ID du programme Pump.fun
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# 📦 Signatures reçues via WebSocket
signatures_queue = deque()

# 📊 Historique pour éviter de traiter 2x la même signature
processed_signatures = set()


async def fetch_new_mints():
    """Toutes les 5s : récupère les mints des nouvelles signatures uniquement."""
    while True:
        await asyncio.sleep(5)  # 🔁 intervalle des requêtes
        if not signatures_queue:
            continue

        # 🧠 Récupérer uniquement les signatures non encore traitées (dans l'ordre d'arrivée)
        seen = set()
        new_signatures = []
        for sig in signatures_queue:
            if sig not in processed_signatures and sig not in seen:
                new_signatures.append(sig)
                seen.add(sig)

        if not new_signatures:
            continue

        print(f"\n📬 {len(new_signatures)} nouvelles signatures à traiter ({datetime.now().time()})")

        mints = await get_mints_from_signatures(new_signatures)
        for mint in mints:
            print(f"✅ Nouveau mint détecté : {mint}")
            print(f"🔗 https://solscan.io/token/{mint}")

        # ✅ Marquer ces signatures comme traitées
        processed_signatures.update(new_signatures)


async def reset_every_30s():
    """Toutes les 30 secondes, vider la liste et le set pour repartir propre."""
    while True:
        await asyncio.sleep(30)
        signatures_queue.clear()
        processed_signatures.clear()
        print("\n♻️ Liste de signatures réinitialisée.")


async def get_mints_from_signatures(signatures):
    """Fait une requête par signature pour éviter les 429."""
    mints = []
    async with aiohttp.ClientSession() as session:
        for sig in signatures:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }
            try:
                async with session.post(RPC_HTTP, json=payload) as resp:
                    data = await resp.json()
                result = data.get("result")
                if result:
                    balances = result["meta"].get("postTokenBalances", [])
                    for bal in balances:
                        mint = bal.get("mint")
                        if mint and len(mint) == 44:
                            mints.append(mint)
                            break
            except Exception as e:
                print(f"⚠️ Erreur sur {sig[:8]}... : {e}")
            await asyncio.sleep(0.15)  # 🧘 petit délai entre chaque requête pour éviter le 429
    return mints


async def subscribe_to_pumpfun_mints():
    """Écoute WebSocket en continu pour ajouter les signatures à la liste."""
    async with websockets.connect(RPC_WS) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [PUMPFUN_PROGRAM]},
                {"commitment": "finalized"}
            ]
        }))
        print("🚀 Abonné aux transactions Pump.fun...")

        while True:
            message = await ws.recv()
            data = json.loads(message)

            if (
                isinstance(data, dict)
                and data.get("method") == "logsNotification"
                and "params" in data
                and "result" in data["params"]
                and isinstance(data["params"]["result"], dict)
                and "value" in data["params"]["result"]
            ):
                signature = data["params"]["result"]["value"]["signature"]
                signatures_queue.append(signature)


async def main():
    await asyncio.gather(
        subscribe_to_pumpfun_mints(),  # 👂 écoute en continu
        fetch_new_mints(),             # 📬 requêtes toutes les 5s
        reset_every_30s()              # ♻️ reset toutes les 30s
    )

asyncio.run(main())
