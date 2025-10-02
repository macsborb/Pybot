// swap.ts
import fetch from "node-fetch";
import { Connection, Keypair, VersionedTransaction } from "@solana/web3.js";
import base58 from "bs58";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";

dotenv.config();

type Args = {
  inputMint: string;
  outputMint: string;
  amount: bigint;           // en base units de l'input
  slippageBps: number;      // ex 200 = 2%
  priorityLamports: bigint; // ex 100000 = 0.0001 SOL
  outPath: string;
};

function parseArgs(): Args {
  const argv = process.argv.slice(2);
  const get = (name: string, def?: string) => {
    const i = argv.findIndex(a => a === `--${name}`);
    if (i !== -1 && argv[i + 1]) return argv[i + 1];
    return def;
  };
  const required = (name: string) => {
    const v = get(name);
    if (!v) throw new Error(`Missing --${name}`);
    return v;
  };

  const inputMint = required("inputMint");
  const outputMint = required("outputMint");
  const amountStr = required("amount");
  const slippageBps = Number(get("slippageBps", "200")); // 2%
  const priorityLamportsStr = get("priorityLamports", "100000"); // 0.0001 SOL
  const outPathArg = get("out", "last_swap.json")!;
  const outPath = path.join("swap", outPathArg);

  const amount = BigInt(amountStr);
  const priorityLamports = BigInt(priorityLamportsStr);

  return { inputMint, outputMint, amount, slippageBps, priorityLamports, outPath };
}

async function getQuote(inputMint: string, outputMint: string, amount: bigint, slippageBps: number) {
  const url =
    `https://lite-api.jup.ag/swap/v1/quote?inputMint=${inputMint}` +
    `&outputMint=${outputMint}&amount=${amount.toString()}&slippageBps=${slippageBps}`;
  const resp = await fetch(url);
  const j = await resp.json();
  // console.log("Quote raw:", JSON.stringify(j, null, 2));
  if (j?.data && j.data.length > 0) return j.data[0];
  if (j?.inputMint && j?.outAmount) return j;
  return null;
}

async function buildSwap(quoteResponse: any, userPublicKey: string, priorityLamports: bigint) {
  const url = `https://lite-api.jup.ag/swap/v1/swap`;
  const body = {
    quoteResponse,
    userPublicKey,
    wrapAndUnwrapSol: true,
    dynamicComputeUnitLimit: true,
    dynamicSlippage: false,
    prioritizationFeeLamports: Number(priorityLamports),
  };
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await resp.json();
  if (!resp.ok) throw new Error(`Swap build error: ${JSON.stringify(j)}`);
  return j;
}

function findWalletIndexInKeys(parsed: any, walletStr: string): number {
  const keys = parsed?.transaction?.message?.accountKeys;
  if (!Array.isArray(keys)) return 0;
  for (let i = 0; i < keys.length; i++) {
    const k = typeof keys[i] === "string" ? keys[i] : keys[i]?.pubkey || "";
    if (k === walletStr) return i;
  }
  return 0;
}

function tokenAmountFor(balances: any[] | undefined, mint: string, owner: string): { amount: bigint, decimals: number } {
  if (!balances || !Array.isArray(balances)) return { amount: 0n, decimals: 0 };
  for (const b of balances) {
    // shapes: {accountIndex, mint, owner, uiTokenAmount:{amount,decimals,…}}
    const m = b?.mint;
    const o = b?.owner;
    if (m === mint && o === owner) {
      const dec = Number(b?.uiTokenAmount?.decimals ?? 0);
      const amtStr = String(b?.uiTokenAmount?.amount ?? "0");
      return { amount: BigInt(amtStr), decimals: dec };
    }
  }
  return { amount: 0n, decimals: 0 };
}

