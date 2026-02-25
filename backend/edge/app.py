from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Set, Tuple
from urllib.parse import quote
from urllib.request import Request, urlopen

import mysql.connector
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from PIL import Image

from .auth import create_access_token, decode_access_token, hash_password, require_role, verify_password
from .thermal_print import print_ticket

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "mysql")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mysql")
DB_NAME = os.getenv("DB_NAME", "chamador")

APP_HOST = os.getenv("EDGE_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("EDGE_PORT", "7071"))

DEVICE_TOKEN = os.getenv("EDGE_DEVICE_TOKEN", "dev-edge-token")
EDGE_TENANT_CPF_CNPJ = os.getenv("EDGE_TENANT_CPF_CNPJ")  # optional: pin tenant on this edge instance
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


_DEFAULT_DB = object()


@contextmanager
def db_conn(database: Optional[str] | object = _DEFAULT_DB):
    kwargs = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "autocommit": True,
    }
    if database is _DEFAULT_DB:
        kwargs["database"] = DB_NAME
    elif database is None:
        # server-level connection (no database selected)
        pass
    else:
        kwargs["database"] = database
    conn = mysql.connector.connect(**kwargs)
    try:
        yield conn
    finally:
        conn.close()


def require_token(auth_header: Optional[str]):
    # Simple MVP auth: Bearer token shared between TV/Test UI and Edge.
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = auth_header.split(" ", 1)[1].strip()
    if token != DEVICE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


def require_jwt(auth_header: Optional[str]) -> Dict[str, Any]:
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = auth_header.split(" ", 1)[1].strip()
    return decode_access_token(token)


def tenant_from_jwt(payload: Dict[str, Any]) -> str:
    tenant = payload.get("tenant_cpf_cnpj")
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid token (tenant)")
    return str(tenant)


def ensure_database_exists():
    with db_conn(database=None) as conn:
        cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )


