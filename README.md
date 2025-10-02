# PyBot: Automated Solana Trading Bot

## 🚀 Overview

**PyBot** is a high-frequency, non-stop automated trading bot designed to detect new token pairs and execute trades on the **Solana** blockchain. It operates in two primary modes: **Live Trading** (using real on-chain swaps via the TypeScript utility `swap.ts`) and **Simulation Mode** (for risk-free strategy testing using the Python utility `jupiter.py`).

The bot is built for continuous, automated interaction with the Solana decentralized exchange (DEX) environment.

-----

## ✨ Features

  * **Non-Stop Trading:** Designed to run 24/7, listening for new token liquidity pools via the SolanaStreaming WebSocket API.
  * **Live Trading (`main.py`):** Executes real swaps on the Solana network using the **Jupiter Aggregator** by calling a TypeScript helper (`swap.ts`) via `subprocess`.
  * **Simulation Mode (`test.py`):** Simulates a full trade cycle (buy and sell) using price quotes from the Jupiter API without executing real transactions.
  * **Two Streamlit Dashboards:** The project provides dedicated dashboards for real-time monitoring of each mode.

-----

## 🛠️ Getting Started

### Prerequisites

You need both a **Python** environment and a **Node.js/TypeScript** environment set up.

1.  **Python 3.7.9+** (The project is configured for this version).
2.  **Node.js & npm/yarn** (Required for the `swap.ts` on-chain execution utility).
3.  **API Key:** A valid **SolanaStreaming API Key** is required in `main.py` and `test.py`.

### 1\. Python Setup

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/PyBot.git
    cd PyBot
    ```

2.  **Setup Virtual Environment and Install Dependencies:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Linux/macOS
    # .\venv\Scripts\activate  # On Windows

    # Install dependencies from the generated file
    pip install -r requirements.txt
    ```

### 2\. TypeScript/Node.js Setup (For Live Trading Only)

The Live Trading script (`main.py`) relies on `swap.ts` for transaction execution.

1.  **Install Global TypeScript Execution Tool:**
    Ensure you can run the `npx ts-node` command:

    ```bash
    npm install -g ts-node typescript
    ```

2.  **Install Project-Specific Node Dependencies** (in the directory containing `swap.ts`):
    The `swap.ts` file requires several Solana/Node packages:

    ```bash
    # Run these commands in the directory where swap.ts is located, usually the root 'PyBot/main' directory
    npm install @solana/web3.js bs58 dotenv node-fetch
    ```

    ***Note on Path:*** *The `main.py` script executes `swap.ts` using a hardcoded path (`C:/Users/soonb/Desktop/Pybot/jup-swap/swap.ts`). You **must** update this path within `main.py` to match your local setup for live trading to work.*

-----

## ▶️ Running PyBot and Dashboards

### 1\. Launching the Trading Bot

| Mode | Main File | Command | Log Files Used |
| :--- | :--- | :--- | :--- |
| **Live Trading** | `main/main.py` | `python main/main.py` | Writes to `SWAP/*.json` |
| **Simulation** | `test/test.py` | `python test/test.py` | Writes to `test/stats.json`, `test/result.txt` |

### 2\. Launching the Dashboards

The dashboard is launched using the Streamlit command with the file path.

| Dashboard | File | Launch Command | Status |
| :--- | :--- | :--- | :--- |
| **Main** | `main/dashboard.py` | `python -m streamlit run main/dashboard.py` | **Currently under development.** It reads real trade data from the `SWAP/` directory. It **does not** accurately reflect simulation results from `test.py`. |
| **Test** | `test/dashboard.py` | `python -m streamlit run test/dashboard.py` | **Perfectly Functional.** This dashboard is specifically designed to read and display the detailed stats and PnL logs from `test/stats.json` and `test/result.txt` (the simulation files). **This is the recommended dashboard for monitoring the Simulation Bot.** |

-----

## 📂 Project Structure

*(Based on the provided image)*

```
PYBOT/
├── main/                           # Live Trading Environment
│   ├── node_modules/
│   ├── swap/                       # Directory for swap.ts output files
│   ├── .env
│   ├── control.json                # Used to Pause/Run the bot
│   ├── dashboard.py                # Main Dashboard (Reads SWAP/ files - currently buggy)
│   ├── main.py                     # Core LIVE trading logic (calls swap.ts)
│   ├── package-lock.json
│   ├── package.json
│   ├── swap.ts                     # TypeScript script for real on-chain swap execution
│   └── tsconfig.json
├── test/                           # Simulation/Test Environment
│   ├── other_func/
│   ├── dashboard.py                # Test Dashboard (Reads stats.json - perfectly functional)
│   ├── jupiter.py                  # Utility for getting Jupiter price quotes (Python)
│   ├── result.txt                  # Log of completed trades
│   ├── stats.json                  # PnL tracking log for simulation mode
│   └── test.py                     # Core SIMULATION logic (calls jupiter.py for price)
└── requirements.txt                # Python dependencies (must be created)
└── LICENSE                         # MIT License details (must be created)
```

-----

## 🤝 Contributing

Contributions, issues, and feature requests are welcome\!

-----

## 📜 License

This project is released under the **MIT License**.

-----
