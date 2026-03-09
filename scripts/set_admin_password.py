#!/usr/bin/env python3
"""One-off: set admin@ferreiracosta.com.br password to 'admin' for tenant fcosta-gus.
Run from project root: .venv/bin/python3 scripts/set_admin_password.py
"""
import os
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(root, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip("'\"")
                os.environ.setdefault(k.strip(), v)

# Use same deps as backend (bcrypt, mysql.connector)
import bcrypt
import mysql.connector

def main():
    h = bcrypt.hashpw(b"admin", bcrypt.gensalt(rounds=12)).decode()
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "mysql"),
        password=os.getenv("DB_PASSWORD", "mysql"),
        database=os.getenv("DB_NAME", "chamador"),
        autocommit=True,
    )
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tenant_users tu
        INNER JOIN tenants t ON t.cpf_cnpj = tu.tenant_cpf_cnpj AND t.slug = %s
        SET tu.password_hash = %s
        WHERE tu.email = %s
        """,
        ("fcosta-gus", h, "admin@ferreiracosta.com.br"),
    )
    n = cur.rowcount
    cur.close()
    conn.close()
    print(f"Updated {n} row(s).")
    return 0 if n >= 0 else 1

if __name__ == "__main__":
    sys.exit(main())
