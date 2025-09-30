import requests
import time
from datetime import datetime

# 📍 RPC public de Solana (tu peux changer pour QuickNode ou Helius pour plus de vitesse)
RPC_URL = "https://api.mainnet-beta.solana.com"

# 📍 Adresse du programme SPL Token – tous les tokens créés passent par lui
SPL_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# 📍 DexScreener API base
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/"

# 📍 Pour éviter de revoir les mêmes tokens
seen_tokens = set()

def get_recent_transactions(limit=50):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [SPL_PROGRAM_ID, {"limit": limit}]
    }
    r = requests.post(RPC_URL, json=payload)
    return r.json().get("result", [])

def get_transaction_detail(signature):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    r = requests.post(RPC_URL, json=payload)
    if r.status_code == 429 or (r.json().get("error", {}).get("code") == 429):
        print("⏳ Rate limit atteint, pause de 30 secondes...")
        time.sleep(30)
        return get_transaction_detail(signature)
    try:
        result = r.json().get("result", {})
        if not result:
            print(f"Aucune donnée pour la transaction {signature}. Réponse brute : {r.text}")
        return result
    except Exception as e:
        print(f"Erreur lors du décodage JSON pour la transaction {signature} : {e}\nRéponse brute : {r.text}")
        return {}

def extract_new_mints(tx):
    """Détecte les nouveaux tokens créés dans une transaction en analysant les instructions initializeMint, y compris dans innerInstructions."""
    new_mints = set()
    if not tx or "transaction" not in tx or "message" not in tx["transaction"]:
        return list(new_mints)

    # Instructions principales
    instructions = tx["transaction"]["message"].get("instructions", [])
    all_instructions = list(instructions)

    # Ajout des innerInstructions si elles existent
    meta = tx.get("meta", {})
    for inner in meta.get("innerInstructions", []):
        all_instructions.extend(inner.get("instructions", []))

    for ix in all_instructions:
        # On vérifie que c'est bien le programme SPL Token
        if ix.get("programId") == SPL_PROGRAM_ID:
            accounts = ix.get("accounts", [])
            if accounts:
                mint = accounts[0]
                new_mints.add(mint)
    return list(new_mints)

def check_dexscreener(token_ca):
    r = requests.get(DEXSCREENER_URL + token_ca)
    if r.status_code != 200:
        return None
    data = r.json()
    if "pairs" not in data:
        return None
    return data["pairs"]

def main():
    print("🚀 Scanner lancé... détection de nouveaux tokens SPL en continu.\n")

    while True:
        txs = get_recent_transactions(limit=20)
        print(f"⏰ Vérification à {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {len(txs)} transactions récentes récupérées.")
        for tx in txs:
            sig = tx["signature"]
            detail = get_transaction_detail(sig)
            new_tokens = extract_new_mints(detail)
            print(f"🔍 Transaction {sig} - Nouveaux tokens détectés : {new_tokens}")
            print("--------------------------------------------------")
            for mint in new_tokens:
                if mint not in seen_tokens:
                    seen_tokens.add(mint)
                    print(f"\n📍 Nouveau token détecté : {mint}")

                    # Vérification sur DexScreener
                    pairs = check_dexscreener(mint)
                    if pairs:
                        for p in pairs:
                            print("✅ Token trouvé sur DexScreener :")
                            print(f"   - Nom       : {p.get('baseToken', {}).get('name')}")
                            print(f"   - Symbole   : {p.get('baseToken', {}).get('symbol')}")
                            print(f"   - Volume 24h: {p.get('volume', {}).get('h24')} USD")
                            print(f"   - Liquidité : {p.get('liquidity', {}).get('usd')} USD")
                            print(f"   - URL Dex   : {p.get('url')}")
                    else:
                        print("⚠️ Pas encore listé sur DexScreener.")

        time.sleep(10)  # vérifie toutes les 10 secondes

if __name__ == "__main__":
    main()
