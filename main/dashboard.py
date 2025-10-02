import streamlit as st
import json
import os
import pandas as pd
import time

st.set_page_config(page_title="🚀 Bot Dashboard", page_icon="🚀", layout="wide")
st.title("🚀 Dashboard du Bot")

# --------- Options Sidebar ----------
with st.sidebar:
    st.header("⚙️ Options")
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    refresh_sec = st.slider("Intervalle (sec)", 1, 10, 2)

    # Contrôle pause/reprise (via control.json)
    control_file = "control.json"
    if os.path.exists(control_file):
        with open(control_file, "r") as f:
            control = json.load(f)
    else:
        control = {"running": True}

    running = control.get("running", True)
    if running:
        if st.button("⏸️ Mettre en pause le bot"):
            control["running"] = False
            with open(control_file, "w") as f:
                json.dump(control, f)
            st.success("Bot mis en pause ✅")
    else:
        if st.button("▶️ Relancer le bot"):
            control["running"] = True
            with open(control_file, "w") as f:
                json.dump(control, f)
            st.success("Bot relancé ✅")

# --------- Lecture swaps ----------
def load_swaps(swap_dir="SWAP"):
    swaps = {}
    if not os.path.exists(swap_dir):
        return swaps

    for fname in os.listdir(swap_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(swap_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # clef = mint
            mint = data.get("inputMint") if "buy" in fname else data.get("outputMint")
            if mint not in swaps:
                swaps[mint] = {}
            if "buy" in fname:
                swaps[mint]["buy"] = data
            elif "sell" in fname:
                swaps[mint]["sell"] = data
        except Exception as e:
            st.error(f"Erreur lecture {fname}: {e}")
    return swaps

swaps = load_swaps()

# --------- Paramètres initiaux ----------
SOL_PRICE_USD = 220.0
initial_balance = st.sidebar.number_input("💵 Solde initial (SOL)", min_value=0.0, value=1.0, step=0.1)

# --------- Reconstruction trades ----------
successful_trades = []
failed_trades = []
rugpull_trades = []

portfolio_balance = initial_balance
revenue_total = 0.0

for mint, pair in swaps.items():
    buy = pair.get("buy")
    sell = pair.get("sell")

    if not buy:
        continue  # pas d'achat = ignorer

    buy_sol = float(buy.get("inAmount", 0))
    buy_price = float(buy.get("priceExecSolPerToken") or 0)
    amount_token = float(buy.get("outAmount", 0))

    if not sell:
        # Trade en attente
        continue

    sell_sol = float(sell.get("outAmount", 0))
    sell_price = float(sell.get("priceExecSolPerToken") or 0)

    pnl = sell_sol - buy_sol
    revenue_total += pnl
    portfolio_balance += pnl

    trade_data = {
        "time": sell.get("time", ""),
        "mint": f"https://dexscreener.com/solana/{mint}",
        "amount_token": amount_token,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "pnl": pnl,
        "equity_before": portfolio_balance - pnl,
        "equity_after": portfolio_balance
    }

    if pnl > 0:
        successful_trades.append(trade_data)
    else:
        failed_trades.append(trade_data)

# --------- Affichage stats globales ----------
col1, col2, col3 = st.columns(3)

portfolio_balance_usd = portfolio_balance * SOL_PRICE_USD
revenue_total_usd = revenue_total * SOL_PRICE_USD
pnl_percent_total = (revenue_total / initial_balance * 100) if initial_balance > 0 else 0.0

col1.metric("💰 Solde portefeuille", f"{portfolio_balance:.4f} SOL", f"≈ {portfolio_balance_usd:,.2f} $")
col2.metric("📊 PnL total", f"{revenue_total:.4f} SOL", f"{revenue_total_usd:+,.2f} $ / {pnl_percent_total:+.2f}%")
col3.metric("📈 Trades pris", len(successful_trades) + len(failed_trades))

st.markdown("---")

# --------- Détails trades ----------
def format_dataframe(logs, title, color):
    if not logs:
        st.info(f"Aucun {title}")
        return
    df = pd.DataFrame(logs)
    st.markdown(f"### {title}")
    df["pnl_usd"] = df["pnl"] * SOL_PRICE_USD
    df["pnl_percent"] = (df["pnl"] / df["equity_before"] * 100).map(lambda v: f"{v:+.2f}%" if pd.notna(v) else "")
    df["mint"] = df["mint"].apply(lambda x: f"[Lien Dexscreener]({x})")
    st.markdown(df.to_markdown(index=False), unsafe_allow_html=True)

format_dataframe(successful_trades, "✅ Trades réussis", "green")
format_dataframe(failed_trades, "❌ Trades ratés", "red")

# --------- Graphique évolution ---------
df_all = pd.DataFrame(successful_trades + failed_trades)
if not df_all.empty:
    df_all = df_all.sort_values("time")
    df_all["cum_pnl"] = df_all["pnl"].cumsum()
    df_all["equity_sol"] = initial_balance + df_all["cum_pnl"]
    df_all["equity_usd"] = df_all["equity_sol"] * SOL_PRICE_USD
    st.line_chart(df_all.set_index("time")[["equity_sol", "equity_usd"]])

# --------- Auto-refresh ----------
if auto_refresh:
    time.sleep(refresh_sec)
    st.experimental_rerun()
