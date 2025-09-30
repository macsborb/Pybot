import asyncio
import json
import websockets
import aiohttp
from datetime import datetime
import time
import traceback
import re
from base58 import b58decode
import winsound
import importlib.util
import sys

# ================== CONFIG ==================
RPC_URL = "wss://api.solanastreaming.com"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
DEXSCREENER_URL = "https://api.dexscreener.com/token-pairs/v1/solana/"

MAX_AGE_SECONDS = 5  # max 15s depuis création

FEE_RATE = 0.0025         # 0.25% par transaction (achat & vente)
SLIPPAGE_RATE_BUY = 0.08    # 8% à l'achat
SLIPPAGE_RATE_SELL = 0.03   # 3% à la vente
TAX_RATE = 0.0              # 0% achat & vente


TRADE_HOLD_SECONDS = 60           # durée d'attente avant revente
TRADE_SIZE_SOL = 0.3               # montant investi par trade (en SOL)

MAX_CONCURRENT_TRADES = 5         # ✅ limite de trades simultanés



# ================== STATE ==================
seen_tokens = set()

portfolio_balance = 5.0        # Solde fictif du portefeuille en SOL
revenue_total = 0.0            # PnL cumulé
start_time = time.time()

trade_count = 0
rugged_count = 0
successful_trades = 0
nosuccessful_trades = 0
pending_trades = 0
successful_trades_log = []
nosuccessful_trades_log = []
trade_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRADES)

def save_stats():
    global portfolio_balance, revenue_total, trade_count, successful_trades, nosuccessful_trades, rugged_count, pending_trades, successful_trades_log, nosuccessful_trades_log
    stats = {
        "portfolio_balance": portfolio_balance,
        "revenue_total": revenue_total,
        "trade_count": trade_count,
        "successful_trades": successful_trades,
        "nosuccessful_trades": nosuccessful_trades,
        "rugged_count": rugged_count,
        "pending_trades": pending_trades,
        "successful_trades_log": successful_trades_log,
        "nosuccessful_trades_log": nosuccessful_trades_log
    }
    with open("stats.json", "w") as f:
        json.dump(stats, f, indent=2)


# ================== LOGGING ==================
def stats_header() -> str:
    global trade_count, rugged_count, portfolio_balance, revenue_total, start_time, successful_trades, pending_trades, successful_trades_log, nosuccessful_trades, nosuccessful_trades_log
    elapsed = time.time() - start_time
    minutes = elapsed / 60 if elapsed > 0 else 0.0
    hours = elapsed / 3600 if elapsed > 0 else 0.0
    avg_per_min = revenue_total / minutes if minutes > 0 else 0.0
    avg_per_hour = revenue_total / hours if hours > 0 else 0.0
    header = (
        f"Trades pris : {trade_count}\n"
        f"Rugged : {rugged_count}\n"
        f"Trades réussis : {successful_trades}\n"
        f"Trades non réussis : {nosuccessful_trades}\n"
        f"Trades en cours : {pending_trades}\n"
        f"Solde portefeuille : {portfolio_balance:.4f} SOL\n"
        f"Revenu total : {revenue_total:.4f} SOL\n"
        f"Temps écoulé : {int(elapsed//60)} min {int(elapsed%60)} sec\n"
        f"Gain moyen/min : {avg_per_min:.4f} SOL | Gain moyen/heure : {avg_per_hour:.4f} SOL\n"
    )
    if successful_trades_log:
        header += "\n--- Détail des trades réussis ---\n"
        for t in successful_trades_log:
            header += (
                f"[{t['time']}] {t['mint']} | +{t['pnl']:.4f} SOL | Buy: {t['buy_price']:.8f} | Sell: {t['sell_price']:.8f}\n"
            )
    else:
        header += "\n--- Détail des trades non réussis ---\n"
        for t in nosuccessful_trades_log:
            header += (
                f"[{t['time']}] {t['mint']} | -{t['pnl']:.4f} SOL | Buy: {t['buy_price']:.8f} | Sell: {t['sell_price']:.8f}\n"
            )

    return header

def print_and_write_end_of_trade(extra: str):
    header = stats_header()
    out = header + (extra or "")
    try:
        with open("result.txt", "w", encoding="utf-8") as f:
            f.write(header)
    except Exception:
        pass

