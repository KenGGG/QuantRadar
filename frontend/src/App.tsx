import { useEffect, useState } from "react";
import { getHealth, type HealthResp } from "./api";
import { PriceQuery } from "./components/PriceQuery";
import { BacktestPanel } from "./components/BacktestPanel";

export function App() {
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [tab, setTab] = useState<"price" | "backtest">("price");

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="app">
      <header>
        <h1>量子雷达 · QuantRadar</h1>
        <p className="subtitle">
          基于本地真实数据、可审计、可复现的 A 股量化研究平台
          {health ? `（数据源：${health.provider}）` : "（数据源未连接）"}
        </p>
      </header>
      <nav>
        <button className={tab === "price" ? "active" : ""} onClick={() => setTab("price")}>
          行情
        </button>
        <button className={tab === "backtest" ? "active" : ""} onClick={() => setTab("backtest")}>
          回测
        </button>
      </nav>
      <main>{tab === "price" ? <PriceQuery /> : <BacktestPanel />}</main>
      <footer>数据全部来自后端 /api/* 真实接口，前端不含任何价格或复权逻辑。</footer>
    </div>
  );
}
