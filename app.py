from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, os, uuid, hashlib
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
DATA_PATH = os.path.join(BASE_DIR, "data", "latest_signals.json")
HISTORY_DIR = os.path.join(BASE_DIR, "data", "history")
ALLOWED_UPLOAD_EXTENSIONS = {"json"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

PLANS = {
    "week": {"name": "周卡", "days": 7, "price": "¥39", "amount": 39},
    "month": {"name": "月卡", "days": 30, "price": "¥129", "amount": 129},
    "year": {"name": "年卡", "days": 365, "price": "¥999", "amount": 999},
}

def now():
    return datetime.utcnow()

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        membership_plan TEXT DEFAULT 'free',
        membership_expires_at TEXT,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        plan_code TEXT NOT NULL,
        payer_name TEXT,
        payer_note TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        plan_code TEXT NOT NULL,
        plan_name TEXT NOT NULL,
        amount INTEGER NOT NULL,
        payment_method TEXT DEFAULT 'manual_qr',
        payer_name TEXT,
        payer_note TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        approved_at TEXT,
        rejected_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        nickname TEXT,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        reviewed_at TEXT
    )
    """)
    for sql in [
        "ALTER TABLE users ADD COLUMN invite_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by TEXT"
    ]:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass
    cur.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_username TEXT NOT NULL,
        referred_username TEXT NOT NULL,
        reward_days INTEGER NOT NULL DEFAULT 3,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        approved_at TEXT
    )
    """)
    conn.commit()
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        cur.execute(
            """INSERT INTO users (username, password_hash, role, membership_plan, membership_expires_at, created_at)
               VALUES (?, ?, 'admin', 'year', ?, ?)""",
            ("admin", generate_password_hash(admin_password, method="pbkdf2:sha256"), (now() + timedelta(days=3650)).isoformat(), now().isoformat())
        )
        conn.commit()
    conn.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS

def save_uploaded_signals(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("未选择文件")
    if not allowed_file(file_storage.filename):
        raise ValueError("只允许上传 .json 文件")
    raw = file_storage.read()
    if not raw:
        raise ValueError("上传文件为空")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"JSON 解析失败: {e}")

    if isinstance(parsed, dict) and "signals" in parsed:
        parsed = parsed["signals"]

    if not isinstance(parsed, list):
        raise ValueError("JSON 顶层必须是列表，或包含 signals 字段")

    required_keys = {"rank", "code", "name", "score", "reason"}
    for idx, item in enumerate(parsed[:3]):
        if not isinstance(item, dict):
            raise ValueError(f"第 {idx+1} 条不是对象")
        missing = required_keys - set(item.keys())
        if missing:
            raise ValueError(f"第 {idx+1} 条缺少字段: {', '.join(sorted(missing))}")

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    return len(parsed)

def load_signals():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
            if isinstance(payload, dict) and "signals" in payload:
                return payload.get("signals", [])
            return payload if isinstance(payload, list) else []
    return []

def load_signal_meta():
    meta = {"source": "unknown", "generated_at": None}
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, dict):
                    meta["source"] = payload.get("source", "dict")
                    meta["generated_at"] = payload.get("generated_at")
                elif isinstance(payload, list):
                    meta["source"] = "uploaded-list"
        except Exception:
            meta["source"] = "unreadable"
    return meta



def source_label(source):
    mapping = {
        "live-stock_zh_a_spot_em": "实时行情｜东方财富A股行情",
        "live-stock_zh_a_spot": "实时行情｜新浪A股行情",
        "live-stock_zh_a_spot_tx": "实时行情｜腾讯A股行情",
        "fallback-demo": "备用演示数据",
        "uploaded-list": "后台上传数据",
    }
    return mapping.get(source or "", source or "未知来源")

def is_cn_trading_time():
    dt = now() + timedelta(hours=8)
    if dt.weekday() >= 5:
        return False
    minutes = dt.hour * 60 + dt.minute
    return (9*60+30 <= minutes <= 11*60+30) or (13*60 <= minutes <= 15*60)

