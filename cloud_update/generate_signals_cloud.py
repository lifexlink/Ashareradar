from datetime import datetime, timedelta
import json
import os

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "latest_signals.json")


def fmt_num(value, digits=2):
    try:
        return round(float(value), digits)
    except Exception:
        return 0


def fmt_amount_cn(value):
    try:
        v = float(value)
        if v >= 100000000:
            return f"{v / 100000000:.2f}亿"
        if v >= 10000:
            return f"{v / 10000:.2f}万"
        return f"{v:.0f}"
    except Exception:
        return "-"


def fallback_records(reason="fallback"):
    rows = [
        ("300308", "中际旭创", 88), ("002230", "科大讯飞", 84), ("601138", "工业富联", 82),
        ("002371", "北方华创", 80), ("300750", "宁德时代", 78), ("603019", "中科曙光", 77),
        ("688981", "中芯国际", 75), ("300124", "汇川技术", 74), ("600941", "中国移动", 72), ("002415", "海康威视", 71)
    ]
    return "fallback-demo", [
        {
            "rank": i + 1,
            "code": code,
            "name": name,
            "score": score,
            "price": "-",
            "change_pct": "-",
            "amount": "-",
            "turnover": "-",
            "amplitude": "-",
            "speed": "-",
            "signal_tags": ["演示数据"],
            "reason": f"演示数据：{reason}"
        } for i, (code, name, score) in enumerate(rows)
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
        "speed": ["涨速"],
        "amplitude": ["振幅"],
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

    for col in ["price", "change_pct", "volume", "amount", "turnover", "speed", "amplitude"]:
        if col not in spot.columns:
            spot[col] = 0
        spot[col] = pd.to_numeric(spot[col], errors="coerce").fillna(0)

    if "code" not in spot.columns or "name" not in spot.columns:
        return fallback_records("missing code/name columns")

    spot["name"] = spot["name"].astype(str)
    spot = spot[~spot["name"].str.contains("ST|退", regex=True, na=False)].copy()

    amount_rank = spot["amount"].rank(pct=True)
    volume_rank = spot["volume"].rank(pct=True)
    turnover_rank = spot["turnover"].rank(pct=True)
    speed_rank = spot["speed"].rank(pct=True)
    amplitude_rank = spot["amplitude"].rank(pct=True)

    spot["score"] = (
        spot["change_pct"].clip(lower=-20, upper=20) * 3.0
        + amount_rank.fillna(0) * 25
        + volume_rank.fillna(0) * 15
        + turnover_rank.fillna(0) * 12
        + speed_rank.fillna(0) * 6
        + amplitude_rank.fillna(0) * 4
    )

    spot = spot[(spot["change_pct"] > 0) & (spot["change_pct"] < 10.05)].copy()

    if spot.empty:
        return fallback_records("filtered empty")

    spot = spot.sort_values("score", ascending=False).head(10).reset_index(drop=True)

    records = []

    for i, row in spot.iterrows():
        change_pct = fmt_num(row.get("change_pct", 0))

        raw_turnover = (
            row.get("turnover_rate") or
            row.get("turnover") or
            row.get("换手率")
        )

        if raw_turnover in [0, 0.0, None]:
            turnover = None
        else:
            turnover = fmt_num(raw_turnover)

        amplitude = fmt_num(row.get("amplitude", 0))
        speed = fmt_num(row.get("speed", 0))
        price = fmt_num(row.get("price", 0))
        amount_raw = row.get("amount", 0)
        amount_text = fmt_amount_cn(amount_raw)

        tags = []

        if change_pct >= 9:
            tags.append("接近涨停")
        elif change_pct >= 5:
            tags.append("强势上涨")

        if amount_raw >= 1000000000:
            tags.append("成交额10亿+")
        elif amount_raw >= 300000000:
            tags.append("成交活跃")

        if turnover is not None:
            if turnover >= 8:
                tags.append("高换手")
            elif turnover >= 3:
                tags.append("换手较活跃")

        if speed > 0:
            tags.append("盘中上攻")

        if not tags:
            tags.append("强势候选")

        reason_parts = [
            f"涨跌幅 {change_pct}%",
            f"成交额约 {amount_text}",
            f"换手率 {turnover if turnover is not None else '-'}%",
        ]

        if amplitude:
            reason_parts.append(f"振幅 {amplitude}%")

        if speed:
            reason_parts.append(f"涨速 {speed}%")

        reason = "；".join(reason_parts)
        reason += "。综合动量、成交额、换手率、涨速和活跃度排序，数据源：东方财富A股行情。"

        records.append({
            "rank": i + 1,
            "code": str(row.get("code", "")),
            "name": str(row.get("name", "")),
            "score": round(float(row.get("score", 0)), 2),
            "price": price,
            "change_pct": change_pct,
            "amount": amount_text,
            "turnover": turnover,
            "amplitude": amplitude,
            "speed": speed,
            "signal_tags": tags,
            "reason": reason
        })

    return f"live-{used_source}", records


def write_output(source, records):
    now = datetime.utcnow() + timedelta(hours=8)
    today = now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "date": today,
        "generated_at": generated_at,
        "source": source,
        "signals": records
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    history_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "history")
    os.makedirs(history_dir, exist_ok=True)

    history_path = os.path.join(history_dir, f"{today}.json")

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "source": source,
        "count": len(records),
        "history": history_path
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        source, records = live_records()
    except Exception as e:
        source, records = fallback_records(str(e))

    write_output(source, records)

