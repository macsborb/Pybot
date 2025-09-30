import aiohttp
import asyncio

DEXSCREENER_LATEST = "https://api.dexscreener.com/token-boosts/latest/v1"

async def fetch_latest(limit=10):
    async with aiohttp.ClientSession() as session:
        async with session.get(DEXSCREENER_LATEST) as resp:
            if resp.status != 200:
                print(f"❌ Erreur API DexScreener: {resp.status}")
                return

            data = await resp.json()
            tokens = data if isinstance(data, list) else data.get("tokens", data)
            # Si la réponse est une liste, on la prend, sinon on cherche une clé 'tokens' (sécurité)

            print(f"📊 Derniers {limit} tokens listés (Solana uniquement):\n")
            count = 0
            for token in tokens:
                if token.get("chainId") != "solana":
                    continue
                name = token.get("tokenAddress")  # Pas de nom dans la réponse, on affiche l'adresse
                address = token.get("tokenAddress")
                url = token.get("url")
                icon = token.get("icon")
                header = token.get("header")
                description = token.get("description", "")
                # Socials
                twitter = None
                telegram = None
                website = None
                for link in token.get("links", []):
                    if link.get("type", "").lower() == "twitter" or "twitter" in link.get("url", "").lower():
                        twitter = link.get("url")
                    if link.get("type", "").lower() == "telegram" or "t.me" in link.get("url", "").lower():
                        telegram = link.get("url")
                    if link.get("label", "").lower() == "website" or "website" in link.get("label", "").lower():
                        website = link.get("url")
                print(f"🆕 Mint: {address}")
                print(f"   DexScreener: {url}")
                print(f"   Icon: {icon}")
                print(f"   Header: {header}")
                print(f"   Description: {description}")
                print(f"   Twitter: {twitter}")
                print(f"   Telegram: {telegram}")
                print(f"   Website: {website}\n")
                count += 1
                if count >= limit:
                    break

asyncio.run(fetch_latest(10))
