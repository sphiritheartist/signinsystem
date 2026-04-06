from flask import Flask, request, jsonify, session, Response, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
from datetime import datetime, date
import os
import csv

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Local SQLite for testing (no Supabase needed)
DB_PATH = 'attendance.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Init DB
with get_db() as db:
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'employee'
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date DATE,
        sign_in DATETIME,
        sign_out DATETIME,
        lat REAL,
        lng REAL
    )''')
    # Sample data
    hashed_admin = generate_password_hash('STA.Ad26_P@$$')
    hashed_emp = generate_password_hash('pass')
    db.execute("INSERT OR IGNORE INTO users (id, name, username, password_hash, role) VALUES (1, 'Simphiwe Phiri', 'simphiwe', ?, 'admin')", (hashed_admin,))
    db.execute("INSERT OR IGNORE INTO users (id, name, username, password_hash, role) VALUES (2, 'Employee', 'emp', ?, 'employee')", (hashed_emp,))
    db.commit()

# Auth Decorator
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, password_hash, role FROM users WHERE username=?", (data['username'],))
    user = cur.fetchone()

    if user and check_password_hash(user['password_hash'], data['password']):
        session['user_id'] = user['id']
        session['role'] = user['role']
        return jsonify({"message": "Login successful", "role": user['role']})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role', 'employee')
    return render_template('dashboard.html', role=role)

@app.route('/admin')
@login_required
def admin_page():
    if session.get('role') != 'admin':
        return "Access denied. Admin only.", 403
    return render_template('admin.html')

@app.route('/report-page')
@login_required
def report_page():
    if session.get('role') != 'admin':
        return "Access denied. Admin only.", 403
    return render_template('report.html')

@app.route('/admin/create-user', methods=['POST'])
@login_required
def create_user():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    hashed = generate_password_hash(data['password'])

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (name, username, password_hash, role) VALUES (?, ?, ?, ?)",
        (data['name'], data['username'], hashed, data.get('role', 'employee'))
    )
    db.commit()
    return jsonify({"message": "User created"})

@app.route('/admin/users', methods=['GET'])
@login_required
def get_users():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, name, username, role FROM users")
    users = cur.fetchall()
    return jsonify([dict(u) for u in users])

@app.route('/signin', methods=['POST'])
@login_required
def signin():
    user_id = session['user_id']
    today = date.today()
    data = request.json

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM attendance WHERE user_id=? AND date=?", (user_id, today))
    existing = cur.fetchone()

    if existing:
        return jsonify({"error": "Already signed in today"})

    cur.execute(
        "INSERT INTO attendance (user_id, date, sign_in, lat, lng) VALUES (?, ?, ?, ?, ?)",
        (user_id, today, datetime.now(), data.get('lat'), data.get('lng'))
    )
    db.commit()
    return jsonify({"message": "Signed in with location"})

@app.route('/signout', methods=['POST'])
@login_required
def signout():
    user_id = session['user_id']
    today = date.today()

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE attendance SET sign_out=? WHERE user_id=? AND date=?",
        (datetime.now(), user_id, today)
    )
    db.commit()
    return jsonify({"message": "Signed out"})

@app.route('/report', methods=['GET'])
@login_required
def report():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 
            u.name,
            COUNT(a.id) AS days_present,
            ROUND(SUM(strftime('%s', a.sign_out) - strftime('%s', a.sign_in)) / 3600.0, 2) AS total_hours
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE a.sign_out IS NOT NULL
        GROUP BY u.name
    """)
    data = cur.fetchall()
    return jsonify([dict(d) for d in data])

@app.route('/user-report/<user_id>', methods=['GET'])
@login_required
def user_report(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 
            date,
            sign_in,
            sign_out,
            (strftime('%s', sign_out) - strftime('%s', sign_in)) / 3600.0 AS hours
        FROM attendance
        WHERE user_id=?
        ORDER BY date DESC
    """, (user_id,))
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route('/export', methods=['GET'])
@login_required
def export_csv():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 
            u.name,
            COUNT(a.id),
            SUM((strftime('%s', a.sign_out) - strftime('%s', a.sign_in)) / 3600.0)
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
