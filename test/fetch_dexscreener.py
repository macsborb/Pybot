# ================== PROCESSOR ==================
DEXSCREENER_URL = "https://api.dexscreener.com/token-pairs/v1/solana/"
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