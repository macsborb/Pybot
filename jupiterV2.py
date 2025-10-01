import os
import asyncio
import base64
import json
from typing import Optional

import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.keypair import Keypair
from solana.transaction import Transaction, TransactionInstruction
from solana.rpc.types import TxOpts
from solana.publickey import PublicKey

# compute budget instruction (solana-py)
try:
    # new solana-py exposes ComputeBudgetInstruction
    from solana.compute_budget import ComputeBudgetInstruction
    HAVE_COMPUTE_BUDGET = True
except Exception:
    HAVE_COMPUTE_BUDGET = False

# --- CONFIG ---
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v1/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v1/swap"
# mints
SOL_MINT = "So11111111111111111111111111111111111111112"  # wrapped SOL
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # mainnet USDC (change if other)
# slippage in percent
SLIPPAGE = 2  # 2%
# priority tip settings (tweakable)
# compute unit price in micro-lamports per CU (this value is a 'tip' — raise to be more competitive)
# Typical values: 0 (none), 10_000, 100_000, 1_000_000 ... bigger == more priority
PRIORITY_COMPUTE_UNIT_PRICE = 300_000  # tune this (increase to outbid others)
# optionally request extra compute units (not always needed)
REQUESTED_COMPUTE_UNITS = 400_000

# -----------------------------------------------------------------------------
# Helper: push a simple trade log for Streamlit (you can adapt: write to DB, queue, file)
def report_trade_to_streamlit(trade_dict: dict):
    # Exemple : écrire dans un fichier JSONL que ton Streamlit lit / refresh
    out_path = "trades_log.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(trade_dict, default=str) + "\n")


# -----------------------------------------------------------------------------
async def get_jupiter_quote(session: aiohttp.ClientSession, amount_in_lamports: int):
    params = {
        "inputMint": SOL_MINT,
        "outputMint": USDC_MINT,
        "amount": str(amount_in_lamports),
        "slippage": str(SLIPPAGE),
        # "onlyDirectRoutes": "true"  # optional
    }
    async with session.get(JUPITER_QUOTE_URL, params=params, timeout=10) as r:
        r.raise_for_status()
        data = await r.json()
        if not data.get("data"):
            raise RuntimeError("No route returned by Jupiter quote API: " + str(data))
        # choose best route (first)
        return data["data"][0]


async def get_jupiter_swap(session: aiohttp.ClientSession, route: dict, user_pubkey: str):
    payload = {
        "route": route,
        "userPublicKey": user_pubkey,
        "slippage": SLIPPAGE,
        # "wrapUnwrapSOL": True,  # optional, if swapping native SOL
    }
    headers = {"Content-Type": "application/json"}
    async with session.post(JUPITER_SWAP_URL, json=payload, headers=headers, timeout=20) as r:
        r.raise_for_status()
        data = await r.json()
        if "error" in data:
            raise RuntimeError("Jupiter swap error: " + str(data["error"]))
        # Jupiter returns fields like 'swapTransaction' (base64) and 'signatures' etc.
        return data


