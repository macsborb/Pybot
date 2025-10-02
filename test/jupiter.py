import aiohttp
import asyncio

async def get_jupiter_swap_price(input_mint, output_mint, amount_in_lamports):
    url = (
        f"https://lite-api.jup.ag/swap/v1/quote"
        f"?inputMint={input_mint}&outputMint={output_mint}"
        f"&amount={amount_in_lamports}&slippageBps=100"
    )
    try:
        timeout = aiohttp.ClientTimeout(total=10)  # timeout 10 sec max
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"❌ Erreur HTTP {resp.status} sur Jupiter API : {text[:200]}...")
                    return None
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    print(f"⚠️ Réponse non-JSON : {text[:200]}...")
                    return None

                if not data or "routePlan" not in data or not data["routePlan"]:
                    print("⚠️ Aucune route trouvée pour ce token.")
                    return None

                route = data["routePlan"][0]["swapInfo"]
                in_amount = int(route["inAmount"])
                out_amount = int(route["outAmount"])
                fee_amount = int(route["feeAmount"])
                price_per_token = out_amount / in_amount if in_amount else 0

                return {
                    "in_amount": in_amount,
                    "out_amount": out_amount,
                    "fee_amount": fee_amount,
                    "price_per_token": price_per_token,
                    "amm": route["label"],
                }
    except Exception as e:
        print(f"⚠️ Exception lors de la requête Jupiter: {e}")
        return None