def ensure_migrations_table(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version VARCHAR(32) NOT NULL PRIMARY KEY,
          applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def list_migration_files() -> List[Tuple[str, str]]:
    """
    Returns list of (version, filepath) sorted by version asc.
    File pattern: 001_init.sql -> version '001'
    """
    if not os.path.isdir(MIGRATIONS_DIR):
        return []
    items: List[Tuple[str, str]] = []
    for name in os.listdir(MIGRATIONS_DIR):
        if not name.endswith(".sql"):
            continue
        prefix = name.split("_", 1)[0]
        if not prefix.isdigit():
            continue
        items.append((prefix, os.path.join(MIGRATIONS_DIR, name)))
    items.sort(key=lambda x: int(x[0]))
    return items


def applied_migrations(conn) -> Set[str]:
    ensure_migrations_table(conn)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT version FROM schema_migrations")
    return {r["version"] for r in cur.fetchall()}


def apply_sql_file(conn, filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    cur = conn.cursor()
    for stmt in statements:
        cur.execute(stmt)


def run_migrations(reset: bool = False) -> Dict[str, Any]:
    if reset:
        with db_conn(database=None) as conn:
            cur = conn.cursor()
            cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
    ensure_database_exists()

    files = list_migration_files()
    if not files:
        return {"ok": True, "applied": [], "note": "no migrations found"}

    applied_now: List[str] = []
    with db_conn() as conn:
        ensure_migrations_table(conn)
        already = applied_migrations(conn)
        for version, path in files:
            if version in already:
                continue
            apply_sql_file(conn, path)
            cur = conn.cursor()
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    return {"ok": True, "applied": applied_now}


app = FastAPI(title="Chamador Edge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _get_lan_ip() -> Optional[str]:
    """IP da interface usada para a rota padrão (útil para QR no dashboard)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


@app.get("/health")
def health():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
    return {"ok": True, "time": utc_now().isoformat()}


@app.get("/api/host")
def api_host():
    """Retorna o host/IP acessível na rede (para QR do Totem etc). Usar PUBLIC_HOST ou EDGE_PUBLIC_HOST se definido."""
    host = os.getenv("PUBLIC_HOST") or os.getenv("EDGE_PUBLIC_HOST") or _get_lan_ip()
    return {"host": host or ""}


@app.post("/admin/init-db")
def init_db(reset: bool = Query(default=False), authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    # Backward-compatible endpoint: now runs migrations.
    return run_migrations(reset=reset)


@app.post("/admin/migrate")
def migrate(reset: bool = Query(default=False), authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    return run_migrations(reset=reset)


@app.post("/admin/seed")
def seed(authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        tenant_cpf_cnpj = EDGE_TENANT_CPF_CNPJ or "10230480000130"
        cur.execute("SELECT cpf_cnpj FROM tenants WHERE cpf_cnpj = %s", (tenant_cpf_cnpj,))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO tenants (cpf_cnpj, nome_razao_social, nome_fantasia, situacao, logo_base64)
                VALUES (%s, %s, %s, 'ativo', NULL)
                """,
                (tenant_cpf_cnpj, "FERREIRA COSTA & CIA LTDA", "FERREIRA COSTA"),
            )

        cur.execute("SELECT COUNT(*) AS c FROM youtube_urls WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        if (cur.fetchone() or {}).get("c", 0) == 0:
            cur.execute(
                """
                INSERT INTO youtube_urls (id, tenant_cpf_cnpj, url, title, position, enabled)
                VALUES
                  (UUID(), %s, %s, %s, 1, 1),
                  (UUID(), %s, %s, %s, 2, 1)
                """,
                (
                    tenant_cpf_cnpj,
                    "https://www.youtube.com/watch?v=G0YWhbsBuRc",
                    "Vídeo 1 (tenant)",
                    tenant_cpf_cnpj,
                    "https://www.youtube.com/watch?v=CK4b9_0tQOk",
                    "Vídeo 2 (tenant)",
                ),
            )

        cur.execute("SELECT COUNT(*) AS c FROM announcements")
        if (cur.fetchone() or {}).get("c", 0) == 0:
            cur.execute(
                """
                INSERT INTO announcements (id, message, position, enabled)
                VALUES
                  (UUID(), 'INFORMATIVO: Atendimento até às 19h durante o mês de Dezembro.', 1, 1),
                  (UUID(), 'AVISO: Tenha em mãos seu documento para agilizar o atendimento.', 2, 1)
                """
            )

        # Tenant announcements (ticker) - per tenant
        cur.execute("SELECT COUNT(*) AS c FROM tenant_announcements WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        if (cur.fetchone() or {}).get("c", 0) == 0:
            cur2 = conn.cursor()
            cur2.execute(
                """
                INSERT INTO tenant_announcements (id, tenant_cpf_cnpj, message, position, enabled)
                VALUES
                  (UUID(), %s, %s, 1, 1),
                  (UUID(), %s, %s, 2, 1)
                """,
                (
                    tenant_cpf_cnpj,
                    "INFORMATIVO: Atendimento até às 19h durante o mês de Dezembro.",
                    tenant_cpf_cnpj,
                    "AVISO: Tenha em mãos seu documento para agilizar o atendimento.",
                ),
            )

        # Users (admin/operator) for portal/operator UI
        cur.execute("SELECT COUNT(*) AS c FROM tenant_users WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        if (cur.fetchone() or {}).get("c", 0) == 0:
            admin_hash = hash_password("admin123")
            op_hash = hash_password("amanda123")
            cur2 = conn.cursor()
            cur2.execute(
                """
                INSERT INTO tenant_users (id, tenant_cpf_cnpj, email, full_name, role, password_hash, active)
                VALUES
                  (UUID(), %s, %s, %s, 'admin', %s, 1),
                  (UUID(), %s, %s, %s, 'operator', %s, 1)
                """,
                (
                    tenant_cpf_cnpj,
                    "admin@ferreiracosta.com.br",
                    "Admin Ferreira Costa",
                    admin_hash,
                    tenant_cpf_cnpj,
                    "amanda@ferreiracosta.com.br",
                    "Amanda Operadora",
                    op_hash,
                ),
            )

        # Basic counters and services
        cur.execute("SELECT COUNT(*) AS c FROM counters WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        if (cur.fetchone() or {}).get("c", 0) == 0:
            cur2 = conn.cursor()
            cur2.execute(
                """
                INSERT INTO counters (id, tenant_cpf_cnpj, name, active)
                VALUES
                  (UUID(), %s, 'Guichê 01', 1),
                  (UUID(), %s, 'Guichê 02', 1),
                  (UUID(), %s, 'Guichê 03', 1)
                """,
                (tenant_cpf_cnpj, tenant_cpf_cnpj, tenant_cpf_cnpj),
            )

        cur.execute("SELECT COUNT(*) AS c FROM services WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        if (cur.fetchone() or {}).get("c", 0) == 0:
            cur2 = conn.cursor()
            cur2.execute(
                """
                INSERT INTO services (id, tenant_cpf_cnpj, name, priority_mode, active)
                VALUES
                  (UUID(), %s, 'Atendimento', 'normal', 1),
                  (UUID(), %s, 'Preferencial', 'preferential', 1)
                """,
                (tenant_cpf_cnpj, tenant_cpf_cnpj),
            )

    return {"ok": True}


def extract_youtube_id(url: str) -> Optional[str]:
    url = (url or "").strip()
    if not url:
        return None
    # Support:
    # - https://www.youtube.com/watch?v=ID
    # - https://youtu.be/ID
    # - https://www.youtube.com/embed/ID
    # - https://www.youtube.com/shorts/ID
    if "youtu.be/" in url:
        part = url.split("youtu.be/", 1)[1]
        vid = part.split("?", 1)[0].split("&", 1)[0].strip()
        return vid or None
    if "/embed/" in url:
        part = url.split("/embed/", 1)[1]
        vid = part.split("?", 1)[0].split("&", 1)[0].strip().strip("/")
        return vid or None
    if "/shorts/" in url:
        part = url.split("/shorts/", 1)[1]
        vid = part.split("?", 1)[0].split("&", 1)[0].strip().strip("/")
        return vid or None
    if "watch?v=" in url:
        part = url.split("watch?v=", 1)[1]
        vid = part.split("&", 1)[0].strip()
        return vid or None
    return None


def fetch_youtube_oembed(video_url: str) -> Dict[str, Any]:
    """
    Fetch YouTube metadata via oEmbed (no API key).
    Returns dict with keys: title, author_name, thumbnail_url (best effort).
    """
    # https://www.youtube.com/oembed?url=...&format=json
    oembed_url = f"https://www.youtube.com/oembed?url={quote(video_url, safe='')}&format=json"
    req = Request(oembed_url, headers={"User-Agent": "Chamador/1.0 (+oEmbed)"})
    try:
        with urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return {
            "title": data.get("title"),
            "author_name": data.get("author_name"),
            "thumbnail_url": data.get("thumbnail_url"),
        }
    except Exception:
        return {}


def resolve_tenant_cpf_cnpj() -> Optional[str]:
    if EDGE_TENANT_CPF_CNPJ:
        return EDGE_TENANT_CPF_CNPJ
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT cpf_cnpj FROM tenants WHERE situacao = 'ativo' ORDER BY created_at ASC LIMIT 1")
        row = cur.fetchone()
        return row["cpf_cnpj"] if row else None


def fetch_state() -> Dict[str, Any]:
    tenant_cpf_cnpj = resolve_tenant_cpf_cnpj()
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT cpf_cnpj, nome_razao_social, nome_fantasia, situacao, logo_base64, tv_theme, tv_audio_enabled, tv_call_sound, tv_video_muted, tv_video_paused, admin_playlist_filter,
                   tts_enabled, tts_voice, tts_speed, tts_volume
            FROM tenants
            WHERE cpf_cnpj = %s
            """,
            (tenant_cpf_cnpj or "",),
        )
        tenant = cur.fetchone()

        # Buscar todas as chamadas em atendimento (status 'called') do tenant
        cur.execute(
            """
            SELECT * FROM calls
            WHERE tenant_cpf_cnpj = %s AND status IN ('called')
            ORDER BY called_at DESC
            """,
            (tenant_cpf_cnpj or "",),
        )
        legacy_current_calls = cur.fetchall()

        # Para compatibilidade, current_call é a mais recente
        current_call = legacy_current_calls[0] if legacy_current_calls else None

        # Histórico: últimas 10 chamadas (para o painel lateral)
        cur.execute(
            """
            SELECT * FROM calls
            WHERE tenant_cpf_cnpj = %s AND status IN ('called')
            ORDER BY called_at DESC
            LIMIT 10
            """,
            (tenant_cpf_cnpj or "",),
        )
        legacy_history = cur.fetchall()

        # Tickets (novo fluxo): refletir chamados/em atendimento e histórico finalizado no /tv/state
        cur.execute(
            """
            SELECT id, ticket_code, service_name, priority, status, counter_name, operator_name,
                   called_at, service_started_at, completed_at
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status IN ('called', 'in_service')
            ORDER BY COALESCE(service_started_at, called_at) DESC
            """,
            (tenant_cpf_cnpj or "",),
        )
        tickets_current = cur.fetchall()

        cur.execute(
            """
            SELECT id, ticket_code, service_name, priority, status, counter_name, operator_name,
                   called_at, service_started_at, completed_at
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status IN ('completed', 'no_show', 'cancelled')
            ORDER BY completed_at DESC
            LIMIT 10
            """,
            (tenant_cpf_cnpj or "",),
        )
        tickets_history = cur.fetchall()

        # Fila de espera: tickets aguardando (para a TV mostrar quem está esperando)
        cur.execute(
            """
            SELECT id, ticket_code, service_name, priority, issued_at
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'waiting'
            ORDER BY issued_at ASC
            LIMIT 20
            """,
            (tenant_cpf_cnpj or "",),
        )
        waiting_rows = cur.fetchall()
        waiting_queue = [
            {
                "id": r.get("id"),
                "ticket_code": r.get("ticket_code"),
                "service_name": r.get("service_name"),
                "priority": r.get("priority"),
                "issued_at": r.get("issued_at").isoformat() if r.get("issued_at") else None,
            }
            for r in waiting_rows
        ]

        # Tenant ticker messages
        cur.execute(
            """
            SELECT id, message, position
            FROM tenant_announcements
            WHERE enabled = 1 AND tenant_cpf_cnpj = %s
            ORDER BY position ASC
            """,
            (tenant_cpf_cnpj or "",),
        )
        announcements = cur.fetchall()

        cur.execute(
            """
            SELECT id, tenant_cpf_cnpj, media_type, url, title, description, author_name, thumbnail_url, duration_seconds,
                   youtube_id, metadata_fetched_at, image_url, slide_duration_seconds,
                   position, enabled, created_at
            FROM youtube_urls
            WHERE enabled = 1 AND tenant_cpf_cnpj = %s
            ORDER BY position ASC, created_at ASC
            """,
            (tenant_cpf_cnpj or "",),
        )
        urls = cur.fetchall()
        playlist = []
        for r in urls:
            media_type = (r.get("media_type") or "youtube").strip().lower()
            
            if media_type == "youtube":
                yid = (r.get("youtube_id") or "").strip() or extract_youtube_id(r.get("url") or "")
                if not yid:
                    continue
                playlist.append(
                    {
                        "id": r["id"],
                        "media_type": "youtube",
                        "youtube_id": yid,
                        "url": r.get("url"),
                        "title": r.get("title") or "",
                        "description": r.get("description") or "",
                        "author_name": r.get("author_name") or "",
                        "thumbnail_url": r.get("thumbnail_url") or "",
                        "duration_seconds": r.get("duration_seconds"),
                        "metadata_fetched_at": r.get("metadata_fetched_at").isoformat() if r.get("metadata_fetched_at") else None,
                        "position": r.get("position"),
                        "enabled": 1,
                        "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                    }
                )
            else:  # slide
                image_url = (r.get("image_url") or "").strip()
                if not image_url:
                    continue
                playlist.append(
                    {
                        "id": r["id"],
                        "media_type": "slide",
                        "image_url": image_url,
                        "title": r.get("title") or "Slide",
                        "description": r.get("description") or "",
                        "slide_duration_seconds": r.get("slide_duration_seconds") or 10,
                        "position": r.get("position"),
                        "enabled": 1,
                        "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                    }
                )

    def normalize_call(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        return {
            "id": row["id"],
            "ticket_code": row["ticket_code"],
            "service_name": row["service_name"],
            "priority": row["priority"],
            "counter_name": row["counter_name"],
            "status": row["status"],
            "called_at": row["called_at"].isoformat() if row.get("called_at") else None,
        }

    def normalize_ticket_to_call(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        return {
            "id": row.get("id"),
            "ticket_code": row.get("ticket_code"),
            "service_name": row.get("service_name"),
            "priority": row.get("priority"),
            "counter_name": row.get("counter_name") or "",
            "status": row.get("status"),
            "operator_name": row.get("operator_name"),
            "called_at": row.get("called_at").isoformat() if row.get("called_at") else None,
            "service_started_at": row.get("service_started_at").isoformat() if row.get("service_started_at") else None,
            "completed_at": row.get("completed_at").isoformat() if row.get("completed_at") else None,
        }

    merged_current_calls: List[Dict[str, Any]] = []
    merged_current_calls.extend([c for c in (normalize_ticket_to_call(r) for r in tickets_current) if c])
    merged_current_calls.extend([c for c in (normalize_call(r) for r in legacy_current_calls) if c])

    def sort_key(x: Dict[str, Any]) -> str:
        return str(x.get("called_at") or "")

    merged_current_calls.sort(key=sort_key, reverse=True)

    # Prefer to show real ticket history (completed/no_show/cancelled).
    # Legacy calls are only a fallback when there is no ticket history at all.
    merged_history: List[Dict[str, Any]] = [c for c in (normalize_ticket_to_call(r) for r in tickets_history) if c]
    if merged_history:
        merged_history.sort(key=sort_key, reverse=True)
        merged_history = merged_history[:10]
    else:
        merged_history = [c for c in (normalize_call(r) for r in legacy_history) if c][:10]

    # Garantir que campos Decimal do tenant sejam float (JSON serializable)
    if tenant:
        for _f in ("tts_speed", "tts_volume"):
            if _f in tenant and tenant[_f] is not None:
                tenant[_f] = float(tenant[_f])

    return {
        "tenant_cpf_cnpj": tenant_cpf_cnpj,
        "tenant": tenant,
        "current_call": normalize_call(current_call),
        "current_calls": merged_current_calls,
        "history": merged_history,
        "waiting_queue": waiting_queue,
        "announcements": announcements,
        "playlist": playlist,
        "server_time": utc_now().isoformat(),
    }


@app.get("/tv/state")
def tv_state(authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    return JSONResponse(fetch_state())


@app.get("/tenant/me")
def tenant_me(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT cpf_cnpj, nome_razao_social, nome_fantasia, situacao, logo_base64
            FROM tenants
            WHERE cpf_cnpj = %s
            """,
            (tenant_cpf_cnpj,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return row


@app.get("/tenant/dashboard")
def tenant_dashboard(authorization: Optional[str] = Header(default=None)):
    """
    Mini-dashboard administrativo do tenant.
    Nota (MVP): a tabela `calls` ainda não está tenant-scoped, então os contadores de chamadas são globais.
    """
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Tenant identification
        cur.execute(
            """
            SELECT cpf_cnpj, nome_razao_social, nome_fantasia, situacao
            FROM tenants
            WHERE cpf_cnpj = %s
            """,
            (tenant_cpf_cnpj,),
        )
        tenant = cur.fetchone()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Counters/services/users are tenant-scoped
        cur.execute("SELECT COUNT(*) AS n FROM counters WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        counters_total = int((cur.fetchone() or {}).get("n") or 0)

        cur.execute("SELECT COUNT(*) AS n FROM services WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        services_total = int((cur.fetchone() or {}).get("n") or 0)

        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM tenant_users
            WHERE tenant_cpf_cnpj = %s AND role = 'operator' AND active = 1
            """,
            (tenant_cpf_cnpj,),
        )
        operators_total = int((cur.fetchone() or {}).get("n") or 0)

        # Atendimentos hoje: tickets completed + calls (tenant-scoped)
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'completed' AND DATE(completed_at) = CURDATE()
            """,
            (tenant_cpf_cnpj,),
        )
        tickets_today = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM calls
            WHERE tenant_cpf_cnpj = %s AND called_at IS NOT NULL AND DATE(called_at) = CURDATE()
            """,
            (tenant_cpf_cnpj,),
        )
        calls_today = int((cur.fetchone() or {}).get("n") or 0)
        tickets_attended_today = max(tickets_today, calls_today)

        # Em atendimento (últimos 60 min): tickets called/in_service
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status IN ('called', 'in_service')
              AND (service_started_at IS NOT NULL OR called_at IS NOT NULL)
              AND TIMESTAMPDIFF(MINUTE, COALESCE(service_started_at, called_at), NOW()) <= 60
            """,
            (tenant_cpf_cnpj,),
        )
        in_service_last_60m = int((cur.fetchone() or {}).get("n") or 0)

        cur.execute(
            """
            SELECT MAX(completed_at) AS last_at FROM tickets
            WHERE tenant_cpf_cnpj = %s AND completed_at IS NOT NULL
            """,
            (tenant_cpf_cnpj,),
        )
        last_called_at = (cur.fetchone() or {}).get("last_at")
        if not last_called_at:
            cur.execute(
                "SELECT MAX(called_at) AS last_at FROM calls WHERE tenant_cpf_cnpj = %s AND called_at IS NOT NULL",
                (tenant_cpf_cnpj,),
            )
            last_called_at = (cur.fetchone() or {}).get("last_at")

    return {
        "tenant": tenant,
        "counters_total": counters_total,
        "services_total": services_total,
        "operators_total": operators_total,
        "in_service_last_60m": in_service_last_60m,
        "tickets_attended_today": tickets_attended_today,
        "last_called_at": last_called_at.isoformat() if last_called_at else None,
        "server_time": utc_now().isoformat(),
    }


@app.get("/tenant/dashboard/analytics")
def dashboard_analytics(
    period: str = Query(default="7d", description="7d ou 30d"),
    authorization: Optional[str] = Header(default=None),
):
    """Atendimentos por dia no período (para gráfico). Baseado em tickets completed."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    days = 7 if period == "7d" else 30

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT DATE(completed_at) AS dt, COUNT(*) AS n
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'completed' AND completed_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY DATE(completed_at)
            ORDER BY dt ASC
            """,
            (tenant_cpf_cnpj, days),
        )
        rows = cur.fetchall()
    from datetime import date, timedelta
    result = {}
    for r in rows:
        dt = r.get("dt")
        key = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        result[key] = int(r.get("n") or 0)
    labels = []
    values = []
    today = date.today()
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        labels.append(d.strftime("%d/%m"))
        values.append(result.get(key, 0))
    return {"labels": labels, "values": values, "period": period}


@app.get("/tenant/dashboard/top-operators")
def dashboard_top_operators(
    period: str = Query(default="7d", description="today, 7d, 30d"),
    limit: int = Query(default=10, ge=1, le=50),
    authorization: Optional[str] = Header(default=None),
):
    """Ranking de atendentes por quantidade de atendimentos concluídos."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    if period == "today":
        date_filter = "AND DATE(t.completed_at) = CURDATE()"
    elif period == "30d":
        date_filter = "AND t.completed_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"
    else:
        date_filter = "AND t.completed_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT t.operator_id, t.operator_name, COUNT(*) AS completed_count
            FROM tickets t
            WHERE t.tenant_cpf_cnpj = %s AND t.status = 'completed' AND t.operator_id IS NOT NULL
            {date_filter}
            GROUP BY t.operator_id, t.operator_name
            ORDER BY completed_count DESC
            LIMIT %s
            """,
            (tenant_cpf_cnpj, limit),
        )
        rows = cur.fetchall()
    return [{"operator_id": r["operator_id"], "operator_name": r["operator_name"] or "—", "completed_count": int(r["completed_count"] or 0)} for r in rows]


@app.get("/tenant/dashboard/history")
def dashboard_history(
    from_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    operator_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
):
    """Histórico de atendimentos com filtros (para modal)."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    conditions = ["t.tenant_cpf_cnpj = %s", "t.status = 'completed'"]
    args = [tenant_cpf_cnpj]
    if from_date:
        conditions.append("DATE(t.completed_at) >= %s")
        args.append(from_date)
    if to_date:
        conditions.append("DATE(t.completed_at) <= %s")
        args.append(to_date)
    if operator_id:
        conditions.append("t.operator_id = %s")
        args.append(operator_id)
    args.append(limit)
    where = " AND ".join(conditions)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT t.id, t.ticket_code, t.service_name, t.priority, t.operator_name, t.counter_name,
                   t.called_at, t.service_started_at, t.completed_at
            FROM tickets t
            WHERE {where}
            ORDER BY t.completed_at DESC
            LIMIT %s
            """,
            args,
        )
        rows = cur.fetchall()
    def row_to_dict(r):
        return {
            "id": r.get("id"),
            "ticket_code": r.get("ticket_code"),
            "service_name": r.get("service_name"),
            "priority": r.get("priority"),
            "operator_name": r.get("operator_name"),
            "counter_name": r.get("counter_name"),
            "called_at": r["called_at"].isoformat() if r.get("called_at") else None,
            "service_started_at": r["service_started_at"].isoformat() if r.get("service_started_at") else None,
            "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
        }
    return [row_to_dict(r) for r in rows]


@app.get("/tenant/dashboard/kpis")
def dashboard_kpis(
    period: str = Query(default="30d", description="7d ou 30d"),
    authorization: Optional[str] = Header(default=None),
):
    """KPIs para cards do dashboard: preferenciais x normais, maior/menor tempo, operador destaque, menor tempo médio."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    days = 7 if period == "7d" else 30
    date_filter = "AND completed_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)"

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        # Preferenciais x Normais
        cur.execute(
            """
            SELECT priority, COUNT(*) AS n
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'completed'
            """ + date_filter + """
            GROUP BY priority
            """,
            (tenant_cpf_cnpj, days),
        )
        by_priority = {r["priority"]: int(r["n"] or 0) for r in cur.fetchall()}
        preferential_count = by_priority.get("preferential", 0)
        normal_count = by_priority.get("normal", 0)

        # Maior e menor tempo de atendimento (segundos entre service_started_at e completed_at)
        cur.execute(
            """
            SELECT
              MAX(TIMESTAMPDIFF(SECOND, service_started_at, completed_at)) AS max_sec,
              MIN(TIMESTAMPDIFF(SECOND, service_started_at, completed_at)) AS min_sec
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'completed'
              AND service_started_at IS NOT NULL AND completed_at IS NOT NULL
            """ + date_filter,
            (tenant_cpf_cnpj, days),
        )
        row = cur.fetchone() or {}
        max_duration_seconds = int(row.get("max_sec") or 0)
        min_duration_seconds = int(row.get("min_sec") or 0)

        # Operador com mais atendimentos (destaque / maior quantidade)
        cur.execute(
            """
            SELECT operator_id, operator_name, COUNT(*) AS completed_count
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'completed' AND operator_id IS NOT NULL
            """ + date_filter + """
            GROUP BY operator_id, operator_name
            ORDER BY completed_count DESC
            LIMIT 1
            """,
            (tenant_cpf_cnpj, days),
        )
        top_row = cur.fetchone()
        top_operator_name = (top_row.get("operator_name") or "—") if top_row else "—"
        top_operator_count = int((top_row or {}).get("completed_count") or 0)

        # Operador com menor tempo médio de atendimento (só quem tem pelo menos 1 atendimento com duração)
        cur.execute(
            """
            SELECT t.operator_id, t.operator_name,
                   AVG(TIMESTAMPDIFF(SECOND, t.service_started_at, t.completed_at)) AS avg_sec
            FROM tickets t
            WHERE t.tenant_cpf_cnpj = %s AND t.status = 'completed'
              AND t.service_started_at IS NOT NULL AND t.completed_at IS NOT NULL
              AND t.operator_id IS NOT NULL
              AND t.completed_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY t.operator_id, t.operator_name
            HAVING COUNT(*) >= 1
            ORDER BY avg_sec ASC
            LIMIT 1
            """,
            (tenant_cpf_cnpj, days),
        )
        fast_row = cur.fetchone()
        fastest_operator_name = (fast_row.get("operator_name") or "—") if fast_row else "—"
        fastest_operator_avg_seconds = int((fast_row or {}).get("avg_sec") or 0)

    return {
        "period": period,
        "preferential_count": preferential_count,
        "normal_count": normal_count,
        "max_duration_seconds": max_duration_seconds,
        "min_duration_seconds": min_duration_seconds,
        "top_operator_name": top_operator_name,
        "top_operator_count": top_operator_count,
        "fastest_operator_name": fastest_operator_name,
        "fastest_operator_avg_seconds": fastest_operator_avg_seconds,
    }


@app.get("/tenant/dashboard/live")
def dashboard_live(authorization: Optional[str] = Header(default=None)):
    """Monitor ao vivo: fila atual, atendimentos de hoje, médias e breakdown por hora."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Fila atual (aguardando)
        cur.execute(
            """
            SELECT priority, COUNT(*) AS n
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'waiting'
            GROUP BY priority
            """,
            (tenant_cpf_cnpj,),
        )
        queue_by_priority = {r["priority"]: int(r["n"] or 0) for r in cur.fetchall()}

        # Contagens do dia por status
        cur.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND DATE(issued_at) = CURDATE()
            GROUP BY status
            """,
            (tenant_cpf_cnpj,),
        )
        today_by_status = {r["status"]: int(r["n"] or 0) for r in cur.fetchall()}

        # Tempo médio de espera hoje (issued_at → called_at)
        cur.execute(
            """
            SELECT AVG(TIMESTAMPDIFF(SECOND, issued_at, called_at)) AS avg_wait
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND called_at IS NOT NULL
              AND DATE(issued_at) = CURDATE()
            """,
            (tenant_cpf_cnpj,),
        )
        row = cur.fetchone() or {}
        avg_wait = int(row.get("avg_wait") or 0)

        # Tempo médio de atendimento hoje (service_started_at → completed_at)
        cur.execute(
            """
            SELECT AVG(TIMESTAMPDIFF(SECOND, service_started_at, completed_at)) AS avg_svc
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'completed'
              AND service_started_at IS NOT NULL AND completed_at IS NOT NULL
              AND DATE(issued_at) = CURDATE()
            """,
            (tenant_cpf_cnpj,),
        )
        row = cur.fetchone() or {}
        avg_service = int(row.get("avg_svc") or 0)

        # Breakdown por hora (últimas 12h, baseado em completed_at e no_show/called)
        cur.execute(
            """
            SELECT
              HOUR(COALESCE(completed_at, called_at)) AS hora,
              SUM(status = 'completed') AS atendidos,
              SUM(status IN ('no_show', 'cancelled')) AS desistentes
            FROM tickets
            WHERE tenant_cpf_cnpj = %s
              AND DATE(issued_at) = CURDATE()
              AND (completed_at IS NOT NULL OR called_at IS NOT NULL)
            GROUP BY hora
            ORDER BY hora ASC
            """,
            (tenant_cpf_cnpj,),
        )
        hourly_rows = cur.fetchall()

    pref_queue = queue_by_priority.get("preferential", 0)
    norm_queue = queue_by_priority.get("normal", 0)
    attended = today_by_status.get("completed", 0)
    in_service = today_by_status.get("called", 0) + today_by_status.get("in_service", 0)
    no_show = today_by_status.get("no_show", 0)
    cancelled = today_by_status.get("cancelled", 0)

    hourly = [
        {
            "hour": f"{int(r['hora']):02d}:00",
            "attended": int(r["atendidos"] or 0),
            "desistentes": int(r["desistentes"] or 0),
        }
        for r in hourly_rows
        if r["hora"] is not None
    ]

    return {
        "queue": {"preferential": pref_queue, "normal": norm_queue, "total": pref_queue + norm_queue},
        "today": {
            "attended": attended,
            "in_service": in_service,
            "no_show": no_show,
            "cancelled": cancelled,
            "desistentes": no_show + cancelled,
        },
        "avg_wait_seconds": avg_wait,
        "avg_service_seconds": avg_service,
        "hourly": hourly,
        "server_time": utc_now().isoformat(),
    }


# ============================================================
# YouTube playlist (tenant-scoped) - CRUD for Admin Tenant
# ============================================================


@app.get("/tenant/youtube")
def tenant_list_youtube(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, url, title,
                   description, author_name, thumbnail_url, duration_seconds,
                   youtube_id, metadata_fetched_at,
                   media_type, image_url, slide_duration_seconds,
                   position, enabled, created_at
            FROM youtube_urls
            WHERE tenant_cpf_cnpj = %s
            ORDER BY position ASC, created_at ASC
            """,
            (tenant_cpf_cnpj,),
        )
        rows = cur.fetchall()
        for r in rows:
            if r.get("metadata_fetched_at"):
                r["metadata_fetched_at"] = r["metadata_fetched_at"].isoformat()
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return rows


@app.post("/tenant/youtube")
def tenant_create_youtube(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    # Get media_type from payload
    media_type_raw = payload_in.get("media_type")
    if media_type_raw:
        media_type = str(media_type_raw).strip().lower()
    else:
        media_type = "youtube"
    
    if media_type not in ("youtube", "slide"):
        media_type = "youtube"

    description = (payload_in.get("description") or "").strip() or None  # comment
    enabled = 1 if payload_in.get("enabled", True) else 0
    position = payload_in.get("position")
    try:
        position_i = int(position) if position is not None else 1
    except Exception:
        position_i = 1
    if position_i < 1:
        position_i = 1

    now = utc_now()
    youtube_id = None
    title = None
    author_name = None
    thumbnail_url = None
    image_url = None
    slide_duration = None
    url = None

    if media_type == "youtube":
        url = (payload_in.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required for YouTube videos")
        youtube_id = extract_youtube_id(url) or None
        meta = fetch_youtube_oembed(url)
        title = (meta.get("title") or "").strip() or None
        author_name = (meta.get("author_name") or "").strip() or None
        thumbnail_url = (meta.get("thumbnail_url") or "").strip() or None
    else:  # slide
        # Para slides, aceitar apenas image_base64 (upload de arquivo)
        image_base64 = payload_in.get("image_base64")
        if image_base64:
            image_base64 = str(image_base64).strip()
        else:
            image_base64 = ""
        
        if not image_base64:
            raise HTTPException(status_code=400, detail="image_base64 is required for slides (upload a file)")
        
        # Salvar imagem base64 no servidor
        try:
            if not image_base64.startswith("data:image/"):
                raise HTTPException(status_code=400, detail="image_base64 must be a data URL (data:image/...)")
            # Extrair tipo e dados
            header, data = image_base64.split(",", 1)
            mime_type = header.split(";")[0].replace("data:", "")
            ext = mime_type.split("/")[1] if "/" in mime_type else "png"
            
            # Criar diretório para slides
            base_dir = os.getcwd()
            slides_dir = os.path.join(base_dir, ".run", "slides")
            os.makedirs(slides_dir, exist_ok=True)
            
            # Salvar arquivo
            slide_id = str(uuid.uuid4())
            fname = f"{slide_id}.{ext}"
            saved_path = os.path.join(slides_dir, fname)
            
            import base64
            with open(saved_path, "wb") as f:
                f.write(base64.b64decode(data))
            
            # URL relativa para servir depois
            image_url = f"/api/slides/{fname}"
            title = payload_in.get("title") or "Slide"
            # Não gerar thumbnail - usar image_url diretamente com CSS resize
            thumbnail_url = None
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error saving image: {str(e)}")
        
        slide_duration = payload_in.get("slide_duration_seconds")
        try:
            slide_duration = int(slide_duration) if slide_duration is not None else 10
        except Exception:
            slide_duration = 10
        if slide_duration < 1:
            slide_duration = 10

    with db_conn() as conn:
        cur = conn.cursor()
        vid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO youtube_urls
              (id, tenant_cpf_cnpj, media_type, url, title, description, author_name, thumbnail_url,
               duration_seconds, youtube_id, metadata_fetched_at, image_url, slide_duration_seconds,
               position, enabled)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s,
               %s, %s, %s, %s, %s,
               %s, %s)
            """,
            (
                vid,
                tenant_cpf_cnpj,
                media_type,
                url,
                title,
                description,
                author_name,
                thumbnail_url,
                None,  # duration_seconds (só para YouTube, NULL para slides)
                youtube_id,
                now if (media_type == "youtube" and (title or author_name or thumbnail_url or youtube_id)) else None,
                image_url,
                slide_duration if media_type == "slide" else None,
                position_i,
                enabled,
            ),
        )
    return {"ok": True, "id": vid}


@app.put("/tenant/youtube/{video_id}")
def tenant_update_youtube(video_id: str, payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    # Verificar o tipo de mídia atual
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT media_type FROM youtube_urls WHERE id = %s AND tenant_cpf_cnpj = %s",
            (video_id, tenant_cpf_cnpj),
        )
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Item not found")
        current_media_type = (existing.get("media_type") or "youtube").strip().lower()

    url = payload_in.get("url")
    description = payload_in.get("description")
    enabled = payload_in.get("enabled")
    position = payload_in.get("position")
    refetch = bool(payload_in.get("refetch_metadata", False))
    title = payload_in.get("title")
    image_url = payload_in.get("image_url")
    image_base64 = payload_in.get("image_base64")
    slide_duration = payload_in.get("slide_duration_seconds")

    sets: List[str] = []
    args: List[Any] = []

    if current_media_type == "youtube":
        if url is not None:
            u = str(url).strip()
            if not u:
                raise HTTPException(status_code=400, detail="url cannot be empty")
            sets.append("url = %s")
            args.append(u)
            if refetch:
                youtube_id = extract_youtube_id(u) or None
                meta = fetch_youtube_oembed(u)
                title = (meta.get("title") or "").strip() or None
                author_name = (meta.get("author_name") or "").strip() or None
                thumbnail_url = (meta.get("thumbnail_url") or "").strip() or None
                sets.extend(
                    [
                        "youtube_id = %s",
                        "title = %s",
                        "author_name = %s",
                        "thumbnail_url = %s",
                        "metadata_fetched_at = %s",
                    ]
                )
                args.extend([youtube_id, title, author_name, thumbnail_url, utc_now()])
    else:  # slide
        if image_base64:
            # Salvar nova imagem
            try:
                if not image_base64.startswith("data:image/"):
                    raise HTTPException(status_code=400, detail="image_base64 must be a data URL (data:image/...)")
                header, data = image_base64.split(",", 1)
                mime_type = header.split(";")[0].replace("data:", "")
                ext = mime_type.split("/")[1] if "/" in mime_type else "png"
                
                base_dir = os.getcwd()
                slides_dir = os.path.join(base_dir, ".run", "slides")
                os.makedirs(slides_dir, exist_ok=True)
                
                slide_id = str(uuid.uuid4())
                fname = f"{slide_id}.{ext}"
                saved_path = os.path.join(slides_dir, fname)
                
                import base64
                with open(saved_path, "wb") as f:
                    f.write(base64.b64decode(data))
                
                image_url = f"/api/slides/{fname}"
                sets.append("image_url = %s")
                args.append(str(image_url).strip())
                # Não gerar thumbnail - usar image_url diretamente com CSS resize
                # Remover thumbnail_url se existir
                sets.append("thumbnail_url = NULL")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error saving image: {str(e)}")
        # Se não houver image_base64 na edição, mantém a imagem existente (não atualiza image_url)
        
        if slide_duration is not None:
            try:
                sd = int(slide_duration)
                if sd < 1:
                    sd = 10
            except Exception:
                sd = 10
            sets.append("slide_duration_seconds = %s")
            args.append(sd)

    if title is not None:
        sets.append("title = %s")
        args.append(str(title).strip() or None)

    if description is not None:
        sets.append("description = %s")
        args.append(str(description).strip() or None)

    if enabled is not None:
        sets.append("enabled = %s")
        args.append(1 if enabled else 0)

    if position is not None:
        try:
            p = int(position)
        except Exception:
            raise HTTPException(status_code=400, detail="position must be an integer")
        if p < 1:
            p = 1
        sets.append("position = %s")
        args.append(p)

    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE youtube_urls SET {', '.join(sets)} WHERE id = %s AND tenant_cpf_cnpj = %s",
            (*args, video_id, tenant_cpf_cnpj),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@app.delete("/tenant/youtube/{video_id}")
def tenant_delete_youtube(video_id: str, authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM youtube_urls WHERE id = %s AND tenant_cpf_cnpj = %s", (video_id, tenant_cpf_cnpj))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Video not found")
    return {"ok": True}


@app.post("/tenant/youtube/{video_id}/toggle")
def tenant_toggle_youtube(video_id: str, payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    enabled = payload_in.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="enabled is required")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE youtube_urls SET enabled = %s WHERE id = %s AND tenant_cpf_cnpj = %s",
            (1 if enabled else 0, video_id, tenant_cpf_cnpj),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Video not found")
    return {"ok": True}


@app.post("/tenant/youtube/reorder")
def tenant_reorder_youtube(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    items = payload_in.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")

    updates: List[Tuple[int, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        vid = str(it.get("id") or "").strip()
        pos = it.get("position")
        if not vid:
            continue
        try:
            p = int(pos)
        except Exception:
            raise HTTPException(status_code=400, detail="position must be an integer")
        if p < 1:
            p = 1
        updates.append((p, vid))

    if not updates:
        raise HTTPException(status_code=400, detail="No valid items")

    with db_conn() as conn:
        cur = conn.cursor()
        for p, vid in updates:
            cur.execute(
                "UPDATE youtube_urls SET position = %s WHERE id = %s AND tenant_cpf_cnpj = %s",
                (p, vid, tenant_cpf_cnpj),
            )
    return {"ok": True, "updated": len(updates)}


def generate_thumbnail(image_path: str, output_path: str, size: Tuple[int, int] = (128, 72), quality: int = 85) -> str:
    """
    Gera uma thumbnail da imagem original.
    
    Args:
        image_path: Caminho da imagem original
        output_path: Caminho onde salvar a thumbnail
        size: Tamanho da thumbnail (width, height), padrão (128, 72)
        quality: Qualidade JPEG (1-100), padrão 85
    
    Returns:
        Caminho do arquivo gerado
    """
    try:
        # Abrir imagem original
        img = Image.open(image_path)
        # Converter para RGB se necessário (para JPEG)
        if img.mode in ('RGBA', 'LA'):
            # Criar fundo branco para imagens com transparência
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                rgb_img.paste(img, mask=img.split()[3])  # Usar canal alpha
            else:  # LA
                rgb_img.paste(img, mask=img.split()[1])  # Usar canal alpha
            img.close()
            img = rgb_img
        elif img.mode == 'P':
            # Imagem com paleta - converter para RGB
            if 'transparency' in img.info:
                img = img.convert('RGBA')
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3])
                img.close()
                img = rgb_img
            else:
                img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Calcular dimensões mantendo proporção (crop center)
        target_width, target_height = size
        img_width, img_height = img.size
        target_ratio = target_width / target_height
        img_ratio = img_width / img_height
        
        if img_ratio > target_ratio:
            # Imagem é mais larga - crop horizontal
            new_height = img_height
            new_width = int(img_height * target_ratio)
            left = (img_width - new_width) // 2
            top = 0
            right = left + new_width
            bottom = new_height
        else:
            # Imagem é mais alta - crop vertical
            new_width = img_width
            new_height = int(img_width / target_ratio)
            left = 0
            top = (img_height - new_height) // 2
            right = new_width
            bottom = top + new_height
        
        # Crop e resize
        cropped = img.crop((left, top, right, bottom))
        thumbnail = cropped.resize(size, Image.LANCZOS)
        
        # Salvar como JPEG
        thumbnail.save(output_path, 'JPEG', quality=quality, optimize=True)
        thumbnail.close()
        if hasattr(img, 'close'):
            img.close()
            
        return output_path
    except Exception as e:
        raise Exception(f"Error generating thumbnail: {str(e)}")


def _sounds_dir() -> str:
    """Directory containing call sound files (project root / sounds)."""
    base = os.getcwd()
    return os.path.join(base, "sounds")


@app.get("/api/sounds")
def list_sounds():
    """List available sound filenames for call alert (MP3/WAV in sounds/)."""
    import glob
    sounds_dir = _sounds_dir()
    if not os.path.isdir(sounds_dir):
        return {"sounds": ["notification-1.mp3"]}
    names = []
    for ext in ("*.mp3", "*.wav"):
        for path in glob.glob(os.path.join(sounds_dir, ext)):
            names.append(os.path.basename(path))
    names.sort()
    return {"sounds": names if names else ["notification-1.mp3"]}


@app.get("/api/sounds/{filename}")
def serve_sound(filename: str):
    """Serve a sound file from the sounds/ directory (for TV call alert)."""
    import mimetypes
    if not all(c.isalnum() or c in ("-", "_", ".") for c in filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    sounds_dir = _sounds_dir()
    file_path = os.path.join(sounds_dir, filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(sounds_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "audio/mpeg"
    with open(file_path, "rb") as f:
        body = f.read()
    return StreamingResponse(iter([body]), media_type=mime_type)


_TTS_DIGIT_WORDS = {
    '0': 'zero', '1': 'um', '2': 'dois', '3': 'três', '4': 'quatro',
    '5': 'cinco', '6': 'seis', '7': 'sete', '8': 'oito', '9': 'nove',
}
_TTS_KOKORO_URL = os.environ.get("KOKORO_TTS_URL", "http://localhost:8880/v1/audio/speech")
_TTS_VALID_VOICES = {"pf_dora", "pm_alex", "pm_santa"}


def _tts_cache_dir() -> str:
    return os.path.join(os.getcwd(), ".run", "tts_cache")


def _format_call_text(ticket_code: str, service_name: str, counter_name: str = "") -> str:
    parts = []
    for ch in (ticket_code or "").upper():
        if ch.isdigit():
            parts.append(_TTS_DIGIT_WORDS[ch])
        elif ch.isalpha():
            parts.append(ch)
    ticket_text = " ".join(parts) if parts else ticket_code
    label = service_name.strip() if service_name and service_name.strip() else counter_name.strip()
    return f"Senha {ticket_text}, {label}." if label else f"Senha {ticket_text}."


def _prefetch_tts(tenant_cpf_cnpj: str, ticket_code: str, service_name: str, counter_name: str) -> None:
    """Pré-gera o MP3 do TTS em background para eliminar latência na TV."""
    def _run():
        try:
            with db_conn() as conn:
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    "SELECT tts_enabled, tts_voice, tts_speed, tts_volume FROM tenants WHERE cpf_cnpj = %s",
                    (tenant_cpf_cnpj,),
                )
                row = cur.fetchone()
            if not row or not row.get("tts_enabled"):
                return
            voice = (row.get("tts_voice") or "pf_dora").strip() or "pf_dora"
            speed = max(0.25, min(4.0, float(row.get("tts_speed") or 0.85)))
            volume = max(0.1, min(4.0, float(row.get("tts_volume") or 1.0)))
            text = _format_call_text(ticket_code, service_name, counter_name)
            cache_key = hashlib.md5(f"{text}|{voice}|{speed:.2f}|{volume:.2f}".encode()).hexdigest()
            cache_file = os.path.join(_tts_cache_dir(), f"{cache_key}.mp3")
            if os.path.isfile(cache_file):
                return
            os.makedirs(_tts_cache_dir(), exist_ok=True)
            payload = json.dumps({
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "response_format": "mp3",
                "speed": speed,
                "volume_multiplier": volume,
            }).encode()
            req = Request(_TTS_KOKORO_URL, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=15) as resp:
                audio_bytes = resp.read()
            with open(cache_file, "wb") as f:
                f.write(audio_bytes)
        except Exception:
            pass  # Falha silenciosa — o endpoint /api/tts/call tentará de novo quando a TV pedir

    threading.Thread(target=_run, daemon=True).start()


@app.get("/api/tts/call")
def get_tts_call(ticket_code: str, counter_name: str = "", service_name: str = "",
                 voice: str = "pf_dora", speed: float = 0.85, volume: float = 1.0):
    """Gera (e cacheia) MP3 com anúncio de voz via Kokoro TTS."""
    if voice not in _TTS_VALID_VOICES:
        voice = "pf_dora"
    speed = max(0.25, min(4.0, speed))
    volume = max(0.1, min(4.0, volume))
    cache_dir = _tts_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    text = _format_call_text(ticket_code, service_name, counter_name)
    cache_key = hashlib.md5(f"{text}|{voice}|{speed:.2f}|{volume:.2f}".encode()).hexdigest()
    cache_file = os.path.join(cache_dir, f"{cache_key}.mp3")
    if not os.path.isfile(cache_file):
        payload = json.dumps({
            "model": "kokoro",
            "input": text,
            "voice": voice,
            "response_format": "mp3",
            "speed": speed,
            "volume_multiplier": volume,
        }).encode()
        try:
            req = Request(_TTS_KOKORO_URL, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=15) as resp:
                audio_bytes = resp.read()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Kokoro TTS indisponível: {e}")
        with open(cache_file, "wb") as f:
            f.write(audio_bytes)
    with open(cache_file, "rb") as f:
        body = f.read()
    return StreamingResponse(
        iter([body]),
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/slides/{filename}")
def serve_slide_image(filename: str):
    """Serve slide images from .run/slides/ directory"""
    import mimetypes
    from pathlib import Path
    
    # Security: only allow alphanumeric, dash, underscore, and dot in filename
    if not all(c.isalnum() or c in ('-', '_', '.') for c in filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    base_dir = os.getcwd()
    slides_dir = os.path.join(base_dir, ".run", "slides")
    file_path = os.path.join(slides_dir, filename)
    
    # Prevent directory traversal
    if not os.path.abspath(file_path).startswith(os.path.abspath(slides_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine content type
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/png"
    
    def generate():
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk
    
    return StreamingResponse(generate(), media_type=mime_type)


@app.get("/api/slides/thumbs/{filename}")
def serve_slide_thumbnail(filename: str):
    """Serve slide thumbnails from .run/slides/thumbs/ directory"""
    import mimetypes
    
    # Security: only allow alphanumeric, dash, underscore, and dot in filename
    if not all(c.isalnum() or c in ('-', '_', '.') for c in filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    base_dir = os.getcwd()
    slides_dir = os.path.join(base_dir, ".run", "slides")
    thumbs_dir = os.path.join(slides_dir, "thumbs")
    file_path = os.path.join(thumbs_dir, filename)
    
    # Prevent directory traversal
    if not os.path.abspath(file_path).startswith(os.path.abspath(thumbs_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Thumbnails são sempre JPEG
    def generate():
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk
    
    return StreamingResponse(generate(), media_type="image/jpeg")


@app.post("/tenant/logo")
def tenant_set_logo(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    logo_base64 = (payload_in.get("logo_base64") or "").strip()
    if not logo_base64:
        raise HTTPException(status_code=400, detail="logo_base64 is required")

    # Allow clear
    if logo_base64 == "data:,":
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE tenants
                SET logo_base64 = NULL
                WHERE cpf_cnpj = %s
                """,
                (tenant_cpf_cnpj,),
            )
        return {"ok": True}

    # Expect a data URL: data:image/png;base64,... (preferred)
    if not logo_base64.startswith("data:"):
        raise HTTPException(status_code=400, detail="logo_base64 must be a data URL (data:...)")
    # Simple size guard (~1MB)
    if len(logo_base64) > 1_000_000:
        raise HTTPException(status_code=413, detail="logo too large")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tenants
            SET logo_base64 = %s
            WHERE cpf_cnpj = %s
            """,
            (logo_base64, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.post("/auth/login")
def auth_login(payload: Dict[str, Any]):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, tenant_cpf_cnpj, email, role, password_hash, active
            FROM tenant_users
            WHERE email = %s
            LIMIT 1
            """,
            (email,),
        )
        u = cur.fetchone()
        if not u or not u.get("active"):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not verify_password(password, u["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        sub=u["id"],
        tenant_cpf_cnpj=u["tenant_cpf_cnpj"],
        role=u["role"],
        email=u["email"],
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    return {
        "sub": payload.get("sub"),
        "tenant_cpf_cnpj": payload.get("tenant_cpf_cnpj"),
        "email": payload.get("email"),
        "role": payload.get("role"),
    }


@app.get("/tenant/users")
def list_users(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, email, full_name, role, active, created_at
            FROM tenant_users
            WHERE tenant_cpf_cnpj = %s
            ORDER BY created_at DESC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.post("/tenant/users")
def create_user(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    email = (payload_in.get("email") or "").strip().lower()
    full_name = (payload_in.get("full_name") or "").strip() or None
    role = (payload_in.get("role") or "operator").strip()
    password = payload_in.get("password") or ""
    active = 1 if payload_in.get("active", True) else 0
    if role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tenant_users (id, tenant_cpf_cnpj, email, full_name, role, password_hash, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, tenant_cpf_cnpj, email, full_name, role, pw_hash, active),
        )
    return {"ok": True, "id": user_id}


@app.post("/tenant/users/delete")
def delete_user(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    uid = (payload_in.get("id") or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="id is required")
    if uid == (payload.get("sub") or ""):
        raise HTTPException(status_code=400, detail="cannot delete current user")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM tenant_users WHERE id = %s AND tenant_cpf_cnpj = %s",
            (uid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.put("/tenant/users/{user_id}")
def update_user(
    user_id: str,
    payload_in: Dict[str, Any],
    authorization: Optional[str] = Header(default=None),
):
    """Atualiza email, nome, tipo (role) e ativo. Senha opcional (só atualiza se enviada e não vazia)."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    uid = (user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required")

    email = (payload_in.get("email") or "").strip().lower()
    full_name = (payload_in.get("full_name") or "").strip() or None
    role = (payload_in.get("role") or "operator").strip()
    active = payload_in.get("active")
    password = (payload_in.get("password") or "").strip()

    if role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="role must be admin or operator")
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    if active is None:
        raise HTTPException(status_code=400, detail="active is required")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id FROM tenant_users WHERE id = %s AND tenant_cpf_cnpj = %s",
            (uid, tenant_cpf_cnpj),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        if password:
            pw_hash = hash_password(password)
            cur.execute(
                """UPDATE tenant_users
                   SET email = %s, full_name = %s, role = %s, active = %s, password_hash = %s
                   WHERE id = %s AND tenant_cpf_cnpj = %s""",
                (email, full_name, role, 1 if active else 0, pw_hash, uid, tenant_cpf_cnpj),
            )
        else:
            cur.execute(
                """UPDATE tenant_users
                   SET email = %s, full_name = %s, role = %s, active = %s
                   WHERE id = %s AND tenant_cpf_cnpj = %s""",
                (email, full_name, role, 1 if active else 0, uid, tenant_cpf_cnpj),
            )
    return {"ok": True}


@app.post("/tenant/users/toggle")
def toggle_user(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    uid = (payload_in.get("id") or "").strip()
    active = payload_in.get("active")
    if not uid:
        raise HTTPException(status_code=400, detail="id is required")
    if active is None:
        raise HTTPException(status_code=400, detail="active is required")
    if uid == (payload.get("sub") or ""):
        raise HTTPException(status_code=400, detail="cannot toggle current user")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tenant_users SET active = %s WHERE id = %s AND tenant_cpf_cnpj = %s",
            (1 if active else 0, uid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.get("/tenant/counters")
def list_counters(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, name, active, created_at
            FROM counters
            WHERE tenant_cpf_cnpj = %s
            ORDER BY created_at DESC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.post("/tenant/counters")
def create_counter(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    name = (payload_in.get("name") or "").strip()
    active = 1 if payload_in.get("active", True) else 0
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    cid = str(uuid.uuid4())
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO counters (id, tenant_cpf_cnpj, name, active)
            VALUES (%s, %s, %s, %s)
            """,
            (cid, tenant_cpf_cnpj, name, active),
        )
    return {"ok": True, "id": cid}


@app.post("/tenant/counters/delete")
def delete_counter(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    cid = (payload_in.get("id") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="id is required")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM counters WHERE id = %s AND tenant_cpf_cnpj = %s",
            (cid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.post("/tenant/counters/toggle")
def toggle_counter(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    cid = (payload_in.get("id") or "").strip()
    active = payload_in.get("active")
    if not cid:
        raise HTTPException(status_code=400, detail="id is required")
    if active is None:
        raise HTTPException(status_code=400, detail="active is required")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE counters SET active = %s WHERE id = %s AND tenant_cpf_cnpj = %s",
            (1 if active else 0, cid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.get("/tenant/services")
def list_services(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, name, priority_mode, active, created_at
            FROM services
            WHERE tenant_cpf_cnpj = %s
            ORDER BY created_at DESC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.post("/tenant/services")
def create_service(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    name = (payload_in.get("name") or "").strip()
    priority_mode = (payload_in.get("priority_mode") or "normal").strip()
    active = 1 if payload_in.get("active", True) else 0
    if priority_mode not in ("normal", "preferential"):
        raise HTTPException(status_code=400, detail="Invalid priority_mode")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    sid = str(uuid.uuid4())
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO services (id, tenant_cpf_cnpj, name, priority_mode, active)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (sid, tenant_cpf_cnpj, name, priority_mode, active),
        )
    return {"ok": True, "id": sid}


@app.post("/tenant/services/delete")
def delete_service(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    sid = (payload_in.get("id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="id is required")

    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM services WHERE id = %s AND tenant_cpf_cnpj = %s",
                (sid, tenant_cpf_cnpj),
            )
    except mysql.connector.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Não é possível excluir este serviço pois há senhas vinculadas a ele. Desative-o em vez de excluir.",
        )
    return {"ok": True}


@app.post("/tenant/services/toggle")
def toggle_service(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    sid = (payload_in.get("id") or "").strip()
    active = payload_in.get("active")
    if not sid:
        raise HTTPException(status_code=400, detail="id is required")
    if active is None:
        raise HTTPException(status_code=400, detail="active is required")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE services SET active = %s WHERE id = %s AND tenant_cpf_cnpj = %s",
            (1 if active else 0, sid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.get("/tenant/announcements")
def list_tenant_announcements(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, message, position, enabled, created_at
            FROM tenant_announcements
            WHERE tenant_cpf_cnpj = %s
            ORDER BY position ASC, created_at DESC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.post("/tenant/announcements")
def create_tenant_announcement(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    message = (payload_in.get("message") or "").strip()
    position = int(payload_in.get("position") or 1)
    enabled = 1 if payload_in.get("enabled", True) else 0
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if position < 1:
        position = 1
    aid = str(uuid.uuid4())
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tenant_announcements (id, tenant_cpf_cnpj, message, position, enabled)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (aid, tenant_cpf_cnpj, message, position, enabled),
        )
    return {"ok": True, "id": aid}


@app.post("/tenant/announcements/delete")
def delete_tenant_announcement(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    aid = (payload_in.get("id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="id is required")
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM tenant_announcements WHERE id = %s AND tenant_cpf_cnpj = %s",
            (aid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.post("/tenant/announcements/toggle")
def toggle_tenant_announcement(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    aid = (payload_in.get("id") or "").strip()
    enabled = payload_in.get("enabled")
    if not aid:
        raise HTTPException(status_code=400, detail="id is required")
    if enabled is None:
        raise HTTPException(status_code=400, detail="enabled is required")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tenant_announcements SET enabled = %s WHERE id = %s AND tenant_cpf_cnpj = %s",
            (1 if enabled else 0, aid, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.get("/tenant/tv-settings")
def get_tenant_tv_settings(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT tv_theme, tv_audio_enabled, tv_call_sound, tv_video_muted, tv_video_paused, tts_enabled, tts_voice, tts_speed, tts_volume FROM tenants WHERE cpf_cnpj = %s",
            (tenant_cpf_cnpj,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {
            "tv_theme": row.get("tv_theme") or "dark",
            "tv_audio_enabled": bool(row.get("tv_audio_enabled", 1)),
            "tv_call_sound": (row.get("tv_call_sound") or "").strip() or "notification-1.mp3",
            "tv_video_muted": bool(row.get("tv_video_muted", 1)),
            "tv_video_paused": bool(row.get("tv_video_paused", 0)),
            "tts_enabled": bool(row.get("tts_enabled", 0)),
            "tts_voice": (row.get("tts_voice") or "pf_dora").strip() or "pf_dora",
            "tts_speed": float(row.get("tts_speed") or 0.85),
            "tts_volume": float(row.get("tts_volume") or 1.0),
        }


@app.post("/tenant/tv-settings")
def set_tenant_tv_settings(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    tv_theme = (payload_in.get("tv_theme") or "dark").strip()
    tv_audio_enabled = payload_in.get("tv_audio_enabled")
    tv_call_sound = (payload_in.get("tv_call_sound") or "notification-1.mp3").strip() or "notification-1.mp3"
    tv_video_muted = payload_in.get("tv_video_muted")
    tv_video_paused = payload_in.get("tv_video_paused")
    tts_enabled = payload_in.get("tts_enabled", False)
    tts_voice = (payload_in.get("tts_voice") or "pf_dora").strip()
    tts_speed = float(payload_in.get("tts_speed") or 0.85)
    tts_volume = float(payload_in.get("tts_volume") or 1.0)
    tts_speed = max(0.25, min(4.0, tts_speed))
    tts_volume = max(0.1, min(4.0, tts_volume))

    if tv_theme not in ("dark", "light"):
        raise HTTPException(status_code=400, detail="tv_theme must be 'dark' or 'light'")
    if tv_audio_enabled is None:
        raise HTTPException(status_code=400, detail="tv_audio_enabled is required")
    if tv_video_muted is None:
        raise HTTPException(status_code=400, detail="tv_video_muted is required")
    if tv_video_paused is None:
        raise HTTPException(status_code=400, detail="tv_video_paused is required")
    # Sanitize filename: only alphanumeric, dash, underscore, dot
    if not all(c.isalnum() or c in ("-", "_", ".") for c in tv_call_sound):
        tv_call_sound = "notification-1.mp3"
    if tts_voice not in _TTS_VALID_VOICES:
        tts_voice = "pf_dora"

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE tenants
               SET tv_theme = %s, tv_audio_enabled = %s, tv_call_sound = %s, tv_video_muted = %s, tv_video_paused = %s,
                   tts_enabled = %s, tts_voice = %s, tts_speed = %s, tts_volume = %s
               WHERE cpf_cnpj = %s""",
            (tv_theme, 1 if tv_audio_enabled else 0, tv_call_sound, 1 if tv_video_muted else 0, 1 if tv_video_paused else 0,
             1 if tts_enabled else 0, tts_voice, tts_speed, tts_volume, tenant_cpf_cnpj),
        )
    return {"ok": True}


@app.post("/tenant/reset-history")
def tenant_reset_history(authorization: Optional[str] = Header(default=None)):
    """Limpa todo o histórico de senhas/chamadas do tenant (tickets e calls). Apenas admin."""
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM tickets WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        deleted_tickets = cur.rowcount
        cur.execute("DELETE FROM calls WHERE tenant_cpf_cnpj = %s", (tenant_cpf_cnpj,))
        deleted_calls = cur.rowcount
    return {
        "ok": True,
        "deleted_tickets": deleted_tickets,
        "deleted_calls": deleted_calls,
    }


@app.get("/tenant/admin-settings")
def get_tenant_admin_settings(authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT admin_playlist_filter FROM tenants WHERE cpf_cnpj = %s",
            (tenant_cpf_cnpj,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {
            "admin_playlist_filter": row.get("admin_playlist_filter") or "all",
        }


@app.post("/tenant/admin-settings")
def set_tenant_admin_settings(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    payload = require_jwt(authorization)
    require_role(payload, {"admin"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    admin_playlist_filter = (payload_in.get("admin_playlist_filter") or "all").strip()
    if admin_playlist_filter not in ("all", "videos", "slides"):
        raise HTTPException(status_code=400, detail="admin_playlist_filter must be 'all', 'videos', or 'slides'")

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tenants SET admin_playlist_filter = %s WHERE cpf_cnpj = %s",
            (admin_playlist_filter, tenant_cpf_cnpj),
        )
    return {"ok": True}


# ============================================================
# Tickets Queue System - Sistema de Fila de Senhas
# ============================================================


def get_next_ticket_number(conn, tenant_cpf_cnpj: str, ticket_prefix: str) -> int:
    """Incrementa e retorna o próximo número de senha para o prefixo/dia."""
    from datetime import date

    today = date.today()
    cur = conn.cursor(dictionary=True)

    # Tentar atualizar sequência existente
    cur.execute(
        """
        UPDATE ticket_sequences
        SET current_number = current_number + 1
        WHERE tenant_cpf_cnpj = %s AND ticket_prefix = %s AND sequence_date = %s
        """,
        (tenant_cpf_cnpj, ticket_prefix, today),
    )

    if cur.rowcount == 0:
        # Criar nova sequência para o dia
        seq_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO ticket_sequences (id, tenant_cpf_cnpj, ticket_prefix, current_number, sequence_date)
            VALUES (%s, %s, %s, 1, %s)
            ON DUPLICATE KEY UPDATE current_number = current_number + 1
            """,
            (seq_id, tenant_cpf_cnpj, ticket_prefix, today),
        )

    # Buscar número atual
    cur.execute(
        """
        SELECT current_number FROM ticket_sequences
        WHERE tenant_cpf_cnpj = %s AND ticket_prefix = %s AND sequence_date = %s
        """,
        (tenant_cpf_cnpj, ticket_prefix, today),
    )
    row = cur.fetchone()
    return row["current_number"] if row else 1


def format_ticket_code(prefix: str, number: int) -> str:
    """Formata código da senha: A-001, P-015, etc."""
    return f"{prefix}-{str(number).zfill(3)}"


def emit_ticket_for_service(
    conn,
    tenant_cpf_cnpj: str,
    service_id: str,
    priority_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Emite um ticket (senha) para um serviço ativo do tenant.
    - priority_override: 'normal'|'preferential' (opcional)
    Retorna: {ticket_id, ticket_code, service_name, priority, position_in_queue}
    """
    cur = conn.cursor(dictionary=True)

    cur.execute(
        "SELECT id, name, ticket_prefix, priority_mode FROM services WHERE id = %s AND tenant_cpf_cnpj = %s AND active = 1",
        (service_id, tenant_cpf_cnpj),
    )
    service = cur.fetchone()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    priority = (priority_override or "normal").strip()
    if priority not in ("normal", "preferential"):
        priority = "normal"
    # If service itself is preferential, keep it preferential
    if service.get("priority_mode") == "preferential":
        priority = "preferential"

    ticket_prefix = service.get("ticket_prefix") or "A"
    ticket_number = get_next_ticket_number(conn, tenant_cpf_cnpj, ticket_prefix)
    ticket_code = format_ticket_code(ticket_prefix, ticket_number)

    ticket_id = str(uuid.uuid4())
    now = utc_now()

    cur.execute(
        """
        INSERT INTO tickets (id, tenant_cpf_cnpj, ticket_code, service_id, service_name, priority, status, issued_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'waiting', %s)
        """,
        (ticket_id, tenant_cpf_cnpj, ticket_code, service_id, service["name"], priority, now),
    )

    cur.execute(
        """
        SELECT COUNT(*) AS pos FROM tickets
        WHERE tenant_cpf_cnpj = %s AND status = 'waiting' AND issued_at < %s
        """,
        (tenant_cpf_cnpj, now),
    )
    position = (cur.fetchone() or {}).get("pos", 0) + 1

    return {
        "ticket_id": ticket_id,
        "ticket_code": ticket_code,
        "service_name": service["name"],
        "priority": priority,
        "position_in_queue": position,
        "issued_at": now,
    }


@app.post("/tickets/emit")
def emit_ticket(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    """
    Emite uma nova senha (totem).
    Body: { service_id, priority? }
    """
    require_token(authorization)

    service_id = (payload_in.get("service_id") or "").strip()
    priority = (payload_in.get("priority") or "normal").strip()
    if not service_id:
        raise HTTPException(status_code=400, detail="service_id is required")

    tenant_cpf_cnpj = resolve_tenant_cpf_cnpj()
    if not tenant_cpf_cnpj:
        raise HTTPException(status_code=400, detail="No active tenant")

    with db_conn() as conn:
        out = emit_ticket_for_service(conn, tenant_cpf_cnpj, service_id, priority_override=priority)
    return {"ok": True, **out}


# ============================================================
# Acompanhamento de senha (público – link do QR Code do recibo)
# Mesma porta 7071, não exige autenticação
# ============================================================


@app.get("/acompanhar/{ticket_id}", response_class=HTMLResponse)
def acompanhar_ticket(ticket_id: str):
    """
    Página pública de acompanhamento da senha (acessada pelo QR Code do recibo).
    Mostra status, posição na fila e guichê quando chamada.
    """
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, tenant_cpf_cnpj, ticket_code, service_name, priority, status,
                   issued_at, counter_name, called_at
            FROM tickets
            WHERE id = %s
            LIMIT 1
            """,
            (ticket_id.strip(),),
        )
        row = cur.fetchone()

    if not row:
        return HTMLResponse(
            content="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Senha não encontrada</title><style>body{font-family:sans-serif;max-width:360px;margin:2rem auto;padding:1rem;text-align:center;}
h1{font-size:1.25rem;color:#666;}</style></head><body><h1>Senha não encontrada</h1><p>Verifique o link ou tente novamente.</p></body></html>""",
            status_code=404,
        )

    status = row.get("status") or "waiting"
    ticket_code = row.get("ticket_code") or "—"
    service_name = row.get("service_name") or ""
    counter_name = row.get("counter_name") or ""
    tenant_cpf_cnpj = row.get("tenant_cpf_cnpj") or ""

    # Posição na fila (somente se ainda aguardando)
    position = None
    if status == "waiting":
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM tickets
                WHERE tenant_cpf_cnpj = %s AND status = 'waiting' AND issued_at <= (SELECT issued_at FROM tickets WHERE id = %s)
                """,
                (tenant_cpf_cnpj, ticket_id.strip()),
            )
            position = (cur.fetchone() or (0,))[0]

    status_msg = {
        "waiting": "Aguardando na fila",
        "called": "Chamada – dirija-se ao guichê",
        "in_service": "Em atendimento",
        "completed": "Atendimento finalizado",
        "no_show": "Não compareceu",
        "cancelled": "Cancelada",
    }.get(status, status)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Acompanhamento – {ticket_code}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 360px; margin: 2rem auto; padding: 1rem; background: #f5f5f5; }}
    .card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    .code {{ font-size: 2rem; font-weight: 800; letter-spacing: .1em; color: #0d6efd; margin: 0.5rem 0; }}
    .status {{ font-weight: 600; color: #198754; margin: 0.5rem 0; }}
    .status.called, .status.in_service {{ color: #0d6efd; }}
    .meta {{ color: #666; font-size: 0.9rem; margin-top: 1rem; }}
    p {{ margin: 0.25rem 0; }}
  </style>
</head>
<body>
  <div class="card">
    <p class="meta">Sua senha</p>
    <p class="code">{ticket_code}</p>
    <p class="meta">{service_name}</p>
    <p class="status">{status_msg}</p>
    {f'<p class="meta">Posição na fila: {position}ª</p>' if position is not None else ''}
    {f'<p class="meta">Guichê: {counter_name}</p>' if counter_name else ''}
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)


# ============================================================
# Totem (MVP) - endpoints device-token para emitir senhas
# ============================================================


@app.get("/totem/services")
def totem_list_services(authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    tenant_cpf_cnpj = resolve_tenant_cpf_cnpj()
    if not tenant_cpf_cnpj:
        raise HTTPException(status_code=400, detail="No active tenant")
    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, name, priority_mode, ticket_prefix
            FROM services
            WHERE tenant_cpf_cnpj = %s AND active = 1
            ORDER BY name ASC, priority_mode ASC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.post("/totem/emit")
def totem_emit(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    service_id = (payload_in.get("service_id") or "").strip()
    if not service_id:
        raise HTTPException(status_code=400, detail="service_id is required")
    tenant_cpf_cnpj = resolve_tenant_cpf_cnpj()
    if not tenant_cpf_cnpj:
        raise HTTPException(status_code=400, detail="No active tenant")

    with db_conn() as conn:
        out = emit_ticket_for_service(conn, tenant_cpf_cnpj, service_id)

    # Nome do tenant para o recibo (opcional)
    tenant_name = None
    try:
        with db_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT nome_fantasia, nome_razao_social FROM tenants WHERE cpf_cnpj = %s LIMIT 1", (tenant_cpf_cnpj,))
            row = cur.fetchone()
            if row:
                tenant_name = (row.get("nome_fantasia") or row.get("nome_razao_social") or "").strip() or None
    except Exception:
        pass

    # Logo do tenant no recibo (path do arquivo). Desativado por padrão para evitar travamento na impressora.
    logo_path = os.environ.get("TICKET_LOGO_PATH", "").strip()
    if logo_path and os.path.isfile(logo_path):
        pass  # usa logo_path
    else:
        logo_path = None
    ticket_print_data = {**out, "tenant_name": tenant_name, "logo_path": logo_path}

    # Impressão térmica (ESC/POS): envia para /dev/usb/lp1 se PRINTER_ENABLED não for 0
    printed = False
    if os.environ.get("PRINTER_ENABLED", "1") != "0":
        printed = print_ticket(
            ticket_print_data,
            base_url=os.environ.get("TOTEM_BASE_URL"),
            device=os.environ.get("PRINTER_DEVICE") or "/dev/usb/lp1",
        )

    # Minimal print text (raw). Later we will add DB audit + server file write.
    print_text = (
        "CHAMADOR - TOTEM\\n"
        f"TENANT: {tenant_cpf_cnpj}\\n"
        "------------------------------\\n"
        f"SENHA: {out['ticket_code']}\\n"
        f"SERVIÇO: {out['service_name']}\\n"
        f"PRIORIDADE: {out['priority']}\\n"
        f"EMITIDO EM: {utc_now().strftime('%d/%m/%Y %H:%M:%S')}\\n"
        "------------------------------\\n"
        "Aguarde ser chamado no painel.\\n"
    )

    # Save to server (.run/prints) + audit in DB (ticket_print_jobs)
    saved_path = None
    try:
        base_dir = os.getcwd()
        prints_dir = os.path.join(base_dir, ".run", "prints")
        os.makedirs(prints_dir, exist_ok=True)
        safe_code = (out.get("ticket_code") or "ticket").replace("/", "-")
        fname = f"{safe_code}_{int(time.time())}.txt"
        saved_path = os.path.join(prints_dir, fname)
        with open(saved_path, "w", encoding="utf-8") as f:
            f.write(print_text)
    except Exception:
        saved_path = None

    print_job_id = str(uuid.uuid4())
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ticket_print_jobs
                  (id, tenant_cpf_cnpj, ticket_id, ticket_code, service_id, service_name, priority, counter_id, print_text, output_mode)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, NULL, %s, 'both')
                """,
                (
                    print_job_id,
                    tenant_cpf_cnpj,
                    out["ticket_id"],
                    out["ticket_code"],
                    service_id,
                    out["service_name"],
                    out["priority"],
                    print_text,
                ),
            )
    except Exception:
        # keep emitting working even if audit fails
        pass

    return {"ok": True, **out, "print_text": print_text, "print_job_id": print_job_id, "saved_path": saved_path, "printed": printed}


@app.get("/tickets/queue")
def get_tickets_queue(
    priority: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """
    Lista fila de senhas aguardando (operador vê).
    Query: ?priority=normal|preferential (opcional)
    """
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        if priority and priority in ("normal", "preferential"):
            cur.execute(
                """
                SELECT id, ticket_code, service_name, priority, status, issued_at
                FROM tickets
                WHERE tenant_cpf_cnpj = %s AND status = 'waiting' AND priority = %s
                ORDER BY issued_at ASC
                """,
                (tenant_cpf_cnpj, priority),
            )
        else:
            cur.execute(
                """
                SELECT id, ticket_code, service_name, priority, status, issued_at
                FROM tickets
                WHERE tenant_cpf_cnpj = %s AND status = 'waiting'
                ORDER BY priority DESC, issued_at ASC
                """,
                (tenant_cpf_cnpj,),
            )

        tickets = cur.fetchall()

        # Calcular tempo de espera para cada ticket
        now = utc_now()
        for t in tickets:
            if t.get("issued_at"):
                delta = now - t["issued_at"].replace(tzinfo=timezone.utc)
                t["wait_seconds"] = int(delta.total_seconds())
                t["issued_at"] = t["issued_at"].isoformat()
            else:
                t["wait_seconds"] = 0

    return tickets


@app.get("/tickets/queue/stats")
def get_queue_stats(authorization: Optional[str] = Header(default=None)):
    """Estatísticas da fila (contadores)."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
            SELECT priority, COUNT(*) AS count
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status = 'waiting'
            GROUP BY priority
            """,
            (tenant_cpf_cnpj,),
        )
        rows = cur.fetchall()
        stats = {"normal": 0, "preferential": 0, "total": 0}
        for r in rows:
            p = r.get("priority", "normal")
            c = int(r.get("count", 0))
            stats[p] = c
            stats["total"] += c

    return stats


@app.post("/tickets/{ticket_id}/call")
def call_ticket(ticket_id: str, payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    """
    Chamar uma senha específica (operador).
    Body: { counter_id }
    """
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    operator_id = payload.get("sub")

    counter_id = (payload_in.get("counter_id") or "").strip()
    if not counter_id:
        raise HTTPException(status_code=400, detail="counter_id is required")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Buscar operador
        cur.execute(
            "SELECT id, full_name FROM tenant_users WHERE id = %s AND tenant_cpf_cnpj = %s",
            (operator_id, tenant_cpf_cnpj),
        )
        operator = cur.fetchone()
        operator_name = operator.get("full_name") if operator else None

        # Buscar guichê
        cur.execute(
            "SELECT id, name FROM counters WHERE id = %s AND tenant_cpf_cnpj = %s AND active = 1",
            (counter_id, tenant_cpf_cnpj),
        )
        counter = cur.fetchone()
        if not counter:
            raise HTTPException(status_code=404, detail="Counter not found")

        # Buscar ticket
        cur.execute(
            "SELECT * FROM tickets WHERE id = %s AND tenant_cpf_cnpj = %s",
            (ticket_id, tenant_cpf_cnpj),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] not in ("waiting", "called"):
            raise HTTPException(status_code=400, detail=f"Ticket cannot be called (status: {ticket['status']})")

        is_recall = ticket["status"] == "called"
        now = utc_now()
        cur.execute(
            """
            UPDATE tickets
            SET status = 'called', called_at = %s, operator_id = %s, operator_name = %s,
                counter_id = %s, counter_name = %s, recall_count = recall_count + 1
            WHERE id = %s
            """,
            (now, operator_id, operator_name, counter_id, counter["name"], ticket_id),
        )

        # Criar evento SSE para TV
        # Rechamadas usam "ticket.recalled" para bypassar deduplicação na TV
        event_type = "ticket.recalled" if is_recall else "ticket.called"
        event_id = str(uuid.uuid4())
        event_payload = {
            "call": {
                "id": ticket_id,
                "ticket_code": ticket["ticket_code"],
                "service_name": ticket["service_name"],
                "priority": ticket["priority"],
                "counter_name": counter["name"],
                "operator_name": operator_name,
                "called_at": now.isoformat(),
                "is_recall": is_recall,
            }
        }
        cur.execute(
            """
            INSERT INTO events (event_id, event_type, payload_json, created_at, synced)
            VALUES (%s, %s, %s, %s, 0)
            """,
            (event_id, event_type, json.dumps(event_payload, ensure_ascii=False), now),
        )

    _prefetch_tts(tenant_cpf_cnpj, ticket["ticket_code"], ticket["service_name"] or "", counter["name"])
    return {"ok": True, "ticket_id": ticket_id, "status": "called", "counter_name": counter["name"], "is_recall": is_recall}


@app.post("/tickets/{ticket_id}/start")
def start_ticket_service(ticket_id: str, authorization: Optional[str] = Header(default=None)):
    """Iniciar atendimento de uma senha chamada."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT * FROM tickets WHERE id = %s AND tenant_cpf_cnpj = %s",
            (ticket_id, tenant_cpf_cnpj),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] != "called":
            raise HTTPException(status_code=400, detail=f"Ticket cannot be started (status: {ticket['status']})")

        now = utc_now()
        cur.execute(
            "UPDATE tickets SET status = 'in_service', service_started_at = %s WHERE id = %s",
            (now, ticket_id),
        )

    return {"ok": True, "ticket_id": ticket_id, "status": "in_service"}


@app.post("/tickets/{ticket_id}/complete")
def complete_ticket(ticket_id: str, authorization: Optional[str] = Header(default=None)):
    """Finalizar atendimento de uma senha."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT * FROM tickets WHERE id = %s AND tenant_cpf_cnpj = %s",
            (ticket_id, tenant_cpf_cnpj),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] not in ("called", "in_service"):
            raise HTTPException(status_code=400, detail=f"Ticket cannot be completed (status: {ticket['status']})")

        now = utc_now()
        cur.execute(
            "UPDATE tickets SET status = 'completed', completed_at = %s WHERE id = %s",
            (now, ticket_id),
        )

        # Calcular duração
        started = ticket.get("service_started_at") or ticket.get("called_at")
        duration_seconds = 0
        if started:
            started_utc = started.replace(tzinfo=timezone.utc)
            duration_seconds = int((now - started_utc).total_seconds())

    return {"ok": True, "ticket_id": ticket_id, "status": "completed", "duration_seconds": duration_seconds}


@app.post("/tickets/{ticket_id}/no-show")
def ticket_no_show(ticket_id: str, authorization: Optional[str] = Header(default=None)):
    """Marcar senha como não compareceu."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT * FROM tickets WHERE id = %s AND tenant_cpf_cnpj = %s",
            (ticket_id, tenant_cpf_cnpj),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] not in ("called", "in_service"):
            raise HTTPException(status_code=400, detail=f"Ticket cannot be marked as no-show (status: {ticket['status']})")

        now = utc_now()
        cur.execute(
            "UPDATE tickets SET status = 'no_show', completed_at = %s WHERE id = %s",
            (now, ticket_id),
        )

    return {"ok": True, "ticket_id": ticket_id, "status": "no_show"}


@app.post("/tickets/{ticket_id}/cancel")
def cancel_ticket(ticket_id: str, authorization: Optional[str] = Header(default=None)):
    """Cancelar uma senha."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT * FROM tickets WHERE id = %s AND tenant_cpf_cnpj = %s",
            (ticket_id, tenant_cpf_cnpj),
        )
        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] in ("completed", "cancelled"):
            raise HTTPException(status_code=400, detail=f"Ticket cannot be cancelled (status: {ticket['status']})")

        now = utc_now()
        cur.execute(
            "UPDATE tickets SET status = 'cancelled', completed_at = %s WHERE id = %s",
            (now, ticket_id),
        )

    return {"ok": True, "ticket_id": ticket_id, "status": "cancelled"}


@app.post("/tickets/call-next")
def call_next_ticket(payload_in: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    """
    Chamar próxima senha da fila (operador).
    Body: { counter_id, priority?: 'preferential'|'normal' }
    """
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    operator_id = payload.get("sub")

    counter_id = (payload_in.get("counter_id") or "").strip()
    priority = (payload_in.get("priority") or "").strip()
    if not counter_id:
        raise HTTPException(status_code=400, detail="counter_id is required")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)

        # Buscar operador
        cur.execute(
            "SELECT id, full_name FROM tenant_users WHERE id = %s AND tenant_cpf_cnpj = %s",
            (operator_id, tenant_cpf_cnpj),
        )
        operator = cur.fetchone()
        operator_name = operator.get("full_name") if operator else None

        # Buscar guichê
        cur.execute(
            "SELECT id, name FROM counters WHERE id = %s AND tenant_cpf_cnpj = %s AND active = 1",
            (counter_id, tenant_cpf_cnpj),
        )
        counter = cur.fetchone()
        if not counter:
            raise HTTPException(status_code=404, detail="Counter not found")

        # Buscar próximo ticket (preferencial primeiro, se não filtrado)
        if priority == "preferential":
            cur.execute(
                """
                SELECT * FROM tickets
                WHERE tenant_cpf_cnpj = %s AND status = 'waiting' AND priority = 'preferential'
                ORDER BY issued_at ASC
                LIMIT 1
                """,
                (tenant_cpf_cnpj,),
            )
        elif priority == "normal":
            cur.execute(
                """
                SELECT * FROM tickets
                WHERE tenant_cpf_cnpj = %s AND status = 'waiting' AND priority = 'normal'
                ORDER BY issued_at ASC
                LIMIT 1
                """,
                (tenant_cpf_cnpj,),
            )
        else:
            # Prioridade: preferencial > normal (por ordem de emissão dentro de cada grupo)
            cur.execute(
                """
                SELECT * FROM tickets
                WHERE tenant_cpf_cnpj = %s AND status = 'waiting'
                ORDER BY FIELD(priority, 'preferential', 'normal'), issued_at ASC
                LIMIT 1
                """,
                (tenant_cpf_cnpj,),
            )

        ticket = cur.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="No tickets waiting in queue")

        now = utc_now()
        cur.execute(
            """
            UPDATE tickets
            SET status = 'called', called_at = %s, operator_id = %s, operator_name = %s,
                counter_id = %s, counter_name = %s, recall_count = 1
            WHERE id = %s
            """,
            (now, operator_id, operator_name, counter_id, counter["name"], ticket["id"]),
        )

        # Criar evento SSE para TV
        event_id = str(uuid.uuid4())
        event_payload = {
            "call": {
                "id": ticket["id"],
                "ticket_code": ticket["ticket_code"],
                "service_name": ticket["service_name"],
                "priority": ticket["priority"],
                "counter_name": counter["name"],
                "operator_name": operator_name,
                "called_at": now.isoformat(),
            }
        }
        cur.execute(
            """
            INSERT INTO events (event_id, event_type, payload_json, created_at, synced)
            VALUES (%s, %s, %s, %s, 0)
            """,
            (event_id, "ticket.called", json.dumps(event_payload, ensure_ascii=False), now),
        )

    _prefetch_tts(tenant_cpf_cnpj, ticket["ticket_code"], ticket["service_name"] or "", counter["name"])
    return {
        "ok": True,
        "ticket_id": ticket["id"],
        "ticket_code": ticket["ticket_code"],
        "service_name": ticket["service_name"],
        "priority": ticket["priority"],
        "counter_name": counter["name"],
        "status": "called",
    }


@app.get("/tickets/in-service")
def get_tickets_in_service(authorization: Optional[str] = Header(default=None)):
    """Lista tickets em atendimento (para TV e operador)."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, ticket_code, service_name, priority, status, counter_name, operator_name,
                   called_at, service_started_at
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status IN ('called', 'in_service')
            ORDER BY service_started_at DESC, called_at DESC
            """,
            (tenant_cpf_cnpj,),
        )
        tickets = cur.fetchall()

        for t in tickets:
            if t.get("called_at"):
                t["called_at"] = t["called_at"].isoformat()
            if t.get("service_started_at"):
                t["service_started_at"] = t["service_started_at"].isoformat()

    return tickets


@app.get("/tickets/history")
def get_tickets_history(
    limit: int = Query(default=20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
):
    """Lista histórico de tickets finalizados."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, ticket_code, service_name, priority, status, counter_name, operator_name,
                   called_at, service_started_at, completed_at,
                   TIMESTAMPDIFF(SECOND, service_started_at, completed_at) as duration_seconds
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND status IN ('completed', 'no_show', 'cancelled')
            ORDER BY completed_at DESC
            LIMIT %s
            """,
            (tenant_cpf_cnpj, limit),
        )
        tickets = cur.fetchall()

        for t in tickets:
            if t.get("called_at"):
                t["called_at"] = t["called_at"].isoformat()
            if t.get("service_started_at"):
                t["service_started_at"] = t["service_started_at"].isoformat()
            if t.get("completed_at"):
                t["completed_at"] = t["completed_at"].isoformat()

    return tickets


@app.get("/operator/my-ticket")
def get_operator_current_ticket(authorization: Optional[str] = Header(default=None)):
    """Busca ticket atual do operador (em atendimento ou chamado)."""
    payload = require_jwt(authorization)
    tenant_cpf_cnpj = tenant_from_jwt(payload)
    operator_id = payload.get("sub")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, ticket_code, service_name, priority, status, counter_name, counter_id,
                   called_at, service_started_at
            FROM tickets
            WHERE tenant_cpf_cnpj = %s AND operator_id = %s AND status IN ('called', 'in_service')
            ORDER BY called_at DESC
            LIMIT 1
            """,
            (tenant_cpf_cnpj, operator_id),
        )
        ticket = cur.fetchone()

        if ticket:
            if ticket.get("called_at"):
                ticket["called_at"] = ticket["called_at"].isoformat()
            if ticket.get("service_started_at"):
                ticket["service_started_at"] = ticket["service_started_at"].isoformat()

    return ticket


# ============================================================
# Operator helpers (JWT) - endpoints para UI do operador
# ============================================================


@app.get("/public/operators")
def public_list_operators():
    """
    Lista operadores ativos para seleção no login.
    Endpoint público (usa EDGE_TENANT_CPF_CNPJ ou resolve automaticamente).
    """
    tenant_cpf_cnpj = resolve_tenant_cpf_cnpj()
    if not tenant_cpf_cnpj:
        raise HTTPException(status_code=400, detail="No tenant available")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, email, full_name
            FROM tenant_users
            WHERE tenant_cpf_cnpj = %s AND role = 'operator' AND active = 1
            ORDER BY full_name ASC, email ASC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.get("/public/counters")
def public_list_counters():
    """
    Lista guichês ativos para seleção no login.
    Endpoint público (usa EDGE_TENANT_CPF_CNPJ ou resolve automaticamente).
    """
    tenant_cpf_cnpj = resolve_tenant_cpf_cnpj()
    if not tenant_cpf_cnpj:
        raise HTTPException(status_code=400, detail="No tenant available")

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, name
            FROM counters
            WHERE tenant_cpf_cnpj = %s AND active = 1
            ORDER BY name ASC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


@app.get("/operator/counters")
def operator_list_active_counters(authorization: Optional[str] = Header(default=None)):
    """
    Lista guichês ativos para o operador selecionar no login.
    Roles: admin | operator
    """
    payload = require_jwt(authorization)
    require_role(payload, {"admin", "operator"})
    tenant_cpf_cnpj = tenant_from_jwt(payload)

    with db_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, name
            FROM counters
            WHERE tenant_cpf_cnpj = %s AND active = 1
            ORDER BY name ASC
            """,
            (tenant_cpf_cnpj,),
        )
        return cur.fetchall()


# ============================================================
# Legacy Calls Endpoint (mantido para compatibilidade)
# ============================================================


@app.post("/calls")
def create_call(payload: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
    require_token(authorization)
    ticket_code = (payload.get("ticket_code") or "").strip()
    counter_name = (payload.get("counter_name") or "").strip()
    service_name = (payload.get("service_name") or "").strip()
    priority = (payload.get("priority") or "").strip()  # e.g. 'normal' | 'preferential'
    if not ticket_code or not counter_name:
        raise HTTPException(status_code=400, detail="ticket_code and counter_name are required")
    if priority not in ("normal", "preferential"):
        priority = "normal"
    if not service_name:
        service_name = "Atendimento"

    call_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    now = utc_now()

    event_payload = {
        "call": {
            "id": call_id,
            "ticket_code": ticket_code,
            "service_name": service_name,
            "priority": priority,
            "counter_name": counter_name,
            "called_at": now.isoformat(),
        }
    }

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO calls (id, ticket_code, service_name, priority, counter_name, status, called_at)
            VALUES (%s, %s, %s, %s, %s, 'called', %s)
            """,
            (call_id, ticket_code, service_name, priority, counter_name, now),
        )
        cur.execute(
            """
            INSERT INTO events (event_id, event_type, payload_json, created_at, synced)
            VALUES (%s, %s, %s, %s, 0)
            """,
            (event_id, "call.created", json.dumps(event_payload, ensure_ascii=False), now),
        )

    return {"ok": True, "event_id": event_id, "call_id": call_id}


def sse_format(event_id: str, event_type: str, data: str) -> str:
    # SSE format: id, event, data
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"


@app.get("/tv/events")
def tv_events(
    authorization: Optional[str] = Header(default=None),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    token: Optional[str] = Query(default=None),
):
    # EventSource can't send headers; allow ?token=... for MVP.
    if token:
        if token != DEVICE_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")
    else:
        require_token(authorization)

    def gen() -> Generator[bytes, None, None]:
        # Simple long-poll loop that streams SSE events.
        # This is MVP-safe: low throughput, single DB table scan with index on created_at.
        seen_event_id = last_event_id

        # Send a comment immediately to establish the stream.
        yield b": connected\n\n"

        while True:
            try:
                with db_conn() as conn:
                    cur = conn.cursor(dictionary=True)
                    if seen_event_id:
                        cur.execute(
                            """
                            SELECT event_id, event_type, payload_json
                            FROM events
                            WHERE created_at >= (SELECT created_at FROM events WHERE event_id = %s)
                            ORDER BY created_at ASC
                            LIMIT 50
                            """,
                            (seen_event_id,),
                        )
                    else:
                        # Sem Last-Event-ID: nova conexão (F5/reload).
                        # Buscar apenas o evento mais recente para usar como cursor,
                        # sem reenviar histórico (evita reproduzir áudio de chamadas antigas).
                        cur.execute(
                            "SELECT event_id FROM events ORDER BY created_at DESC LIMIT 1"
                        )
                        latest = cur.fetchone()
                        if latest:
                            seen_event_id = latest["event_id"]
                        cur.execute("SELECT 1 WHERE 1=0")  # resultado vazio — próximo loop pega eventos novos
                    rows = cur.fetchall()

                emitted_any = False
                for row in rows:
                    eid = row["event_id"]
                    if seen_event_id and eid == seen_event_id:
                        continue
                    payload = row["payload_json"]
                    msg = sse_format(eid, row["event_type"], payload)
                    yield msg.encode("utf-8")
                    seen_event_id = eid
                    emitted_any = True

                if not emitted_any:
                    # Keep-alive comment to prevent proxies from closing.
                    yield b": keep-alive\n\n"

                time.sleep(1.0)
            except Exception as e:
                err = {"error": str(e)}
                yield sse_format(str(uuid.uuid4()), "edge.error", json.dumps(err)).encode("utf-8")
                time.sleep(2.0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)

