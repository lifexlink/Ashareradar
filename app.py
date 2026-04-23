from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
DATA_PATH = os.path.join(BASE_DIR, "data", "latest_signals.json")
ALLOWED_UPLOAD_EXTENSIONS = {"json"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

PLANS = {
    "week": {"name": "周卡", "days": 7, "price": "¥99"},
    "month": {"name": "月卡", "days": 30, "price": "¥299"},
    "year": {"name": "年卡", "days": 365, "price": "¥1999"},
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
    conn.commit()
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            """INSERT INTO users (username, password_hash, role, membership_plan, membership_expires_at, created_at)
               VALUES (?, ?, 'admin', 'year', ?, ?)""",
            ("admin", generate_password_hash("admin123", method="pbkdf2:sha256"), (now() + timedelta(days=3650)).isoformat(), now().isoformat())
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
    if not isinstance(parsed, list):
        raise ValueError("JSON 顶层必须是列表")
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
        if "user" not in session:
            return redirect(url_for("admin_login"))
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
    return render_template("index.html", user=user, plans=PLANS)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if len(username) < 3 or len(password) < 6:
            flash("用户名至少3位，密码至少6位")
            return render_template("register.html")
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO users (username, password_hash, role, membership_plan, membership_expires_at, created_at)
                   VALUES (?, ?, 'user', 'free', NULL, ?)""",
                (username, generate_password_hash(password, method="pbkdf2:sha256"), now().isoformat())
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
    return render_template("dashboard.html", user=user, signals=visible, all_count=len(signals), paid=paid)

@app.route("/pricing")
def pricing():
    user = current_user()
    return render_template("pricing.html", user=user, plans=PLANS)

@app.route("/pay/<plan_code>", methods=["GET", "POST"])
@login_required
def pay(plan_code):
    user = current_user()
    if not user:
        flash("登录状态已失效，请重新登录后再提交支付申请")
        return redirect(url_for("login"))
    if plan_code not in PLANS:
        flash("套餐不存在")
        return redirect(url_for("pricing"))
    plan = PLANS[plan_code]
    if request.method == "POST":
        payer_name = request.form.get("payer_name", "").strip()
        payer_note = request.form.get("payer_note", "").strip()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO payment_requests (username, plan_code, payer_name, payer_note, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (user["username"], plan_code, payer_name, payer_note, now().isoformat())
        )
        conn.commit()
        conn.close()
        flash("已提交开通申请，请你核对到账后在后台开通")
        return redirect(url_for("dashboard"))
    return render_template("pay.html", user=user, plan=plan, plan_code=plan_code)

@app.route("/admin")
@admin_required
def admin():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payment_requests ORDER BY id DESC")
    payments = cur.fetchall()
    cur.execute("SELECT username, role, membership_plan, membership_expires_at, created_at FROM users ORDER BY id DESC")
    users = cur.fetchall()
    conn.close()
    user = current_user()
    signals = load_signals()
    return render_template("admin.html", payments=payments, users=users, plans=PLANS, user=user, signal_count=len(signals))

@app.route("/admin/approve/<int:payment_id>/<plan_code>", methods=["POST"])
@admin_required
def approve(payment_id, plan_code):
    if plan_code not in PLANS:
        flash("套餐不存在")
        return redirect(url_for("admin"))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payment_requests WHERE id = ?", (payment_id,))
    payment = cur.fetchone()
    if not payment:
        conn.close()
        flash("记录不存在")
        return redirect(url_for("admin"))
    username = payment["username"]
    user = get_user(username)
    days = PLANS[plan_code]["days"]
    base_time = now()
    if user["membership_expires_at"]:
        try:
            existing = datetime.fromisoformat(user["membership_expires_at"])
            if existing > base_time:
                base_time = existing
        except Exception:
            pass
    new_expiry = base_time + timedelta(days=days)
    cur.execute(
        "UPDATE users SET membership_plan = ?, membership_expires_at = ? WHERE username = ?",
        (plan_code, new_expiry.isoformat(), username)
    )
    cur.execute("UPDATE payment_requests SET status = 'approved' WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()
    flash(f"{username} 已开通 {PLANS[plan_code]['name']}")
    return redirect(url_for("admin"))

@app.route("/admin/reject/<int:payment_id>", methods=["POST"])
@admin_required
def reject(payment_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE payment_requests SET status = 'rejected' WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()
    flash("已拒绝该申请")
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

@app.route("/api/signals")
@login_required
def api_signals():
    user = current_user()
    signals = load_signals()
    visible = signals if is_paid(user) else signals[:3]
    return jsonify(visible)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