async def perform_swap_sol_to_usdc(keypair: Keypair, amount_sol: float):
    """
    Perform swap SOL -> USDC via Jupiter API using slippage SLIPPAGE and
    attempting to prepend a compute-budget priority tip.
    Returns dict with details and sends to report_trade_to_streamlit(...)
    """
    async with aiohttp.ClientSession() as session:
        amount_lamports = int(amount_sol * 1e9)  # 1 SOL = 1e9 lamports
        quote = await get_jupiter_quote(session, amount_lamports)

        # route summary
        in_amount = int(quote["inAmount"])
        out_amount = int(quote["outAmount"])
        price_approx = float(quote.get("price", 0))

        # request swap tx from Jupiter
        swap_resp = await get_jupiter_swap(session, quote, str(keypair.public_key))
        swap_tx_b64 = swap_resp.get("swapTransaction") or swap_resp.get("swapTxn") or swap_resp.get("swap_tx")
        if not swap_tx_b64:
            raise RuntimeError("No swap transaction returned by Jupiter: " + str(swap_resp))

        # decode tx
        raw_tx = base64.b64decode(swap_tx_b64)

        # Use the solana client to attach compute-budget instruction *before* sending.
        client = AsyncClient(RPC_URL)
        try:
            # try deserialize to Transaction (solana-py)
            tx = Transaction.deserialize(raw_tx)

            # Prepend ComputeBudget instructions if available
            if HAVE_COMPUTE_BUDGET:
                try:
                    # set price (micro-lamports per CU)
                    set_price_ix = ComputeBudgetInstruction.set_compute_unit_price(PRIORITY_COMPUTE_UNIT_PRICE)
                    request_units_ix = ComputeBudgetInstruction.request_units(REQUESTED_COMPUTE_UNITS, 0)
                    # insert at beginning
                    tx.instructions.insert(0, set_price_ix)
                    tx.instructions.insert(0, request_units_ix)
                except Exception as e:
                    # if API differs, skip but warn
                    print("Warning: couldn't add compute budget instruction:", e)

            # ensure recent blockhash / fee payer is our keypair
            resp = await client.get_recent_blockhash()
            rb = resp["result"]["value"]["blockhash"]
            tx.recent_blockhash = rb
            tx.fee_payer = keypair.public_key

            # sign locally
            tx.sign(keypair)

            # send raw transaction
            send_resp = await client.send_raw_transaction(tx.serialize(), opts=TxOpts(preflight_commitment="confirmed"))
            # send_resp contains 'result' with signature or error
            signature = send_resp.get("result")
            if not signature:
                raise RuntimeError("send_raw_transaction failed: " + json.dumps(send_resp))

            # confirm
            await client.confirm_transaction(signature, commitment="finalized")

            # build trade info for streamlit
            trade_info = {
                "time": asyncio.get_event_loop().time(),
                "amount_token_in": in_amount,
                "amount_token_out": out_amount,
                "buy_price": price_approx,
                "slippage_allowed_percent": SLIPPAGE,
                "priority_compute_unit_price": PRIORITY_COMPUTE_UNIT_PRICE,
                "signature": signature,
                "status": "confirmed",
            }
            report_trade_to_streamlit(trade_info)
            return trade_info

        except Exception as e:
            # if Transaction.deserialize fails (txn uses v1/v0 format unsupported), fallback: send raw base64 directly
            print("Deserialize/send fallback, error:", e)
            try:
                # try sending swap transaction raw as Jupiter returned it (might be already signed by jupiter unsigned though)
                send_resp = await client.send_raw_transaction(raw_tx, opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed"))
                signature = send_resp.get("result")
                if signature:
                    await client.confirm_transaction(signature, commitment="finalized")
                    trade_info = {
                        "time": asyncio.get_event_loop().time(),
                        "amount_token_in": in_amount,
                        "amount_token_out": out_amount,
                        "buy_price": price_approx,
                        "slippage_allowed_percent": SLIPPAGE,
                        "priority_compute_unit_price": PRIORITY_COMPUTE_UNIT_PRICE,
                        "signature": signature,
                        "status": "confirmed_fallback",
                    }
                    report_trade_to_streamlit(trade_info)
                    return trade_info
                else:
                    raise RuntimeError("Fallback send_raw_transaction failed: " + json.dumps(send_resp))
            finally:
                await client.close()
        finally:
            if not client.is_closed:
                await client.close()

# -----------------------------------------------------------------------------
# Example usage (test locally, never commit key on mainnet)
if __name__ == "__main__":
    import sys
    # load keypair from ENV or file (here expects base58-encoded secret key in env)
    sk_b58 = os.getenv("SOLANA_SECRET_KEY_BASE58")
    if not sk_b58:
        print("Please set SOLANA_SECRET_KEY_BASE58 env var (base58 of secret key). Aborting.")
        sys.exit(1)
    # create keypair
    import base58
    secret_bytes = base58.b58decode(sk_b58)
    kp = Keypair.from_secret_key(secret_bytes)

    amount = 0.05  # SOL, tune
    res = asyncio.run(perform_swap_sol_to_usdc(kp, amount))
    print("swap result:", res)
