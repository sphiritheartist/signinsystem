from flask import Flask, request, jsonify, session, Response, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import psycopg2
import sqlite3
from dotenv import load_dotenv
from datetime import datetime, date
import os
import csv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')

# Session Security Config
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv('ENV') == 'production',
    SESSION_COOKIE_SAMESITE='Lax'
)

# Database config from env vars (Render-friendly)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASSWORD', '')

# SQLite fallback for local testing
use_sqlite = (DB_HOST == 'localhost' and not DB_PASS)

if use_sqlite:
    DB_PATH = 'attendance.db'
    DB_CONN = None  # Will use function

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'employee'
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date DATE NOT NULL,
            sign_in DATETIME NOT NULL,
            sign_out DATETIME,
            lat REAL,
            lng REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        # Sample admin/emp for local testing
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            hashed_admin = generate_password_hash('adminpass')
            hashed_emp = generate_password_hash('emppass')
            conn.execute("INSERT INTO users (name, username, password_hash, role) VALUES ('Admin User', 'admin', ?, 'admin')", (hashed_admin,))
            conn.execute("INSERT INTO users (name, username, password_hash, role) VALUES ('Employee', 'emp', ?, 'employee')", (hashed_emp,))
            conn.commit()
        conn.commit()
        return conn
else:
    # PostgreSQL for Render/Supabase
    DB_CONN = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    def get_db():
        cur = DB_CONN.cursor()
        return DB_CONN

# Auth Decorator
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

# Root route
@app.route('/')
def index():
    return render_template('login.html')

# LOGIN POST
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    db = get_db()
    cur = db.cursor()
    if use_sqlite:
        cur.execute("SELECT id, password_hash, role FROM users WHERE username=?", (data['username'],))
        user = cur.fetchone()
        if user:
            user = dict(user)
    else:
        cur.execute("SELECT id, password_hash, role FROM users WHERE username=%s", (data['username'],))
        user = cur.fetchone()
        if user:
            user = (user[0], user[1], user[2])

    if user and check_password_hash(user['password_hash'], data['password']): 
        session['user_id'] = user['id']
        session['role'] = user['role']
        db.close() if use_sqlite else None
        return jsonify({"message": "Login successful", "role": user['role']})
    db.close() if use_sqlite else None
    return jsonify({"error": "Invalid credentials"}), 401

# Dashboard - pass role for template
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', role=session.get('role', 'employee'))

# Admin
@app.route('/admin')
@login_required
def admin_page():
    return render_template('admin.html')

# Report page
@app.route('/report-page')
@login_required
def report_page():
    return render_template('report.html')

