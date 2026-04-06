from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from datetime import datetime, date
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Database connection updated to use environment variable
conn = psycopg2.connect(os.environ.get("DATABASE_URL"))

# LOGIN
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username=%s", (data['username'],))
    user = cur.fetchone()

    if user and check_password_hash(user[1], data['password']):
        session['user_id'] = user[0]
        return jsonify({"message": "Login successful"})
    return jsonify({"error": "Invalid credentials"}), 401


# SIGN IN
@app.route('/signin', methods=['POST'])
def signin():
    user_id = session.get('user_id')
    today = date.today()

    cur = conn.cursor()
    cur.execute("SELECT * FROM attendance WHERE user_id=%s AND date=%s", (user_id, today))
    existing = cur.fetchone()

    if existing:
        return jsonify({"error": "Already signed in today"})

    cur.execute(
        "INSERT INTO attendance (user_id, date, sign_in) VALUES (%s, %s, %s)",
        (user_id, today, datetime.now())
    )
    conn.commit()
    return jsonify({"message": "Signed in"})


# SIGN OUT
@app.route('/signout', methods=['POST'])
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


# REPORT
@app.route('/report', methods=['GET'])
def report():
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            u.name,
            COUNT(a.id),
            SUM(EXTRACT(EPOCH FROM (a.sign_out - a.sign_in)) / 3600)
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        GROUP BY u.name
    """)
    data = cur.fetchall()
    return jsonify(data)


if __name__ == "__main__":
    app.run()