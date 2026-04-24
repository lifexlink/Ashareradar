import json
import os
from datetime import datetime

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "latest_signals.json")

def fallback_records(reason="fallback"):
    return "fallback-demo", [
        {"rank": 1, "code": "300308", "name": "中际旭创", "score": 88, "reason": f"演示数据：{reason}"},
        {"rank": 2, "code": "002230", "name": "科大讯飞", "score": 84, "reason": f"演示数据：{reason}"},
        {"rank": 3, "code": "601138", "name": "工业富联", "score": 82, "reason": f"演示数据：{reason}"},
        {"rank": 4, "code": "002371", "name": "北方华创", "score": 80, "reason": f"演示数据：{reason}"},
        {"rank": 5, "code": "300750", "name": "宁德时代", "score": 78, "reason": f"演示数据：{reason}"},
        {"rank": 6, "code": "603019", "name": "中科曙光", "score": 77, "reason": f"演示数据：{reason}"},
        {"rank": 7, "code": "688981", "name": "中芯国际", "score": 75, "reason": f"演示数据：{reason}"},
        {"rank": 8, "code": "300124", "name": "汇川技术", "score": 74, "reason": f"演示数据：{reason}"},
        {"rank": 9, "code": "600941", "name": "中国移动", "score": 72, "reason": f"演示数据：{reason}"},
        {"rank": 10, "code": "002415", "name": "海康威视", "score": 71, "reason": f"演示数据：{reason}"},
    ]

def normalize_columns(df):
    rename = {}
    candidates = {
        "code": ["代码", "symbol"],
        "name": ["名称", "name"],
        "price": ["最新价", "现价", "price"],
        "change_pct": ["涨跌幅", "涨幅", "changepercent"],
        "volume": ["成交量", "volume"],
        "amount": ["成交额", "amount"],
        "turnover": ["换手率", "turnover"],
    }
    lower_map = {str(c).lower(): c for c in df.columns}
    for target, names in candidates.items():
        for name in names:
            if name in df.columns:
                rename[name] = target
                break
            if str(name).lower() in lower_map:
                rename[lower_map[str(name).lower()]] = target
                break
    return df.rename(columns=rename)

def live_records():
    import akshare as ak
    import pandas as pd

    errors = []
    spot = None
    used_source = None
    for fn_name in ["stock_zh_a_spot_em", "stock_zh_a_spot", "stock_zh_a_spot_tx"]:
        try:
            df = getattr(ak, fn_name)()
            if df is not None and not df.empty:
                spot = normalize_columns(df.copy())
                used_source = fn_name
                break
            errors.append(f"{fn_name}: empty")
        except Exception as e:
            errors.append(f"{fn_name}: {e}")

    if spot is None or spot.empty:
        return fallback_records("; ".join(errors[-2:]))

    for col in ["change_pct", "volume", "amount", "turnover"]:
        if col not in spot.columns:
            spot[col] = 0
        spot[col] = pd.to_numeric(spot[col], errors="coerce").fillna(0)

    if "code" not in spot.columns or "name" not in spot.columns:
        return fallback_records("missing code/name columns")

    spot["name"] = spot["name"].astype(str)
    spot = spot[~spot["name"].str.contains("ST|退", regex=True, na=False)].copy()

    amount_rank = spot["amount"].rank(pct=True) if "amount" in spot.columns else spot["volume"].rank(pct=True)
    volume_rank = spot["volume"].rank(pct=True)
    turnover_rank = spot["turnover"].rank(pct=True)

    spot["score"] = (
        spot["change_pct"].clip(lower=-20, upper=20) * 3.0
        + amount_rank.fillna(0) * 25
        + volume_rank.fillna(0) * 15
        + turnover_rank.fillna(0) * 10
    )

    spot = spot[(spot["change_pct"] > 0) & (spot["change_pct"] < 10.05)].copy()
    if spot.empty:
        return fallback_records("filtered empty")

    spot = spot.sort_values("score", ascending=False).head(10).reset_index(drop=True)

    records = []
    for i, row in spot.iterrows():
        records.append({
            "rank": i + 1,
            "code": str(row.get("code", "")),
            "name": str(row.get("name", "")),
            "score": round(float(row.get("score", 0)), 2),
            "reason": f"实时数据：涨跌幅 {round(float(row.get('change_pct', 0)), 2)}%，成交活跃度靠前，来源 {used_source}"
        })
    return f"live-{used_source}", records

def write_output(source, records):
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": source,
        "signals": records
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps({"source": source, "count": len(records)}, ensure_ascii=False))

if __name__ == "__main__":
    try:
        source, records = live_records()
    except Exception as e:
        source, records = fallback_records(str(e))
    write_output(source, records)
