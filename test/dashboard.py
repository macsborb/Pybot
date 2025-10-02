import streamlit as st
import json
import os
import pandas as pd
import time

st.set_page_config(page_title="Bot Dashboard", page_icon="🚀", layout="wide")
st.title("🚀 Dashboard du Bot")

# --------- Paramètres UI ----------
with st.sidebar:
    st.header("⚙️ Options")
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    refresh_sec = st.slider("Intervalle (sec)", 1, 10, 2)

# --- Fonction pour charger les stats ---
def load_stats():
    if not os.path.exists("stats.json"):
        return {}
    with open("stats.json", "r", encoding="utf-8") as f:
        return json.load(f)

# Timer de session (affichage)
if "start_time" not in st.session_state:
    st.session_state["start_time"] = time.time()

# Charger les stats
stats = load_stats()

if not stats:
    st.warning("Aucune donnée disponible pour l'instant...")
else:
    # --- Bases ---
    portfolio_balance = float(stats.get("portfolio_balance", 0.0))
    revenue_total = float(stats.get("revenue_total", 0.0))

    # Conversion en USD
    SOL_PRICE_USD = 208.72
    portfolio_balance_usd = portfolio_balance * SOL_PRICE_USD
    revenue_total_usd = revenue_total * SOL_PRICE_USD

    # initial_balance : pris depuis stats, sinon approx
    initial_balance = stats.get("initial_balance", None)
    if initial_balance is None:
        initial_balance = portfolio_balance - revenue_total
    initial_balance = float(initial_balance)

    pnl_percent_total = (revenue_total / initial_balance * 100) if initial_balance > 0 else 0.0

    # 3 colonnes
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "💰 Solde portefeuille",
        f"{portfolio_balance:.4f} SOL (~${portfolio_balance_usd:,.2f})",
        delta=f"{revenue_total:.4f} SOL ({revenue_total_usd:+,.2f} $ / {pnl_percent_total:+.2f}%)"
    )

    revenue_color = "green" if revenue_total >= 0 else "red"
    col2.markdown(
        f"""
        <div style="text-align:center; font-size:24px;">
          <strong>Revenu total</strong><br>
          <span style="color:{revenue_color}; font-size:28px;">
            {revenue_total:.4f} SOL<br>
            ({pnl_percent_total:+.2f}%)<br>
            <span style="font-size:20px;">≈ {revenue_total_usd:+,.2f} USD</span>
          </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    elapsed_seconds = int(time.time() - st.session_state["start_time"])
    h, rem = divmod(elapsed_seconds, 3600)
    m, s = divmod(rem, 60)
    col3.metric("⏱️ Temps depuis ouverture", f"{h:02d}:{m:02d}:{s:02d}")

    st.markdown("---")

    # --- Détails des trades ---
    st.subheader("📊 Détails des trades")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Trades pris", stats.get("trade_count", 0))
    c2.metric("Trades réussis ✅", stats.get("successful_trades", 0))
    c3.metric("Trades ratés ❌", stats.get("nosuccessful_trades", 0))
    c4.metric("Rug Pull 💀", stats.get("rugged_count", 0))
    c5.metric("Trades en cours ⏳", stats.get("pending_trades", 0))

    st.markdown("---")

    # --- Historique des trades ---
    st.subheader("📜 Historique")

    success_log = stats.get("successful_trades_log", [])
    fail_log = stats.get("nosuccessful_trades_log", [])
    rugpull_log = stats.get("rugpull_trades_log", [])

    def format_dataframe(logs, title):
        if not logs:
            return pd.DataFrame()
        st.markdown(f"### {title}")
        df = pd.DataFrame(logs)

        # Nettoyage types
        for col in ("pnl", "buy_price", "sell_price", "equity_before", "equity_after"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Conversion en USD pour le PNL
        if "pnl" in df:
            df["pnl_usd"] = df["pnl"] * SOL_PRICE_USD

        # Lien Dexscreener
        if "mint" in df:
            df["mint"] = df["mint"].apply(
                lambda x: f"[Lien Dexscreener]({x})" if isinstance(x, str) and x.startswith("http") else x
            )

        # % PNL par trade
        if "pnl" in df:
            if "equity_before" in df and df["equity_before"].notna().any():
                df["pnl_percent"] = (df["pnl"] / df["equity_before"] * 100).map(lambda v: f"{v:+.2f}%")
            else:
                df["pnl_percent"] = (df["pnl"] / initial_balance * 100).map(lambda v: f"{v:+.2f}%")

            # mise en forme
            df["pnl"] = df["pnl"].map(lambda v: f"{v:.6f}" if pd.notna(v) else v)
            df["pnl_usd"] = df["pnl_usd"].map(lambda v: f"{v:+.2f} $" if pd.notna(v) else v)

        if "buy_price" in df:
            df["buy_price"] = df["buy_price"].map(lambda v: f"{float(v):.12f}" if pd.notna(v) else v)
        if "sell_price" in df:
            df["sell_price"] = df["sell_price"].map(lambda v: f"{float(v):.12f}" if pd.notna(v) else v)
        if "amount_token" in df:
            df["amount_token"] = df["amount_token"].map(lambda v: f"{float(v):,.2f}" if pd.notna(v) else v)

        # Colonnes réordonnées
        cols = []
        for c in ("time","mint","amount_token","buy_price","sell_price","pnl","pnl_usd","pnl_percent"):
            if c in df.columns: cols.append(c)
        df = df[cols]

        df = df.rename(columns={
            "time": "⏰ time",
            "mint": "🎯 mint",
            "amount_token": "📦 amount_token",
            "buy_price": "🟢 buy_price (SOL/token)",
            "sell_price": "🔴 sell_price (SOL/token)",
            "pnl": "💰 pnl (SOL)",
            "pnl_usd": "💵 pnl (USD)",
            "pnl_percent": "📈 pnl (%)"
        })

        st.markdown(df.to_markdown(index=False), unsafe_allow_html=True)
        return df

    df_success = format_dataframe(success_log, "✅ Trades réussis")
    df_fail    = format_dataframe(fail_log,   "❌ Trades ratés")
    df_rug     = format_dataframe(rugpull_log,"💀 Rug Pulls")

    st.markdown("---")

    # --- Graphique d'évolution ---
    st.subheader("📈 Évolution du portefeuille")

    df_all = pd.concat([pd.DataFrame(success_log),
                        pd.DataFrame(fail_log),
                        pd.DataFrame(rugpull_log)],
                       ignore_index=True)

    if not df_all.empty and "pnl" in df_all:
        df_all["pnl"] = pd.to_numeric(df_all["pnl"], errors="coerce").fillna(0.0)
        df_all["cum_pnl"] = df_all["pnl"].cumsum()
        df_all["equity_sol"] = initial_balance + df_all["cum_pnl"]
        df_all["cum_pnl_usd"] = df_all["cum_pnl"] * SOL_PRICE_USD
        df_all["equity_usd"] = df_all["equity_sol"] * SOL_PRICE_USD

        # convertir time
        df_all["time_dt"] = pd.to_datetime(df_all["time"], format="%H:%M:%S", errors="coerce")
        df_all = df_all.sort_values("time_dt")

        chart = df_all.set_index("time_dt")[["cum_pnl","equity_sol","cum_pnl_usd","equity_usd"]]
        chart = chart.rename(columns={
            "cum_pnl":"PNL cumulé (SOL)",
            "equity_sol":"Équity (SOL)",
            "cum_pnl_usd":"PNL cumulé (USD)",
            "equity_usd":"Équity (USD)"
        })
        st.line_chart(chart, height=400)
    else:
        st.info("Aucun trade pour générer le graphique.")

# --- Auto-refresh ---
if auto_refresh:
    time.sleep(refresh_sec)
    st.experimental_rerun()
