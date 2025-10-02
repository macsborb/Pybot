import asyncio
import json
import websockets
from datetime import datetime
import time
import traceback
import winsound
import subprocess


# ================== CONFIG ==================
TRADE_HOLD_SECONDS = 30           # durée d'attente avant revente
TRADE_SIZE_SOL = 0.15               # montant investi par trade (en SOL)
MAX_CONCURRENT_TRADES = 2         # ✅ limite de trades simultanés
API_KEY = "Your_SolanaStreaming_API_Key"  # mettre votre clé API SolanaStreaming ici
SOLANA_STREAM_WS = "wss://api.solanastreaming.com/"  # remplace si nécessaire


# ================== STATE ==================
seen_tokens = set()
trade_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRADES)

def is_running():
    try:
        with open("control.json", "r") as f:
            data = json.load(f)
            return data.get("running", True)
    except Exception:
        return True

def save_stats():
    global initial_balance, portfolio_balance, revenue_total, trade_count, successful_trades, nosuccessful_trades, rugged_count, pending_trades, successful_trades_log, nosuccessful_trades_log, rugpull_trades_log
    stats = {
        "initial_balance": initial_balance,
        "portfolio_balance": portfolio_balance,
        "revenue_total": revenue_total,
        "trade_count": trade_count,
        "successful_trades": successful_trades,
        "nosuccessful_trades": nosuccessful_trades,
        "rugged_count": rugged_count,
        "pending_trades": pending_trades,
        "successful_trades_log": successful_trades_log,
        "nosuccessful_trades_log": nosuccessful_trades_log,
        "rugpull_trades_log": rugpull_trades_log
    }
    with open("stats.json", "w") as f:
        json.dump(stats, f, indent=2)

# ================== LOGGING ==================

def print_runtime(msg: str):
    print(msg, flush=True)

# ================== TRADE SIMULATION ==================

import subprocess
import json

def swap_token(input_mint: str, output_mint: str, amount_raw: int, out_file: str) -> dict:
    """
    Lance le swap TS:
      npx ts-node swap.ts --inputMint ... --outputMint ... --amount ... --slippageBps 200 --priorityLamports 100000 --outFile out_file
    Retourne le dict JSON lu depuis out_file.
    """
    cmd = [
        "npx", "ts-node", "C:/Users/soonb/Desktop/Pybot/jup-swap/swap.ts",
        "--inputMint", input_mint,
        "--outputMint", output_mint,
        "--amount", str(amount_raw),
        "--slippageBps", "100",        # 2 %
        "--priorityLamports", "100000",# 0.0001 SOL
        "--out", out_file,
    ]

    print_runtime(f"[DEBUG] Running swap CLI command: {' '.join(cmd)}")

    subprocess.run(cmd, text=True, shell=True)

    # Lire le fichier JSON de sortie
    try:
        with open(out_file, "r", encoding="utf-8") as f:
            raw_data = f.read()
        print_runtime(f"[DEBUG] Raw JSON content from {out_file}:\n{raw_data}")
        data = json.loads(raw_data)
    except Exception as e:
        raise RuntimeError(f"[ERROR] Failed to read/parse {out_file}: {e}")

    if not data.get("ok") and "signature" not in data:
        raise RuntimeError(f"[ERROR] swap.ts did not produce a valid JSON: {data}")

    print_runtime(f"[DEBUG] Parsed swap result: {json.dumps(data, indent=2)}")
    return data