# ADMIN: CREATE USER
@app.route('/admin/create-user', methods=['POST'])
@login_required
def create_user():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    hashed = generate_password_hash(data['password'])

    db = get_db()
    cur = db.cursor()
    try:
        if use_sqlite:
            cur.execute(
                "INSERT INTO users (name, username, password_hash, role) VALUES (?, ?, ?, ?)",
                (data['name'], data['username'], hashed, data.get('role', 'employee'))
            )
        else:
            cur.execute(
                "INSERT INTO users (name, username, password_hash, role) VALUES (%s, %s, %s, %s)",
                (data['name'], data['username'], hashed, data.get('role', 'employee'))
            )
        db.commit()
        db.close() if use_sqlite else None
        return jsonify({"message": "User created"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ADMIN: GET ALL USERS
@app.route('/admin/users', methods=['GET'])
@login_required
def get_users():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, name, username, role FROM users")
    users = cur.fetchall()
    if use_sqlite:
        users = [dict(u) for u in users]
    db.close() if use_sqlite else None
    return jsonify(users)


# ADMIN: DELETE USER
@app.route('/admin/delete-user', methods=['POST'])
@login_required
def delete_user():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    user_id = data['user_id']
    
    db = get_db()
    cur = db.cursor()
    try:
        if use_sqlite:
            cur.execute("DELETE FROM attendance WHERE user_id=?", (user_id,))
            cur.execute("DELETE FROM users WHERE id=?", (user_id,))
        else:
            cur.execute("DELETE FROM attendance WHERE user_id=%s", (user_id,))
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        db.commit()
        db.close() if use_sqlite else None
        return jsonify({"message": "User deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# SIGN IN with GPS
@app.route('/signin', methods=['POST'])
@login_required
def signin():
    user_id = session['user_id']
    today = date.today()
    data = request.json

    db = get_db()
    cur = db.cursor()
    if use_sqlite:
        cur.execute("SELECT * FROM attendance WHERE user_id=? AND date=?", (user_id, today))
        existing = cur.fetchone()
    else:
        cur.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
        existing = cur.fetchone()

    if existing:
        db.close() if use_sqlite else None
        return jsonify({"error": "Already signed in today"})

    if use_sqlite:
        cur.execute(
            "INSERT INTO attendance (user_id, date, sign_in, lat, lng) VALUES (?, ?, ?, ?, ?)",
            (user_id, today, datetime.now(), data.get('lat'), data.get('lng'))
        )
    else:
        # Add columns if missing
        cur.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS lat NUMERIC")
        cur.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS lng NUMERIC")
        db.commit()
        cur.execute(
            "INSERT INTO attendance (user_id, date, sign_in, lat, lng) VALUES (%s, %s, %s, %s, %s)",
            (user_id, today, datetime.now(), data.get('lat'), data.get('lng'))
        )
    db.commit()
    db.close() if use_sqlite else None
    return jsonify({"message": "Signed in with location"})

# SIGN OUT
@app.route('/signout', methods=['POST'])
@login_required
def signout():
    user_id = session['user_id']
    today = date.today()

    db = get_db()
    cur = db.cursor()
    if use_sqlite:
        cur.execute(
            "UPDATE attendance SET sign_out=? WHERE user_id=? AND date=?",
            (datetime.now(), user_id, today)
        )
    else:
        cur.execute(
            "UPDATE attendance SET sign_out=%s WHERE user_id=%s AND date=%s",
            (datetime.now(), user_id, today)
        )
    db.commit()
    db.close() if use_sqlite else None
    return jsonify({"message": "Signed out"})

# REPORT JSON for charts
@app.route('/report', methods=['GET'])
@login_required
def report():
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            u.name,
            COUNT(a.id) AS days_present,
            ROUND(SUM(EXTRACT(EPOCH FROM (a.sign_out - a.sign_in)) / 3600), 2) AS total_hours,
            ROUND(AVG(EXTRACT(HOUR FROM a.sign_in)), 2) AS avg_sign_in,
            ROUND(AVG(EXTRACT(HOUR FROM a.sign_out)), 2) AS avg_sign_out,
            SUM(CASE WHEN EXTRACT(HOUR FROM a.sign_in) > 8 THEN 1 ELSE 0 END) AS late_days,
            SUM(CASE WHEN EXTRACT(HOUR FROM a.sign_out) < 17 THEN 1 ELSE 0 END) AS early_leaves
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE a.sign_out IS NOT NULL
        GROUP BY u.name
    """)
    data = cur.fetchall()
    return jsonify(data)

# USER REPORT
@app.route('/user-report/<user_id>', methods=['GET'])
@login_required
def user_report(user_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            date,
            sign_in,
            sign_out,
            EXTRACT(EPOCH FROM (sign_out - sign_in)) / 3600 AS hours
        FROM attendance
        WHERE user_id=%s
        ORDER BY date DESC
    """, (user_id,))
    return jsonify(cur.fetchall())

# EXPORT CSV
@app.route('/export', methods=['GET'])
@login_required
def export_csv():
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            u.name,
            COUNT(a.id),
            SUM(EXTRACT(EPOCH FROM (a.sign_out - a.sign_in)) / 3600)
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE a.sign_out IS NOT NULL
        GROUP BY u.name
    """)

    rows = cur.fetchall()

    def generate():
        yield "Name,Days Present,Total Hours\n"
        for r in rows:
            yield f"{r[0]},{r[1]},{round(r[2],2)}\n"

    return Response(generate(), mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=report.csv"})


if __name__ == "__main__":
    app.run(debug=True)

