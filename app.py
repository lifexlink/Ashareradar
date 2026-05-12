# ================================
# A-SHARE SaaS V8 FULL PATCH
# PostgreSQL + SQLite Dual Support
# Keep ALL V7 Features
# ================================

from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash

import os
import json
import uuid
import hashlib
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

# ================================
# PostgreSQL Support
# ================================

DATABASE_URL = os.environ.get("DATABASE_URL")

USE_POSTGRES = False
pg = None

if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    try:
        import psycopg2
        import psycopg2.extras
        USE_POSTGRES = True
        print("✅ PostgreSQL mode enabled")
    except Exception as e:
        print("❌ psycopg2 not installed:", e)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SQLITE_DB_PATH = os.path.join(BASE_DIR, "users.db")

DATA_PATH = os.path.join(BASE_DIR, "data", "latest_signals.json")
HISTORY_DIR = os.path.join(BASE_DIR, "data", "history")

ALLOWED_UPLOAD_EXTENSIONS = {"json"}

# ================================
# Flask
# ================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-me-in-production"
)

# ================================
# Plans
# ================================

PLANS = {
    "week": {
        "name": "周卡",
        "days": 7,
        "price": "¥39",
        "amount": 39
    },
    "month": {
        "name": "月卡",
        "days": 30,
        "price": "¥129",
        "amount": 129
    },
    "year": {
        "name": "年卡",
        "days": 365,
        "price": "¥999",
        "amount": 999
    },
}

# ================================
# Utils
# ================================

def now():
    return datetime.utcnow()

# ================================
# Database Connection
# ================================

def get_conn():

    if USE_POSTGRES:

        conn = psycopg2.connect(DATABASE_URL)

        return conn

    else:

        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row

        return conn

# ================================
# Query Helpers
# ================================

def fetchone_dict(cur):

    row = cur.fetchone()

    if not row:
        return None

    if USE_POSTGRES:
        return dict(row)

    return row

def fetchall_dict(cur):

    rows = cur.fetchall()

    if USE_POSTGRES:
        return [dict(r) for r in rows]

    return rows

def q(sql):

    if USE_POSTGRES:
        return sql.replace("?", "%s")

    return sql

# ================================
# Init DB
# ================================

def init_db():

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    # USERS

    cur.execute(q("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        membership_plan TEXT DEFAULT 'free',
        membership_expires_at TEXT,
        created_at TEXT NOT NULL,
        invite_code TEXT,
        referred_by TEXT
    )
    """))

    # ORDERS

    cur.execute(q("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
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
    """))

    # FEEDBACK

    cur.execute(q("""
    CREATE TABLE IF NOT EXISTS feedback (
        id SERIAL PRIMARY KEY,
        username TEXT,
        nickname TEXT,
        content TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        reviewed_at TEXT
    )
    """))

    # REFERRALS

    cur.execute(q("""
    CREATE TABLE IF NOT EXISTS referrals (
        id SERIAL PRIMARY KEY,
        referrer_username TEXT NOT NULL,
        referred_username TEXT NOT NULL,
        reward_days INTEGER NOT NULL DEFAULT 3,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        approved_at TEXT
    )
    """))

    conn.commit()

    # CREATE ADMIN

    cur.execute(
        q("SELECT * FROM users WHERE username = ?"),
        ("admin",)
    )

    admin = fetchone_dict(cur)

    if not admin:

        admin_password = os.environ.get(
            "ADMIN_PASSWORD",
            "admin123"
        )

        cur.execute(
            q("""
            INSERT INTO users
            (
                username,
                password_hash,
                role,
                membership_plan,
                membership_expires_at,
                created_at
            )
            VALUES (?, ?, 'admin', 'year', ?, ?)
            """),
            (
                "admin",
                generate_password_hash(
                    admin_password,
                    method="pbkdf2:sha256"
                ),
                (
                    now() + timedelta(days=3650)
                ).isoformat(),
                now().isoformat()
            )
        )

        conn.commit()

    conn.close()

# ================================
# User
# ================================

def get_user(username):

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    cur.execute(
        q("SELECT * FROM users WHERE username = ?"),
        (username,)
    )

    row = fetchone_dict(cur)

    conn.close()

    return row

def current_user():

    username = session.get("user")

    if not username:
        return None

    return get_user(username)

def is_paid(user):

    if not user:
        return False

    if user["role"] == "admin":
        return True

    expires = user.get("membership_expires_at")

    if not expires:
        return False

    try:
        return datetime.fromisoformat(expires) > now()
    except:
        return False

# ================================
# Decorators
# ================================

def login_required(fn):

    @wraps(fn)

    def wrapper(*args, **kwargs):

        if not current_user():
            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapper

def admin_required(fn):

    @wraps(fn)

    def wrapper(*args, **kwargs):

        user = current_user()

        if not user or user["role"] != "admin":

            flash("请先登录管理员")

            return redirect(url_for("admin_login"))

        return fn(*args, **kwargs)

    return wrapper