async function main() {

  const RPC = "https://api.mainnet-beta.solana.com";
  const conn = new Connection(RPC, "confirmed");

  // charge la clé
  const pk = "Your_Solana_Private_Key";
  const secretKey = base58.decode(pk);
  const wallet = Keypair.fromSecretKey(secretKey);
  const walletStr = wallet.publicKey.toBase58();

  const { inputMint, outputMint, amount, slippageBps, priorityLamports, outPath } = parseArgs();

  // 1) Quote
  const quote = await getQuote(inputMint, outputMint, amount, slippageBps);
  if (!quote) throw new Error("No quote found");

  // 2) Build swap tx
  const swapResp = await buildSwap(quote, walletStr, priorityLamports);
  const swapB64 = swapResp?.swapTransaction;
  if (!swapB64) throw new Error("No swapTransaction from swap API");

  // 3) Send
  const txn = VersionedTransaction.deserialize(Buffer.from(swapB64, "base64"));
  txn.sign([wallet]);
  console.log("[TS DEBUG] sending transaction...");
  const sig = await conn.sendTransaction(txn, { skipPreflight: true });
  await conn.confirmTransaction(sig, "confirmed");

  // 4) Parse executed amounts (vrai exécution)
  const parsed = await conn.getParsedTransaction(sig, {
    commitment: "confirmed",
    maxSupportedTransactionVersion: 0,
  });

  if (!parsed || !parsed.meta) {
    // fallback minimal
    fs.writeFileSync(outPath, JSON.stringify({
      signature: sig,
      inputMint, outputMint,
      // on renvoie au moins la quote convertie
      inAmountRaw: String(quote.inAmount),
      outAmountRaw: String(quote.outAmount),
      usedQuote: true,
      time: new Date().toISOString(),
      explorer: `https://solscan.io/tx/${sig}`,
    }, null, 2));
    console.log("✅ Swap sent (fallback logging).", `https://solscan.io/tx/${sig}`);
    return;
  }

  const meta = parsed.meta;
  const feeLamports: bigint = BigInt(meta.fee ?? 0);
  const walletIndex = findWalletIndexInKeys(parsed, walletStr);

  // SOL deltas
  const preSol = BigInt(meta.preBalances?.[walletIndex] ?? 0);
  const postSol = BigInt(meta.postBalances?.[walletIndex] ?? 0);
  const lamportsDelta = postSol - preSol; // positif si reçu plus de SOL, négatif si dépensé

  // Token deltas (pour l'owner = wallet)
  const preTokIn = tokenAmountFor(meta.preTokenBalances, inputMint, walletStr);
  const postTokIn = tokenAmountFor(meta.postTokenBalances, inputMint, walletStr);
  const deltaTokIn = (postTokIn.amount - preTokIn.amount); // devrait être négatif si on a dépensé l'input token

  const preTokOut = tokenAmountFor(meta.preTokenBalances, outputMint, walletStr);
  const postTokOut = tokenAmountFor(meta.postTokenBalances, outputMint, walletStr);
  const deltaTokOut = (postTokOut.amount - preTokOut.amount); // devrait être positif si on a reçu l'output token

  // Calcul des montants exécutés réels normalisés + priceExecSolPerToken
  const SOL_MINT = "So11111111111111111111111111111111111111112";
  const LAMPORTS_PER_SOL = 1_000_000_000n;

  let inAmountRaw = 0n;
  let outAmountRaw = 0n;
  let inDecimals = 0;
  let outDecimals = 0;
  let priceExecSolPerToken: number | null = null;

  if (inputMint === SOL_MINT) {
    // SOL -> token
    // lamports dépensés pour le swap = valeur nette + frais base + priority
    const lamportsSpentOnSwap = (preSol - postSol) - feeLamports - priorityLamports;
    inAmountRaw = lamportsSpentOnSwap > 0n ? lamportsSpentOnSwap : 0n;
    outAmountRaw = deltaTokOut > 0n ? deltaTokOut : 0n;
    inDecimals = 9;
    outDecimals = postTokOut.decimals || preTokOut.decimals || 0;

    const inSol = Number(inAmountRaw) / 1e9;
    const outTokens = outDecimals ? Number(outAmountRaw) / Math.pow(10, outDecimals) : 0;
    priceExecSolPerToken = (inSol > 0 && outTokens > 0) ? (inSol / outTokens) : null;

  } else if (outputMint === SOL_MINT) {
    // token -> SOL
    // lamports reçus du swap = delta net + frais + priority
    const lamportsReceivedFromSwap = (postSol - preSol) + feeLamports + priorityLamports;
    outAmountRaw = lamportsReceivedFromSwap > 0n ? lamportsReceivedFromSwap : 0n;
    // tokens dépensés (positif)
    inAmountRaw = (preTokIn.amount - postTokIn.amount);
    if (inAmountRaw < 0n) inAmountRaw = 0n;
    inDecimals = postTokIn.decimals || preTokIn.decimals || 0;
    outDecimals = 9;

    const outSol = Number(outAmountRaw) / 1e9;
    const inTokens = inDecimals ? Number(inAmountRaw) / Math.pow(10, inDecimals) : 0;
    // prix SOL/token
    priceExecSolPerToken = (inTokens > 0 && outSol > 0) ? (outSol / inTokens) : null;

  } else {
    // token -> token (si jamais tu t'en sers un jour)
    inAmountRaw = (preTokIn.amount - postTokIn.amount);
    if (inAmountRaw < 0n) inAmountRaw = 0n;
    outAmountRaw = deltaTokOut > 0n ? deltaTokOut : 0n;
    inDecimals = postTokIn.decimals || preTokIn.decimals || 0;
    outDecimals = postTokOut.decimals || preTokOut.decimals || 0;
    priceExecSolPerToken = null; // pas de SOL directement
  }

  const outJson = {
    signature: sig,
    explorer: `https://dexscreener.com//${sig}`,
    inputMint, outputMint,
    inAmountRaw: inAmountRaw.toString(),
    outAmountRaw: outAmountRaw.toString(),
    inDecimals,
    outDecimals,
    // normalisés (pratique côté Python)
    inAmount: inDecimals ? Number(inAmountRaw) / Math.pow(10, inDecimals) : Number(inAmountRaw) / 1e9,
    outAmount: outDecimals ? Number(outAmountRaw) / Math.pow(10, outDecimals) : Number(outAmountRaw) / 1e9,
    priceExecSolPerToken,    // prix réel exécuté (SOL/token) si SOL est impliqué
    feeLamports: Number(feeLamports),
    priorityLamports: Number(priorityLamports),
    time: new Date().toISOString(),
  };

  fs.writeFileSync(outPath, JSON.stringify(outJson, null, 2));
  console.log("✅ Swap confirmé:", outJson.explorer);
}

main().catch(e => {
  console.error("Erreur swap:", e);
  process.exit(1);
});