def print_runtime(msg: str):
    print(msg, flush=True)

async def fetch_dexscreener(token_address: str, session: aiohttp.ClientSession = None):
    """
    Récupère les infos DexScreener pour un token (endpoint search qui renvoie une liste).
    Compatible avec les paires renvoyées sous forme de liste.
    """
    url = DEXSCREENER_URL + token_address
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    start = time.time()
    try:
        async with session.get(url, timeout=5) as resp:
            elapsed = time.time() - start
            if resp.status != 200:
                print_runtime(f"[DEBUG] fetch_dexscreener: HTTP {resp.status} pour {token_address} en {elapsed:.2f}s")
                return None
            data = await resp.json()
            if not isinstance(data, list) or len(data) == 0:
                return None

            pair = data[0]  # on prend la première paire
            if not isinstance(pair, dict):
                return None

            # Extraction classique
            base_token = pair.get("baseToken", {})
            quote_token = pair.get("quoteToken", {})
            volume = pair.get("volume", {})
            txns = pair.get("txns", {})
            liquidity = pair.get("liquidity", {})
            price_change = pair.get("priceChange", {})

            # --- Extraction socials & websites ---
            socials = {}
            websites = []
            info_block = pair.get("info")
            if isinstance(info_block, dict):
                if "websites" in info_block and isinstance(info_block["websites"], list):
                    websites = [w.get("url") for w in info_block["websites"] if isinstance(w, dict) and "url" in w]
                if "socials" in info_block and isinstance(info_block["socials"], list):
                    for s in info_block["socials"]:
                        if isinstance(s, dict):
                            socials[s.get("type")] = s.get("url")

            return {
                "chainId": pair.get("chainId"),
                "dexId": pair.get("dexId"),
                "url": pair.get("url"),
                "pairAddress": pair.get("pairAddress"),
                "base_name": base_token.get("name"),
                "base_symbol": base_token.get("symbol"),
                "base_address": base_token.get("address"),
                "quote_name": quote_token.get("name"),
                "quote_symbol": quote_token.get("symbol"),
                "quote_address": quote_token.get("address"),
                "price_native": pair.get("priceNative"),
                "price_usd": pair.get("priceUsd"),
                "fdv": pair.get("fdv"),
                "market_cap": pair.get("marketCap"),
                "pair_created_at": pair.get("pairCreatedAt"),
                "volume_m5": volume.get("m5"),
                "volume_h1": volume.get("h1"),
                "volume_h6": volume.get("h6"),
                "volume_h24": volume.get("h24"),
                "txns_m5_buys": (txns.get("m5") or {}).get("buys"),
                "txns_m5_sells": (txns.get("m5") or {}).get("sells"),
                "txns_h1_buys": (txns.get("h1") or {}).get("buys"),
                "txns_h1_sells": (txns.get("h1") or {}).get("sells"),
                "txns_h24_buys": (txns.get("h24") or {}).get("buys"),
                "txns_h24_sells": (txns.get("h24") or {}).get("sells"),
                "price_change_m5": price_change.get("m5"),
                "price_change_h1": price_change.get("h1"),
                "price_change_h6": price_change.get("h6"),
                "price_change_h24": price_change.get("h24"),
                "liquidity_usd": liquidity.get("usd"),
                "liquidity_base": liquidity.get("base"),
                "liquidity_quote": liquidity.get("quote"),
                "websites": websites,
                "socials": socials,
            }
    except Exception as e:
        elapsed = time.time() - start
        print_runtime(f"[DEBUG] fetch_dexscreener: Exception {e} pour {token_address} en {elapsed:.2f}s")
        return None
    finally:
        if close_session:
            await session.close()

API_KEY = "eecbc989b2a944a6c7462016941249cc"
SOLANA_STREAM_WS = "wss://api.solanastreaming.com/"  # remplace si nécessaire

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


# ================== TRADE SIMULATION ==================
# Jupiter swap util
spec = importlib.util.spec_from_file_location("jupiter", "jupiter.py")
jupiter = importlib.util.module_from_spec(spec)
sys.modules["jupiter"] = jupiter
spec.loader.exec_module(jupiter)

