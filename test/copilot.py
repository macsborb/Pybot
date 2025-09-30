# copilot.py
"""
Bot asynchrone pour détecter les nouveaux tokens SPL sur Solana et interroger DexScreener.
"""
import asyncio
import aiohttp
import time
from typing import Set, Dict

SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens/{}"
CHECK_INTERVAL = 10  # secondes
LIQUIDITY_FILTER = 1000  # $ (bonus)
VOLUME_FILTER = 10000    # $ (bonus)

async def get_new_mints(session: aiohttp.ClientSession, seen_mints: Set[str]) -> Set[str]:
    """
    Récupère les nouveaux comptes mint SPL Token via getProgramAccounts.
    Retourne l'ensemble des nouveaux mint addresses non encore vus.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getProgramAccounts",
        "params": [
            SPL_TOKEN_PROGRAM,
            {
                "encoding": "jsonParsed",
                "filters": [
                    {"dataSize": 82}  # Mint account size
                ]
            }
        ]
    }
    try:
        async with session.post(SOLANA_RPC, json=payload, timeout=20) as resp:
            data = await resp.json()
            accounts = data.get("result", [])
            mints = set(acc["pubkey"] for acc in accounts)
            new_mints = mints - seen_mints
            return new_mints
    except Exception as e:
        print(f"[Erreur Solana RPC] {e}")
        return set()

async def fetch_token_info(session: aiohttp.ClientSession, mint: str) -> Dict:
    """
    Interroge DexScreener pour obtenir les infos du token SPL.
    """
    url = DEXSCREENER_API.format(mint)
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            if not data.get("pairs"):  # Pas de pool trouvé
                return {}
            # On prend la première pool trouvée (souvent la plus pertinente)
            pair = data["pairs"][0]
            return pair
    except Exception as e:
        print(f"[Erreur DexScreener] {mint}: {e}")
        return {}

def has_socials(pair: Dict) -> Dict:
    """
    Détecte la présence de liens sociaux (Twitter, Telegram) dans les données DexScreener.
    """
    socials = {"twitter": False, "telegram": False}
    links = pair.get("info", {}).get("links", {})
    if links:
        for k in links:
            if "twitter" in k.lower():
                socials["twitter"] = True
            if "telegram" in k.lower():
                socials["telegram"] = True
    return socials

async def main():
    seen_mints = set()
    print("[Bot Solana SPL] Démarrage du scan en continu...")
    async with aiohttp.ClientSession() as session:
        while True:
            new_mints = await get_new_mints(session, seen_mints)
            if new_mints:
                print(f"\n[+] {len(new_mints)} nouveau(x) token(s) détecté(s) !")
            tasks = [fetch_token_info(session, mint) for mint in new_mints]
            results = await asyncio.gather(*tasks)
            for mint, pair in zip(new_mints, results):
                if not pair:
                    continue  # Pas de pool DexScreener
                # Filtres bonus
                liquidity = float(pair.get("liquidity", {}).get("usd", 0))
                volume = float(pair.get("volume", {}).get("h24", 0))
                if liquidity < LIQUIDITY_FILTER and volume < VOLUME_FILTER:
                    continue  # Ignore tokens trop petits
                name = pair.get("baseToken", {}).get("name", "?")
                symbol = pair.get("baseToken", {}).get("symbol", "?")
                url = pair.get("url", "?")
                socials = has_socials(pair)
                print(f"\nToken: {name} ({symbol})")
                print(f"Mint: {mint}")
                print(f"Volume 24h: {volume:,.0f} $")
                print(f"Liquidité: {liquidity:,.0f} $")
                print(f"DexScreener: {url}")
                print(f"Twitter: {'Oui' if socials['twitter'] else 'Non'} | Telegram: {'Oui' if socials['telegram'] else 'Non'}")
            seen_mints.update(new_mints)
            await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt du bot.")
