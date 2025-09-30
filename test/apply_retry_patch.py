from pathlib import Path
import re

path = Path("test.py")
text = path.read_text(encoding="utf-8")

pattern = r"(MAX_CONCURRENT_TRADES = 10[^\r\n]*\r\n)\r\n"
match = re.search(pattern, text)
if not match:
    raise SystemExit("Failed to locate MAX_CONCURRENT_TRADES block")
replacement = (
    r"\1\r\n"
    "RETRY_INTERVAL_SECONDS = 5          # seconds between retry attempts\r\n"
    "RETRY_WINDOW_SECONDS = 60           # lifespan of retry bucket in seconds\r\n"
    "MAX_RETRY_ATTEMPTS = 12             # per-mint retry cap within window\r\n\r\n"
)
text, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit("Failed to insert retry constants")

pattern = r"(trade_semaphore = asyncio\.Semaphore\(MAX_CONCURRENT_TRADES\)\r\n)\r\n"
match = re.search(pattern, text)
if not match:
    raise SystemExit("Failed to locate trade_semaphore block")
replacement = (
    r"\1"
    "retry_candidates = {}              # mint -> retry state\r\n"
    "retry_lock = asyncio.Lock()        # protects retry_candidates\r\n\r\n"
)
text, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit("Failed to insert retry globals")

marker = "async def get_price"
idx = text.find(marker)
if idx == -1:
    raise SystemExit("Failed to locate get_price definition")
retry_helpers = (
    "# ================== RETRY MANAGER ==================\r\n"
    "async def register_retry_candidate(mint: str, reason: str) -> bool:\r\n"
    "    \"\"\"Track a mint that failed because the pair was unavailable. Return True to keep retrying.\"\"\"\r\n"
    "    now = time.time()\r\n"
    "    drop_message = None\r\n"
    "    log_message = None\r\n"
    "    async with retry_lock:\r\n"
    "        entry = retry_candidates.get(mint)\r\n"
    "        if entry is None:\r\n"
    "            entry = {\r\n"
    "                \"first_seen\": now,\r\n"
    "                \"last_attempt\": now,\r\n"
    "                \"attempts\": 1,\r\n"
    "                \"last_reason\": reason,\r\n"
    "                \"inflight\": False,\r\n"
    "            }\r\n"
    "            retry_candidates[mint] = entry\r\n"
    "            log_message = f\"[RETRY] {mint} awaiting DexScreener pair (reason: {reason})\"\r\n"
    "        else:\r\n"
    "            entry[\"last_attempt\"] = now\r\n"
    "            entry[\"attempts\"] += 1\r\n"
    "            entry[\"last_reason\"] = reason\r\n"
    "            entry[\"inflight\"] = False\r\n"
    "            log_message = f\"[RETRY] {mint} still unavailable (attempt {entry['attempts']}, reason: {reason})\"\r\n"
    "        attempts = entry[\"attempts\"]\r\n"
    "        age = now - entry[\"first_seen\"]\r\n"
    "        if attempts >= MAX_RETRY_ATTEMPTS:\r\n"
    "            drop_message = f\"max attempts reached ({attempts})\"\r\n"
    "        elif age >= RETRY_WINDOW_SECONDS:\r\n"
    "            drop_message = f\"expired after {age:.1f}s\"\r\n"
    "        if drop_message:\r\n"
    "            retry_candidates.pop(mint, None)\r\n"
    "    if drop_message:\r\n"
    "        print_runtime(f\"[RETRY] Giving up on {mint}: {drop_message}; last reason: {reason}\")\r\n"
    "        return False\r\n"
    "    if log_message:\r\n"
    "        print_runtime(log_message)\r\n"
    "    return True\r\n\r\n"
    "async def mark_retry_success(mint: str):\r\n"
    "    \"\"\"Remove mint from retry tracking once DexScreener returns data.\"\"\"\r\n"
    "    async with retry_lock:\r\n"
    "        entry = retry_candidates.pop(mint, None)\r\n"
    "    if entry:\r\n"
    "        attempts = entry.get(\"attempts\", 0)\r\n"
    "        if attempts > 0:\r\n"
    "            plural = \"s\" if attempts > 1 else \"\"\r\n"
    "            print_runtime(f\"[RETRY] {mint} ready after {attempts} retry{plural}\")\r\n\r\n"
    "async def abandon_retry_candidate(mint: str, reason: str = None):\r\n"
    "    \"\"\"Stop retrying this mint (used when we intentionally drop it).\"\"\"\r\n"
    "    async with retry_lock:\r\n"
    "        entry = retry_candidates.pop(mint, None)\r\n"
    "    if entry and reason:\r\n"
    "        print_runtime(f\"[RETRY] Dropping {mint}: {reason}\")\r\n\r\n"
    "async def retry_worker(token_queue: asyncio.Queue):\r\n"
    "    while True:\r\n"
    "        await asyncio.sleep(RETRY_INTERVAL_SECONDS)\r\n"
    "        now = time.time()\r\n"
    "        to_enqueue = []\r\n"
    "        expired = []\r\n"
    "        async with retry_lock:\r\n"
    "            for mint, entry in list(retry_candidates.items()):\r\n"
    "                age = now - entry[\"first_seen\"]\r\n"
    "                if age >= RETRY_WINDOW_SECONDS:\r\n"
    "                    expired.append((mint, entry.get(\"last_reason\"), entry.get(\"attempts\", 0), \"expired\"))\r\n"
    "                    retry_candidates.pop(mint, None)\r\n"
    "                    continue\r\n"
    "                if entry.get(\"attempts\", 0) >= MAX_RETRY_ATTEMPTS:\r\n"
    "                    expired.append((mint, entry.get(\"last_reason\"), entry.get(\"attempts\", 0), \"max attempts\"))\r\n"
    "                    retry_candidates.pop(mint, None)\r\n"
    "                    continue\r\n"
    "                if entry.get(\"inflight\"):\r\n"
    "                    continue\r\n"
    "                if now - entry.get(\"last_attempt\", 0) < RETRY_INTERVAL_SECONDS:\r\n"
    "                    continue\r\n"
    "                entry[\"inflight\"] = True\r\n"
    "                entry[\"last_attempt\"] = now\r\n"
    "                to_enqueue.append((mint, entry.get(\"attempts\", 0)))\r\n"
    "        for mint, attempts in to_enqueue:\r\n"
    "            await token_queue.put(mint)\r\n"
    "            print_runtime(f\"[RETRY] Requeue {mint} (next attempt {attempts + 1})\")\r\n"
    "        for mint, reason, attempts, why in expired:\r\n"
    "            print_runtime(f\"[RETRY] Giving up on {mint}: {why}; attempts={attempts}; last reason: {reason}\")\r\n\r\n"
)
text = text[:idx] + retry_helpers + text[idx:]

