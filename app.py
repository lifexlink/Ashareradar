# ================== V8 FINAL PATCH ==================
# 基于 V7 完整版修复（不删功能）

from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, os, uuid, hashlib
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ✅ 修复1：支持 Railway 持久化数据库
DB_PATH = os.environ.get("DATABASE_URL")
if not DB_PATH:
    DB_PATH = os.path.join(BASE_DIR, "users.db")

DATA_PATH = os.path.join(BASE_DIR, "data", "latest_signals.json")
HISTORY_DIR = os.path.join(BASE_DIR, "data", "history")
ALLOWED_UPLOAD_EXTENSIONS = {"json"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

# ================== DB ==================
def get_conn():
    # ✅ 修复2：防止多线程问题 + 保证稳定
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.utcnow()

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        membership_plan TEXT,
        membership_expires_at TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no TEXT,
        username TEXT,
        plan_code TEXT,
        plan_name TEXT,
        amount INTEGER,
        status TEXT,
        created_at TEXT,
        approved_at TEXT
    )
    """)

    conn.commit()

    # 默认管理员
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("""
        INSERT INTO users (username,password_hash,role,membership_plan,created_at)
        VALUES (?,?,?,?,?)
        """, (
            "admin",
            generate_password_hash("admin123"),
            "admin",
            "year",
            now().isoformat()
        ))
        conn.commit()

    conn.close()

# ================== USER ==================
def get_user(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return row

def current_user():
    u = session.get("user")
    return get_user(u) if u else None

def is_paid(user):
    if not user:
        return False
    if user["role"] == "admin":
        return True
    exp = user["membership_expires_at"]
    if not exp:
        return False
    return datetime.fromisoformat(exp) > now()

# ================== STATS（关键修复） ==================
def get_public_stats():
    conn = get_conn()
    cur = conn.cursor()

    stats = {"users": 0, "orders": 0, "paid_orders": 0}

    try:
        cur.execute("SELECT COUNT(*) as n FROM users")
        stats["users"] = cur.fetchone()["n"] or 0

        cur.execute("SELECT COUNT(*) as n FROM orders")
        stats["orders"] = cur.fetchone()["n"] or 0

        cur.execute("SELECT COUNT(*) as n FROM orders WHERE status='approved'")
        stats["paid_orders"] = cur.fetchone()["n"] or 0

    except Exception as e:
        print("stats error:", e)

    conn.close()
    return stats

# ================== ROUTES ==================

@app.route("/")
def index():
    return render_template("index.html", stats=get_public_stats())

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
            INSERT INTO users (username,password_hash,role,created_at)
            VALUES (?,?,?,?)
            """, (u, generate_password_hash(p), "user", now().isoformat()))
            conn.commit()
        except:
            flash("用户名已存在")
            conn.close()
            return redirect("/register")

        conn.close()
        return redirect("/login")

    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        user = get_user(u)

        if not user or not check_password_hash(user["password_hash"], p):
            flash("错误")
            return redirect("/login")

        session["user"] = u
        return redirect("/dashboard")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", user=current_user())

# ================== ORDER ==================
def make_order_no():
    return "ORD" + datetime.utcnow().strftime("%Y%m%d%H%M%S")

@app.route("/pay/<plan>")
def pay(plan):
    user = current_user()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO orders (order_no,username,plan_code,status,created_at)
    VALUES (?,?,?,?,?)
    """, (make_order_no(), user["username"], plan, "pending", now().isoformat()))

    conn.commit()
    conn.close()

    return "订单已提交"

@app.route("/admin")
def admin():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders")
    orders = cur.fetchall()

    conn.close()
    return render_template("admin.html", orders=orders)

@app.route("/admin/approve/<int:id>")
def approve(id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("UPDATE orders SET status='approved', approved_at=? WHERE id=?", (now().isoformat(), id))
    conn.commit()
    conn.close()

    return redirect("/admin")

# ================== API ==================
@app.route("/health")
def health():
    return {
        "status": "ok",
        "db": DB_PATH,
        "stats": get_public_stats()
    }

# ================== INIT ==================
init_db()

if __name__ == "__main__":
    app.run(debug=True)
