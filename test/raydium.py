import aiohttp
import asyncio

RAY_API = "https://api.raydium.io/v2/sdk/liquidity/mainnet.json"

async def get_price_via_raydium(mint: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(RAY_API) as resp:
            if resp.status != 200:
                print("❌ Erreur API:", resp.status)
                return None

            pools = await resp.json()

            # 📌 ici 'pools' est souvent un dict avec 'official' et 'unOfficial'
            if isinstance(pools, dict):
                all_pools = pools.get("official", []) + pools.get("unOfficial", [])
            elif isinstance(pools, list):
                all_pools = pools
            else:
                print("⚠️ Format de réponse inattendu :", type(pools))
                return None

            candidate = None
            for pool in all_pools:
                base_mint = pool.get("baseMint")
                quote_mint = pool.get("quoteMint")

                if mint in [base_mint, quote_mint]:
                    # Priorité : USDC, USDT, SOL comme contrepartie
                    if (
                        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" in [base_mint, quote_mint] or
                        "Es9vMFrzaCERcKZHz4x6aFz2F7h6z5Q6znk5v5h1hF1" in [base_mint, quote_mint] or
                        "So11111111111111111111111111111111111111112" in [base_mint, quote_mint]
                    ):
                        candidate = pool
                        break

            if not candidate:
                print("❌ Aucun pool trouvé pour ce mint.")
                return None

            base_reserve = float(candidate.get("baseReserve", 0))
            quote_reserve = float(candidate.get("quoteReserve", 0))
            base_mint = candidate.get("baseMint")
            quote_mint = candidate.get("quoteMint")

            if base_reserve == 0 or quote_reserve == 0:
                print("⚠️ Réserves invalides.")
                return None

            # 📈 Calcule le prix en fonction de la position du mint
            if mint == base_mint:
                price = quote_reserve / base_reserve
            else:
                price = base_reserve / quote_reserve

            print(f"✅ Prix estimé de {mint}: {price} USD")
            return price


async def main():
    mint = "So11111111111111111111111111111111111111112"  # SOL
    price = await get_price_via_raydium(mint)
    print("💰 Prix final:", price)

asyncio.run(main())
