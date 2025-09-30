import streamlit as st
import json
import os

# --- Fonction pour charger les stats ---
def load_stats():
    if not os.path.exists("stats.json"):
        return {}
    with open("stats.json", "r", encoding="utf-8") as f:
        return json.load(f)

# --- UI ---
st.set_page_config(page_title="Bot Dashboard", page_icon="🚀", layout="wide")
st.title("🚀 Dashboard du Bot")

# Charger les stats
stats = load_stats()

if not stats:
    st.warning("Aucune donnée disponible pour l'instant...")
else:
    # --- Style dynamique ---
    portfolio_balance = stats.get("portfolio_balance", 0.0)
    revenue_total = stats.get("revenue_total", 0.0)

    # 2 colonnes
    col1, col2 = st.columns(2)

    # Solde portefeuille
    col1.metric(
        "💰 Solde portefeuille",
        f"{portfolio_balance:.4f} SOL",
        delta=f"{revenue_total:.4f} SOL",
        delta_color="normal"
    )

    # Revenu total avec couleurs
    revenue_color = "green" if revenue_total >= 0 else "red"
    col2.markdown(
        f"""
        <div style="text-align:center; font-size:24px;">
            <strong>Revenu total</strong><br>
            <span style="color:{revenue_color}; font-size:28px;">
                {revenue_total:.4f} SOL
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

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

    if success_log:
        st.markdown("### ✅ Trades réussis")
        st.table(success_log)

    if fail_log:
        st.markdown("### ❌ Trades ratés")
        st.table(fail_log)
