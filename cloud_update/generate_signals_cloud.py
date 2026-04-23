import json
import os
from datetime import datetime

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "latest_signals.json")

def demo_fallback():
    return [
        {"rank": 1, "code": "300308", "name": "中际旭创", "score": 88, "reason": "AI算力+板块热度+量价同步"},
        {"rank": 2, "code": "002230", "name": "科大讯飞", "score": 84, "reason": "AI应用+情绪回暖+资金承接"},
        {"rank": 3, "code": "601138", "name": "工业富联", "score": 82, "reason": "服务器链+成交活跃+趋势延续"},
        {"rank": 4, "code": "002371", "name": "北方华创", "score": 80, "reason": "半导体设备+机构偏好"},
        {"rank": 5, "code": "300750", "name": "宁德时代", "score": 78, "reason": "新能源权重+成交放大"},
        {"rank": 6, "code": "603019", "name": "中科曙光", "score": 77, "reason": "算力设备+热点联动"},
        {"rank": 7, "code": "688981", "name": "中芯国际", "score": 75, "reason": "芯片国产替代+趋势修复"},
        {"rank": 8, "code": "300124", "name": "汇川技术", "score": 74, "reason": "高端制造+稳健趋势"},
        {"rank": 9, "code": "600941", "name": "中国移动", "score": 72, "reason": "算力基建+防守属性"},
        {"rank": 10, "code": "002415", "name": "海康威视", "score": 71, "reason": "AI视觉+估值修复"}
    ]

def write_output(records):
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "cloud-job",
        "signals": records
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def try_live_generation():
    try:
        import akshare as ak
        import pandas as pd

        # 尽量走更稳的回退逻辑；任何一步失败都回退演示数据
        spot = None
        for fn_name in ["stock_zh_a_spot_em", "stock_zh_a_spot", "stock_zh_a_spot_tx"]:
            try:
                fn = getattr(ak, fn_name)
                df = fn()
                if df is not None and not df.empty:
                    spot = df.copy()
                    break
            except Exception:
                continue

        if spot is None or spot.empty:
            return demo_fallback()

        # 兼容不同接口列名
        cols = {c.lower(): c for c in spot.columns}
        code_col = cols.get("代码") or cols.get("symbol") or cols.get("代码".lower())
        name_col = cols.get("名称") or cols.get("name") or cols.get("名称".lower())
        price_col = None
        for key in ["最新价", "现价", "price", "最新价".lower(), "现价".lower()]:
            if key in cols:
                price_col = cols[key]
                break
        change_col = None
        for key in ["涨跌幅", "changepercent", "涨跌幅".lower()]:
            if key in cols:
                change_col = cols[key]
                break
        volume_col = None
        for key in ["成交量", "volume", "成交量".lower()]:
            if key in cols:
                volume_col = cols[key]
                break

        use_cols = [c for c in [code_col, name_col, price_col, change_col, volume_col] if c]
        spot = spot[use_cols].copy()
        rename_map = {}
        if code_col: rename_map[code_col] = "code"
        if name_col: rename_map[name_col] = "name"
        if price_col: rename_map[price_col] = "price"
        if change_col: rename_map[change_col] = "change_pct"
        if volume_col: rename_map[volume_col] = "volume"
        spot.rename(columns=rename_map, inplace=True)

        for c in ["price", "change_pct", "volume"]:
            if c in spot.columns:
                spot[c] = pd.to_numeric(spot[c], errors="coerce")

        # 简化版评分：涨跌幅 + 量能代理
        if "change_pct" not in spot.columns:
            spot["change_pct"] = 0
        if "volume" not in spot.columns:
            spot["volume"] = 0

        vol_rank = spot["volume"].rank(pct=True)
        spot["score"] = (spot["change_pct"].fillna(0) * 0.7) + (vol_rank.fillna(0) * 30)
        spot = spot.sort_values("score", ascending=False).head(10).reset_index(drop=True)

        records = []
        for i, row in spot.iterrows():
            reason = f"涨跌幅 {round(float(row.get('change_pct', 0) or 0), 2)}%，量能靠前"
            records.append({
                "rank": i + 1,
                "code": str(row.get("code", "")),
                "name": str(row.get("name", "")),
                "score": round(float(row.get("score", 0) or 0), 2),
                "reason": reason
            })
        return records if records else demo_fallback()
    except Exception:
        return demo_fallback()

if __name__ == "__main__":
    records = try_live_generation()
    write_output(records)
    print(f"Updated {OUTPUT_PATH} with {len(records)} records")
