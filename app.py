from flask import Flask, request, jsonify, session, Response, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import psycopg2
from datetime import datetime, date
import os
import csv

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Session Security Config
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# Database connection updated to discrete parameters
conn = psycopg2.connect(
    host="db.cavvrgrzkgandndcyzrl.supabase.co",
    database="postgres",
    user="postgres",
    password=os.environ.get("STA.Ad26_P@$$"),
    port=5432
)

# Auth Decorator
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

# LOGIN
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash, role FROM users WHERE username=%s", (data['username'],))
    user = cur.fetchone()

    if user and check_password_hash(user[1], data['password']):
        session['user_id'] = user[0]
        session['role'] = user[2]
        return jsonify({"message": "Login successful", "role": user[2]})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/')
def index():
    return render_template('login.html')

# ADMIN: CREATE USER
@app.route('/admin/create-user', methods=['POST'])
def create_user():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    hashed = generate_password_hash(data['password'])

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (name, username, password_hash, role) VALUES (%s, %s, %s, %s)",
        (data['name'], data['username'], hashed, data.get('role', 'employee'))
    )
    conn.commit()

    return jsonify({"message": "User created"})

# ADMIN: GET ALL USERS
@app.route('/admin/users', methods=['GET'])
def get_users():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    cur = conn.cursor()
    cur.execute("SELECT id, name, username, role FROM users")
    users = cur.fetchall()

    return jsonify(users)

# SIGN IN
@app.route('/signin', methods=['POST'])
@login_required
def signin():
    user_id = session.get('user_id')
    today = date.today()
    data = request.json

    cur = conn.cursor()
    cur.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
    existing = cur.fetchone()

    if existing:
        return jsonify({"error": "Already signed in today"})

    # Add lat/lng columns if not exist
    cur.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS lat NUMERIC")
    cur.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS lng NUMERIC")
    conn.commit()

    cur.execute(
        "INSERT INTO attendance (user_id, date, sign_in, lat, lng) VALUES (%s, %s, %s, %s, %s)",
        (user_id, today, datetime.now(), data.get('lat'), data.get('lng'))
    )
    conn.commit()
    return jsonify({"message": "Signed in"})

# SIGN OUT
@app.route('/signout', methods=['POST'])
@login_required
def signout():
    user_id = session.get('user_id')
    today = date.today()

    cur = conn.cursor()
    cur.execute(
        "UPDATE attendance SET sign_out=%s WHERE user_id=%s AND date=%s",
        (datetime.now(), user_id, today)
    )
    conn.commit()
    return jsonify({"message": "Signed out"})

# GENERAL REPORT
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

# USER SPECIFIC REPORT
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

# New routes
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/report-page')
def report_page():
    return render_template('report.html')

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
    app.run()