async def simulate_trade(mint, decimals, buy_amount_sol=TRADE_SIZE_SOL, hold_seconds=TRADE_HOLD_SECONDS):
    global portfolio_balance, revenue_total, trade_count, rugged_count, successful_trades, pending_trades, successful_trades_log, nosuccessful_trades, nosuccessful_trades_log

    # 🚦 Attendre qu'il y ait un slot dispo
    while pending_trades >= MAX_CONCURRENT_TRADES:
        print_runtime(f"⏸️ Trop de trades actifs ({pending_trades}/{MAX_CONCURRENT_TRADES}), attente...")
        await asyncio.sleep(1)

    async with trade_semaphore:
        log_lines = []
        log_lines.append(f"\n🤖 [SIMU] Achat fictif de {buy_amount_sol} SOL sur {mint} (decimals={decimals})...")
        try:
            winsound.Beep(800, 200)
        except Exception:
            pass

        SOL_MINT = "So11111111111111111111111111111111111111112"
        try:
            amount_in = int(buy_amount_sol * 1e9)  # SOL = 9 décimales
            swap_info = await jupiter.get_jupiter_swap_price(SOL_MINT, mint, amount_in)
            if not swap_info or swap_info["out_amount"] <= 0:
                log_lines.append("   ⚠️ Impossible d'obtenir un prix valide via Jupiter. Achat annulé.")
                print_and_write_end_of_trade("\n".join(log_lines))
                return
            pending_trades += 1
            save_stats()
            buy_price = swap_info["price_per_token"]  # token par SOL
            amount_token = swap_info["out_amount"] / (10 ** decimals)

            if buy_price <= 0 or amount_token <= 0:
                log_lines.append("   ⚠️ Prix/quantité invalides. Achat annulé.")
                pending_trades -= 1
                save_stats()
                print_and_write_end_of_trade("\n".join(log_lines))
                return
            # ✅ seulement maintenant on déduit du portefeuille
            buy_fee = buy_amount_sol * FEE_RATE
            buy_tax = buy_amount_sol * TAX_RATE
            total_buy_cost = buy_amount_sol + buy_fee + buy_tax

            if portfolio_balance < total_buy_cost:
                log_lines.append(f"   ❌ Solde insuffisant ({portfolio_balance:.4f} SOL restants). Achat annulé.")
                pending_trades -= 1
                save_stats()
                print_and_write_end_of_trade("\n".join(log_lines))
                return

            portfolio_balance -= total_buy_cost
            save_stats()

        except Exception as e:
            log_lines.append(f"   ⚠️ Erreur Jupiter buy: {e}")
            pending_trades -= 1
            save_stats()
            print_and_write_end_of_trade("\n".join(log_lines))
            return

        log_lines.append(f"   ➤ Prix d'achat Jupiter : {buy_price:.8f} token/SOL")
        log_lines.append(f"   ➤ Quantité achetée : {amount_token:.6f} token")
        log_lines.append(f"   ➤ Frais+taxes : {(buy_fee+buy_tax):.4f} SOL")
        log_lines.append(f"   ➤ Solde portefeuille : {portfolio_balance:.4f} SOL")
        log_lines.append(f"   ➤ Attente {hold_seconds}s...\n")
        print_runtime("\n".join(log_lines))

        await asyncio.sleep(hold_seconds)

        # -------- VENTE --------
        end_log = []
        try:
            amount_out = int(amount_token * (10 ** decimals))
            swap_info_sell = await jupiter.get_jupiter_swap_price(mint, SOL_MINT, amount_out)

            if (not swap_info_sell 
                or "error" in swap_info_sell 
                or swap_info_sell.get("out_amount", 0) <= 0):
                # 🚨 Rug pull détecté : achat ok mais plus de liquidité au sell
                end_log.append("   💀 Rug pull détecté : plus aucune liquidité pour revendre.")
                rugged_count += 1
                pending_trades -= 1
                save_stats()
                print_and_write_end_of_trade("\n".join(end_log))
                return
            trade_count += 1
            save_stats()
            sell_price = swap_info_sell["price_per_token"]
            sol_received = swap_info_sell["out_amount"] / 1e9

        except Exception as e:
            end_log.append(f"   ⚠️ Erreur Jupiter sell: {e}")
            pending_trades -= 1
            save_stats()
            print_and_write_end_of_trade("\n".join(end_log))
            return

        sell_value = sol_received * (1 - SLIPPAGE_RATE_SELL)
        sell_fee = sell_value * FEE_RATE
        sell_tax = sell_value * TAX_RATE

        pnl = sell_value - total_buy_cost - sell_fee - sell_tax
        portfolio_balance += sell_value - sell_fee - sell_tax
        revenue_total += pnl

        if pnl > 0:
            successful_trades += 1
            save_stats()
            now = datetime.now().strftime("%H:%M:%S")
            successful_trades_log.append({
                "time": now,
                "mint": mint,
                "pnl": pnl,
                "buy_price": buy_price,
                "sell_price": sell_price
            })
        else:
            nosuccessful_trades += 1
            save_stats()
            now = datetime.now().strftime("%H:%M:%S")
            nosuccessful_trades_log.append({
                "time": now,
                "mint": mint,
                "pnl": pnl,
                "buy_price": buy_price,
                "sell_price": sell_price
            })
        pending_trades -= 1
        save_stats()

        end_log.append(f"   ➤ Prix de vente : {sell_price:.8f} SOL/token")
        end_log.append(f"   ➤ SOL reçu : {sell_value:.6f} SOL")
        end_log.append(f"   ➤ PnL : {pnl:.4f} SOL ✅")
        end_log.append(f"   ➤ Solde portefeuille : {portfolio_balance:.4f} SOL")
        print_and_write_end_of_trade("\n".join(end_log))

