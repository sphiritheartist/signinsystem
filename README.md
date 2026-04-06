# Mntambo Safety Services - Attendance System

## Local Testing (SQLite)
1. Copy `.env.example` to `.env` (leave empty)
2. `pip install -r requirements.txt`
3. `python app.py`
4. Login: admin/adminpass or emp/emppass
5. Visit http://localhost:5000

## Render Deployment
1. Push to GitHub
2. Connect to Render
3. Set Environment Variables (from .env.example):
   - DB_HOST=hostlink - not actual
   - DB_PORT=5432
   - DB_NAME=postgres
   - DB_USER=postgres
   - DB_PASSWORD=PASSWORD - not actual
   - SECRET_KEY=your-strong-secret
   - ENV=production
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app`

**Note**: Create `users` and `attendance` tables in Supabase first, matching local schema.