start = text.find("async def fetch_dexscreener")
if start == -1:
    raise SystemExit("Failed to find fetch_dexscreener start")
end = text.find("# >>> NEW: moteur de", start)
if end == -1:
    raise SystemExit("Failed to find fetch_dexscreener end marker")
old_func = text[start:end]
new_func = (
    "async def fetch_dexscreener(token_address: str, session: aiohttp.ClientSession = None):\r\n"
    "    \"\"\"\r\n"
    "    Recupere les infos DexScreener pour un token. Utilise une session reutilisable si fournie.\r\n"
    "    Optimise pour vitesse maximale (pas de sleep, timeout court, parsing minimal).\r\n"
    "    Retourne (donnees, raison_echec).\r\n"
    "    \"\"\"\r\n"
    "    url = DEXSCREENER_URL + token_address\r\n"
    "    close_session = False\r\n"
    "    if session is None:\r\n"
    "        session = aiohttp.ClientSession()\r\n"
    "        close_session = True\r\n"
    "    start = time.time()\r\n"
    "    try:\r\n"
    "        async with session.get(url, timeout=3) as resp:\r\n"
    "            elapsed = time.time() - start\r\n"
    "            if resp.status != 200:\r\n"
    "                reason = f\"HTTP {resp.status}\"\r\n"
    "                print_runtime(f\"[DEBUG] fetch_dexscreener: {reason} pour {token_address} en {elapsed:.2f}s\")\r\n"
    "                return None, reason\r\n"
    "            data = await resp.json()\r\n"
    "            pairs = data.get(\"pairs\")\r\n"
    "            if not pairs:\r\n"
    "                reason = \"Pair not ready on DexScreener\"\r\n"
    "                print_runtime(f\"[DEBUG] fetch_dexscreener: Pas de pair pour {token_address} en {elapsed:.2f}s\")\r\n"
    "                return None, reason\r\n"
    "            pair = pairs[0]\r\n"
    "            pair_created_at = pair.get(\"pairCreatedAt\")\r\n"
    "            age_sec = None\r\n"
    "            if pair_created_at:\r\n"
    "                created_dt = datetime.utcfromtimestamp(pair_created_at / 1000)\r\n"
    "                age_sec = (datetime.utcnow() - created_dt).total_seconds()\r\n"
    "                print_runtime(f\"[DEBUG] {token_address} age pool: {age_sec:.1f}s (max {MAX_AGE_SECONDS})\")\r\n"
    "                if age_sec > MAX_AGE_SECONDS:\r\n"
    "                    return None, None\r\n"
    "            base_token = pair.get(\"baseToken\") or {}\r\n"
    "            volume = pair.get(\"volume\") or {}\r\n"
    "            liquidity = pair.get(\"liquidity\") or {}\r\n"
    "            socials = pair.get(\"info\") or {}\r\n"
    "            txns = pair.get(\"txns\") or {}\r\n"
    "            url = pair.get(\"url\")\r\n"
    "            print_runtime(f\"[DEBUG] fetch_dexscreener OK {token_address} en {elapsed:.2f}s\")\r\n"
    "            return {\r\n"
    "                \"name\": base_token.get(\"name\"),\r\n"
    "                \"symbol\": base_token.get(\"symbol\"),\r\n"
    "                \"volume_1h\": volume.get(\"h1\"),\r\n"
    "                \"volume_24h\": volume.get(\"h24\"),\r\n"
    "                \"liquidity_usd\": liquidity.get(\"usd\"),\r\n"
    "                \"price_usd\": pair.get(\"priceUsd\"),\r\n"
    "                \"fdv\": pair.get(\"fdv\"),\r\n"
    "                \"pair_created_at\": pair_created_at,\r\n"
    "                \"age_sec\": age_sec,\r\n"
    "                \"txns_1h_buys\": ((txns.get(\"h1\") or {}).get(\"buys\")),\r\n"
    "                \"txns_1h_sells\": ((txns.get(\"h1\") or {}).get(\"sells\")),\r\n"
    "                \"txns_1h_volume\": ((txns.get(\"h1\") or {}).get(\"volume\")),\r\n"
    "                \"url\": url,\r\n"
    "                \"socials\": {\r\n"
    "                    \"twitter\": (socials.get(\"twitter\") if isinstance(socials, dict) else None),\r\n"
    "                    \"telegram\": (socials.get(\"telegram\") if isinstance(socials, dict) else None),\r\n"
    "                    \"discord\": (socials.get(\"discord\") if isinstance(socials, dict) else None),\r\n"
    "                    \"website\": (socials.get(\"website\") if isinstance(socials, dict) else None),\r\n"
    "                },\r\n"
    "            }, None\r\n"
    "    except Exception as e:\r\n"
    "        elapsed = time.time() - start\r\n"
    "        reason = f\"Exception {e}\"\r\n"
    "        print_runtime(f\"[DEBUG] fetch_dexscreener: {reason} pour {token_address} en {elapsed:.2f}s\")\r\n"
    "        return None, reason\r\n"
    "    finally:\r\n"
    "        if close_session:\r\n"
    "            await session.close()\r\n"
)
text = text.replace(old_func, new_func)

