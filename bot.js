import "dotenv/config";
import { ethers } from "ethers";

const req = (k) => {
  const v = process.env[k];
  if (!v) throw new Error(`ENV kosong: ${k}`);
  return v;
};

const MODE = (process.env.MODE || "eth").toLowerCase(); // eth | base

const CFG = {
  eth: {
    name: "ETH",
    chainId: 1,
    ws: req("ETH_WS_RPC"),
    http: req("ETH_HTTP_RPC"),
    contract: req("ETH_CONTRACT"),
    gasUsdCap: Number(req("ETH_GAS_USD_CAP")),
    prioGwei: Number(req("ETH_PRIORITY_GWEI")),
  },
  base: {
    name: "BASE",
    chainId: 8453,
    ws: req("BASE_WS_RPC"),
    http: req("BASE_HTTP_RPC"),
    contract: req("BASE_CONTRACT"),
    gasUsdCap: Number(req("BASE_GAS_USD_CAP")),
    prioGwei: Number(req("BASE_PRIORITY_GWEI")),
  },
}[MODE];

const GAS_LIMIT = BigInt(process.env.GAS_LIMIT || "180000");
const MINT_FN = req("MINT_FN");
const MINT_ARGS = JSON.parse(process.env.MINT_ARGS || "[]");
const MINT_PRICE_ETH = process.env.MINT_PRICE_ETH ? Number(process.env.MINT_PRICE_ETH) : 0;
const PENDING_CHECK_EVERY_BLOCKS = Number(process.env.PENDING_CHECK_EVERY_BLOCKS || "1");
const BUMP_MULT = Number(process.env.BUMP_MULT || "1.18");
const MAX_BUMPS = Number(process.env.MAX_BUMPS || "6");

const PKS = Array.from({ length: 10 }, (_, i) => process.env[`PK_${i + 1}`]).filter(Boolean);

function short(addr) {
  return addr.slice(0, 6) + "..." + addr.slice(-4);
}

// ===== Minimal ABI =====
// Kalau function mint kamu beda signature, cukup ganti ABI di bawah sesuai contract.
const ABI = [
  `function ${MINT_FN}(${""}) payable`,
];

function buildIface() {
  // ABI di atas cuma placeholder. Kita akan encode pakai fragment dinamis:
  // supaya tetap bisa jalan dengan args JSON.
  // Cara paling aman: kamu isi ABI yang benar kalau args-nya non-trivial.
  //
  // Untuk banyak kasus sederhana (mint() / publicMint()) ini cukup.
  return new ethers.Interface([
    `function ${MINT_FN}(${MINT_ARGS.map(() => "uint256").join(",")}) payable`,
  ]);
}

async function getEthUsdFallback() {
  // Tanpa web price feed: kita pakai nilai perkiraan agar hardcap tetap “masuk akal”.
  // Kamu bisa ganti manual kalau mau lebih presisi.
  return 2500; // USD per ETH (perkiraan)
}

function capMaxFeePerGasGwei({ gasUsdCap, gasLimit, ethUsd }) {
  // gasUSD = gasLimit * maxFeePerGas(ETH) * ethUsd
  // maxFeePerGas(ETH) <= gasUSD / (gasLimit*ethUsd)
  const maxFeeEth = gasUsdCap / (Number(gasLimit) * ethUsd);
  const gwei = maxFeeEth * 1e9; // 1 gwei = 1e-9 ETH
  return Math.max(0.000000001, gwei);
}

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function fireOneWallet({
  wallet,
  providerHttp,
  txTemplate,
  ethUsd,
}) {
  const addr = await wallet.getAddress();

  // Saldo check: saldo >= mintValue + gasCap(USD -> ETH)
  const bal = await providerHttp.getBalance(addr);

  const gasCapEth = CFG.gasUsdCap / ethUsd; // ETH
  const needEth = MINT_PRICE_ETH + gasCapEth;

  const balEth = Number(ethers.formatEther(bal));
  if (balEth + 1e-12 < needEth) {
    return {
      wallet: addr,
      status: "SKIP_BALANCE",
      reason: `saldo ${balEth.toFixed(6)} < need ${needEth.toFixed(6)}`,
    };
  }

  // nonce fixed untuk RBF
  const nonce = await providerHttp.getTransactionCount(addr, "pending");

  let bump = 0;
  let lastHash = null;

  while (bump <= MAX_BUMPS) {
    // hitung maxFeePerGas (gwei) patuh cap USD
    let maxFeeGwei = capMaxFeePerGasGwei({
      gasUsdCap: CFG.gasUsdCap,
      gasLimit: GAS_LIMIT,
      ethUsd,
    });

    // agresif: naikkan maxFee berdasarkan bump
    maxFeeGwei = maxFeeGwei * Math.pow(BUMP_MULT, bump);

    // tapi tetap jangan lewat cap (re-cap)
    const maxFeeGweiCapped = Math.min(
      maxFeeGwei,
      capMaxFeePerGasGwei({ gasUsdCap: CFG.gasUsdCap, gasLimit: GAS_LIMIT, ethUsd })
    );

    const prioGwei = Math.min(CFG.prioGwei * Math.pow(BUMP_MULT, bump), maxFeeGweiCapped);

    const tx = {
      ...txTemplate,
      nonce,
      gasLimit: GAS_LIMIT,
      maxFeePerGas: ethers.parseUnits(maxFeeGweiCapped.toFixed(9), "gwei"),
      maxPriorityFeePerGas: ethers.parseUnits(prioGwei.toFixed(9), "gwei"),
      type: 2,
      chainId: CFG.chainId,
    };

    try {
      const sent = await wallet.sendTransaction(tx);
      lastHash = sent.hash;

      // tunggu sebentar, kalau masuk ya selesai
      const receipt = await sent.wait(1).catch(() => null);
      if (receipt) {
        return {
          wallet: addr,
          txHash: sent.hash,
          status: receipt.status === 1 ? "SUCCESS" : "FAILED",
          gasUsdCap: CFG.gasUsdCap,
          mintPriceEth: MINT_PRICE_ETH,
        };
      }

      // pending -> bump
      bump += 1;
    } catch (e) {
      // kalau "replacement fee too low" / nonce issue -> bump lagi
      bump += 1;
      await wait(150);
    }
  }

  return {
    wallet: addr,
    txHash: lastHash,
    status: "PENDING_OR_FAILED",
    gasUsdCap: CFG.gasUsdCap,
    mintPriceEth: MINT_PRICE_ETH,
  };
}

