-- Safe idempotent Supabase setup (DROP IF EXISTS)
DROP TABLE IF EXISTS attendance CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
  id uuid primary key default gen_random_uuid(),
  name text,
  username text unique,
  password_hash text,
  role text default 'employee'
);

CREATE TABLE attendance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id),
  date date,
  sign_in timestamp,
  sign_out timestamp,
  lat float,
  lng float
);

-- Admin user (password: password)
INSERT INTO users (name, username, password_hash, role) 
VALUES ('Admin', 'admin', '$2b$12$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 'admin') 
ON CONFLICT (username) DO NOTHING;