async def trade(mint, decimals, buy_amount_sol=TRADE_SIZE_SOL, hold_seconds=TRADE_HOLD_SECONDS):
    global portfolio_balance, revenue_total, trade_count, rugged_count, successful_trades, pending_trades
    global successful_trades_log, nosuccessful_trades, nosuccessful_trades_log, rugpull_trades_log
    print_runtime(f"\n🚀 Simulation de trade sur {mint} (decimals={decimals}) avec {buy_amount_sol} SOL...")
    # 🚦 Attendre qu'il y ait un slot dispo
    while pending_trades >= MAX_CONCURRENT_TRADES:
        print_runtime(f"⏸️ Trop de trades actifs ({pending_trades}/{MAX_CONCURRENT_TRADES}), attente...")
        await asyncio.sleep(1)

    async with trade_semaphore:
        print(f"\n🤖 [SIMU] Achat fictif de {buy_amount_sol} SOL sur {mint} (decimals={decimals})...")
        try:
            winsound.Beep(800, 200)
        except Exception:
            pass

        SOL_MINT = "So11111111111111111111111111111111111111112"
        USD_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        try:
            amount_in = int(buy_amount_sol * 1e9)  # lamports (input = SOL)
            out_path = f"swap_buy_{mint}.json"

            # 🟢 Swap réel SOL -> token (output = mint)
            buy_swap = swap_token(SOL_MINT, mint, amount_in, out_path)

        except Exception as e:
            print(f"   ⚠️ Erreur swap TS buy: {e}")
            pending_trades -= 1
            return
        print("wait_seconds")
        await asyncio.sleep(hold_seconds)

        # -------- VENTE (réelle) --------
        try:
            # montant de tokens à vendre en unités de base
            amount_token = buy_swap.get("outAmount", 0)
            amount_token_raw = int(amount_token * 10**decimals)
            print(amount_token_raw)
            out_path_sell = f"swap_sell_{mint}.json"

            # 🔄 Swap réel : token -> SOL
            swap_token(mint, SOL_MINT, amount_token_raw, out_path_sell)

        except Exception as e:
            print(f"   ⚠️ Erreur swap TS sell: {e}")
            return
        
# ================== WEBSOCKET LISTENER ==================
async def listen_pools(token_queue: asyncio.Queue):
    try:
        async with websockets.connect(
            SOLANA_STREAM_WS,
            ping_interval=None,
            close_timeout=10,
            extra_headers={"X-API-KEY": API_KEY}
        ) as ws:
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "newPairSubscribe",
                "params": {
                    "include_pumpfun": False
                }
            }))
            print_runtime("📡 Listening SolanaStreaming new pairs...")

            while True:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    #print_runtime(f"[DEBUG] WS message: {data}")

                    pair = data.get("params", {}).get("pair", {})
                    if not pair:
                        continue

                    base = pair.get("baseToken", {})
                    mint = base.get("account")
                    decimals = base.get("info", {}).get("decimals", 9)  # fallback 9

                    if mint and mint not in seen_tokens:
                        seen_tokens.add(mint)
                        await token_queue.put((mint, decimals))
                    await asyncio.sleep(0.1)  # 🧘 petit délai pour éviter de spammer la boucle
                except Exception as e:
                    print_runtime(f"⚠️ Inner WS error: {e}")
                    continue  # 🔑 rester dans la boucle

    except Exception as e:
        print_runtime(f"⚠️ Outer WS error: {e} — retrying in 5s")
        await asyncio.sleep(5)


async def process_tokens(token_queue: asyncio.Queue):
    last_trade_time = 0
    RATE_LIMIT = 5  # secondes entre chaque trade
    while True:
        if not is_running():
            print_runtime("⏸️ Bot en pause (pas de nouveaux tokens)")
            await asyncio.sleep(2)
            continue
        try:
            try:
                now = time.time()
                if now - last_trade_time < RATE_LIMIT:
                    # trop tôt → on remet le token en file et attend un peu
                    await asyncio.sleep(1)
                    continue
                mint, decimals = await asyncio.wait_for(token_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                await asyncio.sleep(0)
                continue

            print_runtime(f"\n🔍 Nouveau token détecté : {mint}")
            await asyncio.sleep(0.3)

            print_runtime(f"✅ Nouveau token retenu: https://dexscreener.com/solana/{mint}")
            asyncio.create_task(trade(mint, decimals))

            last_trade_time = time.time()  # mise à jour du timestamp

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print_runtime(f"⚠️ Erreur process_tokens: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(1)

# ================== MAIN ==================
async def main():
    token_queue = asyncio.LifoQueue()
    await asyncio.gather(
        listen_pools(token_queue),
        process_tokens(token_queue),
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Bot arrêté.")
