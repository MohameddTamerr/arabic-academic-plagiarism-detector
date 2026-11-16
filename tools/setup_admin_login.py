# -*- coding: utf-8 -*-
import sqlite3
import bcrypt
import urllib.request
import json
from pathlib import Path
from datetime import datetime

new_password = 'Academic@2026#Secure'
pw_bytes = new_password.encode('utf-8')
salt = bcrypt.gensalt(rounds=12)
new_hash = bcrypt.hashpw(pw_bytes, salt).decode('utf-8')

db_paths = [
    Path(r'C:\Users\user\AppData\Local\ArabicAcademicPlagiarismSystem\Data\Database\papers.db'),
    Path(r'C:\Users\user\AppData\Roaming\ArabicPlagiarismDetector\papers.db')
]

for db_path in db_paths:
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        
        # Ensure Tamer Darwish has the new password
        c.execute('UPDATE users SET password_hash = ?, is_active = 1 WHERE LOWER(username) = ?', (new_hash, 'tamer darwish'))
        
        # Check if 'admin' exists
        existing_admin = c.execute('SELECT id FROM users WHERE LOWER(username) = ?', ('admin',)).fetchone()
        if existing_admin:
            c.execute('UPDATE users SET password_hash = ?, role = "system_admin", is_active = 1 WHERE id = ?', (new_hash, existing_admin[0]))
            print(f'{db_path.name}: updated existing admin user (id={existing_admin[0]})')
        else:
            c.execute('''
                INSERT INTO users (username, password_hash, full_name, role, is_active, session_version, created_at)
                VALUES (?, ?, ?, ?, 1, 1, ?)
            ''', ('admin', new_hash, 'مدير النظام (Admin)', 'system_admin', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            print(f'{db_path.name}: created new admin user with role system_admin')
            
        # Clear lockouts
        c.execute('UPDATE auth_lockouts SET failed_count = 0, locked_until = NULL, lockout_count = 0')
        conn.commit()
        conn.close()

# Test login for both 'admin' and 'Tamer Darwish'
for uname in ['admin', 'Tamer Darwish']:
    try:
        with urllib.request.urlopen('http://127.0.0.1:5000/api/auth/csrf_token', timeout=5) as resp:
            csrf_token = json.loads(resp.read().decode()).get('csrf_token')
            
        login_data = json.dumps({'username': uname, 'password': new_password}).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:5000/api/auth/login',
            data=login_data,
            headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf_token}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode())
            print(f'Login [{uname}]: success={res.get("success")} | role={res.get("user", {}).get("role")} | name={res.get("user", {}).get("full_name")}')
    except Exception as e:
        print(f'Login [{uname}] error:', e)