async function main() {
  console.log(`\n=== FCFS BOT (${CFG.name}) ===`);

  if (PKS.length === 0) throw new Error("PK_1..PK_10 belum diisi");

  const wsProvider = new ethers.WebSocketProvider(CFG.ws);
  const httpProvider = new ethers.JsonRpcProvider(CFG.http);

  const net = await httpProvider.getNetwork();
  if (Number(net.chainId) !== CFG.chainId) {
    throw new Error(`ChainId mismatch: RPC=${net.chainId} cfg=${CFG.chainId}`);
  }

  // Prebuild calldata
  // Catatan: untuk function dengan argumen non-uint, sebaiknya kamu isi ABI yang benar.
  const iface = buildIface();
  const data = iface.encodeFunctionData(MINT_FN, MINT_ARGS);

  const mintValue = ethers.parseEther(String(MINT_PRICE_ETH));

  const txTemplate = {
    to: CFG.contract,
    data,
    value: mintValue,
  };

  console.log("RPC OK ✅", "chainId =", CFG.chainId);
  console.log("Contract =", CFG.contract);
  console.log("Mint fn =", MINT_FN, "args =", JSON.stringify(MINT_ARGS));
  console.log("Mint price (ETH) =", MINT_PRICE_ETH);
  console.log("GasLimit preset =", GAS_LIMIT.toString());
  console.log("Gas USD cap =", CFG.gasUsdCap);

  // ===== Trigger: cek “mint live” via callStatic (eth_call)
  // Strategi: kita coba simulate call. Kalau revert -> belum live.
  async function isLive() {
    try {
      await httpProvider.call({
        to: txTemplate.to,
        data: txTemplate.data,
        value: txTemplate.value,
      });
      return true;
    } catch {
      return false;
    }
  }

  let fired = false;

  wsProvider.on("block", async (bn) => {
    if (fired) return;

    // cek tiap block
    const live = await isLive();
    process.stdout.write(`\rBlock ${bn} | live=${live ? "YES" : "no "}   `);

    if (!live) return;

    fired = true;
    console.log(`\n\n🔥 FIRE MODE! block=${bn}\n`);

    const ethUsd = await getEthUsdFallback();

    const wallets = PKS.map((pk) => new ethers.Wallet(pk, httpProvider));

    const results = await Promise.all(
      wallets.map((w) =>
        fireOneWallet({
          wallet: w,
          providerHttp: httpProvider,
          txTemplate,
          ethUsd,
        })
      )
    );

    console.log("\n=== RESULT ===");
    for (const r of results) {
      console.log(
        `[${short(r.wallet)}]`,
        r.status,
        r.txHash ? `tx=${r.txHash}` : "",
        r.reason ? `| ${r.reason}` : ""
      );
    }

    // stop ws
    try { wsProvider.destroy(); } catch {}
    process.exit(0);
  });
}

main().catch((e) => {
  console.error("\n❌ ERROR:", e?.message || e);
  process.exit(1);
});
