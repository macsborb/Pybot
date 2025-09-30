import aiohttp
import asyncio

async def get_jupiter_swap_price(input_mint, output_mint, amount_in_lamports):
    url = f"https://quote-api.jup.ag/v6/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amount_in_lamports}&slippageBps=1000"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if "routePlan" not in data or not data["routePlan"]:
                print("⚠️ Aucune route trouvée. Réponse complète :", data)
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
                "amm": route["label"]
            }