pattern = (
    "            token_data = await fetch_dexscreener(mint)\r\n"
    "            if token_data:\r\n"
)
replacement = (
    "            token_data, fetch_reason = await fetch_dexscreener(mint)\r\n"
    "            if not token_data:\r\n"
    "                if fetch_reason:\r\n"
    "                    await register_retry_candidate(mint, fetch_reason)\r\n"
    "                else:\r\n"
    "                    await abandon_retry_candidate(mint, \"filtered out (age window)\")\r\n"
    "                continue\r\n"
    "            await mark_retry_success(mint)\r\n"
    "            # >>> NEW: filtre d'achat AVANT le log detaille et la simu\r\n"
)
text, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit("Failed to update process_tokens fetch block")

pattern = (
    "    await asyncio.gather(\r\n"
    "        listen_new_raydium_pools(token_queue),\r\n"
    "        listen_new_pumpfun_mints(token_queue),  # >>> NEW: Pump.fun branch\r\n"
    "        process_tokens(token_queue),\r\n"
    "    )\r\n"
)
replacement = (
    "    await asyncio.gather(\r\n"
    "        listen_new_raydium_pools(token_queue),\r\n"
    "        listen_new_pumpfun_mints(token_queue),  # >>> NEW: Pump.fun branch\r\n"
    "        process_tokens(token_queue),\r\n"
    "        retry_worker(token_queue),\r\n"
    "    )\r\n"
)
text, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit("Failed to patch main gather block")

path.write_text(text, encoding="utf-8")
