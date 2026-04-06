-- SAFE: Create only if missing (NO DROP - preserves data!)
-- Run once or anytime

DO $$ BEGIN
  CREATE TABLE IF NOT EXISTS users (
    id uuid primary key default gen_random_uuid(),
    name text,
    username text unique,
    password_hash text,
    role text default 'employee'
  );
EXCEPTION WHEN duplicate_table THEN RAISE NOTICE 'users table already exists';
END $$;

DO $$ BEGIN
  CREATE TABLE IF NOT EXISTS attendance (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id),
    date date,
    sign_in timestamp,
    sign_out timestamp,
    lat float,
    lng float
  );
EXCEPTION WHEN duplicate_table THEN RAISE NOTICE 'attendance table already exists';
END $$;

-- Add columns if missing (safe)
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS lat float;
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS lng float;

-- Admin (safe insert)
INSERT INTO users (name, username, password_hash, role) 
VALUES ('Admin', 'admin', '$2b$12$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 'admin') 
ON CONFLICT (username) DO NOTHING;

-- Password: password