def display_value(value, suffix=""):
    if value in (None, "", "-", "0", 0, 0.0, "0.0", "0.00"):
        return "-"
    return f"{value}{suffix}"

def generate_invite_code(username):
    raw = f"{username}-{datetime.utcnow().isoformat()}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8].upper()

def ensure_invite_code(username):
    user = get_user(username)
    if not user:
        return None
    try:
        code = user["invite_code"]
    except Exception:
        code = None
    if code:
        return code
    code = generate_invite_code(username)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET invite_code = ? WHERE username = ?", (code, username))
    conn.commit()
    conn.close()
    return code

def load_history_records(limit=30):
    records = []
    if not os.path.exists(HISTORY_DIR):
        return records
    files = sorted([f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")], reverse=True)
    for fname in files[:limit]:
        path = os.path.join(HISTORY_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            signals = payload.get("signals", payload if isinstance(payload, list) else [])
            date = payload.get("date") or fname.replace(".json", "")
            source = payload.get("source", "unknown")
            generated_at = payload.get("generated_at")
            records.append({
                "date": date,
                "source": source,
                "generated_at": generated_at,
                "signals": signals
            })
        except Exception:
            continue
    return records

def pct_value(x):
    try:
        if x in ("-", None, ""):
            return None
        return float(x)
    except Exception:
        return None

def summarize_snapshot(snapshot):
    signals = snapshot.get("signals", [])
    changes = [pct_value(s.get("change_pct")) for s in signals]
    changes = [x for x in changes if x is not None]
    top3_changes = [pct_value(s.get("change_pct")) for s in signals[:3]]
    top3_changes = [x for x in top3_changes if x is not None]

    def avg(vals):
        return round(sum(vals) / len(vals), 2) if vals else None

    limit_up = 0
    up_count = 0
    for s in signals:
        ch = pct_value(s.get("change_pct"))
        if ch is None:
            continue
        if ch >= 9.8:
            limit_up += 1
        if ch > 0:
            up_count += 1

    strongest = signals[0] if signals else {}
    return {
        "date": snapshot.get("date"),
        "source": snapshot.get("source"),
        "generated_at": snapshot.get("generated_at"),
        "top3_avg": avg(top3_changes),
        "top10_avg": avg(changes),
        "limit_up": limit_up,
        "up_count": up_count,
        "total": len(signals),
        "strongest_name": strongest.get("name", "-"),
        "strongest_code": strongest.get("code", "-"),
        "strongest_change": strongest.get("change_pct", "-"),
    }

def get_public_feedback(limit=6):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM feedback WHERE status = 'approved' ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_user(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row

def current_user():
    username = session.get("user")
    if not username:
        return None
    user = get_user(username)
    if not user:
        session.clear()
        return None
    return user

def is_paid(user):
    if not user:
        return False
    if user["role"] == "admin":
        return True
    expires = user["membership_expires_at"]
    if not expires:
        return False
    try:
        return datetime.fromisoformat(expires) > now()
    except Exception:
        return False

def make_order_no():
    return "ASR" + datetime.utcnow().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper()

def get_user_orders(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE username = ? ORDER BY id DESC", (username,))
    rows = cur.fetchall()
    conn.close()
    return rows

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            flash("请先使用管理员账号登录后台")
            session.clear()
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    user = current_user()
    history = load_history_records(limit=1)
    latest_summary = summarize_snapshot(history[0]) if history else None
    feedback_items = get_public_feedback(limit=3)
    return render_template("index.html", user=user, plans=PLANS, latest_summary=latest_summary, feedback_items=feedback_items)

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        invite_code = request.form.get("invite_code", request.args.get("ref", "")).strip().upper()
        if len(username) < 3 or len(password) < 6:
            flash("用户名至少3位，密码至少6位")
            return render_template("register.html")
        if request.form.get("agree_disclaimer") != "yes":
            flash("请先阅读并同意免责声明")
            return render_template("register.html")
        conn = get_conn()
        cur = conn.cursor()
        try:
            referred_by = None
            if invite_code:
                cur.execute("SELECT username FROM users WHERE invite_code = ?", (invite_code,))
                ref = cur.fetchone()
                if ref:
                    referred_by = ref["username"]
            new_code = generate_invite_code(username)
            cur.execute(
                """INSERT INTO users (username, password_hash, role, membership_plan, membership_expires_at, created_at, invite_code, referred_by)
                   VALUES (?, ?, 'user', 'free', NULL, ?, ?, ?)""",
                (username, generate_password_hash(password, method="pbkdf2:sha256"), now().isoformat(), new_code, referred_by)
            )
            if referred_by:
                cur.execute(
                    "INSERT INTO referrals (referrer_username, referred_username, reward_days, status, created_at) VALUES (?, ?, 3, 'pending', ?)",
                    (referred_by, username, now().isoformat())
                )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("用户名已存在")
            conn.close()
            return render_template("register.html")
        conn.close()
        flash("注册成功，请登录")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = get_user(username)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("用户名或密码错误")
            return render_template("login.html")
        session["user"] = username
        next_url = request.args.get("next") or url_for("dashboard")
        return redirect(next_url)
    return render_template("login.html")

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = get_user(username)
        if not user or user["role"] != "admin" or not check_password_hash(user["password_hash"], password):
            flash("管理员账号或密码错误")
            return render_template("admin_login.html")
        session["user"] = username
        return redirect(url_for("admin"))
    return render_template("admin_login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    signals = load_signals()
    paid = is_paid(user)
    visible = signals if paid else signals[:3]
    meta = load_signal_meta()
    return render_template("dashboard.html", user=user, signals=visible, all_count=len(signals), paid=paid, meta=meta, source_label=source_label(meta.get("source")), trading_time=is_cn_trading_time(), display_value=display_value)

@app.route("/pricing")
def pricing():
    user = current_user()
    return render_template("pricing.html", user=user, plans=PLANS)

@app.route("/pay/<plan_code>", methods=["GET", "POST"])
@login_required
def pay(plan_code):
    user = current_user()
    if plan_code not in PLANS:
        flash("套餐不存在")
        return redirect(url_for("pricing"))
    plan = PLANS[plan_code]

    if request.method == "POST":
        payer_name = request.form.get("payer_name", "").strip()
        payer_note = request.form.get("payer_note", "").strip()
        payment_method = request.form.get("payment_method", "manual_qr").strip() or "manual_qr"
        conn = get_conn()
        cur = conn.cursor()

        # 防重复提交：同一用户同一套餐，3分钟内已有待审核订单则不新建
        cutoff = (now() - timedelta(minutes=3)).isoformat()
        cur.execute(
            """SELECT * FROM orders
               WHERE username = ? AND plan_code = ? AND status = 'pending' AND created_at >= ?
               ORDER BY id DESC LIMIT 1""",
            (user["username"], plan_code, cutoff)
        )
        existing_order = cur.fetchone()
        if existing_order:
            conn.close()
            flash(f"你刚刚已经提交过订单：{existing_order['order_no']}，请勿重复提交。")
            return redirect(url_for("orders"))

        order_no = make_order_no()
        cur.execute(
            """INSERT INTO orders
               (order_no, username, plan_code, plan_name, amount, payment_method, payer_name, payer_note, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (order_no, user["username"], plan_code, plan["name"], plan["amount"], payment_method, payer_name, payer_note, now().isoformat())
        )
        conn.commit()
        conn.close()

        flash(f"订单已提交：{order_no}。请等待管理员核对到账后开通。")
        return redirect(url_for("orders"))

    return render_template("pay.html", user=user, plan=plan, plan_code=plan_code)

@app.route("/orders")
@login_required
def orders():
    user = current_user()
    rows = get_user_orders(user["username"])
    return render_template("orders.html", user=user, orders=rows, plans=PLANS)


@app.route("/admin/change-password", methods=["GET", "POST"])
@admin_required
def change_admin_password():
    user = current_user()
    if request.method == "POST":
        old_password = request.form.get("old_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not check_password_hash(user["password_hash"], old_password):
            flash("原密码错误")
            return render_template("change_password.html", user=user)

        if len(new_password) < 8:
            flash("新密码至少8位")
            return render_template("change_password.html", user=user)

        if new_password != confirm_password:
            flash("两次输入的新密码不一致")
            return render_template("change_password.html", user=user)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (generate_password_hash(new_password, method="pbkdf2:sha256"), user["username"])
        )
        conn.commit()
        conn.close()

        flash("管理员密码已修改，请重新登录")
        session.clear()
        return redirect(url_for("admin_login"))

    return render_template("change_password.html", user=user)


@app.route("/backtest")
def backtest():
    history = load_history_records(limit=30)
    summaries = [summarize_snapshot(h) for h in history]
    last7 = summaries[:7]
    def avg_field(rows, field):
        vals = [r.get(field) for r in rows if r.get(field) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    stats = {
        "days": len(summaries),
        "last7_top3_avg": avg_field(last7, "top3_avg"),
        "last7_top10_avg": avg_field(last7, "top10_avg"),
        "last7_limit_up": sum([r.get("limit_up", 0) for r in last7]),
        "last7_up_count": sum([r.get("up_count", 0) for r in last7]),
        "last7_total": sum([r.get("total", 0) for r in last7]),
    }
    return render_template("backtest.html", summaries=summaries, stats=stats, source_label=source_label)

@app.route("/review")
def review():
    history = load_history_records(limit=2)
    latest = history[0] if history else None
    previous = history[1] if len(history) > 1 else None
    latest_summary = summarize_snapshot(latest) if latest else None
    previous_summary = summarize_snapshot(previous) if previous else None
    return render_template("review.html", latest=latest, previous=previous, latest_summary=latest_summary, previous_summary=previous_summary, source_label=source_label, display_value=display_value)

@app.route("/methodology")
def methodology():
    return render_template("methodology.html")

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    user = current_user()
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        content = request.form.get("content", "").strip()
        if len(content) < 5:
            flash("反馈内容至少5个字")
            return render_template("feedback.html", user=user)
        banned_words = ["稳赚", "包赚", "必涨", "内幕", "保证收益", "荐股", "跟着买"]
        if any(w in content for w in banned_words):
            flash("反馈中请避免收益承诺、荐股或误导性表述")
            return render_template("feedback.html", user=user)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feedback (username, nickname, content, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (user["username"], nickname, content, now().isoformat())
        )
        conn.commit()
        conn.close()
        flash("反馈已提交，审核后可能展示在首页")
        return redirect(url_for("feedback"))
    return render_template("feedback.html", user=user)

@app.route("/admin/feedback")
@admin_required
def admin_feedback():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM feedback ORDER BY id DESC")
    feedback_rows = cur.fetchall()
    conn.close()
    user = current_user()
    return render_template("admin_feedback.html", user=user, feedback_rows=feedback_rows)

@app.route("/admin/feedback/<int:feedback_id>/<action>", methods=["POST"])
@admin_required
def admin_feedback_action(feedback_id, action):
    if action not in ["approved", "rejected", "hidden"]:
        flash("操作无效")
        return redirect(url_for("admin_feedback"))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE feedback SET status = ?, reviewed_at = ? WHERE id = ?", (action, now().isoformat(), feedback_id))
    conn.commit()
    conn.close()
    flash("反馈状态已更新")
    return redirect(url_for("admin_feedback"))


@app.route("/affiliate")
@login_required
def affiliate():
    user = current_user()
    code = ensure_invite_code(user["username"])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM referrals WHERE referrer_username = ? ORDER BY id DESC", (user["username"],))
    referrals = cur.fetchall()
    conn.close()
    invite_url = url_for("register", ref=code, _external=True)
    return render_template("affiliate.html", user=user, invite_code=code, invite_url=invite_url, referrals=referrals)

@app.route("/admin/export")
@admin_required
def export_data():
    conn = get_conn()
    cur = conn.cursor()
    export = {"exported_at": now().isoformat(), "version": "v7"}
    for table in ["users", "orders", "feedback", "referrals"]:
        try:
            cur.execute(f"SELECT * FROM {table}")
            export[table] = [dict(row) for row in cur.fetchall()]
        except Exception:
            export[table] = []
    conn.close()
    response = make_response(json.dumps(export, ensure_ascii=False, indent=2))
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=ashare_v7_backup.json"
    return response

@app.route("/admin/import", methods=["GET", "POST"])
@admin_required
def import_data():
    user = current_user()
    if request.method == "POST":
        file = request.files.get("backup_file")
        if not file or not file.filename:
            flash("请选择备份文件")
            return render_template("import_data.html", user=user)
        try:
            payload = json.loads(file.read().decode("utf-8"))
            conn = get_conn()
            cur = conn.cursor()
            for row in payload.get("users", []):
                cur.execute(
                    """INSERT OR REPLACE INTO users
                       (id, username, password_hash, role, membership_plan, membership_expires_at, created_at, invite_code, referred_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row.get("id"), row.get("username"), row.get("password_hash"), row.get("role", "user"), row.get("membership_plan", "free"), row.get("membership_expires_at"), row.get("created_at", now().isoformat()), row.get("invite_code"), row.get("referred_by"))
                )
            for row in payload.get("orders", []):
                cur.execute(
                    """INSERT OR REPLACE INTO orders
                       (id, order_no, username, plan_code, plan_name, amount, payment_method, payer_name, payer_note, status, created_at, approved_at, rejected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row.get("id"), row.get("order_no"), row.get("username"), row.get("plan_code"), row.get("plan_name"), row.get("amount"), row.get("payment_method"), row.get("payer_name"), row.get("payer_note"), row.get("status"), row.get("created_at"), row.get("approved_at"), row.get("rejected_at"))
                )
            for row in payload.get("feedback", []):
                cur.execute(
                    """INSERT OR REPLACE INTO feedback (id, username, nickname, content, status, created_at, reviewed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (row.get("id"), row.get("username"), row.get("nickname"), row.get("content"), row.get("status"), row.get("created_at"), row.get("reviewed_at"))
                )
            for row in payload.get("referrals", []):
                cur.execute(
                    """INSERT OR REPLACE INTO referrals (id, referrer_username, referred_username, reward_days, status, created_at, approved_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (row.get("id"), row.get("referrer_username"), row.get("referred_username"), row.get("reward_days", 3), row.get("status", "pending"), row.get("created_at"), row.get("approved_at"))
                )
            conn.commit()
            conn.close()
            flash("数据导入完成")
            return redirect(url_for("admin"))
        except Exception as e:
            flash(f"导入失败：{e}")
    return render_template("import_data.html", user=user)

@app.route("/admin/referrals")
@admin_required
def admin_referrals():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM referrals ORDER BY id DESC")
    referrals = cur.fetchall()
    conn.close()
    user = current_user()
    return render_template("admin_referrals.html", user=user, referrals=referrals)

@app.route("/admin/referrals/<int:referral_id>/approve", methods=["POST"])
@admin_required
def approve_referral(referral_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM referrals WHERE id = ?", (referral_id,))
    ref = cur.fetchone()
    if not ref:
        conn.close()
        flash("邀请记录不存在")
        return redirect(url_for("admin_referrals"))
    if ref["status"] == "approved":
        conn.close()
        flash("该邀请已奖励")
        return redirect(url_for("admin_referrals"))
    username = ref["referrer_username"]
    days = int(ref["reward_days"] or 3)
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    u = cur.fetchone()
    if u:
        base_time = now()
        if u["membership_expires_at"]:
            try:
                existing = datetime.fromisoformat(u["membership_expires_at"])
                if existing > base_time:
                    base_time = existing
            except Exception:
                pass
        new_expiry = base_time + timedelta(days=days)
        plan = u["membership_plan"] if u["membership_plan"] != "free" else "week"
        cur.execute("UPDATE users SET membership_plan = ?, membership_expires_at = ? WHERE username = ?", (plan, new_expiry.isoformat(), username))
        cur.execute("UPDATE referrals SET status='approved', approved_at=? WHERE id=?", (now().isoformat(), referral_id))
        conn.commit()
        flash(f"已为 {username} 增加 {days} 天会员")
    conn.close()
    return redirect(url_for("admin_referrals"))

@app.route("/admin")
@admin_required
def admin():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cur.fetchall()
    cur.execute("SELECT username, role, membership_plan, membership_expires_at, created_at FROM users ORDER BY id DESC")
    users = cur.fetchall()
    conn.close()
    user = current_user()
    signals = load_signals()
    return render_template("admin.html", orders=orders, users=users, plans=PLANS, user=user, signal_count=len(signals))

@app.route("/admin/approve-order/<int:order_id>", methods=["POST"])
@admin_required
def approve_order(order_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cur.fetchone()
    if not order:
        conn.close()
        flash("订单不存在")
        return redirect(url_for("admin"))
    if order["status"] == "approved":
        conn.close()
        flash("该订单已开通，无需重复操作")
        return redirect(url_for("admin"))

    plan_code = order["plan_code"]
    if plan_code not in PLANS:
        conn.close()
        flash("套餐不存在")
        return redirect(url_for("admin"))

    username = order["username"]
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    target_user = cur.fetchone()
    if not target_user:
        conn.close()
        flash("用户不存在，无法开通")
        return redirect(url_for("admin"))

    days = PLANS[plan_code]["days"]
    base_time = now()
    if target_user["membership_expires_at"]:
        try:
            existing = datetime.fromisoformat(target_user["membership_expires_at"])
            if existing > base_time:
                base_time = existing
        except Exception:
            pass

    new_expiry = base_time + timedelta(days=days)
    cur.execute(
        "UPDATE users SET membership_plan = ?, membership_expires_at = ? WHERE username = ?",
        (plan_code, new_expiry.isoformat(), username)
    )
    cur.execute(
        "UPDATE orders SET status = 'approved', approved_at = ? WHERE id = ?",
        (now().isoformat(), order_id)
    )
    conn.commit()
    conn.close()
    flash(f"订单 {order['order_no']} 已开通：{username} / {PLANS[plan_code]['name']}")
    return redirect(url_for("admin"))

@app.route("/admin/reject-order/<int:order_id>", methods=["POST"])
@admin_required
def reject_order(order_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = 'rejected', rejected_at = ? WHERE id = ? AND status = 'pending'", (now().isoformat(), order_id))
    conn.commit()
    conn.close()
    flash("已拒绝该订单")
    return redirect(url_for("admin"))

@app.route("/admin/upload-signals", methods=["POST"])
@admin_required
def upload_signals():
    file = request.files.get("signals_file")
    try:
        count = save_uploaded_signals(file)
        flash(f"信号文件上传成功，已更新 {count} 条记录")
    except Exception as e:
        flash(f"上传失败：{e}")
    return redirect(url_for("admin"))

@app.route("/health")
def health():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM users")
        n = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM orders")
        o = cur.fetchone()["n"]
        conn.close()
        signals = load_signals()
        source = "unknown"
        generated_at = None
        if os.path.exists(DATA_PATH):
            try:
                with open(DATA_PATH, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                    if isinstance(payload, dict):
                        source = payload.get("source", "dict")
                        generated_at = payload.get("generated_at")
                    else:
                        source = "list"
            except Exception:
                source = "unreadable"
        history_files = len([f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")]) if os.path.exists(HISTORY_DIR) else 0
        return {"status": "ok", "version": "v7-final", "users": n, "orders": o, "signals": len(signals), "source": source, "source_label": source_label(source), "generated_at": generated_at, "history_files": history_files}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/api/signals")
@login_required
def api_signals():
    user = current_user()
    signals = load_signals()
    visible = signals if is_paid(user) else signals[:3]
    return jsonify(visible)

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