# ================== PROCESSOR ==================
async def fetch_with_retry(mint, retries, delay):
    """
    Essaie de récupérer les infos DexScreener avec plusieurs tentatives.
    - retries : nombre de tentatives max
    - delay   : délai de base entre chaque retry (progressif)
    """
    for i in range(retries):
        data = await fetch_dexscreener(mint)
        if data:
            return data
        wait_time = delay
        #print_runtime(f"[DEBUG-Retry-{i}] {mint} pas encore indexé, retry dans {wait_time}s...")
        await asyncio.sleep(wait_time)
    return None


async def process_tokens(token_queue: asyncio.Queue):
    last_trade_time = 0
    RATE_LIMIT = 10  # secondes entre chaque trade

    while True:
        try:
            try:
                mint, decimals = await asyncio.wait_for(token_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                await asyncio.sleep(0)
                continue

            now = time.time()
            if now - last_trade_time < RATE_LIMIT:
                # trop tôt → on remet le token en file et attend un peu
                await token_queue.put((mint, decimals))
                await asyncio.sleep(1)
                continue

            print_runtime(f"\n🔍 Nouveau token détecté : {mint}")
            await asyncio.sleep(2)
            # ✅ On attend DexScreener avec retry intelligent
            # token_data = await fetch_with_retry(mint, retries=40, delay=1)
            # if not token_data:
            #     print_runtime(f"⏭️  {mint} ignoré (pas de données DexScreener).")
            #     continue

            print_runtime(f"✅ Nouveau token retenu: https://dexscreener.com/solana/{mint}")
            asyncio.create_task(simulate_trade(mint, decimals))

            last_trade_time = time.time()  # mise à jour du timestamp
            await asyncio.sleep(0)  # yield pour éviter blocage

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print_runtime(f"⚠️ Erreur process_tokens: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(1)

def passes_buy_filters(meta: dict) -> (bool, str):
    """
    Vérifie si le token est intéressant pour un achat.
    Retourne (True/False, raison).
    """

    # Sécurité : cast des champs numériques
    def safe_float(x, default=0.0):
        try:
            return float(x) if x is not None else default
        except:
            return default

    def safe_int(x, default=0):
        try:
            return int(x) if x is not None else default
        except:
            return default
        
    # # 5️⃣ Socials (twitter, tg, site…)
    # socials = meta.get("socials", {})
    # has_socials = any([
    #     socials.get("twitter"),
    #     socials.get("telegram"),
    #     socials.get("website"),
    #     socials.get("discord")
    # ])
    # if not has_socials:
    #     return False, "Pas de réseaux sociaux (shitcoin probable)"

    # ✅ Si tout est ok
    return True, "OK"

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