# ================================
# Signal Loader
# ================================

def load_signals():

    if not os.path.exists(DATA_PATH):
        return []

    try:

        with open(DATA_PATH, "r", encoding="utf-8") as f:

            payload = json.load(f)

        if isinstance(payload, dict):
            return payload.get("signals", [])

        if isinstance(payload, list):
            return payload

    except Exception as e:

        print("load signals error:", e)

    return []

# ================================
# Public Stats
# ================================

def get_public_stats():

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    stats = {
        "users": 0,
        "orders": 0,
        "paid_orders": 0
    }

    try:

        cur.execute(q(
            "SELECT COUNT(*) AS n FROM users"
        ))

        stats["users"] = fetchone_dict(cur)["n"]

        cur.execute(q(
            "SELECT COUNT(*) AS n FROM orders"
        ))

        stats["orders"] = fetchone_dict(cur)["n"]

        cur.execute(q(
            "SELECT COUNT(*) AS n FROM orders WHERE status='approved'"
        ))

        stats["paid_orders"] = fetchone_dict(cur)["n"]

    except Exception as e:

        print("stats error:", e)

    conn.close()

    return stats

# ================================
# Order No
# ================================

def make_order_no():

    return (
        "ASR"
        + datetime.utcnow().strftime("%Y%m%d%H%M%S")
        + uuid.uuid4().hex[:6].upper()
    )

# ================================
# Routes
# ================================

@app.route("/")
def index():

    user = current_user()

    signals = load_signals()

    stats = get_public_stats()

    return render_template(
        "index.html",
        user=user,
        plans=PLANS,
        signal_count=len(signals),
        public_stats=stats
    )

# ================================
# Register
# ================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        if len(username) < 3:
            flash("用户名至少3位")
            return render_template("register.html")

        if len(password) < 6:
            flash("密码至少6位")
            return render_template("register.html")

        conn = get_conn()

        if USE_POSTGRES:
            cur = conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        else:
            cur = conn.cursor()

        try:

            cur.execute(
                q("""
                INSERT INTO users
                (
                    username,
                    password_hash,
                    role,
                    membership_plan,
                    created_at
                )
                VALUES (?, ?, 'user', 'free', ?)
                """),
                (
                    username,
                    generate_password_hash(
                        password,
                        method="pbkdf2:sha256"
                    ),
                    now().isoformat()
                )
            )

            conn.commit()

        except Exception as e:

            conn.rollback()

            flash("用户名已存在")

            conn.close()

            return render_template("register.html")

        conn.close()

        flash("注册成功")

        return redirect(url_for("login"))

    return render_template("register.html")

# ================================
# Login
# ================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        user = get_user(username)

        if not user:

            flash("账号不存在")

            return render_template("login.html")

        if not check_password_hash(
            user["password_hash"],
            password
        ):

            flash("密码错误")

            return render_template("login.html")

        session["user"] = username

        return redirect(url_for("dashboard"))

    return render_template("login.html")

# ================================
# Admin Login
# ================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        user = get_user(username)

        if not user:

            flash("管理员不存在")

            return render_template("admin_login.html")

        if user["role"] != "admin":

            flash("不是管理员")

            return render_template("admin_login.html")

        if not check_password_hash(
            user["password_hash"],
            password
        ):

            flash("密码错误")

            return render_template("admin_login.html")

        session["user"] = username

        return redirect(url_for("admin"))

    return render_template("admin_login.html")

# ================================
# Logout
# ================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))

# ================================
# Dashboard
# ================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    signals = load_signals()

    paid = is_paid(user)

    visible = signals if paid else signals[:3]

    return render_template(
        "dashboard.html",
        user=user,
        signals=visible,
        paid=paid,
        all_count=len(signals)
    )

# ================================
# Pricing
# ================================

@app.route("/pricing")
def pricing():

    return render_template(
        "pricing.html",
        plans=PLANS,
        user=current_user()
    )

# ================================
# Pay
# ================================

@app.route("/pay/<plan_code>", methods=["GET", "POST"])
@login_required
def pay(plan_code):

    user = current_user()

    if plan_code not in PLANS:

        flash("套餐不存在")

        return redirect(url_for("pricing"))

    plan = PLANS[plan_code]

    if request.method == "POST":

        payer_name = request.form.get(
            "payer_name",
            ""
        ).strip()

        payer_note = request.form.get(
            "payer_note",
            ""
        ).strip()

        conn = get_conn()

        if USE_POSTGRES:
            cur = conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        else:
            cur = conn.cursor()

        order_no = make_order_no()

        cur.execute(
            q("""
            INSERT INTO orders
            (
                order_no,
                username,
                plan_code,
                plan_name,
                amount,
                payer_name,
                payer_note,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """),
            (
                order_no,
                user["username"],
                plan_code,
                plan["name"],
                plan["amount"],
                payer_name,
                payer_note,
                now().isoformat()
            )
        )

        conn.commit()

        conn.close()

        flash("订单提交成功")

        return redirect(url_for("orders"))

    return render_template(
        "pay.html",
        user=user,
        plan=plan,
        plan_code=plan_code
    )

# ================================
# Orders
# ================================

@app.route("/orders")
@login_required
def orders():

    user = current_user()

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    cur.execute(
        q("""
        SELECT *
        FROM orders
        WHERE username = ?
        ORDER BY id DESC
        """),
        (user["username"],)
    )

    rows = fetchall_dict(cur)

    conn.close()

    return render_template(
        "orders.html",
        user=user,
        orders=rows,
        plans=PLANS
    )

# ================================
# Admin
# ================================

@app.route("/admin")
@admin_required
def admin():

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    cur.execute(
        q("""
        SELECT *
        FROM orders
        ORDER BY id DESC
        """)
    )

    orders = fetchall_dict(cur)

    cur.execute(
        q("""
        SELECT
        username,
        role,
        membership_plan,
        membership_expires_at,
        created_at
        FROM users
        ORDER BY id DESC
        """)
    )

    users = fetchall_dict(cur)

    conn.close()

    return render_template(
        "admin.html",
        user=current_user(),
        orders=orders,
        users=users,
        plans=PLANS,
        signal_count=len(load_signals())
    )

# ================================
# Approve Order
# ================================

@app.route("/admin/approve-order/<int:order_id>", methods=["POST"])
@admin_required
def approve_order(order_id):

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    cur.execute(
        q("SELECT * FROM orders WHERE id = ?"),
        (order_id,)
    )

    order = fetchone_dict(cur)

    if not order:

        conn.close()

        flash("订单不存在")

        return redirect(url_for("admin"))

    if order["status"] == "approved":

        conn.close()

        flash("订单已开通")

        return redirect(url_for("admin"))

    username = order["username"]

    cur.execute(
        q("SELECT * FROM users WHERE username = ?"),
        (username,)
    )

    user = fetchone_dict(cur)

    if not user:

        conn.close()

        flash("用户不存在")

        return redirect(url_for("admin"))

    plan_code = order["plan_code"]

    days = PLANS[plan_code]["days"]

    base_time = now()

    if user["membership_expires_at"]:

        try:

            existing = datetime.fromisoformat(
                user["membership_expires_at"]
            )

            if existing > base_time:
                base_time = existing

        except:
            pass

    new_expiry = (
        base_time + timedelta(days=days)
    ).isoformat()

    cur.execute(
        q("""
        UPDATE users
        SET membership_plan = ?,
            membership_expires_at = ?
        WHERE username = ?
        """),
        (
            plan_code,
            new_expiry,
            username
        )
    )

    cur.execute(
        q("""
        UPDATE orders
        SET status='approved',
            approved_at=?
        WHERE id=?
        """),
        (
            now().isoformat(),
            order_id
        )
    )

    conn.commit()

    conn.close()

    flash("订单已开通")

    return redirect(url_for("admin"))

# ================================
# Reject Order
# ================================

@app.route("/admin/reject-order/<int:order_id>", methods=["POST"])
@admin_required
def reject_order(order_id):

    conn = get_conn()

    if USE_POSTGRES:
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    else:
        cur = conn.cursor()

    cur.execute(
        q("""
        UPDATE orders
        SET status='rejected',
            rejected_at=?
        WHERE id=?
        """),
        (
            now().isoformat(),
            order_id
        )
    )

    conn.commit()

    conn.close()

    flash("已拒绝订单")

    return redirect(url_for("admin"))

# ================================
# Health
# ================================

@app.route("/health")
def health():

    try:

        conn = get_conn()

        if USE_POSTGRES:
            cur = conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        else:
            cur = conn.cursor()

        cur.execute(q(
            "SELECT COUNT(*) AS n FROM users"
        ))

        users = fetchone_dict(cur)["n"]

        cur.execute(q(
            "SELECT COUNT(*) AS n FROM orders"
        ))

        orders = fetchone_dict(cur)["n"]

        conn.close()

        return {
            "status": "ok",
            "version": "v8-full-postgres",
            "database": (
                "postgresql"
                if USE_POSTGRES
                else "sqlite"
            ),
            "users": users,
            "orders": orders,
            "signals": len(load_signals())
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }, 500

# ================================
# API Signals
# ================================

@app.route("/api/signals")
@login_required
def api_signals():

    user = current_user()

    signals = load_signals()

    visible = (
        signals
        if is_paid(user)
        else signals[:3]
    )

    return jsonify(visible)

# ================================
# Init
# ================================

init_db()

# ================================
# Main
# ================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )