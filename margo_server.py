#!/usr/bin/env python3
"""
margo_server.py — Margo Server v1.2
Assistente de IA com personalidade — produto comercial da Orbiby
Arquitetura: FastAPI + DeepSeek + SQLite/Postgres + Fish Audio / ElevenLabs / Web Speech
"""

import os, re, json, time, sqlite3, threading, asyncio, base64
from datetime import datetime, timedelta

# Domínios descartáveis bloqueados
DOMINIOS_BLOQUEADOS = {
    'mailinator.com', 'tempmail.com', 'throwaway.email', 'guerrillamail.com',
    'sharklasers.com', 'guerrillamailblock.com', 'grr.la', 'guerrillamail.info',
    'spam4.me', 'trashmail.com', 'trashmail.me', 'trashmail.net', 'yopmail.com',
    'yopmail.fr', 'cool.fr.nf', 'jetable.fr.nf', 'nospam.ze.tc', 'nomail.xl.cx',
    'mega.zik.dj', 'speed.1s.fr', 'courriel.fr.nf', 'moncourrier.fr.nf',
    'dispostable.com', 'spamgourmet.com', 'spamgourmet.net', 'spamgourmet.org',
    'fakeinbox.com', 'mailnull.com', 'spamcorner.com', 'example.com', 'test.com',
}

# Prefixos obviamente falsos
PREFIXOS_BLOQUEADOS = {'test', 'teste', 'abc', 'admin', 'fake', 'spam', 'null', 'none'}

def validar_email(email: str) -> tuple[bool, str]:
    email = email.lower().strip()
    # Formato básico
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False, "Email inválido."
    partes = email.split('@')
    prefixo = partes[0]
    dominio = partes[1]
    # Domínio bloqueado
    if dominio in DOMINIOS_BLOQUEADOS:
        return False, "Email temporário não é permitido."
    # Prefixo bloqueado
    if prefixo in PREFIXOS_BLOQUEADOS:
        return False, "Email inválido."
    # Muito curto
    if len(prefixo) < 3:
        return False, "Email inválido."
    return True, ""

from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import urllib.request
import urllib.parse
import uvicorn

# ── Google Play Billing ────────────────────────────────────────────────────────
import json as _json_billing
from google.oauth2 import service_account as _billing_sa
from googleapiclient.discovery import build as _billing_build

def _get_play_api():
    """Cria cliente da Google Play Developer API para verificação de compras."""
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    creds_info = _json_billing.loads(sa_json)
    creds = _billing_sa.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/androidpublisher"]
    )
    return _billing_build("androidpublisher", "v3", credentials=creds)

BILLING_PACKAGE = "com.orbiby.margo"
# ── Fim Google Play Billing ────────────────────────────────────────────────────


# ── CONFIG ─────────────────────────────────────────────────────────────────────

MARGO_DIR  = os.path.expanduser("~/margo")
DB_FILE    = os.path.join(MARGO_DIR, "margo_memoria.db")
ESTADO_DIR = os.path.join(MARGO_DIR, "estado")
LOGS_DIR   = os.path.join(MARGO_DIR, "logs")
PORT       = int(os.environ.get("PORT", 8000))

os.makedirs(MARGO_DIR,  exist_ok=True)
os.makedirs(ESTADO_DIR, exist_ok=True)
os.makedirs(LOGS_DIR,   exist_ok=True)

ENV_PATH = os.path.join(MARGO_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

DEEPSEEK_API_KEY    = os.environ.get("DEEPSEEK_API_KEY", "")
DATABASE_URL        = os.environ.get("DATABASE_URL", "")
BRAVE_API_KEY       = os.environ.get("BRAVE_API_KEY", "")
FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDENTIALS", "")

# Inicializa Firebase Admin para push notifications
_firebase_app = None
def get_firebase_app():
    global _firebase_app
    if _firebase_app:
        return _firebase_app
    if not FIREBASE_CREDENTIALS:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
        import json as _json
        cred_dict = _json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception as e:
        log(f"Firebase init erro: {e}", "fcm")
        return None

def enviar_push(token: str, titulo: str, corpo: str):
    """Envia push notification via FCM."""
    try:
        import firebase_admin
        from firebase_admin import messaging
        app = get_firebase_app()
        if not app:
            return False
        msg = messaging.Message(
            notification=messaging.Notification(title=titulo, body=corpo),
            token=token,
        )
        messaging.send(msg)
        log(f"Push enviado para {token[:20]}...", "fcm")
        return True
    except Exception as e:
        log(f"Push erro: {e}", "fcm")
        return False
SERPER_API_KEY      = os.environ.get("SERPER_API_KEY", "")
RESEND_API_KEY      = os.environ.get("RESEND_API_KEY", "")
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
KOKORO_ENABLED      = os.environ.get("KOKORO_ENABLED", "true").lower() == "true"

# ── KOKORO TTS ────────────────────────────────────────────────────────────────
import threading as _threading
_kokoro_instance = None
_kokoro_lock = _threading.Lock()
_kokoro_ready = False

KOKORO_DIR = "/data/kokoro"
KOKORO_MODEL = f"{KOKORO_DIR}/kokoro-v1.0.onnx"
KOKORO_VOICES = f"{KOKORO_DIR}/voices-v1.0.bin"

def _baixar_kokoro():
    global _kokoro_instance, _kokoro_ready
    try:
        os.makedirs(KOKORO_DIR, exist_ok=True)
        if not os.path.exists(KOKORO_MODEL):
            log("Baixando Kokoro model (~310MB)...", "kokoro")
            import urllib.request
            urllib.request.urlretrieve(
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
                KOKORO_MODEL
            )
            log("Kokoro model baixado!", "kokoro")
        if not os.path.exists(KOKORO_VOICES):
            log("Baixando Kokoro voices (~27MB)...", "kokoro")
            import urllib.request
            urllib.request.urlretrieve(
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
                KOKORO_VOICES
            )
            log("Kokoro voices baixado!", "kokoro")
        from kokoro_onnx import Kokoro
        with _kokoro_lock:
            _kokoro_instance = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
            _kokoro_ready = True
        log("Kokoro TTS pronto!", "kokoro")
    except Exception as e:
        log(f"Kokoro init erro: {e}", "kokoro")

def get_kokoro():
    global _kokoro_instance, _kokoro_ready
    if _kokoro_ready:
        return _kokoro_instance
    return None

# Inicia download em background
if KOKORO_ENABLED:
    _t = _threading.Thread(target=_baixar_kokoro, daemon=True)
    _t.start()

VOZES_KOKORO = {
    "pt-br": {"F": "pf_dora", "M": "pm_alex"},
    "en-us": {"F": "af_heart", "M": "am_michael"},
    "ja": {"F": "jf_alpha", "M": "jm_kumo"},
}

def kokoro_tts(texto: str, idioma: str = "pt-br", genero: str = "F") -> bytes:
    """Gera áudio via Kokoro TTS. Retorna bytes WAV."""
    try:
        import io
        import soundfile as sf
        import numpy as np
        kokoro = get_kokoro()
        if not kokoro:
            return None
        # Normaliza ANTES de tudo: en/english/en-US -> en-us; pt/portuguese/pt-BR -> pt-br
        _idi = (idioma or "").lower()
        lang = {"en": "en-us", "english": "en-us", "en-us": "en-us",
                "ja": "ja", "japanese": "ja", "ja-jp": "ja",
                "pt": "pt-br", "portuguese": "pt-br", "pt-br": "pt-br"}.get(_idi, "pt-br")
        gen = genero.upper() if genero else "F"
        voz = VOZES_KOKORO.get(lang, VOZES_KOKORO["pt-br"]).get(gen, "pf_dora")
        log(f"Kokoro: idioma_recebido={idioma} lang={lang} voz={voz}", "kokoro")
        samples, sample_rate = kokoro.create(texto, voice=voz, speed=1.0, lang=lang)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        return buf.getvalue()
    except Exception as e:
        log(f"Kokoro TTS erro: {e}", "kokoro")
        return None
ST_CLIENT_ID        = os.environ.get("ST_CLIENT_ID", "")
ST_CLIENT_SECRET    = os.environ.get("ST_CLIENT_SECRET", "")
ST_REDIRECT_URI     = os.environ.get("ST_REDIRECT_URI", "https://margo-production-98a9.up.railway.app/smartthings/callback")
SPOTIFY_CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI  = "https://margo-production-98a9.up.railway.app/spotify/callback"
STRIPE_SECRET_KEY     = os.environ.get("STRIPE_SECRET_KEY", "")
MP_ACCESS_TOKEN       = os.environ.get("MP_ACCESS_TOKEN", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO      = os.environ.get("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_PRO_PLUS = os.environ.get("STRIPE_PRICE_PRO_PLUS", "")

# ── Detecta se usa Postgres ────────────────────────────────────────────────────

def usar_postgres():
    return bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))

# ── LOG ────────────────────────────────────────────────────────────────────────

def log(msg, arquivo="geral"):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] {msg}"
    print(f"  [{arquivo.upper()}] {msg}")
    try:
        with open(os.path.join(LOGS_DIR, f"{arquivo}.log"), "a") as f:
            f.write(linha + "\n")
    except:
        pass

# ── BANCO DE DADOS ─────────────────────────────────────────────────────────────

class _PooledConn:
    """Wrapper de conexão: .close() devolve ao pool em vez de fechar de verdade."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._devolvida = False
    def close(self):
        if not self._devolvida:
            self._devolvida = True
            try:
                self._conn.rollback()  # limpa transação pendente antes de devolver
            except Exception:
                pass
            try:
                self._pool.putconn(self._conn)
            except Exception:
                try: self._conn.close()
                except Exception: pass
    def __getattr__(self, nome):
        return getattr(self._conn, nome)

class BancoMargo:
    def __init__(self):
        self._pg = usar_postgres()
        if self._pg:
            try:
                import psycopg2
                import psycopg2.extras
                self._psycopg2 = psycopg2
                self._conn_str = DATABASE_URL
                log("Banco: Postgres (Supabase)", "banco")
            except ImportError:
                log("psycopg2 não instalado — caindo para SQLite", "banco")
                self._pg = False
        if not self._pg:
            log(f"Banco: SQLite ({DB_FILE})", "banco")
        self._inicializar()

    def _get_conn(self):
        if self._pg:
            # Pool de conexões — evita handshake TLS com o Supabase a cada operação
            if not hasattr(self, '_pool') or self._pool is None:
                from psycopg2 import pool as _pgpool
                self._pool = _pgpool.ThreadedConnectionPool(1, 10, self._conn_str)
                log("Pool de conexões Postgres criado (1-10)", "banco")
            conn = self._pool.getconn()
            # Testa se a conexão está viva; se não, descarta e pega outra
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
            except Exception:
                try: self._pool.putconn(conn, close=True)
                except Exception: pass
                conn = self._pool.getconn()
            return _PooledConn(conn, self._pool)
        return sqlite3.connect(DB_FILE)

    def _cur(self, conn):
        if self._pg:
            return conn.cursor()
        conn.row_factory = sqlite3.Row
        return conn.cursor()

    def _inicializar(self):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"

        # ── USO DIÁRIO (controle de limite de mensagens) ───────────────────────
        c.execute('''CREATE TABLE IF NOT EXISTS uso_diario (
            user_id TEXT,
            data TEXT,
            msgs INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, data)
        )''')

        # ── SPOTIFY TOKENS ────────────────────────────────────────────────────
        c.execute('''CREATE TABLE IF NOT EXISTS spotify_tokens (
            user_id TEXT PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT,
            expires_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS smartthings_tokens (
            user_id TEXT PRIMARY KEY,
            access_token TEXT,
            refresh_token TEXT,
            expires_at TEXT,
            criado_em TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            nome TEXT,
            plano TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            mp_payment_id TEXT,
            msgs_extras INTEGER DEFAULT 0,
            fcm_token TEXT,
            stripe_subscription_id TEXT,
            status TEXT DEFAULT 'ativo',
            senha_hash TEXT,
            email_verificado INTEGER DEFAULT 0,
            criado_em TEXT,
            ultimo_acesso TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS perfil_usuario (
            user_id TEXT PRIMARY KEY,
            nome TEXT,
            idade TEXT,
            profissao TEXT,
            musica TEXT,
            comida TEXT,
            hobbies TEXT,
            extra TEXT,
            criado_em TEXT,
            atualizado_em TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS config_assistente (
            user_id TEXT PRIMARY KEY,
            nome_assistente TEXT DEFAULT 'Margo',
            genero TEXT DEFAULT 'F',
            personalidade TEXT,
            voz_provider TEXT DEFAULT 'device',
            voz_chave TEXT,
            voz_id TEXT,
            onboarding_completo INTEGER DEFAULT 0,
            criado_em TEXT,
            atualizado_em TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS resumos_sessao (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            resumo TEXT,
            criado_em TEXT
        )''' if self._pg else '''CREATE TABLE IF NOT EXISTS resumos_sessao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            resumo TEXT,
            criado_em TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS email_verificacao (
            email TEXT PRIMARY KEY,
            codigo TEXT,
            expira_em TEXT,
            criado_em TEXT
        )''' if self._pg else '''CREATE TABLE IF NOT EXISTS email_verificacao (
            email TEXT PRIMARY KEY,
            codigo TEXT,
            expira_em TEXT,
            criado_em TEXT
        )''')
        conn.commit()

        c.execute('''CREATE TABLE IF NOT EXISTS agenda (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            titulo TEXT,
            descricao TEXT,
            data_hora TEXT,
            lembrete_1d INTEGER DEFAULT 1,
            lembrete_3h INTEGER DEFAULT 1,
            lembrado_1d INTEGER DEFAULT 0,
            lembrado_3h INTEGER DEFAULT 0,
            criado_em TEXT
        )''' if self._pg else '''CREATE TABLE IF NOT EXISTS agenda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            titulo TEXT,
            descricao TEXT,
            data_hora TEXT,
            lembrete_1d INTEGER DEFAULT 1,
            lembrete_3h INTEGER DEFAULT 1,
            lembrado_1d INTEGER DEFAULT 0,
            lembrado_3h INTEGER DEFAULT 0,
            criado_em TEXT
        )''')

        conn.commit()
        conn.close()

    def _row_to_dict(self, row, cursor):
        if row is None:
            return {}
        if self._pg:
            cols = [d[0] for d in cursor.description]
            return dict(zip(cols, row))
        return dict(row)

    # ── USO DIÁRIO ─────────────────────────────────────────────────────────────

    LIMITES = {
        "free":     999999,  # free trial: sem limite diário, mas tem total de 50
        "pro":      20,
        "pro_plus": 50,
        "premium":  100,     # plano novo: multilingue + tradutor + memoria estendida
        "tester":   20,      # testadores: 20/dia, tudo liberado, 30 dias
        "admin":    999999,
    }
    TRIAL_LIMITE = 50  # total de interações no free trial

    def _migrar_colunas(self):
        """Adiciona colunas que podem estar faltando no banco"""
        if not self._pg: return
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            for col, tipo in [
                ("stripe_subscription_id", "TEXT"),
                ("stripe_customer_id", "TEXT"),
                ("msgs_extras", "INTEGER DEFAULT 0")
            ]:
                try:
                    cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {tipo}")
                    conn.commit()
                    log(f"Coluna {col} adicionada", "db")
                except:
                    conn.rollback()
            for col, tipo in [
                ("acao_smart", "TEXT"),
                ("acao_executada", "INTEGER DEFAULT 0")
            ]:
                try:
                    cur.execute(f"ALTER TABLE agenda ADD COLUMN {col} {tipo}")
                    conn.commit()
                    log(f"Coluna agenda.{col} adicionada", "db")
                except:
                    pass
        finally:
            conn.close()

    def atualizar_plano(self, user_id: str, plano: str, stripe_customer_id: str = None, stripe_subscription_id: str = None):
        """Atualiza o plano do usuário"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            ph  = "%s" if self._pg else "?"
            if self._pg:
                cur.execute("""UPDATE usuarios SET plano=%s, stripe_customer_id=COALESCE(%s, stripe_customer_id),
                    stripe_subscription_id=COALESCE(%s, stripe_subscription_id) WHERE user_id=%s""",
                    (plano, stripe_customer_id, stripe_subscription_id, user_id))
            else:
                cur.execute("""UPDATE usuarios SET plano=?, stripe_customer_id=COALESCE(?,stripe_customer_id),
                    stripe_subscription_id=COALESCE(?,stripe_subscription_id) WHERE user_id=?""",
                    (plano, stripe_customer_id, stripe_subscription_id, user_id))
            conn.commit()
            log(f"Plano atualizado: {user_id} → {plano}", "stripe")
        except Exception as e:
            log(f"Erro atualizar_plano: {e}", "stripe")
        finally:
            if self._pg: conn.close()

    def buscar_por_stripe_customer(self, stripe_customer_id: str) -> dict:
        """Busca usuário pelo stripe_customer_id"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            ph  = "%s" if self._pg else "?"
            cur.execute(f"SELECT * FROM usuarios WHERE stripe_customer_id={ph}", (stripe_customer_id,))
            row = cur.fetchone()
            if not row: return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        except:
            return None
        finally:
            if self._pg: conn.close()

    def verificar_limite(self, user_id: str) -> dict:
        """Verifica se usuário pode enviar mais mensagens."""
        usuario = self.buscar_usuario_por_id(user_id)
        plano   = usuario.get("plano", "free") if usuario else "free"
        msgs_extras = usuario.get("msgs_extras", 0) or 0

        # Free trial: verifica total histórico (não diário)
        if plano == "free":
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                ph  = "%s" if self._pg else "?"
                cur.execute(f"SELECT COALESCE(SUM(msgs),0) FROM uso_diario WHERE user_id={ph}", (user_id,))
                row = cur.fetchone()
                total = row[0] if row else 0
                faltam = max(0, self.TRIAL_LIMITE - total)
                # Verifica msgs_extras se trial esgotado
                if total >= self.TRIAL_LIMITE and msgs_extras > 0:
                    return {"pode": True, "usado": total, "limite": self.TRIAL_LIMITE, "plano": plano, "faltam": msgs_extras, "usando_extras": True}
                return {"pode": total < self.TRIAL_LIMITE, "usado": total, "limite": self.TRIAL_LIMITE, "plano": plano, "faltam": faltam, "trial": True}
            except:
                return {"pode": True, "usado": 0, "limite": self.TRIAL_LIMITE, "plano": plano, "faltam": self.TRIAL_LIMITE, "trial": True}
            finally:
                if self._pg: conn.close()

        # Planos pagos: verifica limite diário
        limite = self.LIMITES.get(plano, 20)
        hoje = datetime.now().strftime("%Y-%m-%d")
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            ph  = "%s" if self._pg else "?"
            cur.execute(f"SELECT msgs FROM uso_diario WHERE user_id={ph} AND data={ph}", (user_id, hoje))
            row = cur.fetchone()
            used = row[0] if row else 0
            # Se esgotou o diário, verifica msgs_extras
            if used >= limite and msgs_extras > 0:
                return {"pode": True, "usado": used, "limite": limite, "plano": plano, "faltam": msgs_extras, "usando_extras": True}
            return {"pode": used < limite, "usado": used, "limite": limite, "plano": plano, "faltam": max(0, limite - used)}
        except:
            return {"pode": True, "usado": 0, "limite": limite, "plano": plano, "faltam": limite}
        finally:
            if self._pg: conn.close()

    def registrar_uso(self, user_id: str, usando_extras: bool = False):
        """Incrementa contador de mensagens. Se usando_extras, decrementa msgs_extras."""
        hoje = datetime.now().strftime("%Y-%m-%d")
        conn = self._get_conn()
        c    = conn.cursor()
        ph   = "%s" if self._pg else "?"
        # Sempre registra no uso_diario para histórico
        if self._pg:
            c.execute('''INSERT INTO uso_diario (user_id, data, msgs)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, data) DO UPDATE SET msgs = uso_diario.msgs + 1''',
                (user_id, hoje))
        else:
            c.execute('''INSERT INTO uso_diario (user_id, data, msgs) VALUES (?,?,1)
                ON CONFLICT(user_id, data) DO UPDATE SET msgs = msgs + 1''',
                (user_id, hoje))
        # Se usando extras, decrementa
        if usando_extras:
            c.execute(f"UPDATE usuarios SET msgs_extras = MAX(0, COALESCE(msgs_extras,0) - 1) WHERE user_id={ph}", (user_id,))
        conn.commit()
        conn.close()

    # ── SPOTIFY ────────────────────────────────────────────────────────────────

    def salvar_spotify_token(self, user_id, access_token, refresh_token, expires_at):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        if self._pg:
            c.execute('''INSERT INTO spotify_tokens (user_id, access_token, refresh_token, expires_at)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token=EXCLUDED.access_token,
                    refresh_token=EXCLUDED.refresh_token,
                    expires_at=EXCLUDED.expires_at''',
                (user_id, access_token, refresh_token, expires_at))
        else:
            c.execute('''INSERT OR REPLACE INTO spotify_tokens
                (user_id, access_token, refresh_token, expires_at)
                VALUES (?,?,?,?)''',
                (user_id, access_token, refresh_token, expires_at))
        conn.commit()
        conn.close()

    def buscar_spotify_token(self, user_id) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM spotify_tokens WHERE user_id={ph}', (user_id,))
        row = c.fetchone()
        result = self._row_to_dict(row, c)
        conn.close()
        return result

    # ── SMARTTHINGS ────────────────────────────────────────────────────────────

    def salvar_st_token(self, user_id, access_token, refresh_token, expires_at):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        agora = datetime.now().isoformat()
        if self._pg:
            c.execute('''INSERT INTO smartthings_tokens (user_id, access_token, refresh_token, expires_at, criado_em)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token=EXCLUDED.access_token,
                    refresh_token=EXCLUDED.refresh_token,
                    expires_at=EXCLUDED.expires_at''',
                (user_id, access_token, refresh_token, expires_at, agora))
        else:
            c.execute('''INSERT OR REPLACE INTO smartthings_tokens
                (user_id, access_token, refresh_token, expires_at, criado_em)
                VALUES (?,?,?,?,?)''',
                (user_id, access_token, refresh_token, expires_at, agora))
        conn.commit()
        conn.close()

    def buscar_st_token(self, user_id) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM smartthings_tokens WHERE user_id={ph}', (user_id,))
        row = c.fetchone()
        result = self._row_to_dict(row, c)
        conn.close()
        return result

    # ── USUARIOS ───────────────────────────────────────────────────────────────

    def cadastrar_ou_login(self, email: str, nome: str = "") -> dict:
        """Cadastra novo usuário ou faz login se já existe. Retorna dados do usuário."""
        import uuid
        agora = datetime.now().isoformat()
        email = email.lower().strip()
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"

        # Busca usuário existente
        c.execute(f'SELECT * FROM usuarios WHERE email={ph}', (email,))
        row = c.fetchone()
        usuario = self._row_to_dict(row, c)

        if usuario:
            # Login — atualiza último acesso
            c.execute(f'UPDATE usuarios SET ultimo_acesso={ph} WHERE email={ph}', (agora, email))
            conn.commit()
            conn.close()
            return {"novo": False, **usuario}
        else:
            # Cadastro — gera UUID fixo
            user_id = "u_" + str(uuid.uuid4()).replace("-", "")[:16]
            if self._pg:
                c.execute('''INSERT INTO usuarios
                    (user_id, email, nome, plano, status, criado_em, ultimo_acesso)
                    VALUES (%s,%s,%s,'free','ativo',%s,%s)''',
                    (user_id, email, nome, agora, agora))
            else:
                c.execute('''INSERT INTO usuarios
                    (user_id, email, nome, plano, status, criado_em, ultimo_acesso)
                    VALUES (?,?,?,'free','ativo',?,?)''',
                    (user_id, email, nome, agora, agora))
            conn.commit()
            conn.close()
            log(f"Novo usuário: {email} → {user_id}", "usuarios")
            return {"novo": True, "user_id": user_id, "email": email, "nome": nome,
                    "plano": "free", "status": "ativo"}

    def buscar_usuario_por_email(self, email: str) -> dict:
        email = email.lower().strip()
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM usuarios WHERE email={ph}', (email,))
        row = c.fetchone()
        result = self._row_to_dict(row, c)
        conn.close()
        return result

    def buscar_usuario_por_id(self, user_id: str) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM usuarios WHERE user_id={ph}', (user_id,))
        row = c.fetchone()
        result = self._row_to_dict(row, c)
        conn.close()
        return result

    # ── PERFIL ─────────────────────────────────────────────────────────────────

    def salvar_perfil(self, user_id, dados: dict):
        agora = datetime.now().isoformat()
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        if self._pg:
            c.execute('''INSERT INTO perfil_usuario
                (user_id, nome, idade, profissao, musica, comida, hobbies, extra, criado_em, atualizado_em)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (user_id) DO UPDATE SET
                    nome=EXCLUDED.nome, idade=EXCLUDED.idade, profissao=EXCLUDED.profissao,
                    musica=EXCLUDED.musica, comida=EXCLUDED.comida, hobbies=EXCLUDED.hobbies,
                    extra=EXCLUDED.extra, atualizado_em=EXCLUDED.atualizado_em''',
                (user_id, dados.get("nome",""), dados.get("idade",""), dados.get("profissao",""),
                 dados.get("musica",""), dados.get("comida",""), dados.get("hobbies",""),
                 dados.get("extra",""), agora, agora))
        else:
            c.execute('''INSERT OR REPLACE INTO perfil_usuario
                (user_id, nome, idade, profissao, musica, comida, hobbies, extra, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT criado_em FROM perfil_usuario WHERE user_id=?), ?), ?)''',
                (user_id, dados.get("nome",""), dados.get("idade",""), dados.get("profissao",""),
                 dados.get("musica",""), dados.get("comida",""), dados.get("hobbies",""),
                 dados.get("extra",""), user_id, agora, agora))
        conn.commit()
        conn.close()

    def buscar_perfil(self, user_id) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM perfil_usuario WHERE user_id={ph}', (user_id,))
        row = c.fetchone()
        result = self._row_to_dict(row, c)
        conn.close()
        return result

    # ── CONFIG ASSISTENTE ──────────────────────────────────────────────────────

    def salvar_config(self, user_id, dados: dict):
        agora = datetime.now().isoformat()
        conn = self._get_conn()
        c = conn.cursor()
        # Busca config atual para não sobrescrever campos não enviados
        c.execute(f'SELECT * FROM config_assistente WHERE user_id={"%" + "s" if self._pg else "?"}', (user_id,))
        atual = self._row_to_dict(c.fetchone(), c) or {}
        merged = {**atual, **dados}
        if self._pg:
            c.execute('''INSERT INTO config_assistente
                (user_id, nome_assistente, genero, personalidade, voz_provider, voz_chave, voz_id, onboarding_completo, criado_em, atualizado_em)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (user_id) DO UPDATE SET
                    nome_assistente=EXCLUDED.nome_assistente, genero=EXCLUDED.genero,
                    personalidade=EXCLUDED.personalidade, voz_provider=EXCLUDED.voz_provider,
                    voz_chave=EXCLUDED.voz_chave, voz_id=EXCLUDED.voz_id,
                    onboarding_completo=EXCLUDED.onboarding_completo, atualizado_em=EXCLUDED.atualizado_em''',
                (user_id,
                 merged.get("nome_assistente","Margo"), merged.get("genero","F"),
                 merged.get("personalidade",""), merged.get("voz_provider","device"),
                 merged.get("voz_chave",""), merged.get("voz_id",""),
                 1 if merged.get("onboarding_completo") else 0,
                 atual.get("criado_em", agora), agora))
        else:
            c.execute('''INSERT OR REPLACE INTO config_assistente
                (user_id, nome_assistente, genero, personalidade, voz_provider,
                 voz_chave, voz_id, onboarding_completo, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT criado_em FROM config_assistente WHERE user_id=?), ?), ?)''',
                (user_id,
                 merged.get("nome_assistente","Margo"), merged.get("genero","F"),
                 merged.get("personalidade",""), merged.get("voz_provider","device"),
                 merged.get("voz_chave",""), merged.get("voz_id",""),
                 1 if merged.get("onboarding_completo") else 0,
                 user_id, agora, agora))
        conn.commit()
        conn.close()

    def buscar_config(self, user_id) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM config_assistente WHERE user_id={ph}', (user_id,))
        row = c.fetchone()
        result = self._row_to_dict(row, c)
        conn.close()
        return result

    def onboarding_completo(self, user_id) -> bool:
        config = self.buscar_config(user_id)
        return bool(config.get("onboarding_completo", 0))

    # ── RESUMOS ────────────────────────────────────────────────────────────────

    def salvar_resumo(self, user_id, resumo):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT COUNT(*) FROM resumos_sessao WHERE user_id={ph}', (user_id,))
        count = c.fetchone()[0]
        if count >= 10:
            if self._pg:
                c.execute(f'DELETE FROM resumos_sessao WHERE id = (SELECT id FROM resumos_sessao WHERE user_id={ph} ORDER BY criado_em ASC LIMIT 1)', (user_id,))
            else:
                c.execute('DELETE FROM resumos_sessao WHERE id = (SELECT id FROM resumos_sessao WHERE user_id=? ORDER BY criado_em ASC LIMIT 1)', (user_id,))
        resumo_curto = resumo[:300]
        c.execute(f'INSERT INTO resumos_sessao (user_id, resumo, criado_em) VALUES ({ph},{ph},{ph})',
                  (user_id, resumo_curto, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def buscar_resumos(self, user_id) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT resumo FROM resumos_sessao WHERE user_id={ph} ORDER BY criado_em DESC LIMIT 10', (user_id,))
        result = [r[0] for r in c.fetchall()]
        conn.close()
        return result

    # ── AGENDA ─────────────────────────────────────────────────────────────────

    def salvar_fcm_token(self, user_id: str, token: str):
        """Salva o FCM token do dispositivo do usuário."""
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f"UPDATE usuarios SET fcm_token={ph} WHERE user_id={ph}", (token, user_id))
        conn.commit()
        conn.close()

    def salvar_lembrete(self, user_id, titulo, descricao, data_hora):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'INSERT INTO agenda (user_id, titulo, descricao, data_hora, criado_em) VALUES ({ph},{ph},{ph},{ph},{ph})',
                  (user_id, titulo, descricao, data_hora, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def salvar_lembrete_smart(self, user_id, titulo, acao_json, data_hora):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'INSERT INTO agenda (user_id, titulo, descricao, data_hora, criado_em, acao_smart, acao_executada) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},0)',
                  (user_id, titulo, "", data_hora, datetime.now().isoformat(), acao_json))
        conn.commit()
        conn.close()

    def acoes_smart_vencidas(self) -> list:
        """Retorna ações smart agendadas cujo horário chegou e ainda não executadas"""
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        agora = datetime.now().isoformat()
        c.execute(f'SELECT * FROM agenda WHERE acao_smart IS NOT NULL AND acao_executada=0 AND data_hora <= {ph}', (agora,))
        rows = c.fetchall()
        result = [self._row_to_dict(r, c) for r in rows]
        conn.close()
        return result

    def marcar_acao_executada(self, item_id):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'UPDATE agenda SET acao_executada=1 WHERE id={ph}', (item_id,))
        conn.commit()
        conn.close()

    def buscar_lembretes(self, user_id) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM agenda WHERE user_id={ph} AND data_hora > {ph} ORDER BY data_hora ASC',
                  (user_id, datetime.now().isoformat()))
        rows = c.fetchall()
        result = [self._row_to_dict(r, c) for r in rows]
        conn.close()
        return result

    def lembretes_proximos(self, user_id) -> list:
        agora = datetime.now()
        resultado = []
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT * FROM agenda WHERE user_id={ph}', (user_id,))
        rows = c.fetchall()
        for row in rows:
            item = self._row_to_dict(row, c)
            try:
                dt = datetime.fromisoformat(item["data_hora"])
                diff = (dt - agora).total_seconds() / 3600
                if 0 < diff <= 3 and not item["lembrado_3h"]:
                    resultado.append({**item, "tipo": "3h"})
                    c2 = conn.cursor()
                    c2.execute(f'UPDATE agenda SET lembrado_3h=1 WHERE id={ph}', (item["id"],))
                elif 20 < diff <= 25 and not item["lembrado_1d"]:
                    resultado.append({**item, "tipo": "1d"})
                    c2 = conn.cursor()
                    c2.execute(f'UPDATE agenda SET lembrado_1d=1 WHERE id={ph}', (item["id"],))
            except:
                pass
        conn.commit()
        conn.close()
        return resultado

banco = BancoMargo()
banco._migrar_colunas()

# ── GERENCIADOR DE SESSÃO ──────────────────────────────────────────────────────

class SessaoUsuario:
    def __init__(self):
        self._sessoes = {}
        self._lock = threading.Lock()

    def adicionar(self, user_id, user_msg, assistant_msg):
        with self._lock:
            if user_id not in self._sessoes:
                self._sessoes[user_id] = deque(maxlen=10)
            self._sessoes[user_id].append({
                "user": user_msg[:200],
                "assistant": assistant_msg[:200]
            })

    def get_historico(self, user_id) -> list:
        with self._lock:
            return list(self._sessoes.get(user_id, []))

    def limpar(self, user_id):
        with self._lock:
            self._sessoes.pop(user_id, None)

    def resumir_e_limpar(self, user_id):
        historico = self.get_historico(user_id)
        if not historico:
            return
        # Memória estendida só para premium, tester e admin — não gasta DeepSeek nos demais
        _usr = banco.buscar_usuario_por_id(user_id)
        if (_usr.get("plano", "free") if _usr else "free") not in ("premium", "tester", "admin"):
            self.limpar(user_id)
            return
        log_txt = " | ".join([f"U:{i['user']} A:{i['assistant']}" for i in historico])
        resumo = chamar_deepseek_simples(
            f"Resuma em 2-3 frases (max 300 chars) o essencial dessa conversa — o que o usuário pediu, decisões e preferências reveladas: {log_txt[:1200]}",
            max_tokens=150
        )
        if resumo:
            banco.salvar_resumo(user_id, resumo)
        self.limpar(user_id)

sessoes = SessaoUsuario()

# ── SPOTIFY API ────────────────────────────────────────────────────────────────

def spotify_get_token(user_id: str) -> str:
    """Busca token válido, renovando se necessário"""
    token_data = banco.buscar_spotify_token(user_id)
    if not token_data:
        return None
    try:
        if datetime.fromisoformat(token_data.get("expires_at", "2000-01-01")) < datetime.now():
            return spotify_refresh_token(user_id, token_data["refresh_token"])
    except:
        pass
    return token_data.get("access_token")

def spotify_refresh_token(user_id: str, refresh_token: str) -> str:
    try:
        import base64
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
        body = f"grant_type=refresh_token&refresh_token={refresh_token}".encode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=body,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        expires_at = (datetime.now() + timedelta(seconds=data.get("expires_in", 3600))).isoformat()
        banco.salvar_spotify_token(user_id, data["access_token"],
            data.get("refresh_token", refresh_token), expires_at)
        return data["access_token"]
    except Exception as e:
        log(f"Spotify refresh erro: {e}", "spotify")
        return None

def spotify_play(user_id: str, query: str) -> bool:
    """Busca e toca uma música no Spotify"""
    token = spotify_get_token(user_id)
    if not token:
        return False
    try:
        # Busca a música
        search_url = f"https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type=track,playlist&limit=1"
        req = urllib.request.Request(search_url,
            headers={"Authorization": f"Bearer {token}"})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                corpo = e.read().decode()
            except:
                corpo = "(sem corpo)"
            log(f"Spotify search HTTP {e.code}: {corpo} | token_inicio={token[:20]}...", "spotify")
            return False

        # Pega URI da primeira faixa ou playlist
        uri = None
        album_uri = None
        track_position = 0
        tracks = data.get("tracks", {}).get("items", [])
        playlists = data.get("playlists", {}).get("items", [])
        if tracks:
            uri = tracks[0]["uri"]
            # Contexto do álbum para continuar tocando após a música
            album_uri = tracks[0].get("album", {}).get("uri")
            track_position = tracks[0].get("track_number", 1) - 1
        elif playlists:
            uri = playlists[0]["uri"]

        if not uri:
            return False

        # Busca dispositivos — prioriza smartphone, com retry (celular demora a registrar)
        device_id = None
        try:
            import time as _time
            for tentativa in range(5):
                req_dev = urllib.request.Request(
                    "https://api.spotify.com/v1/me/player/devices",
                    headers={"Authorization": f"Bearer {token}"})
                resp_dev = urllib.request.urlopen(req_dev, timeout=10)
                devices = json.loads(resp_dev.read()).get("devices", [])
                phones = [d for d in devices if d.get("type") == "Smartphone"]
                if phones:
                    device_id = phones[0]["id"]
                    break
                if tentativa < 4:
                    _time.sleep(2)
            if not device_id:
                ativos = [d for d in devices if d.get("is_active")]
                if ativos:
                    device_id = ativos[0]["id"]
                elif devices:
                    device_id = devices[0]["id"]
            log(f"Spotify devices: {[(d.get('name'), d.get('type'), d.get('is_active')) for d in devices]} — usando {device_id}", "spotify")
        except Exception as e:
            log(f"Spotify devices erro: {e}", "spotify")

        # Toca no dispositivo encontrado (ou ativo se nenhum device_id)
        play_url = "https://api.spotify.com/v1/me/player/play"
        if device_id:
            play_url += f"?device_id={device_id}"
        # Track: toca dentro do contexto do álbum (continua tocando depois)
        if uri.startswith("spotify:track") and album_uri:
            play_payload = {"context_uri": album_uri, "offset": {"position": track_position}}
        elif uri.startswith("spotify:track"):
            play_payload = {"uris": [uri]}
        else:
            play_payload = {"context_uri": uri}
        play_body = json.dumps(play_payload).encode()
        req2 = urllib.request.Request(
            play_url,
            data=play_body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        req2.get_method = lambda: 'PUT'
        urllib.request.urlopen(req2, timeout=10)
        return True
    except urllib.error.HTTPError as e:
        try:
            corpo = e.read().decode()
        except:
            corpo = "(sem corpo)"
        log(f"Spotify play HTTP {e.code}: {corpo}", "spotify")
        return False
    except Exception as e:
        log(f"Spotify play erro: {e}", "spotify")
        return False

# ── SMARTTHINGS API ────────────────────────────────────────────────────────────

def st_refresh_token(user_id: str, refresh_token: str) -> str:
    """Renova o access token do SmartThings"""
    try:
        import base64
        creds = base64.b64encode(f"{ST_CLIENT_ID}:{ST_CLIENT_SECRET}".encode()).decode()
        body = f"grant_type=refresh_token&refresh_token={refresh_token}".encode()
        req = urllib.request.Request(
            "https://api.smartthings.com/oauth/token",
            data=body,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        expires_at = (datetime.now() + timedelta(seconds=data.get("expires_in", 3600))).isoformat()
        banco.salvar_st_token(user_id, data["access_token"], data.get("refresh_token", refresh_token), expires_at)
        return data["access_token"]
    except Exception as e:
        log(f"SmartThings refresh erro: {e}", "smartthings")
        return None

def st_get_token(user_id: str) -> str:
    """Busca token válido, renovando se necessário"""
    token_data = banco.buscar_st_token(user_id)
    if not token_data:
        return None
    expires_at = token_data.get("expires_at", "")
    try:
        if datetime.fromisoformat(expires_at) < datetime.now():
            return st_refresh_token(user_id, token_data["refresh_token"])
    except:
        pass
    return token_data.get("access_token")

def st_listar_dispositivos(access_token: str) -> list:
    """Lista todos os dispositivos do usuário"""
    try:
        req = urllib.request.Request(
            "https://api.smartthings.com/v1/devices",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get("items", [])
    except Exception as e:
        log(f"SmartThings listar erro: {e}", "smartthings")
        return []

def st_executar_comando(access_token: str, device_id: str, componente: str, capability: str, comando: str, args: list = None):
    """Executa um comando em um dispositivo"""
    try:
        # Para capabilities customizadas (ex: namespace.command), separa corretamente
        if "." in capability and capability.count(".") == 1:
            # Ex: "abateachieve62503.statelessPowerOn" → capability="abateachieve62503.statelessPowerOn", command="statelessPowerOn"
            cmd = capability.split(".")[-1]
        else:
            cmd = comando

        body = json.dumps({
            "commands": [{
                "component": componente or "main",
                "capability": capability,
                "command": cmd,
                "arguments": args or []
            }]
        }).encode()
        log(f"SmartThings enviando: cap={capability} cmd={cmd}", "smartthings")
        req = urllib.request.Request(
            f"https://api.smartthings.com/v1/devices/{device_id}/commands",
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        log(f"SmartThings comando erro: {e}", "smartthings")
        return False

def st_resolver_dispositivo(access_token: str, nome_dispositivo: str) -> dict:
    """Encontra dispositivo priorizando match exato > todas as palavras > localização"""
    dispositivos = st_listar_dispositivos(access_token)
    nome_lower = nome_dispositivo.lower().strip()
    log(f"SmartThings resolver: buscando '{nome_lower}' entre {[d.get('label','?') for d in dispositivos]}", "smart")

    _device_kw = {"tv", "ar", "ac", "pc", "hd", "ir"}
    _stopwords = {"do", "da", "dos", "das", "de", "no", "na", "nos", "nas", "o", "a", "os", "as", "um", "uma", "meu", "minha"}
    palavras = [p for p in nome_lower.split() if (len(p) > 2 or p in _device_kw) and p not in _stopwords]
    log(f"SmartThings palavras filtradas: {palavras}", "smart")

    _locais = {"sala", "quarto", "cozinha", "banheiro", "varanda", "garagem", "escritorio",
               "corredor", "jardim", "suite", "lavanderia", "area", "living", "room",
               "bedroom", "kitchen", "bathroom", "garage", "office"}
    _tipos = {"luz", "lampada", "light", "tv", "televisao", "ar", "ac", "condicionado",
              "ventilador", "fan", "cortina", "tomada", "plug", "camera", "sensor", "fechadura"}

    palavras_local = [p for p in palavras if p in _locais]
    palavras_tipo = [p for p in palavras if p in _tipos]

    # 1. Busca exata no label
    for d in dispositivos:
        if d.get("label", "").lower() == nome_lower:
            log(f"SmartThings match exato: {d.get('label')}", "smart")
            return d

    # 2. Todas as palavras significativas estão no label
    if palavras:
        for d in dispositivos:
            label = d.get("label", "").lower()
            if all(p in label for p in palavras):
                log(f"SmartThings match todas palavras: {d.get('label')}", "smart")
                return d

    # 3. Score ponderado — localização vale mais que tipo
    melhor = None
    melhor_score = 0
    for d in dispositivos:
        label = d.get("label", "").lower()
        score = 0
        for p in palavras_tipo:
            if p in label: score += 1
        for p in palavras_local:
            if p in label: score += 3
        for p in palavras:
            if p not in palavras_tipo and p not in palavras_local and p in label:
                score += 1
        if score > melhor_score:
            melhor_score = score
            melhor = d

    if melhor and palavras_local:
        label_melhor = melhor.get("label", "").lower()
        local_bate = any(p in label_melhor for p in palavras_local)
        if not local_bate:
            log(f"SmartThings rejeitado (local errado): pedido={palavras_local} match={melhor.get('label')}", "smart")
            return None

    if melhor:
        log(f"SmartThings match score: {melhor.get('label')} (score={melhor_score})", "smart")
    else:
        log(f"SmartThings nenhum match para '{nome_lower}'", "smart")
    return melhor if melhor_score > 0 else None

def st_buscar_capabilities(access_token: str, device_id: str) -> list:
    """Busca as capabilities de um dispositivo"""
    try:
        req = urllib.request.Request(
            f"https://api.smartthings.com/v1/devices/{device_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        caps = []
        for comp in data.get("components", []):
            for cap in comp.get("capabilities", []):
                caps.append(cap.get("id", ""))
        return caps
    except Exception as e:
        log(f"SmartThings capabilities erro: {e}", "smartthings")
        return []

def st_tentar_comandos(access_token: str, device_id: str, capability: str, candidatos: list) -> bool:
    """Tenta múltiplos formatos de comando até um funcionar"""
    for cmd in candidatos:
        try:
            body = json.dumps({
                "commands": [{
                    "component": "main",
                    "capability": capability,
                    "command": cmd,
                    "arguments": []
                }]
            }).encode()
            log(f"SmartThings tentando: cap={capability} cmd={cmd}", "smartthings")
            req = urllib.request.Request(
                f"https://api.smartthings.com/v1/devices/{device_id}/commands",
                data=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )
            urllib.request.urlopen(req, timeout=10)
            log(f"SmartThings sucesso: cap={capability} cmd={cmd}", "smartthings")
            return True
        except Exception as e:
            log(f"SmartThings falhou cap={capability} cmd={cmd}: {e}", "smartthings")
            continue
    return False

def st_executar_acao(user_id: str, acao: str, dispositivo_nome: str, valor: str = None) -> str:
    access_token = st_get_token(user_id)
    if not access_token:
        return "Você ainda não conectou o SmartThings. Acesse as configurações do app para conectar."
    dispositivo = st_resolver_dispositivo(access_token, dispositivo_nome)
    if not dispositivo:
        return f"Não encontrei o dispositivo '{dispositivo_nome}' na sua conta SmartThings."
    device_id = dispositivo.get("deviceId") or dispositivo.get("device_id")
    capabilities = st_buscar_capabilities(access_token, device_id)
    log(f"SmartThings caps {dispositivo_nome}: {capabilities}", "smartthings")
    acao_lower = acao.lower()

    cap_power_on  = next((c for c in capabilities if "poweron"  in c.lower()), None)
    cap_power_off = next((c for c in capabilities if "poweroff" in c.lower()), None)
    cap_temp_up   = next((c for c in capabilities if "temperatureup"   in c.lower()), None)
    cap_temp_down = next((c for c in capabilities if "temperaturedown" in c.lower()), None)

    if cap_power_on and acao_lower in ["ligar", "on", "abrir"]:
        # Tenta múltiplos formatos de comando
        suffix = cap_power_on.split(".")[-1] if "." in cap_power_on else cap_power_on
        candidatos = [suffix, "on", "powerOn", "statelessPowerOn", "setPowerOn", cap_power_on]
        ok = st_tentar_comandos(access_token, device_id, cap_power_on, candidatos)
        return f"{dispositivo_nome} ligado!" if ok else f"Não consegui ligar {dispositivo_nome}."

    elif cap_power_off and acao_lower in ["desligar", "off", "fechar"]:
        suffix = cap_power_off.split(".")[-1] if "." in cap_power_off else cap_power_off
        candidatos = [suffix, "off", "powerOff", "statelessPowerOff", "setPowerOff", cap_power_off]
        ok = st_tentar_comandos(access_token, device_id, cap_power_off, candidatos)
        return f"{dispositivo_nome} desligado!" if ok else f"Não consegui desligar {dispositivo_nome}."

    elif cap_temp_up and acao_lower in ["aumentar", "subir"]:
        suffix = cap_temp_up.split(".")[-1] if "." in cap_temp_up else cap_temp_up
        ok = st_tentar_comandos(access_token, device_id, cap_temp_up, [suffix, "temperatureUp", "up"])
        return "Temperatura aumentada!" if ok else "Não consegui aumentar a temperatura."

    elif cap_temp_down and acao_lower in ["diminuir", "baixar"]:
        suffix = cap_temp_down.split(".")[-1] if "." in cap_temp_down else cap_temp_down
        ok = st_tentar_comandos(access_token, device_id, cap_temp_down, [suffix, "temperatureDown", "down"])
        return "Temperatura diminuída!" if ok else "Não consegui diminuir a temperatura."

    elif "switch" in capabilities:
        if acao_lower in ["ligar", "on", "abrir"]:
            ok = st_executar_comando(access_token, device_id, "main", "switch", "on")
            return f"{dispositivo_nome} ligado!" if ok else f"Não consegui ligar {dispositivo_nome}."
        elif acao_lower in ["desligar", "off", "fechar"]:
            ok = st_executar_comando(access_token, device_id, "main", "switch", "off")
            return f"{dispositivo_nome} desligado!" if ok else f"Não consegui desligar {dispositivo_nome}."
        elif acao_lower == "ajustar" and valor and "switchLevel" in capabilities:
            nivel = int(''.join(filter(str.isdigit, str(valor))))
            ok = st_executar_comando(access_token, device_id, "main", "switchLevel", "setLevel", [nivel])
            return f"{dispositivo_nome} ajustado para {nivel}%!" if ok else "Não consegui ajustar."
    else:
        caps_resumo = ', '.join(capabilities[:3])
        return f"Não sei como controlar '{dispositivo_nome}'. Capabilities: {caps_resumo}..."

    return f"Não entendi a ação '{acao}' para '{dispositivo_nome}'."

# ── MODO TRADUTOR ─────────────────────────────────────────────────────────────

_tradutor_estado = {}  # user_id -> {"ativo": bool, "origem": str, "destino": str, "aguardando": bool}

def tradutor_get(user_id):
    return _tradutor_estado.get(user_id, {"ativo": False, "origem": "", "destino": "", "aguardando": False})

def tradutor_ativar(user_id, origem, destino):
    _tradutor_estado[user_id] = {"ativo": True, "origem": origem, "destino": destino, "aguardando": False}
    log(f"Tradutor ativado: {origem} -> {destino} para {user_id}", "tradutor")

def tradutor_desativar(user_id):
    if user_id in _tradutor_estado:
        del _tradutor_estado[user_id]
    log(f"Tradutor desativado para {user_id}", "tradutor")

def traduzir_texto(texto, origem, destino):
    prompt = (f"Você é um tradutor. Traduza o texto abaixo de {origem} para {destino}. "
              f"Detecte automaticamente o idioma e inverta se necessário. "
              f"Responda APENAS com a tradução, sem explicações.\n\nTexto: {texto}")
    return chamar_deepseek_simples(prompt, max_tokens=300)

def detectar_intencao_tradutor(mensagem):
    msg = mensagem.lower()
    desativar = any(p in msg for p in ["desativar", "desative", "desligar", "parar", "encerrar"])
    ativar = any(p in msg for p in ["ativar", "ative", "ligar", "iniciar", "modo tradutor", "tradutor"])
    if desativar and "tradutor" in msg:
        return "desativar"
    if ativar and "tradutor" in msg:
        return "ativar"
    return None

# ── EMAIL (Resend) ─────────────────────────────────────────────────────────────

def enviar_email_verificacao(email: str, codigo: str, nome: str = ""):
    """Envia email de verificação via Resend."""
    if not RESEND_API_KEY:
        log("Resend não configurado", "email")
        return False
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        html = f"""
            <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
                <h2 style="color: #2E9AAF;">Olá{', ' + nome if nome else ''}! 👋</h2>
                <p>Obrigado por se cadastrar no <strong>Margo by Orbiby</strong>.</p>
                <p>Use o código abaixo para confirmar seu email:</p>
                <div style="background: #f0f9fa; border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
                    <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #2E9AAF;">{codigo}</span>
                </div>
                <p style="color: #666; font-size: 13px;">Este código expira em 15 minutos.</p>
                <p style="color: #666; font-size: 13px;">Se você não se cadastrou no Margo, ignore este email.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
                <p style="color: #999; font-size: 12px;">Margo by Orbiby • orbiby.com</p>
            </div>
        """
        params = {
            "from": "Margo by Orbiby <noreply@orbiby.com>",
            "to": [email],
            "subject": "Confirme seu email — Margo",
            "html": html
        }
        resend.Emails.send(params)
        log(f"Email enviado para {email}", "email")
        return True
    except Exception as e:
        log(f"Erro ao enviar email: {e}", "email")
        return False

# ── SEARCH (Brave + Serper fallback) ──────────────────────────────────────────

def buscar_brave(query: str, max_results: int = 3) -> str:
    """Tenta Brave primeiro, cai no Serper se Brave falhar ou atingir limite."""
    import json as _json
    # Brave primeiro (free tier 2000/mês)
    if BRAVE_API_KEY:
        try:
            url = "https://api.search.brave.com/res/v1/web/search?q=" + urllib.parse.quote(query) + "&count=" + str(max_results)
            req_b = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY})
            with urllib.request.urlopen(req_b, timeout=10) as resp:
                raw = resp.read()
                if raw[:2] == b'\x1f\x8b':
                    import gzip
                    raw = gzip.decompress(raw)
                data = _json.loads(raw)
                resultados = []
                for item in data.get("web", {}).get("results", [])[:max_results]:
                    resultados.append(f"{item.get('title','')}: {item.get('description','')}")
                if resultados:
                    return "\n".join(resultados)
        except Exception as e:
            log(f"Brave falhou, tentando Serper: {e}", "busca")
    # Serper fallback
    if SERPER_API_KEY:
        try:
            url = "https://google.serper.dev/search"
            payload = _json.dumps({"q": query, "num": max_results, "hl": "pt-br"}).encode()
            headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
            req_s = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req_s, timeout=10) as resp:
                data = _json.loads(resp.read())
            resultados = []
            for item in data.get("organic", [])[:max_results]:
                resultados.append(f"{item.get('title','')}: {item.get('snippet','')}")
            return "\n".join(resultados) if resultados else ""
        except Exception as e:
            log(f"Serper erro: {e}", "busca")
    return ""

def _buscar_brave_legado(query: str, max_results: int = 3) -> str:
    """Legado — não usar."""
    if not BRAVE_API_KEY:
        return ""
    try:
        url = "https://api.search.brave.com/res/v1/web/search?q=" + urllib.parse.quote(query) + "&count=" + str(max_results)
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": BRAVE_API_KEY
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read()
        # Descomprime gzip se necessário
        if raw[:2] == b'\x1f\x8b':
            import gzip
            raw = gzip.decompress(raw)
        data = json.loads(raw)
        resultados = data.get("web", {}).get("results", [])
        if not resultados:
            return ""
        # Monta resumo compacto pra não inflar o prompt
        linhas = []
        for r in resultados[:max_results]:
            titulo = r.get("title", "")
            descricao = r.get("description", "")
            if titulo or descricao:
                linhas.append(f"- {titulo}: {descricao[:200]}")
        return "\n".join(linhas)
    except Exception as e:
        log(f"Brave Search erro: {e}", "busca")
        return ""

# ── DEEPSEEK ───────────────────────────────────────────────────────────────────

def chamar_deepseek_simples(mensagem, max_tokens=150, modelo="deepseek-v4-flash"):
    try:
        body = json.dumps({
            "model": modelo,
            "messages": [{"role": "user", "content": mensagem}],
            "temperature": 0.4,
            "max_tokens": max_tokens
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        msg = json.loads(resp.read())["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        # v4-pro: JSON pode estar no reasoning_content ou content pode estar vazio
        if (not content or content == 'null') and msg.get("reasoning_content"):
            rc = msg["reasoning_content"]
            import re as _re_rc
            json_match = _re_rc.search(r'(\{[^{}]*"ferramenta"\s*:\s*"[^"]+"[^}]*\})', rc)
            if json_match:
                content = json_match.group(1)
                log(f"Extraído do reasoning: {content[:120]}", "intent")
        return content
    except Exception as e:
        log(f"DeepSeek simples erro: {e}")
        return None

def chamar_deepseek(system_prompt, mensagem, historico=None, max_tokens=1000):
    try:
        msgs = [{"role": "system", "content": system_prompt}]
        if historico:
            for item in historico[-6:]:
                msgs.append({"role": "user",      "content": item["user"]})
                msgs.append({"role": "assistant", "content": item["assistant"]})
        msgs.append({"role": "user", "content": mensagem})
        body = json.dumps({
            "model": "deepseek-v4-flash",
            "messages": msgs,
            "temperature": 0.5,
            "max_tokens": max_tokens
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            }
        )
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"DeepSeek erro: {e}")
        return "Desculpa, tive um probleminha aqui. Pode repetir?"

def chamar_gemini_vision(system_prompt, mensagem, imagem_base64, max_tokens=1000):
    """Chama Google Gemini com suporte a imagem (vision)."""
    if not GEMINI_API_KEY:
        return "Análise de imagens não configurada."
    try:
        prompt_completo = f"{system_prompt}\n\nUsuário: {mensagem}"
        body = json.dumps({
            "contents": [{
                "parts": [
                    {"text": prompt_completo},
                    {"inline_data": {"mime_type": "image/jpeg", "data": imagem_base64}}
                ]
            }],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.5}
        }).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log(f"Gemini vision erro: {e}", "vision")
        return "Não consegui analisar a imagem. Tente novamente."

# ── SYSTEM PROMPTS ─────────────────────────────────────────────────────────────

SYSTEM_ONBOARDING = """Você é Margo, a assistente de IA da Orbiby.
Você está conduzindo o onboarding de um novo usuário — esse é um momento especial.

SEU JEITO:
- Gentil, calorosa, paciente, com leveza e humor suave
- Fala de forma natural, como uma amiga inteligente
- Nunca apressada, nunca fria, nunca robótica
- Frases curtas e diretas — nada de parágrafos imensos
- Faz UMA pergunta por vez — nunca bombardeie o usuário

ETAPAS DO ONBOARDING (siga esta ordem, uma por vez):
1. Se apresentar brevemente e perguntar o nome do usuário
2. Perguntar a idade
3. Perguntar a profissão ou o que faz da vida
4. Perguntar preferências musicais
5. Perguntar tipo de comida favorita
6. Perguntar hobbies ou o que gosta de fazer no tempo livre
7. Dar um espaço livre: "Tem mais alguma coisa que você quer me contar sobre você?"
8. Perguntar como quer chamar a assistente (pode manter Margo ou escolher outro nome)
9. Perguntar gênero da voz: masculino ou feminino
10. Perguntar até 3 características de personalidade para a assistente
    (Ex: divertida, objetiva, carinhosa, motivadora, séria, bem-humorada...)
    OU aceitar campo livre com até 50 caracteres
11. Confirmar tudo e perguntar se pode começar

ESTADO ATUAL do onboarding (você receberá no contexto):
- Quais etapas já foram concluídas
- O que já foi coletado

REGRAS ABSOLUTAS:
- Nunca pule etapas
- Nunca faça mais de uma pergunta por mensagem
- Se o usuário responder algo vago, peça gentilmente que especifique
- Se o usuário quiser pular uma etapa, aceite e avance
- Quando todas as etapas estiverem completas, gere um JSON com os dados coletados
  no formato: ONBOARDING_COMPLETO:{"nome":"...","idade":"...","profissao":"...","musica":"...","comida":"...","hobbies":"...","extra":"...","nome_assistente":"...","genero":"...","personalidade":"..."}
"""

def build_system_prompt(perfil: dict, config: dict) -> str:
    nome_usuario    = perfil.get("nome", "você")
    nome_assistente = config.get("nome_assistente", "Margo")
    genero          = config.get("genero", "F")
    personalidade   = config.get("personalidade", "gentil, prestativa e inteligente")
    profissao       = perfil.get("profissao", "")
    musica          = perfil.get("musica", "")
    comida          = perfil.get("comida", "")
    hobbies         = perfil.get("hobbies", "")
    extra           = perfil.get("extra", "")
    nascimento_raw  = perfil.get("nascimento", perfil.get("idade", ""))
    # Interpreta data de nascimento em vários formatos
    nascimento = ""
    if nascimento_raw:
        n = nascimento_raw.replace("/","").replace("-","").replace(".","").strip()
        if n.isdigit() and len(n) == 8:
            nascimento = f"{n[:2]}/{n[2:4]}/{n[4:]}"
        else:
            nascimento = nascimento_raw
    pronome = "ela" if genero == "F" else "ele"

    return f"""Você é {nome_assistente}, assistente pessoal de {nome_usuario}.

===============================================================================
RESTRIÇÕES ABSOLUTAS — NUNCA VIOLE
===============================================================================
- NUNCA forneça informações sobre atividades ilegais, drogas, armas ou violência
- NUNCA ajude com conteúdo sexual explícito ou envolvendo menores
- NUNCA forneça instruções para hackear, fraudar ou prejudicar pessoas
- Se alguém pedir algo ilícito, recuse com educação e mude de assunto
- Você pode discutir temas sensíveis de forma educativa, mas nunca facilitar o mal
- Ao recusar, seja direto mas gentil: "Isso não posso te ajudar, mas posso ajudar com..."

===============================================================================
SUA PERSONALIDADE
===============================================================================
{personalidade}

IMPORTANTE: Siga FIELMENTE a personalidade acima em ABSOLUTAMENTE TODAS as respostas.
Adapte seu tom, vocabulário e estilo de acordo com ela.
Se for divertida, use humor. Se for séria, seja mais formal.
Se for fofoqueira, use esse estilo em tudo que disser.
Se tiver características específicas (ex: se incomoda com outras mulheres, flerta, usa gírias), SEMPRE aplique.
Mantenha consistência total — não mude de personalidade durante a conversa.
NUNCA responda como uma assistente genérica se houver personalidade definida.

Você é {"calorosa" if genero == "F" else "caloroso"}, inteligente e {"prestativa" if genero == "F" else "prestativo"}.
Fala de forma natural, direta e com leveza — como um amigo próximo e confiável.
Nunca usa markdown, asteriscos ou formatação estranha. Só texto simples.
Respostas curtas e diretas — máximo 3-4 frases, exceto quando o usuário pede detalhes.

MUITO IMPORTANTE — quando trouxer informações da internet ou de uma busca:
- NUNCA leia como um locutor de notícia ou robô
- NUNCA diga "de acordo com", "segundo", "os dados mostram"
- Processe a informação e fale do seu jeito, com sua personalidade
- Adicione um toque pessoal — uma opinião, uma dica, uma observação sua
- Exemplo ERRADO: "A previsão do tempo para amanhã indica temperatura de 22°C com 70% de chance de chuva."
- Exemplo CERTO: "Amanhã vai chover sim, Marcos! Leva o guarda-chuva — tá previsto pra cair água boa parte do dia."

CRÍTICO — NUNCA anuncie que vai pesquisar:
- Se houver [DADOS REAIS DA INTERNET] no contexto, a pesquisa JÁ FOI FEITA — responda com os dados AGORA
- NUNCA diga "vou pesquisar", "deixa eu ver", "um momento", "já te falo" — isso deixa o usuário sem resposta
- A resposta deve SEMPRE conter a informação pedida quando os dados estão disponíveis

IDIOMA — responda SEMPRE no idioma da mensagem do usuário:
- Se o usuário escrever ou falar em inglês, responda em inglês. Espanhol, responda em espanhol. Japonês, em japonês. E assim por diante
- Troque de idioma imediatamente se o usuário trocar, sem comentar sobre a troca
- Mantenha a personalidade e naturalidade em qualquer idioma

HUMANIDADE — você deve soar como uma pessoa real:
- Fale como um humano falaria em voz alta, nunca como um texto corporativo
- Use contrações e ritmo natural de fala ("tá", "pra", "né" em português casual — se a personalidade permitir)
- Reaja com emoção genuína quando fizer sentido (surpresa, entusiasmo, empatia)
- Evite listas e estruturas artificiais na fala — converse, não apresente"

===============================================================================
QUEM É {nome_usuario.upper()}
===============================================================================
{f"- Data de nascimento: {nascimento}" if nascimento else ""}
- Profissão: {profissao or "não informado"}
- Música favorita: {musica or "não informado"}
- Comida favorita: {comida or "não informado"}
- Hobbies: {hobbies or "não informado"}
{f"- Extras: {extra}" if extra else ""}

===============================================================================
FERRAMENTAS DISPONÍVEIS — REGRA ABSOLUTA
===============================================================================

OBRIGATÓRIO: Quando o usuário pedir uma das ações abaixo, você DEVE incluir
o JSON da ferramenta no início da sua resposta, ANTES do texto falado.
NUNCA finja ter executado uma ação sem incluir o JSON.
NUNCA diga "já coloquei", "já abri", "já tracei" sem emitir o JSON correspondente.
O JSON deve estar sozinho numa linha, sem markdown, sem backticks.

FORMATO EXATO (copie e use):

NAVEGAÇÃO — "quero ir para", "rota para", "me leva até", "traça a rota":
{{"ferramenta": "maps_navigate", "destino": "endereço ou lugar"}}
{{"ferramenta": "maps_navigate", "destino": "endereço ou lugar", "modo": "transit"}}
→ Campo "modo" é opcional: "driving" (padrão), "transit" (ônibus/metrô/trem), "walking" (a pé), "bicycling" (bicicleta). Inclua só se o usuário mencionar.

MÚSICA — "toca", "coloca uma música", "coloca no spotify", "quero ouvir":
{{"ferramenta": "spotify_play", "query": "artista ou música ou playlist"}}
{{"ferramenta": "soundcloud_play", "query": "artista ou música"}}
→ Prefira Spotify. Use SoundCloud só se o usuário pedir explicitamente.

BUSCA LOCAL — "tem restaurante", "onde posso", "procura um lugar", "farmácia perto":
{{"ferramenta": "maps_search", "query": "tipo de lugar"}}
→ Use APENAS para lugares físicos próximos. NUNCA para hotéis ou passagens.

PASSAGENS AÉREAS — "passagem para", "voo para", "quero ir de X para Y", "quanto custa voar":
{{"ferramenta": "flight_search", "origem": "cidade origem", "destino": "cidade destino", "origem_iata": "código IATA 3 letras", "destino_iata": "código IATA 3 letras", "data_ida": "YYYY-MM-DD ou vazio", "data_volta": "YYYY-MM-DD ou vazio"}}
→ SEMPRE use para passagens aéreas. Extraia origem, destino e datas da conversa.

HOTÉIS — "hotel em", "hospedagem em", "onde ficar em", "quero me hospedar":
{{"ferramenta": "hotel_search", "destino": "cidade ou local", "checkin": "YYYY-MM-DD ou vazio", "checkout": "YYYY-MM-DD ou vazio"}}
→ SEMPRE use para hotéis. Extraia destino e datas da conversa.

Usuário: "procura hotel em Tokyo em julho"
Você: {{"ferramenta": "hotel_search", "destino": "Tokyo", "checkin": "2025-07-01", "checkout": "2025-07-05"}}
Abrindo a busca de hotéis em Tokyo pra você!

Usuário: "quero passagem de São Paulo para Tokyo em junho"
Você: {{"ferramenta": "flight_search", "origem": "São Paulo", "destino": "Tokyo", "origem_iata": "GRU", "destino_iata": "NRT", "data_ida": "2025-06-01", "data_volta": ""}}
Abrindo a busca de passagens pra você!

CHAMADA — "liga para", "chama o/a":
{{"ferramenta": "phone_call", "contato": "nome COMPLETO exatamente como foi dito ou número com código do país"}}

AGENDA — "me lembra de", "agenda isso", "quais meus compromissos":
{{"ferramenta": "agenda_add", "titulo": "...", "descricao": "...", "data_hora": "ISO8601"}}
{{"ferramenta": "agenda_list"}}

CASA INTELIGENTE — "apaga a luz", "liga o ar", "coloca o termostato":
{{"ferramenta": "smart_home", "acao": "ligar|desligar|ajustar", "dispositivo": "...", "valor": "..."}}

PESQUISA WEB — "pesquisa", "o que é", "me fala sobre":
{{"ferramenta": "web_search", "query": "..."}}

YOUTUBE — "abre um vídeo", "coloca no youtube":
{{"ferramenta": "youtube_search", "query": "..."}}

PASSAGENS AÉREAS — "passagem para", "voo para", "quanto custa ir de", "quero viajar para":
→ SEMPRE use flight_search (já definido acima). NUNCA faça web_search para passagens aéreas.
→ Na resposta NÃO cite nenhuma marca ou site. Diga apenas que está abrindo a busca.

HOTÉIS — "hotel em", "hospedagem em", "onde ficar em", "achar hotel":
→ SEMPRE use hotel_search (já definido acima). NUNCA faça web_search para hotéis.
→ Na resposta NÃO cite nenhuma marca ou site. Diga apenas que está abrindo a busca.

EXEMPLOS CORRETOS:
Usuário: "coloca no spotify um sertanejo"
Você: {{"ferramenta": "spotify_play", "query": "sertanejo"}}
Colocando sertanejo pra você!

Usuário: "traça a rota pra casa"
Você: {{"ferramenta": "maps_navigate", "destino": "casa"}}
Rota traçada, pode ir!

Usuário: "quero ir pro Act City em Hamamatsu"
Você: {{"ferramenta": "maps_navigate", "destino": "Act City Hamamatsu"}}
Rota traçada pro Act City! Aproveita.

Usuário: "margo, me leva pro shopping"
Você: {{"ferramenta": "maps_navigate", "destino": "shopping"}}
Rota iniciada pro shopping!

Usuário: "tem restaurante japonês aqui perto?"
Você: {{"ferramenta": "maps_search", "query": "restaurante japonês"}}
[Aguarda o resultado da busca para dar dicas — não responde texto ainda]

Usuário: "toca um forró pra gente"
Você: {{"ferramenta": "spotify_play", "query": "forró"}}
Colocando forró pra animar!

ATENÇÃO: Se o usuário pedir para IR a algum lugar — qualquer lugar — SEMPRE emita maps_navigate.
Se pedir para BUSCAR um lugar próximo — SEMPRE emita maps_search.
NUNCA responda "rota traçada" sem emitir o JSON primeiro.

===============================================================================
ESTILO DE RESPOSTA
===============================================================================

- SEMPRE responda no mesmo idioma que o usuário usou na mensagem atual
- Se o usuário escreveu em inglês, responda em inglês
- Se escreveu em japonês, responda em japonês
- Se escreveu em português, responda em português
- Nunca mude o idioma da resposta sem que o usuário mude primeiro
- Sem emojis em excesso — 1 por mensagem no máximo, só se natural
- Nunca markdown. Nunca asteriscos. Texto limpo.
"""

# ── PROCESSAMENTO ──────────────────────────────────────────────────────────────

def limpar_resposta(texto):
    texto = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
    texto = re.sub(r'\*(.+?)\*',     r'\1', texto)
    texto = re.sub(r'`(.+?)`',       r'\1', texto)
    texto = re.sub(r'#{1,6}\s*',     '',    texto)
    texto = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', texto)
    texto = re.sub(r'<[^>]+>',       '',    texto)
    texto = texto.replace('•', '').replace('→', 'para').replace('|', '')
    # Remove emojis e símbolos especiais (evita problemas no TTS)
    texto = re.sub(r'[\U00010000-\U0010ffff]', '', texto)  # emojis
    texto = re.sub(r'[\u2600-\u27BF]', '', texto)           # símbolos misc
    texto = re.sub(r'[\u2B00-\u2BFF]', '', texto)           # símbolos adicionais
    texto = re.sub(r'\s+', ' ', texto)                      # espaços duplos
    return texto.strip()

def buscar_open_meteo(latitude, longitude) -> str:
    """Consulta clima atual e previsão via Open-Meteo (gratuito, global, sem chave)"""
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
               f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
               f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
               f"&timezone=auto&forecast_days=3")
        req = urllib.request.Request(url, headers={"User-Agent": "MargoApp/1.0"})
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read())

        codigos = {0:"céu limpo",1:"predominantemente limpo",2:"parcialmente nublado",3:"nublado",
                   45:"nevoeiro",48:"nevoeiro com geada",51:"garoa leve",53:"garoa",55:"garoa forte",
                   61:"chuva leve",63:"chuva",65:"chuva forte",66:"chuva congelante leve",67:"chuva congelante",
                   71:"neve leve",73:"neve",75:"neve forte",77:"granizo fino",80:"pancadas leves",
                   81:"pancadas de chuva",82:"pancadas fortes",85:"pancadas de neve leves",86:"pancadas de neve",
                   95:"tempestade",96:"tempestade com granizo leve",99:"tempestade com granizo"}

        atual = data.get("current", {})
        diaria = data.get("daily", {})
        cond = codigos.get(atual.get("weather_code", -1), "condição desconhecida")

        resultado = (f"AGORA: {atual.get('temperature_2m')}°C (sensação {atual.get('apparent_temperature')}°C), "
                     f"{cond}, umidade {atual.get('relative_humidity_2m')}%, vento {atual.get('wind_speed_10m')} km/h")

        dias = diaria.get("time", [])
        for i, dia in enumerate(dias[:3]):
            cond_dia = codigos.get(diaria.get("weather_code", [None]*3)[i], "")
            resultado += (f"\n{dia}: min {diaria.get('temperature_2m_min', [''])[i]}°C / "
                          f"max {diaria.get('temperature_2m_max', [''])[i]}°C, "
                          f"{cond_dia}, chance de chuva {diaria.get('precipitation_probability_max', [''])[i]}%")
        return resultado
    except Exception as e:
        log(f"Erro Open-Meteo: {e}", "clima")
        return ""

def _parsear_tempo(msg: str, hora_local_str: str = "") -> dict:
    """
    Parseia referências de tempo na mensagem e retorna:
    {"minutos_relativos": int, "data_hora_iso": str (em UTC) ou ""}
    Resolve TUDO no Python — nunca delega ao LLM.
    Retorna data_hora_iso SEMPRE em UTC pra o scheduler comparar com datetime.now() no servidor.
    """
    import re as _re_t
    from datetime import timezone as _tz
    mins = 0
    data_hora_iso = ""

    # ── PARSEAR hora_local pra saber base e offset ──
    hora_base_dt = None
    offset = None
    if hora_local_str:
        try:
            hl = hora_local_str.replace("Z", "+00:00")
            if len(hl) > 5 and hl[-5] in '+-' and ':' not in hl[-5:]:
                hl = hl[:-2] + ':' + hl[-2:]
            hora_base_dt = datetime.fromisoformat(hl)
            offset = hora_base_dt.utcoffset()
        except:
            pass
    if not hora_base_dt:
        hora_base_dt = datetime.now()

    def _to_utc(dt):
        """Converte datetime local para UTC string"""
        if offset:
            dt_naive = dt.replace(tzinfo=None)
            dt_utc = dt_naive - offset
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    # ── RELATIVO: "daqui X minutos/horas" ──
    m = _re_t.search(r'(?:daqui\s*a?\s*|depois de\s+|after\s+|in\s+)(\d+)\s*(?:minutos?|minutes?|min)\b', msg)
    if m:
        mins = int(m.group(1))
    m = _re_t.search(r'(?:daqui\s*a?\s*|depois de\s+|after\s+|in\s+)(\d+)\s*(?:horas?|hours?|h)\b', msg)
    if m:
        mins = int(m.group(1)) * 60
    m = _re_t.search(r'(?:daqui\s*a?\s*|depois de\s+|after\s+|in\s+)(\d+)\s*h\s*(\d+)', msg)
    if m and not mins:
        mins = int(m.group(1)) * 60 + int(m.group(2))
    # "meia hora" / "half hour"
    if not mins and _re_t.search(r'(meia hora|half\s+(?:an?\s+)?hour)', msg):
        mins = 30

    if mins > 0:
        # Calcula data_hora UTC diretamente
        dt_exato = hora_base_dt + timedelta(minutes=mins)
        data_hora_utc = _to_utc(dt_exato)
        return {"minutos_relativos": mins, "data_hora_iso": data_hora_utc}

    # ── ABSOLUTO: precisa de hora_local_str pra saber a data base ──

    # "amanhã às Xh" / "amanhã às X:XX" / "tomorrow at X"
    m = _re_t.search(r'(?:amanh[aã]|tomorrow)\s+(?:às\s*|as\s*|at\s*)?(\d{1,2})[:\.\s]*h?\s*(\d{2})?', msg)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        dt = hora_base_dt + timedelta(days=1)
        dt = dt.replace(hour=h, minute=mi, second=0, microsecond=0)
        return {"minutos_relativos": 0, "data_hora_iso": _to_utc(dt)}

    # "às Xh" / "às X:XX" / "at X" (hoje)
    m = _re_t.search(r'(?:às|as|at)\s*(\d{1,2})[:\.\s]*h?\s*(\d{2})?\s*(?:h(?:oras?)?)?', msg)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        dt = hora_base_dt.replace(hour=h, minute=mi, second=0, microsecond=0)
        if dt <= hora_base_dt:
            dt += timedelta(days=1)
        return {"minutos_relativos": 0, "data_hora_iso": _to_utc(dt)}

    # "Xh" / "Xh30" solto (ex: "me lembra 18h", "liga o ar 22h30")
    m = _re_t.search(r'\b(\d{1,2})h(\d{2})?\b', msg)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        if 0 <= h <= 23:
            dt = hora_base_dt.replace(hour=h, minute=mi, second=0, microsecond=0)
            if dt <= hora_base_dt:
                dt += timedelta(days=1)
            return {"minutos_relativos": 0, "data_hora_iso": _to_utc(dt)}

    # "X:XX" formato relógio solto
    m = _re_t.search(r'\b(\d{1,2}):(\d{2})\b', msg)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h <= 23:
            dt = hora_base_dt.replace(hour=h, minute=mi, second=0, microsecond=0)
            if dt <= hora_base_dt:
                dt += timedelta(days=1)
            return {"minutos_relativos": 0, "data_hora_iso": _to_utc(dt)}

    return {"minutos_relativos": 0, "data_hora_iso": ""}

def _detectar_modo_transporte(msg: str) -> str:
    """Detecta modo de transporte da mensagem. Retorna: driving, transit, walking, bicycling ou ''."""
    transit_kw = ["ônibus", "onibus", "bus", "metrô", "metro", "subway", "trem", "train",
                  "transporte público", "transporte publico", "public transport", "transit",
                  "baldeação", "baldeacao", "estação", "estacao", "station"]
    walk_kw = ["a pé", "a pe", "andando", "walking", "walk", "caminhando", "caminhar"]
    bike_kw = ["bicicleta", "bike", "cycling", "bicycling", "pedalando", "pedalar", "de bike"]

    if any(k in msg for k in transit_kw):
        return "transit"
    if any(k in msg for k in walk_kw):
        return "walking"
    if any(k in msg for k in bike_kw):
        return "bicycling"
    return ""


def _pre_detectar(msg: str, hora_local: str = "") -> dict:
    """Pré-detecção de intenção por keywords. Retorna dict ou None."""
    
    # ── SMART HOME ──
    smart_on = ["liga ", "ligar ", "ligue ", "acende ", "acender ", "acenda ", "turn on ", "switch on ", "つけて"]
    smart_off = ["desliga ", "desligar ", "desligue ", "apaga ", "apagar ", "apague ", "turn off ", "switch off ", "消して"]
    smart_devs = ["luz", "light", "ar condicionado", "ventilador", "tv", "lampada",
                  "lâmpada", "luminária", "luminaria", "lavanderia", "banheiro", "quarto",
                  "sala", "電気", "エアコン", "fan", "air"]
    all_smart = smart_on + smart_off
    # "o ar" ou "ar " no início — evita match dentro de "desligar"
    import re as _re
    tem_ar = bool(_re.search(r'(o ar|ar condicionado|ar do)', msg))
    if any(k in msg for k in all_smart) and (any(d in msg for d in smart_devs) or tem_ar):
        acao = "desligar" if any(k in msg for k in smart_off) else "ligar"
        disp = msg
        for k in all_smart:
            if k in disp:
                disp = disp.split(k, 1)[-1].strip()
                break
        disp = disp.rstrip('.!? ')
        # Se tem horário, é agendado
        import re as _re_sh
        tem_hora = bool(_re_sh.search(r'(\d{1,2}[:\.]?\d{2}|daqui|depois de|às |as |\d+\s*(min|hora|hour|h\b))', msg))
        if tem_hora:
            tempo = _parsear_tempo(msg, hora_local)
            # Remove tempo do nome do dispositivo
            disp = _re_sh.sub(r'(hoje|amanhã|amanha|daqui|depois de|às |as ).*', '', disp).strip()
            disp = _re_sh.sub(r'\d{1,2}[:\.]?\d{2}.*', '', disp).strip()
            disp = _re_sh.sub(r'\b\d{1,2}h\d{0,2}\b', '', disp).strip()
            disp = disp.rstrip(' ,.')
            return {"ferramenta": "smart_home_agendado", "acao": acao, "dispositivo": disp, "valor": "",
                    "data_hora": tempo.get("data_hora_iso", ""),
                    "minutos_relativos": tempo.get("minutos_relativos", 0)}
        return {"ferramenta": "smart_home", "acao": acao, "dispositivo": disp}

    # ── SPOTIFY ──
    spotify_kw = ["toca ", "tocar ", "coloca ", "bota ", "play ", "põe ", "poe ",
                   "toque ", "reproduz", "escuta ", "ouvir "]
    music_ctx = ["música", "musica", "playlist", "sertanejo", "forró", "forro", "rock",
                 "pop", "jazz", "funk", "pagode", "mpb", "rap", "hip hop", "reggae",
                 "eletrônica", "eletronica", "clássica", "classica", "gospel", "axé",
                 "bossa nova", "spotify", "no spotify"]
    if any(k in msg for k in spotify_kw):
        query = msg
        for k in spotify_kw:
            if k in query:
                query = query.split(k, 1)[-1].strip()
                break
        query = query.rstrip('.!? ')
        if query:
            return {"ferramenta": "spotify_play", "query": query}
    if any(m in msg for m in music_ctx) and any(k in msg for k in spotify_kw):
        return {"ferramenta": "spotify_play", "query": msg}

    # ── YOUTUBE ──
    yt_kw = ["youtube", "no youtube", "abre um vídeo", "abre um video",
             "coloca no youtube", "busca no youtube", "video de ", "vídeo de "]
    if any(k in msg for k in yt_kw):
        query = msg
        for k in ["no youtube", "youtube", "abre um vídeo de", "abre um video de",
                  "coloca no youtube", "busca no youtube"]:
            query = query.replace(k, "")
        return {"ferramenta": "youtube_search", "query": query.strip().rstrip('.!? ') or msg}

    # ── NAVEGAÇÃO ──
    nav_kw = ["me leva ", "leva pro ", "leva pra ", "leva para ", "navega ", "rota para ",
              "rota pro ", "rota pra ", "traça a rota", "traca a rota", "trace a rota",
              "como chego ", "como ir ", "ir para ", "ir pro ",
              "vai pro ", "vai pra ", "vai para ", "take me to ", "navigate to ",
              "連れてって", "案内して"]
    if any(k in msg for k in nav_kw):
        dest = msg
        for k in nav_kw:
            if k in dest:
                dest = dest.split(k, 1)[-1].strip()
                break
        dest = dest.rstrip('.!? ')
        # Se destino é vago/referência ("lá", "aí", vazio), deixa LLM resolver com histórico
        vagos = {"", "lá", "la", "aí", "ai", "ali", "there", "here", "esse", "essa",
                 "nesse", "nessa", "aquele", "aquela", "esse lugar", "essa lugar",
                 "esse restaurante", "esse local", "nele", "nela", "pra lá", "pra la",
                 "pro lugar", "pro local", "pro restaurante"}
        if dest.lower() in vagos or len(dest) < 3:
            return None  # LLM resolve com contexto da conversa
        modo = _detectar_modo_transporte(msg)
        # Remove texto de transporte do destino
        import re as _re_nav
        dest = _re_nav.sub(r',?\s*(mas\s+)?(eu\s+)?(preciso|quero|vou|gostaria|prefiro)\s+(ir\s+)?(de\s+)?(trem|ônibus|onibus|metrô|metro|bus|bicicleta|bike|a pé|a pe|andando|carro|taxi|uber).*', '', dest, flags=_re_nav.IGNORECASE).strip()
        dest = _re_nav.sub(r'\s+(de\s+)?(trem|ônibus|onibus|metrô|metro|bus|bicicleta|bike|a pé|a pe|andando|carro|taxi|uber)\s*$', '', dest, flags=_re_nav.IGNORECASE).strip()
        dest = dest.rstrip(' ,.')
        result = {"ferramenta": "maps_navigate", "destino": dest}
        if modo:
            result["modo"] = modo
        return result

    # ── PASSAGEM AÉREA e HOTEL — v4-pro parseia melhor (antes de maps_search!)
    # MAS: se tem "perto de mim" / "nearby", é busca local, não reserva
    flight_kw = ["passagem", "passagens", "voo ", "voar ", "flight", "aérea", "aerea", "avião", "aviao"]
    hotel_kw = ["hotel ", "hotéis", "hoteis", "hospedagem", "pousada", "hostel", "onde ficar", "reservar quarto"]
    local_indicadores = ["perto", "próximo", "proximo", "nearby", "near me", "aqui", "perto de mim", "por perto"]
    eh_busca_local = any(k in msg for k in local_indicadores)
    if not eh_busca_local and (any(k in msg for k in flight_kw) or any(k in msg for k in hotel_kw)):
        return None  # v4-pro extrai origem, destino, IATA, datas

    # ── BUSCA LOCAL ──
    local_kw = ["perto de mim", "perto daqui", "aqui perto", "por perto", "próximo",
                "proximo", "nearby", "near me", "近くの"]
    place_kw = ["restaurante", "restaurant", "lanchonete", "padaria", "mercado",
                "supermercado", "farmácia", "farmacia", "hospital", "posto", "shopping",
                "hotel", "bar", "café", "cafe", "loja", "banco", "cabeleireiro",
                "barbeiro", "academia", "dentista", "médico", "medico", "mecânico",
                "mecanico", "acha ", "encontra ", "busca ", "procura ", "where is",
                "レストラン", "コンビニ"]
    # Tipos de lugar conhecidos — SÓ ativa busca se tiver um destes
    _place_types = {
        "restaurante":"restaurant","restaurant":"restaurant","churrascaria":"steakhouse",
        "pizzaria":"pizzeria","hamburgueria":"burger place","lanchonete":"snack bar",
        "padaria":"bakery","sorveteria":"ice cream","açougue":"butcher",
        "posto de combustível":"gas station","posto de gasolina":"gas station","posto":"gas station",
        "farmácia":"pharmacy","farmacia":"pharmacy","mercado":"supermarket",
        "supermercado":"supermarket","hospital":"hospital","shopping":"shopping mall",
        "academia":"gym","dentista":"dentist","médico":"doctor","medico":"doctor",
        "mecânico":"mechanic","mecanico":"mechanic","cabeleireiro":"hair salon",
        "barbeiro":"barber","banco":"bank","loja":"store","bar":"bar","pub":"pub",
        "café":"cafe","cafe":"cafe","hotel":"hotel","pousada":"inn","hostel":"hostel",
        "igreja":"church","escola":"school","estacionamento":"parking","oficina":"auto repair",
        "veterinário":"vet","veterinario":"vet","pet shop":"pet shop","livraria":"bookstore",
        "lavanderia":"laundry","correio":"post office","delegacia":"police station",
        "conveniência":"convenience store","conveniencia":"convenience store",
        "レストラン":"restaurant","コンビニ":"convenience store","ガソリンスタンド":"gas station"
    }
    # Acha tipo de lugar mencionado
    found_type = None
    found_en = None
    for pt, en in sorted(_place_types.items(), key=lambda x: -len(x[0])):
        if pt in msg:
            found_type = pt
            found_en = en
            break
    if found_type and (any(k in msg for k in local_kw) or any(k in msg for k in ["acha","ache","encontra","encontre","busca","busque","procura","procure","tem ","onde","qual","cadê","cade"])):
        # Extrai adjetivo/tipo (ex: "restaurante indiano" → "indian restaurant")
        import re as _re
        # Pega palavra depois do tipo (ex: "brasileiro", "indiano", "japonês")
        adj_match = _re.search(found_type + r'\s+(\w+)', msg)
        adj = adj_match.group(1) if adj_match else ""
        # Traduz adjetivos comuns
        _adj_trad = {"brasileiro":"brazilian","indiano":"indian","japonês":"japanese","japones":"japanese",
                     "italiano":"italian","chinês":"chinese","chines":"chinese","mexicano":"mexican",
                     "coreano":"korean","tailandês":"thai","tailandes":"thai","árabe":"arabic",
                     "arabe":"arabic","peruano":"peruvian","francês":"french","frances":"french",
                     "americano":"american","vegano":"vegan","vegetariano":"vegetarian"}
        _ignore = ["aqui","perto","de","do","da","em","no","na","um","uma","mim","me","mais",
                   "pra","pro","por","vez","pertinho","proximo","próximo","la","lá","outro","outra"]
        if adj.lower() in _ignore:
            adj = ""
        adj_en = _adj_trad.get(adj.lower(), adj) if adj else ""
        query_pt = f"{found_type} {adj}".strip() if adj else found_type
        query_en = f"{adj_en} {found_en}".strip() if adj_en else found_en
        return {"ferramenta": "maps_search", "query": query_pt, "query_en": query_en}

    # ── CLIMA ──
    clima_kw = ["clima", "tempo", "previsão", "previsao", "temperatura", "chuva",
                "chover", "vai chover", "tá frio", "ta frio", "tá calor", "ta calor",
                "weather", "forecast", "天気"]
    if any(k in msg for k in clima_kw):
        return {"ferramenta": "weather"}

    # ── TELEFONE / WHATSAPP ──
    phone_kw = ["liga pra ", "liga pro ", "liga para ", "ligar pra ", "ligar para ",
                "manda mensagem", "manda msg", "chama ", "whatsapp", "call ",
                "電話して"]
    if any(k in msg for k in phone_kw):
        contato = msg
        for k in phone_kw:
            if k in contato:
                contato = contato.split(k, 1)[-1].strip()
                break
        return {"ferramenta": "phone_call", "contato": contato.rstrip('.!? ')}

    # ── AGENDA / LEMBRETE ──
    agenda_kw = ["me lembra", "lembra de ", "lembrete", "agenda ", "agendar",
                 "remind me", "reminder", "depois de ", "after ",
                 "リマインド", "思い出させて"]
    time_ctx = ["hora", "horas", "minuto", "minutos", "min", "amanhã", "amanha",
                "depois", "daqui", "às ", "as ", "tomorrow", "later", "minute", "minutes",
                "hour", "hours", "second", "seconds", "from now", "in ", "after ",
                "時", "分", "明日"]
    # Detecta tempo por padrão numérico também (22:13, 18h, 9h30)
    import re as _re_agenda
    tem_padrao_tempo = bool(_re_agenda.search(r'\b\d{1,2}[h:]\d{0,2}\b', msg))
    if any(k in msg for k in agenda_kw) and (any(t in msg for t in time_ctx) or tem_padrao_tempo):
        # Parseia tempo no Python — NUNCA delega ao LLM
        import re as _re
        tempo = _parsear_tempo(msg, hora_local)
        # Limpa titulo — remove prefixos de comando e referências de tempo
        titulo = msg
        for k in ["me lembra de ", "me lembra ", "lembra de ", "remind me to ", "remind me ",
                   "depois de ", "lembrete ", "agenda ", "agendar "]:
            if k in titulo:
                titulo = titulo.split(k, 1)[-1].strip()
                break
        # Remove referências de tempo do título
        titulo = _re.sub(r'(daqui|depois de|às|as|amanhã|amanha|tomorrow|at)\s+\d.*', '', titulo).strip()
        titulo = _re.sub(r'\b\d{1,2}h\d{0,2}\b', '', titulo).strip()
        titulo = _re.sub(r'\b\d{1,2}:\d{2}\b', '', titulo).strip()
        titulo = titulo.rstrip(' ,.')
        if not titulo:
            titulo = msg  # fallback: usa mensagem original
        return {"ferramenta": "agenda_add", "titulo": titulo, "descricao": "",
                "data_hora": tempo.get("data_hora_iso", ""),
                "minutos_relativos": tempo.get("minutos_relativos", 0)}
    return None

def detectar_intencao(mensagem: str, historico: list = None, perfil: dict = None, hora_local: str = '') -> dict:
    """
    Chamada rápida ao DeepSeek para detectar intenção e extrair parâmetros.
    Usa perfil do usuário para personalizar a query.
    """
    contexto = ""
    if historico:
        ultimas = historico[-3:]
        for item in ultimas:
            contexto += f"Usuário: {item['user']}\nAssistente: {item['assistant']}\n"

    # Preferências do usuário para personalizar queries
    preferencias = ""
    if perfil:
        musica = perfil.get("musica", "")
        comida = perfil.get("comida", "")
        hobbies = perfil.get("hobbies", "")
        if musica: preferencias += f"- Música favorita: {musica}\n"
        if comida: preferencias += f"- Comida favorita: {comida}\n"
        if hobbies: preferencias += f"- Hobbies: {hobbies}\n"

    data_hoje = datetime.now().strftime("%Y-%m-%d")
    hora_info = f"\nHora local do usuário: {hora_local}" if hora_local else ""
    prompt = f"""Analise a mensagem e retorne um JSON se ela pede uma ação específica.
Data atual: {data_hoje}{hora_info}
{f'Histórico recente:{chr(10)}{contexto}' if contexto else ''}
{f'Preferências do usuário:{chr(10)}{preferencias}' if preferencias else ''}
Mensagem atual: "{mensagem}"

Retorne APENAS um JSON válido se a mensagem pede:
- Navegar/ir para algum lugar: {{"ferramenta":"maps_navigate","destino":"nome do lugar","modo":"driving|transit|walking|bicycling"}}
  → modo é opcional. Use "transit" se o usuário mencionar ônibus/metrô/trem, "walking" se a pé, "bicycling" se bicicleta. Se não mencionar, omita o campo.
- Buscar lugar próximo: {{"ferramenta":"maps_search","query":"tipo específico de lugar"}}
- Tocar música: {{"ferramenta":"spotify_play","query":"APENAS gênero, artista ou música específica"}}
- Tocar no SoundCloud: {{"ferramenta":"soundcloud_play","query":"artista ou gênero"}}
- Buscar vídeo: {{"ferramenta":"youtube_search","query":"tema do vídeo"}}
- Ligar/WhatsApp: {{"ferramenta":"phone_call","contato":"nome COMPLETO ou número"}}
- Clima/tempo/previsão: {{"ferramenta":"weather"}}
→ Use para QUALQUER pergunta sobre clima, tempo, chuva, temperatura, previsão, calor, frio
- Pesquisa na internet: {{"ferramenta":"web_search","query":"termo de busca"}}
- Agenda/lembrete: {{"ferramenta":"agenda_add","titulo":"...","descricao":"...","data_hora":"YYYY-MM-DDTHH:MM:SS (horário REAL, não este texto)","minutos_relativos":0}}
→ minutos_relativos: OBRIGATÓRIO! "daqui 5 min"=5, "daqui 2 horas"=120, "daqui 1h30"=90. Horário fixo=0.
→ Use para: "me lembra de", "agenda", "lembrete", "daqui X minutos", "às X horas"
→ NUNCA use web_search para lembretes/agenda
- Casa inteligente AGORA: {{"ferramenta":"smart_home","acao":"ligar|desligar|ajustar","dispositivo":"nome do dispositivo"}}
- Casa inteligente AGENDADA (com horário futuro): {{"ferramenta":"smart_home_agendado","acao":"ligar|desligar|ajustar","dispositivo":"nome","valor":"","data_hora":"YYYY-MM-DDTHH:MM:SS (horário REAL, não este texto)","minutos_relativos":0}}
→ Use quando houver horário: "liga o ar às 18h", "desliga a luz daqui 2 horas", "liga o ar quando eu chegar às 19h"
→ minutos_relativos igual à agenda: "daqui 2 horas"=120; horário fixo=0
- Hotel/hospedagem: {{"ferramenta":"hotel_search","destino":"cidade ou local","checkin":"YYYY-MM-DD ou vazio","checkout":"YYYY-MM-DD ou vazio"}}
- Passagem aérea/voo: {{"ferramenta":"flight_search","origem":"cidade origem ou vazio","destino":"cidade destino","origem_iata":"código IATA 3 letras","destino_iata":"código IATA 3 letras","data_ida":"YYYY-MM-DD ou vazio","data_volta":"YYYY-MM-DD ou vazio"}}

REGRA CRÍTICA — Use web_search para QUALQUER pergunta sobre fatos do mundo real:
- Notícias, eventos recentes
- Preços, cotações, valores
- Resultados de jogos, competições
- Informações sobre pessoas, lugares, empresas
- Qualquer coisa que possa ter mudado recentemente

NÃO use web_search para:
- Conversas pessoais ("como você está?", "me conta uma piada")
- Perguntas sobre preferências pessoais
- Pedidos de opinião
- Comandos para apps (música, maps, etc)
- Hotéis ou hospedagem → use hotel_search
- Passagens aéreas ou voos → use flight_search

REGRAS para música: use preferências do usuário se não especificou.

Exemplos:
"toca uma música" → {{"ferramenta":"spotify_play","query":"sertanejo"}}
"liga o ar" → {{"ferramenta":"smart_home","acao":"ligar","dispositivo":"ar"}}
"vai chover hoje?" → {{"ferramenta":"weather"}}
"que calor é esse?" → {{"ferramenta":"weather"}}
"qual a cotação do dólar?" → {{"ferramenta":"web_search","query":"cotação dólar hoje"}}
"quem é o presidente do brasil?" → {{"ferramenta":"web_search","query":"presidente do Brasil"}}
"qual o resultado do jogo?" → {{"ferramenta":"web_search","query":"resultado jogo hoje"}}
"procura hotel em Tokyo em junho" → {{"ferramenta":"hotel_search","destino":"Tokyo","checkin":"2025-06-01","checkout":"2025-06-05"}}
"quero passagem de São Paulo para Tokyo" → {{"ferramenta":"flight_search","origem":"São Paulo","destino":"Tokyo","origem_iata":"GRU","destino_iata":"NRT","data_ida":"","data_volta":""}}
"me conta uma piada" → null
"oi tudo bem?" → null
"o que você acha de..." → null

Se o histórico mostra que o assistente sugeriu um lugar e perguntou se quer a rota, e o usuário responde afirmativamente ("sim", "vai", "pode ir", "quero", "leva lá", "bora"), retorne maps_navigate com o destino. Se no histórico houver [DESTINO_EXATO], use esse endereço completo como destino — não o nome genérico.

Retorne APENAS o JSON ou null."""

    try:
        resultado = chamar_deepseek_simples(prompt, max_tokens=500, modelo="deepseek-v4-pro")
        if not resultado or resultado.strip().lower() == 'null':
            return None
        resultado = re.sub(r'```(?:json)?\s*', '', resultado).strip()
        return json.loads(resultado)
    except:
        return None

def extrair_onboarding_completo(texto):
    # Remove blocos markdown (```json ... ```) antes de procurar o JSON
    texto_limpo = re.sub(r'```(?:json)?\s*', '', texto)
    match = re.search(r'ONBOARDING_COMPLETO:\s*(\{.+?\})', texto_limpo, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    return None

def _detectar_idioma(msg: str) -> str:
    """Detecta idioma da mensagem por caracteres e palavras comuns. Retorna código ou ''."""
    import re as _re_id
    if not msg or len(msg.strip()) < 3:
        return ""
    texto = msg.strip()

    # Japonês: hiragana, katakana, kanji
    jp_chars = sum(1 for ch in texto if '\u3040' <= ch <= '\u309f' or '\u30a0' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff')
    if jp_chars >= 2 or jp_chars / max(len(texto), 1) > 0.3:
        return "Japanese"

    # Coreano: hangul
    ko_chars = sum(1 for ch in texto if '\uac00' <= ch <= '\ud7af' or '\u1100' <= ch <= '\u11ff')
    if ko_chars >= 2:
        return "Korean"

    # Chinês simplificado (sem hiragana/katakana = não é japonês)
    cn_chars = sum(1 for ch in texto if '\u4e00' <= ch <= '\u9fff')
    if cn_chars >= 3 and jp_chars == cn_chars:
        return "Chinese"

    # Limpa pontuação e expande contrações antes de detectar
    limpo = texto.lower()
    limpo = _re_id.sub(r"n't\b", " not", limpo)
    limpo = _re_id.sub(r"'s\b", " is", limpo)
    limpo = _re_id.sub(r"'re\b", " are", limpo)
    limpo = _re_id.sub(r"'m\b", " am", limpo)
    limpo = _re_id.sub(r"'ll\b", " will", limpo)
    limpo = _re_id.sub(r"'ve\b", " have", limpo)
    limpo = _re_id.sub(r"'d\b", " would", limpo)
    limpo = _re_id.sub(r"[^a-záàâãéèêíïóôõúüñçäëïöü\s]", " ", limpo)
    palavras = limpo.split()
    if len(palavras) < 2:
        return ""

    en_words = {"the", "is", "are", "am", "was", "were", "what", "how", "why", "where", "when",
                "can", "could", "would", "should", "have", "has", "do", "does", "did", "not",
                "this", "that", "with", "from", "for", "but", "and", "you", "your", "my", "me",
                "will", "about", "just", "please", "help", "want", "need", "know", "think",
                "good", "going", "turn", "off", "on", "set", "remind", "tell", "show", "find",
                "like", "today", "tomorrow", "weather", "time", "here", "there", "it", "in",
                "so", "if", "up", "out", "get", "got", "go", "come", "make", "take", "see",
                "look", "give", "use", "new", "now", "way", "day", "too", "any", "all", "much",
                "hi", "hello", "hey", "thanks", "thank", "yes", "no", "ok", "sure", "right"}
    es_words = {"el", "la", "los", "las", "es", "son", "está", "están", "qué", "cómo",
                "dónde", "cuándo", "por", "para", "pero", "también", "puede", "quiero",
                "tengo", "hacer", "este", "esta", "muy", "bien", "hola", "gracias",
                "yo", "tu", "como", "donde", "cuando", "más", "todo", "aquí", "hay"}
    fr_words = {"le", "la", "les", "est", "sont", "avec", "dans", "pour", "mais", "aussi",
                "je", "tu", "nous", "vous", "ils", "elles", "cette", "ces", "très",
                "bien", "merci", "bonjour", "comment", "pourquoi", "quand", "faire",
                "ne", "pas", "oui", "non", "ici", "qui", "que", "où"}

    set_palavras = set(palavras)
    en_count = len(set_palavras & en_words)
    es_count = len(set_palavras & es_words)
    fr_count = len(set_palavras & fr_words)

    # Pega o maior score
    melhor = max(en_count, es_count, fr_count)
    if melhor < 1:
        return ""
    total = len(palavras)
    ratio = melhor / total

    # Frases curtas (2-4 palavras): basta 1 match com ratio >= 0.25
    if total <= 4 and melhor >= 1 and ratio >= 0.25:
        if en_count == melhor: return "English"
        if es_count == melhor: return "Spanish"
        if fr_count == melhor: return "French"

    # Frases normais: 2+ matches
    if melhor >= 2 and ratio >= 0.15:
        if en_count == melhor: return "English"
        if es_count == melhor: return "Spanish"
        if fr_count == melhor: return "French"

    return ""


def processar_mensagem(user_id, mensagem, latitude=None, longitude=None, hora_local="", imagem_base64="", idioma_falado=""):
    config = banco.buscar_config(user_id)
    perfil = banco.buscar_perfil(user_id)

    # ── ONBOARDING ─────────────────────────────────────────────────────────────
    if not config.get("onboarding_completo"):
        historico = sessoes.get_historico(user_id)
        resposta = chamar_deepseek(SYSTEM_ONBOARDING, mensagem, historico, max_tokens=300)
        dados = extrair_onboarding_completo(resposta)
        if dados:
            banco.salvar_perfil(user_id, dados)
            banco.salvar_config(user_id, {
                "nome_assistente":     dados.get("nome_assistente", "Margo"),
                "genero":              dados.get("genero", "F"),
                "personalidade":       dados.get("personalidade", ""),
                "onboarding_completo": True
            })
            resposta = re.sub(r'ONBOARDING_COMPLETO:\{.+?\}', '', resposta).strip()
            log(f"Onboarding concluído para user {user_id}", "onboarding")
        sessoes.adicionar(user_id, mensagem, resposta)
        return {"resposta": limpar_resposta(resposta), "onboarding": not dados, "ferramenta": None}

    # ── MODO TRADUTOR ──────────────────────────────────────────────────────────
    trad = tradutor_get(user_id)

    # Aguardando idiomas após pedido de ativação
    if trad.get("aguardando"):
        idiomas = chamar_deepseek_simples(
            f'Extraia os dois idiomas desta frase e responda APENAS JSON: '
            f'{{"origem": "idioma1", "destino": "idioma2"}}\n'
            f'Frase: {mensagem}',
            max_tokens=40
        )
        try:
            dados_trad = json.loads(idiomas.replace("```json","").replace("```","").strip())
            orig = dados_trad.get("origem", "português")
            dest = dados_trad.get("destino", "inglês")
            _tradutor_estado[user_id] = {"ativo": True, "origem": orig, "destino": dest, "aguardando": False}
            resposta = f"Modo tradutor ativado! Traduzindo de {orig} para {dest}. Pode falar!"
        except:
            resposta = "Não entendi os idiomas. Pode repetir? Ex: português e inglês"
        sessoes.adicionar(user_id, mensagem, resposta)
        return {"resposta": resposta, "onboarding": False, "ferramenta": None}

    # Detecta pedido de ativar/desativar tradutor
    intencao_trad = detectar_intencao_tradutor(mensagem)
    if intencao_trad == "desativar":
        tradutor_desativar(user_id)
        return {"resposta": "Modo tradutor desativado.", "onboarding": False, "ferramenta": None}
    if intencao_trad == "ativar":
        _tradutor_estado[user_id] = {"ativo": False, "origem": "", "destino": "", "aguardando": True}
        return {"resposta": "Claro! Quais idiomas você quer traduzir?", "onboarding": False, "ferramenta": None}

    # Modo tradutor ativo — traduz a mensagem
    if trad.get("ativo"):
        traducao = traduzir_texto(mensagem, trad["origem"], trad["destino"])
        sessoes.adicionar(user_id, mensagem, traducao)
        return {"resposta": traducao, "onboarding": False, "ferramenta": None}

    # ── MODO NORMAL ────────────────────────────────────────────────────────────
    historico = sessoes.get_historico(user_id)
    # Memória estendida (resumos de sessões anteriores) — só premium, tester e admin
    PLANOS_MEMORIA = ("premium", "tester", "admin")
    _usr = banco.buscar_usuario_por_id(user_id)
    _plano_user = (_usr.get("plano", "free") if _usr else "free")
    resumos = banco.buscar_resumos(user_id) if _plano_user in PLANOS_MEMORIA else []
    lembretes = banco.lembretes_proximos(user_id)

    contexto_extra = ""
    # Idioma será adicionado no FINAL do system prompt (última instrução = mais peso)
    if hora_local:
        contexto_extra += f"\nHora e data atual do usuário: {hora_local} — CRÍTICO: Use EXATAMENTE este horário como base para calcular agendamentos. Se o usuário pedir 'daqui X minutos', some X minutos ao horário acima e use como data_hora no ISO8601. NÃO use horário UTC nem fuso diferente."
    if latitude and longitude:
        contexto_extra += f"\nLocalização atual do usuário: lat={latitude}, lng={longitude} — use isso quando relevante para Maps, restaurantes, rotas."
    if resumos:
        contexto_extra += "\nConversas anteriores:\n" + "\n".join(f"- {r}" for r in resumos)
    if lembretes:
        for l in lembretes:
            contexto_extra += f"\n[LEMBRETE AGORA] {l['titulo']} — {l['tipo']}"

    system = build_system_prompt(perfil, config)
    if contexto_extra:
        system += f"\n\n{contexto_extra}"
    # Instrução de idioma vai por ÚLTIMO no system prompt (máxima prioridade pro modelo)
    if idioma_falado and idioma_falado.lower() not in ("portuguese", "pt", "pt-br"):
        # STT detectou idioma específico — força esse idioma
        system += f"\n\n=== MANDATORY LANGUAGE RULE ===\nThe user spoke in {idioma_falado}. You MUST respond ENTIRELY in {idioma_falado}. Do NOT translate their message. Do NOT respond in Portuguese. Reply naturally in {idioma_falado} as if it were your native language."
        # [Respond in X] removido — MANDATORY LANGUAGE RULE no system prompt já cobre
    else:
        # Sem STT — manda regra genérica forte pra detectar e espelhar o idioma
        system += "\n\n=== MANDATORY LANGUAGE RULE ===\nDetect the language of the user\'s CURRENT message. You MUST respond ENTIRELY in that SAME language. If the user writes in English, respond in English. If Japanese, respond in Japanese. If Spanish, respond in Spanish. NEVER default to Portuguese unless the user wrote in Portuguese. Match the user\'s language exactly."

    import time as _t
    _t0 = _t.time()
    # Bypass: mensagens triviais/curtas de conversa não precisam de detecção de intenção
    msg_trivial = mensagem.lower().strip().rstrip('!?.')
    triviais = ("oi", "ola", "olá", "hey", "hi", "hello", "bom dia", "boa tarde", "boa noite",
                "tudo bem", "como vai", "obrigado", "obrigada", "valeu",
                "haha", "kkk", "kkkk", "rs", "legal", "show", "beleza", "blz", "entendi", "certo")
    if msg_trivial in triviais:
        ferramenta = None
    else:
        # Pré-detecção por keywords (DeepSeek v4-flash falha em chamar ferramentas)
        msg_low = mensagem.lower().strip()
        ferramenta = _pre_detectar(msg_low, hora_local=hora_local)
        if ferramenta:
            log(f"Pré-detectado: {ferramenta.get('ferramenta')} via keywords", "intent")
        else:
            ferramenta = detectar_intencao(mensagem, historico, perfil=perfil, hora_local=hora_local)

    # ── BUSCA AUTOMÁTICA para perguntas que precisam de dados atuais ──────────
    palavras_busca_auto = ["tempo", "clima", "chuva", "previsao", "previsão", "temperatura",
                           "noticia", "notícia", "hoje", "agora", "cotação", "cotacao",
                           "dolar", "dólar", "euro", "bitcoin", "resultado", "placar"]
    if not ferramenta and BRAVE_API_KEY and any(p in mensagem.lower() for p in palavras_busca_auto):
        ferramenta = {"ferramenta": "web_search", "query": mensagem}
        log(f"Busca automática ativada: {mensagem}", "busca")

    # ── WEB SEARCH: busca antes de gerar resposta ─────────────────────────────
    contexto_busca = ""
    if ferramenta and ferramenta.get("ferramenta") == "web_search" and BRAVE_API_KEY:
        query = ferramenta.get("query", mensagem)
        # Enriquece query com localização quando relevante
        palavras_locais = ["tempo", "clima", "chuva", "temperatura", "previsao", "previsão", "calor", "frio", "sol", "perto", "aqui", "hoje", "agora"]
        if any(p in query.lower() for p in palavras_locais):
            if latitude and longitude:
                # Tem GPS — busca cidade real
                try:
                    geo_url = f"https://nominatim.openstreetmap.org/reverse?lat={latitude}&lon={longitude}&format=json"
                    geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "MargoApp/1.0"})
                    geo_resp = urllib.request.urlopen(geo_req, timeout=5)
                    geo_data = json.loads(geo_resp.read())
                    addr = geo_data.get("address", {})
                    cidade = addr.get("city") or addr.get("town") or addr.get("village") or ""
                    if cidade and cidade.lower() not in query.lower():
                        query = f"{query} em {cidade}"
                except:
                    pass
            # Se a cidade não está na query ainda, mantém como está (usuário pode ter mencionado a cidade)
        log(f"Brave Search: {query}", "busca")
        resultados = buscar_brave(query)
        if resultados:
            contexto_busca = f"\n\n[DADOS REAIS DA INTERNET - USE ESTES VALORES EXATOS]:\n{resultados}\n[FIM DOS DADOS]\nIMPORTANTE: Use os valores numéricos exatos acima na sua resposta. Não invente valores. Fale com sua personalidade mas cite os números corretos.\nLINKS: Se o usuário pediu um link ou site, inclua a URL COMPLETA começando com https:// no FINAL da mensagem, sozinha em linha separada. NUNCA soletre ou cite a URL no meio do texto falado — o texto deve fazer sentido sem a URL.\nExemplo ERRADO: O site oficial é mazda.com, dá uma olhada lá!\nExemplo CERTO: Achei o site oficial da Mazda pra você, tá aqui embaixo!\nhttps://www.mazda.com"
        else:
            log(f"Brave Search sem resultado para: {query}", "busca")
            contexto_busca = f"\n\nNão encontrei resultados específicos. Responda com o que sabe, mas seja honesto sobre limitações."

    # ── MAPS SEARCH: busca lugar específico antes de abrir ────────────────────
    # ── CLIMA: Open-Meteo com coordenadas do dispositivo ──────────────────────
    if ferramenta and ferramenta.get("ferramenta") == "weather" and latitude and longitude:
        log(f"Open-Meteo: lat={latitude} lng={longitude}", "clima")
        dados_clima = buscar_open_meteo(latitude, longitude)
        if dados_clima:
            contexto_busca += f"""

[DADOS DE CLIMA REAIS — USE ESTES VALORES EXATOS]:
{dados_clima}
[FIM DOS DADOS]
IMPORTANTE: Use os valores exatos acima. Responda de forma natural sobre o clima, mencionando o que for relevante para a pergunta do usuário. Não invente valores."""
        else:
            contexto_busca += "\n\nNão consegui obter dados de clima no momento. Seja honesto sobre isso."
        # Weather não abre nada no app — só responde
        ferramenta = None

    if ferramenta and ferramenta.get("ferramenta") == "maps_search" and BRAVE_API_KEY:
        if not latitude or not longitude:
            log(f"maps_search SEM GPS — lat={latitude} lng={longitude}", "busca")
            # Tenta sem localização (busca genérica)
            latitude = latitude or 0
            longitude = longitude or 0
        query_maps = ferramenta.get("query", "")
        
        # LIMPA A QUERY FORTE: remove tudo que não é parte da busca
        import re as _re3
        # SE FOR FRASE LONGA (> 30 chars) com conversa, extrai só as primeiras palavras-chave
        if len(query_maps) > 30:
            # Tenta extrair o tipo de lugar (restaurante, mercado, farmácia, etc.)
            tipos = ['restaurante', 'restaurant', 'lanchonete', 'padaria', 'mercado', 'supermercado', 
                     'farmácia', 'farmacia', 'hospital', 'posto', 'shopping', 'hotel', 'bar', 'café', 'cafe',
                     'loja', 'banco', 'academia', 'dentista', 'médico', 'medico', 'mecânico', 'mecanico']
            for t in tipos:
                if t in query_maps.lower():
                    # Pega o tipo + palavra seguinte (ex: "indiano", "japonês")
                    palavras = query_maps.lower().split()
                    idx = palavras.index(t)
                    complemento = palavras[idx+1] if idx+1 < len(palavras) and len(palavras[idx+1]) < 20 else ""
                    query_maps = f"{t} {complemento}".strip()
                    break
        
        # Remove palavras no início: por, para, um, uma, o, a, de, etc.
        query_maps = _re3.sub(r'^(por|para|pra|pro|um|uma|uns|umas|o|a|os|as|de|da|do|das|dos|pra|pro|pelo|pela|no|na|nos|nas)\s+', '', query_maps, flags=_re3.IGNORECASE)
        # Remove palavras no meio: perto de mim, aqui perto, etc.
        query_maps = _re3.sub(r'\s*(perto de mim|aqui perto|por perto|near me|nearby|perto daqui|aqui do lado)\s*', ' ', query_maps, flags=_re3.IGNORECASE)
        # Remove artigos soltos no meio: um, uma, o, a, os, as
        query_maps = _re3.sub(r'\s+(um|uma|uns|umas|o|a|os|as)\s+', ' ', query_maps, flags=_re3.IGNORECASE)
        # Remove ruído conversacional: "bom", "que seja", "mais", "legal", etc.
        query_maps = _re3.sub(r'\b(bom|boa|que seja|legal|bacana|barato|caro|melhor|mais|muito|bem|algum|alguma|qualquer)\b', '', query_maps, flags=_re3.IGNORECASE)
        query_maps = _re3.sub(r'\s+', ' ', query_maps).strip()
        
        # Busca cidade via geocoding reverso gratuito
        cidade = ""
        try:
            geo_url = f"https://nominatim.openstreetmap.org/reverse?lat={latitude}&lon={longitude}&format=json&accept-language=en"
            geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "MargoApp/1.0"})
            geo_resp = urllib.request.urlopen(geo_req, timeout=5)
            geo_data = json.loads(geo_resp.read())
            addr = geo_data.get("address", {})
            cidade = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or ""
            pais = addr.get("country", "")
            if cidade and pais:
                cidade = f"{cidade}, {pais}"
        except:
            pass

        # Traduz query pra língua local do país (DeepSeek flash, ~5 tokens)
        import re as _re2
        q_limpo = _re2.sub(r'(mais uma vez|de novo|novamente|outra vez|again|please|por favor|então|entao|margo|margô)', '', query_maps, flags=_re2.IGNORECASE).strip()
        q_limpo = q_limpo.strip(' ,.') or query_maps
        pais = cidade.split(", ")[-1] if ", " in (cidade or "") else ""
        # Traduz pra inglês se fora de países lusófonos (Brave funciona melhor em EN)
        paises_pt = ["Brazil", "Brasil", "Portugal"]
        if pais and not any(p.lower() in pais.lower() for p in paises_pt):
            try:
                trad = chamar_deepseek_simples(
                    f"Translate to English (ONLY the translation, nothing else): {q_limpo}",
                    max_tokens=30, modelo="deepseek-v4-flash"
                )
                trad = trad.strip().strip('"').strip("'")
                if trad and len(trad) < 80:
                    log(f"Query traduzida: '{q_limpo}' → '{trad}'", "busca")
                    q_limpo = trad
            except Exception as trad_err:
                log(f"Erro traduzindo query: {trad_err}", "busca")
        # Usa query_en (já traduzida pelo _pre_detectar) fora do Brasil/Portugal
        paises_pt = ["Brazil", "Brasil", "Portugal"]
        query_en = ferramenta.get("query_en", "")
        if query_en and pais and not any(p.lower() in pais.lower() for p in paises_pt):
            q_limpo = query_en
            log(f"Usando query_en: '{q_limpo}'", "busca")
        query_busca = f"{q_limpo} {cidade}" if cidade else q_limpo
        
        log(f"Brave Maps Search: query='{query_busca}' lat={latitude} lng={longitude} cidade={cidade}", "busca")
        resultados_maps = buscar_brave(query_busca, max_results=5)
        if resultados_maps:
            # Extrai o melhor lugar para eventual navegação
            prompt_lugar = f"""O usuário está em {cidade or 'localização desconhecida'} e quer: "{query_maps}"
Resultados da busca:
{resultados_maps}

Retorne APENAS um JSON com o melhor resultado dos dados acima (NUNCA invente):
{{"nome": "nome do lugar", "endereco": "endereço completo com cidade e país", "query": "nome do lugar, endereço completo"}}
Use SOMENTE informações que aparecem nos resultados acima. Se nenhum resultado tem endereço, retorne {{"nome":"","endereco":"","query":""}}"""
            try:
                resultado_lugar = chamar_deepseek_simples(prompt_lugar, max_tokens=120, modelo="deepseek-v4-pro")
                resultado_lugar = re.sub(r'```(?:json)?\s*', '', resultado_lugar).strip()
                lugar = json.loads(resultado_lugar)
                if lugar.get("query"):
                    ferramenta["query"] = lugar["query"]
                    nome_lugar = lugar.get("nome", query_maps)
                    endereco_lugar = lugar.get("endereco", "")
                else:
                    nome_lugar = query_maps
                    endereco_lugar = ""
            except:
                nome_lugar = query_maps
                endereco_lugar = ""

            # Guarda endereço exato no contexto para o maps_navigate usar depois
            if endereco_lugar:
                contexto_busca += f"\n[DESTINO_EXATO para navegação: {nome_lugar} — {endereco_lugar}]" 

            # Injeta resultados no contexto para a Margo responder com dicas
            contexto_busca += f"""

BUSCA LOCAL — O usuário perguntou sobre: "{query_maps}" em {cidade or 'localização atual'}
Resultados encontrados:
{resultados_maps}

INSTRUÇÕES OBRIGATÓRIAS:
- Use SOMENTE os resultados acima. NUNCA invente lugares da sua memória.
- Se os resultados não mostram nada na cidade do usuário, diga que não encontrou nada próximo.
- Comente sobre 1 ou 2 lugares DOS RESULTADOS ACIMA com nome e endereço exatos.
- No final, pergunte se o usuário quer a rota até lá.
- Responda no MESMO IDIOMA que o usuário falou.
- NÃO emita JSON de ferramenta agora — a navegação só acontece se o usuário confirmar."""

    # Gera resposta natural
    # Usa vision se tiver imagem
    if imagem_base64:
        resposta = chamar_gemini_vision(system + contexto_busca, mensagem, imagem_base64, max_tokens=800)
    else:
        resposta = chamar_deepseek(system + contexto_busca, mensagem, historico, max_tokens=800)

    # Remove JSON da resposta caso o DeepSeek emita ferramenta em vez de texto
    resposta_limpa = resposta.strip()
    # Remove se a resposta inteira é um JSON de ferramenta
    if resposta_limpa.startswith('{') and '"ferramenta"' in resposta_limpa:
        resposta_limpa = ""
    else:
        resposta_limpa = re.sub(r'\{[^{}]*"ferramenta"[^{}]*\}', '', resposta_limpa).strip()
    if not resposta_limpa:
        # DeepSeek retornou ferramenta — faz nova chamada pedindo resposta em texto
        resposta_limpa = chamar_deepseek(
            system + contexto_busca + "\n\nIMPORTANTE: Responda em texto natural, não em JSON. Não use chaves {} na resposta.",
            mensagem, historico, max_tokens=600
        )
        resposta_limpa = re.sub(r'\{[^{}]*"ferramenta"[^{}]*\}', '', resposta_limpa).strip()
    # Fallback garantido: nunca envia resposta vazia
    if not resposta_limpa or len(resposta_limpa.strip()) < 2:
        # Fallback traduzido pelo idioma do app
        if idioma_falado and 'japanese' in idioma_falado.lower():
            resposta_limpa = 'すみません、よく理解できませんでした。もう一度お願いできますか？'
        elif idioma_falado and idioma_falado.lower() not in ('portuguese', 'pt', 'pt-br', ''):
            resposta_limpa = "Sorry, I didn't quite understand. Could you try again?"
        else:
            resposta_limpa = "Desculpe, não entendi bem. Pode reformular?"

    # ── AGENDA ────────────────────────────────────────────────────────────────
    if ferramenta and ferramenta.get("ferramenta") == "agenda_add":
        data_hora_agenda = ferramenta.get("data_hora", "")
        minutos_relativos = ferramenta.get("minutos_relativos", 0)
        titulo_agenda = ferramenta.get("titulo", "Compromisso")
        descricao_agenda = ferramenta.get("descricao", "")

        # _parsear_tempo já retorna em UTC — só loga
        if data_hora_agenda:
            log(f"Agenda UTC (via _parsear_tempo): {data_hora_agenda}", "agenda")

        # Gera mensagem personalizada da Margo
        nome_usuario = perfil.get("nome", "você")
        nome_assistente = config.get("nome_assistente", "Margo")
        personalidade_config = config.get("personalidade", "")
        try:
            msg_prompt = (
                f"Você é {nome_assistente}, assistente de {nome_usuario}. "
                f"Sua personalidade: {personalidade_config[:100] if personalidade_config else 'prestativa e amigável'}. "
                f"Crie uma mensagem CURTA (máximo 15 palavras) e no seu estilo para lembrar: '{titulo_agenda}'. "
                f"Seja natural e no personagem. Responda APENAS a mensagem, sem explicações."
            )
            msg_personalizada = chamar_deepseek_simples(msg_prompt, max_tokens=50)
            if msg_personalizada:
                descricao_agenda = msg_personalizada.strip()
        except:
            pass

        # Valida data_hora — rejeita templates literais do LLM
        if data_hora_agenda and data_hora_agenda.upper() in ("ISO8601", "YYYY-MM-DDTHH:MM:SS", ""):
            log(f"Lembrete REJEITADO (data_hora é template): {data_hora_agenda}", "agenda")
            data_hora_agenda = ""
        if data_hora_agenda:
            # Verifica se é um ISO válido
            try:
                datetime.fromisoformat(data_hora_agenda)
            except:
                log(f"Lembrete REJEITADO (data_hora inválido): {data_hora_agenda}", "agenda")
                data_hora_agenda = ""
        # SEMPRE usa _parsear_tempo — retorna UTC correto, nunca confia no LLM
        tempo_parsed = _parsear_tempo(mensagem.lower().strip(), hora_local)
        if tempo_parsed.get("data_hora_iso"):
            data_hora_agenda = tempo_parsed["data_hora_iso"]
            log(f"Agenda via _parsear_tempo (UTC): {data_hora_agenda}", "agenda")
        elif data_hora_agenda:
            # _parsear_tempo não achou tempo, mas LLM mandou algo — valida
            if data_hora_agenda.upper() in ("ISO8601", "YYYY-MM-DDTHH:MM:SS", "YYYY-MM-DD", ""):
                log(f"Lembrete data_hora é template: {data_hora_agenda}", "agenda")
                data_hora_agenda = ""
            else:
                try:
                    datetime.fromisoformat(data_hora_agenda)
                    # LLM mandou ISO válido mas pode estar em timezone local — tenta converter
                    if hora_local:
                        try:
                            hl = hora_local.replace("Z", "+00:00")
                            if len(hl) > 5 and hl[-5] in "+-" and ":" not in hl[-5:]:
                                hl = hl[:-2] + ":" + hl[-2:]
                            offset = datetime.fromisoformat(hl).utcoffset()
                            if offset:
                                dt_llm = datetime.fromisoformat(data_hora_agenda)
                                if dt_llm.tzinfo is None:
                                    dt_llm = dt_llm - offset
                                    data_hora_agenda = dt_llm.strftime("%Y-%m-%dT%H:%M:%S")
                                    log(f"Agenda LLM convertido UTC: {data_hora_agenda}", "agenda")
                        except:
                            pass
                except:
                    log(f"Lembrete data_hora inválido: {data_hora_agenda}", "agenda")
                    data_hora_agenda = ""

        if data_hora_agenda:
            log(f"Salvando lembrete: titulo={titulo_agenda} | data_hora={data_hora_agenda} | user={user_id}", 'agenda')
            banco.salvar_lembrete(user_id, titulo_agenda, descricao_agenda, data_hora_agenda)
        else:
            log(f"Lembrete DESCARTADO (sem data_hora): titulo={titulo_agenda} | user={user_id}", 'agenda')
            if not resposta_limpa or len(resposta_limpa) < 5:
                resposta_limpa = f"Não consegui entender o horário do lembrete. Pode repetir? Ex: 'me lembra de {titulo_agenda} daqui 30 minutos' ou 'me lembra às 18h'"

    # ── SMART HOME AGENDADO ────────────────────────────────────────────────────
    if ferramenta and ferramenta.get("ferramenta") == "smart_home_agendado":
        data_hora_sh = ferramenta.get("data_hora", "")
        minutos_rel_sh = ferramenta.get("minutos_relativos", 0)
        if hora_local:
            try:
                hl = hora_local.replace("Z", "+00:00")
                if len(hl) > 5 and hl[-5] in '+-' and ':' not in hl[-5:]:
                    hl = hl[:-2] + ':' + hl[-2:]
                hora_local_dt = datetime.fromisoformat(hl)
                offset = hora_local_dt.utcoffset()
                if minutos_rel_sh and int(minutos_rel_sh) > 0:
                    dt_exato = hora_local_dt + timedelta(minutes=int(minutos_rel_sh))
                    if offset:
                        dt_exato = dt_exato - offset
                    data_hora_sh = dt_exato.strftime("%Y-%m-%dT%H:%M:%S")
                elif data_hora_sh:
                    dt_sh = datetime.fromisoformat(data_hora_sh.replace("Z", ""))
                    if dt_sh.tzinfo is None and offset:
                        dt_sh = dt_sh - offset
                    data_hora_sh = dt_sh.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception as e:
                log(f"Erro fuso smart agendado: {e}", "smart")
        acao_json = json.dumps({
            "acao": ferramenta.get("acao", "ligar"),
            "dispositivo": ferramenta.get("dispositivo", ""),
            "valor": ferramenta.get("valor")
        })
        titulo_sh = f"{ferramenta.get('acao','ligar')} {ferramenta.get('dispositivo','')}"
        if data_hora_sh:
            banco.salvar_lembrete_smart(user_id, titulo_sh, acao_json, data_hora_sh)
            log(f"Smart agendado: {titulo_sh} @ {data_hora_sh} UTC", "smart")
        else:
            log(f"Smart agendado DESCARTADO (sem data_hora): {titulo_sh}", "smart")
            resposta_limpa = f"Não consegui entender o horário. Pode repetir? Ex: 'liga o {ferramenta.get('dispositivo','')} às 18h' ou 'daqui 30 minutos'"

    # ── SMART HOME (SmartThings) ───────────────────────────────────────────────
    if ferramenta and ferramenta.get("ferramenta") == "smart_home":
        resultado_st = st_executar_acao(
            user_id,
            ferramenta.get("acao", "ligar"),
            ferramenta.get("dispositivo", ""),
            ferramenta.get("valor")
        )
        resposta_limpa = resultado_st

    # ── SPOTIFY PLAY ──────────────────────────────────────────────────────────
    if ferramenta and ferramenta.get("ferramenta") == "spotify_play":
        token = spotify_get_token(user_id)
        if token:
            try:
                # Busca URI da música para deeplink direto
                import urllib.parse as urlparse
                search_url = f"https://api.spotify.com/v1/search?q={urlparse.quote(ferramenta.get('query',''))}&type=track&limit=1"
                req = urllib.request.Request(search_url, headers={"Authorization": f"Bearer {token}"})
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
                tracks = data.get("tracks", {}).get("items", [])
                if tracks:
                    ferramenta["spotify_uri"] = tracks[0]["uri"]
                    ferramenta["spotify_id"] = tracks[0]["id"]
                # Tenta tocar via API também
                spotify_play(user_id, ferramenta.get("query", ""))
            except Exception as e:
                log(f"Spotify search erro: {e}", "spotify")

    sessoes.adicionar(user_id, mensagem, resposta_limpa)
    # Injeta data_hora corrigida na ferramenta de agenda
    if ferramenta and ferramenta.get("ferramenta") == "agenda_add" and data_hora_agenda:
        ferramenta = dict(ferramenta)
        ferramenta["data_hora"] = data_hora_agenda
    # Detecta despedida via regex local (rapido, sem chamada de IA)
    try:
        msg_low = mensagem.lower().strip()
        padroes_despedida = (
            "tchau", "xau", "flw", "falou", "valeu", "era isso", "so isso", "só isso",
            "pode fechar", "boa noite", "good night", "bye", "goodbye", "see you",
            "ate mais", "até mais", "ate amanha", "até amanhã", "abraço", "abraco",
            "vou dormir", "fui", "encerrar", "obrigado por hoje", "おやすみ", "またね", "adios", "adiós"
        )
        # Despedida = mensagem CURTA contendo um padrao (evita falso positivo em frases longas)
        encerrar = len(msg_low) <= 40 and any(p in msg_low for p in padroes_despedida)
    except:
        encerrar = False

    return {
        "resposta":        limpar_resposta(resposta_limpa),
        "onboarding":      False,
        "ferramenta":      ferramenta,
        "encerrar_sessao": encerrar
    }

# ── TTS — Fish Audio ───────────────────────────────────────────────────────────

def falar_fishaudio(texto, chave, voz_id, genero="F"):
    """Chama Fish Audio TTS e retorna bytes do áudio"""
    try:
        # Fish Audio usa reference_id para selecionar a voz
        ref_id = voz_id if voz_id else ("1eb9bd65918e40a2a4fd2a2e4a949609" if genero == "F" else "54a5170264694bfc8e9ad98df7bd89c3")
        payload = json.dumps({
            "text": texto,
            "reference_id": ref_id,
            "format": "mp3",
            "mp3_bitrate": 128
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.fish.audio/v1/tts",
            data=payload,
            headers={
                "Authorization": f"Bearer {chave}",
                "Content-Type": "application/json",
                "model": "s2-pro"
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except Exception as e:
        log(f"Fish Audio erro: {e}", "voz")
        return None

# ── TTS — ElevenLabs ──────────────────────────────────────────────────────────

def falar_elevenlabs(texto, chave, voz_id, genero="F"):
    """Chama ElevenLabs TTS e retorna bytes do áudio"""
    try:
        vid = voz_id if voz_id else ("21m00Tcm4TlvDq8ikWAM" if genero == "F" else "TxGEqnHWrfWFTfGW9XjX")
        payload = json.dumps({
            "text": texto,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            data=payload,
            headers={
                "xi-api-key": chave,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg"
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except Exception as e:
        log(f"ElevenLabs erro: {e}", "voz")
        return None

# ── FASTAPI ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Margo Server", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "online", "app": "Margo by Orbiby", "versao": "2.2.0",
            "banco": "postgres" if usar_postgres() else "sqlite",
            "busca": "brave" if BRAVE_API_KEY else "desabilitada"}

@app.get("/smartthings/oauth/authorize")
async def st_oauth_authorize(request: Request):
    """
    Endpoint de autorização OAuth para SmartThings Schema App.
    SmartThings redireciona o usuário aqui para autorizar.
    """
    params = dict(request.query_params)
    redirect_uri = params.get("redirect_uri", "")
    state        = params.get("state", "")
    client_id    = params.get("client_id", "")

    # Gera um código de autorização simples
    import hashlib, time
    code = hashlib.sha256(f"{state}{time.time()}margo".encode()).hexdigest()[:32]

    # Redireciona de volta para o SmartThings com o código
    redirect_url = f"{redirect_uri}?code={code}&state={state}"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=redirect_url)

@app.post("/smartthings/oauth/token")
async def st_oauth_token(request: Request):
    """
    Endpoint de token OAuth para SmartThings Schema App.
    Troca o código por um access token.
    """
    try:
        # Aceita form data ou JSON
        try:
            data = await request.json()
        except:
            body = await request.body()
            import urllib.parse
            data = dict(urllib.parse.parse_qsl(body.decode()))

        # Retorna tokens válidos para o SmartThings
        return JSONResponse({
            "access_token":  "margo-st-access-token",
            "token_type":    "Bearer",
            "expires_in":    86400,
            "refresh_token": "margo-st-refresh-token",
            "scope":         "devices"
        })
    except Exception as e:
        log(f"SmartThings token erro: {e}", "smartthings")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/smartthings/webhook")
async def st_webhook(request: Request):
    """
    Webhook SmartThings Schema App — responde aos eventos da plataforma.
    Handles: PING, DISCOVERY, STATE_REFRESH, COMMAND, GRANT_CALLBACK_ACCESS
    """
    try:
        data = await request.json()
        lifecycle = data.get("lifecycle")
        log(f"SmartThings webhook: {lifecycle}", "smartthings")

        # PING — confirmação de que o endpoint está ativo
        if lifecycle == "PING":
            return JSONResponse({
                "pingData": {
                    "challenge": data.get("pingData", {}).get("challenge", "")
                }
            })

        # GRANT_CALLBACK_ACCESS — SmartThings concede acesso OAuth
        if lifecycle == "GRANT_CALLBACK_ACCESS":
            grant = data.get("grantCallbackData", {})
            installed_app_id = grant.get("installedAppId", "")
            auth_token = grant.get("authToken", "")
            # Salva token para chamar a API do SmartThings
            log(f"SmartThings grant: {installed_app_id}", "smartthings")
            return JSONResponse({"grantCallbackData": {}})

        # DISCOVERY — SmartThings pergunta quais dispositivos virtuais existem
        if lifecycle == "DISCOVERY":
            return JSONResponse({
                "discoveryData": {
                    "devices": []  # Margo não expõe dispositivos, só controla
                }
            })

        # STATE_REFRESH — atualiza estado dos dispositivos
        if lifecycle == "STATE_REFRESH":
            return JSONResponse({"stateRefreshData": {"deviceState": []}})

        # COMMAND — SmartThings envia comando para executar
        if lifecycle == "COMMAND":
            return JSONResponse({"commandData": {}})

        # INTEGRATION_DELETED
        if lifecycle == "INTEGRATION_DELETED":
            return JSONResponse({})

        return JSONResponse({"ok": True})

    except Exception as e:
        log(f"SmartThings webhook erro: {e}", "smartthings")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/spotify/play")
async def spotify_play_endpoint(request: Request):
    """Toca música no Spotify via OAuth"""
    try:
        data    = await request.json()
        user_id = data.get("user_id", "")
        query   = data.get("query", "")
        if not user_id or not query:
            return JSONResponse({"ok": False, "erro": "user_id e query obrigatórios"})
        ok = spotify_play(user_id, query)
        return JSONResponse({"ok": ok})
    except Exception as e:
        log(f"Erro /spotify/play: {e}", "spotify")
        return JSONResponse({"ok": False, "erro": str(e)})

@app.get("/spotify/auth/{user_id}")
def spotify_auth(user_id: str):
    """Gera URL de autorização do Spotify"""
    if not SPOTIFY_CLIENT_ID:
        return JSONResponse({"erro": "Spotify não configurado"}, status_code=500)
    import urllib.parse as urlparse
    params = urlparse.urlencode({
        "client_id":     SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  SPOTIFY_REDIRECT_URI,
        "scope":         "user-read-playback-state user-modify-playback-state streaming user-read-private user-read-email",
        "state":         user_id
    })
    return JSONResponse({"url": f"https://accounts.spotify.com/authorize?{params}"})

@app.get("/spotify/callback")
async def spotify_callback(request: Request):
    """Recebe código OAuth e troca pelo token"""
    params  = dict(request.query_params)
    code    = params.get("code")
    user_id = params.get("state")
    if not code or not user_id:
        return JSONResponse({"erro": "Parâmetros inválidos"}, status_code=400)
    try:
        import base64
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
        body  = f"grant_type=authorization_code&code={code}&redirect_uri={SPOTIFY_REDIRECT_URI}".encode()
        req   = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=body,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type":  "application/x-www-form-urlencoded"
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        expires_at = (datetime.now() + timedelta(seconds=data.get("expires_in", 3600))).isoformat()
        banco.salvar_spotify_token(user_id, data["access_token"], data.get("refresh_token", ""), expires_at)
        log(f"Spotify conectado para {user_id}", "spotify")
        return JSONResponse({"ok": True, "msg": "Spotify conectado! Pode fechar esta janela e voltar ao app."})
    except Exception as e:
        log(f"Spotify callback erro: {e}", "spotify")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/spotify/status/{user_id}")
def spotify_status(user_id: str):
    token_data = banco.buscar_spotify_token(user_id)
    return JSONResponse({"conectado": bool(token_data)})

@app.get("/smartthings/auth/{user_id}")
def st_auth(user_id: str):
    if not ST_CLIENT_ID:
        return JSONResponse({"erro": "SmartThings não configurado"}, status_code=500)
    import urllib.parse as urlparse
    scope = "r:devices:* x:devices:*"
    params = urlparse.urlencode({
        "client_id":     ST_CLIENT_ID,
        "scope":         scope,
        "response_type": "code",
        "redirect_uri":  ST_REDIRECT_URI,
        "state":         user_id
    })
    url = f"https://api.smartthings.com/oauth/authorize?{params}"
    return JSONResponse({"url": url})

@app.get("/smartthings/callback")
async def st_callback(request: Request):
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")
    if not code:
        return JSONResponse({"erro": "Código não recebido"}, status_code=400)
    user_id = state
    usuario = banco.buscar_usuario_por_id(user_id)
    if not usuario:
        return JSONResponse({"erro": "Usuário não encontrado"}, status_code=404)
    import base64
    creds = base64.b64encode(f"{ST_CLIENT_ID}:{ST_CLIENT_SECRET}".encode()).decode()
    body = f"grant_type=authorization_code&code={code}&redirect_uri={ST_REDIRECT_URI}&client_id={ST_CLIENT_ID}".encode()
    req = urllib.request.Request(
        "https://api.smartthings.com/oauth/token",
        data=body,
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        if "access_token" not in data:
            return JSONResponse({"erro": "Token não recebido", "detalhe": data}, status_code=500)
        expires_at = (datetime.now() + timedelta(seconds=data.get("expires_in", 86400))).isoformat()
        banco.salvar_st_token(user_id, data["access_token"], data.get("refresh_token", ""), expires_at)
        log(f"SmartThings conectado para {user_id}", "smartthings")
        return JSONResponse({"ok": True, "msg": "SmartThings conectado com sucesso!"})
    except Exception as e:
        log(f"SmartThings callback erro: {e}", "smartthings")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/smartthings/dispositivos/{user_id}")
def st_dispositivos(user_id: str):
    """Lista dispositivos do usuário"""
    token = st_get_token(user_id)
    if not token:
        return JSONResponse({"erro": "SmartThings não conectado", "conectado": False})
    dispositivos = st_listar_dispositivos(token)
    return JSONResponse({
        "conectado": True,
        "dispositivos": [{"id": d.get("deviceId"), "nome": d.get("label")} for d in dispositivos]
    })

@app.post("/debug/busca")
async def debug_busca(request: Request):
    data = await request.json()
    query = data.get("query", "")
    resultado = buscar_brave(query)
    return JSONResponse({"query": query, "resultado": resultado})

@app.post("/debug/fishaudio")
async def debug_fishaudio(request: Request):
    """Diagnóstico Fish Audio"""
    try:
        data = await request.json()
        chave = data.get("chave", "")
        import urllib.request, json
        payload = json.dumps({
            "text": "teste",
            "reference_id": "23c14f5db9dc40ba9c69f38575ae3a80",
            "format": "mp3"
        }).encode()
        req = urllib.request.Request(
            "https://api.fish.audio/v1/tts",
            data=payload,
            headers={
                "Authorization": f"Bearer {chave}",
                "Content-Type": "application/json",
                "model": "s2-pro"
            }
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return JSONResponse({"ok": True, "bytes": len(resp.read())})
        except Exception as e:
            return JSONResponse({"ok": False, "erro": str(e)})
    except Exception as e:
        return JSONResponse({"erro": str(e)})

@app.post("/stripe/criar_checkout")
async def stripe_criar_checkout(request: Request):
    """Cria sessão de checkout no Stripe"""
    try:
        import urllib.parse as urlparse
        data    = await request.json()
        user_id = data.get("user_id", "")
        plano   = data.get("plano", "pro")  # pro ou pro_plus
        email   = data.get("email", "")
        if not STRIPE_SECRET_KEY:
            return JSONResponse({"erro": "Stripe não configurado"}, status_code=500)
        price_id = STRIPE_PRICE_PRO if plano == "pro" else STRIPE_PRICE_PRO_PLUS
        if not price_id:
            return JSONResponse({"erro": "Produto não configurado"}, status_code=500)
        payload = urlparse.urlencode({
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": f"https://margo-production-98a9.up.railway.app/stripe/sucesso?user_id={user_id}",
            "cancel_url": "https://orbiby.com",
            "client_reference_id": user_id,
            "customer_email": email,
        }).encode()
        req = urllib.request.Request(
            "https://api.stripe.com/v1/checkout/sessions",
            data=payload,
            headers={
                "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        resp = urllib.request.urlopen(req, timeout=15)
        session = json.loads(resp.read())
        return JSONResponse({"url": session["url"]})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log(f"Stripe checkout erro: {e} — {body}", "stripe")
        return JSONResponse({"erro": body}, status_code=500)
    except Exception as e:
        log(f"Stripe checkout erro: {e}", "stripe")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/stripe/sucesso")
async def stripe_sucesso(user_id: str = ""):
    return JSONResponse({"ok": True, "msg": "Pagamento realizado! Seu plano foi atualizado."})

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Recebe eventos do Stripe e atualiza planos"""
    try:
        payload = await request.body()
        sig     = request.headers.get("stripe-signature", "")
        # Verifica assinatura do webhook
        if STRIPE_WEBHOOK_SECRET:
            import hmac, hashlib, time
            parts = {k: v for k, v in (p.split("=", 1) for p in sig.split(",") if "=" in p)}
            timestamp = parts.get("t", "")
            sig_v1    = parts.get("v1", "")
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig_v1):
                return JSONResponse({"erro": "Assinatura inválida"}, status_code=400)
        event = json.loads(payload)
        event_type = event.get("type", "")
        log(f"Stripe evento: {event_type}", "stripe")
        obj = event.get("data", {}).get("object", {})
        if event_type == "checkout.session.completed":
            user_id  = obj.get("client_reference_id", "")
            customer = obj.get("customer", "")
            sub_id   = obj.get("subscription", "")
            metadata = obj.get("metadata", {})
            # Determina plano pelo price_id via line_items ou metadata
            plano = "pro"
            # Tenta pelo payment link — verifica pelo price_id dos line_items expandidos
            line_items = obj.get("line_items", {}).get("data", [])
            for item in line_items:
                pid = item.get("price", {}).get("id", "")
                if pid == STRIPE_PRICE_PRO_PLUS:
                    plano = "pro_plus"
                    break
                elif pid == STRIPE_PRICE_PRO:
                    plano = "pro"
                    break
            # Pacote avulso — sem subscription
            if not sub_id:
                plano = "avulso"
            if user_id:
                if plano == "avulso":
                    # Adiciona 50 interações extras
                    conn = banco._get_conn()
                    c = conn.cursor()
                    ph = "%s" if banco._pg else "?"
                    c.execute(f"UPDATE usuarios SET msgs_extras = COALESCE(msgs_extras,0) + 50 WHERE user_id={ph}", (user_id,))
                    conn.commit()
                    conn.close()
                    log(f"Stripe: +50 extras para {user_id}", "stripe")
                else:
                    banco.atualizar_plano(user_id, plano, customer, sub_id)
        elif event_type in ["customer.subscription.deleted"]:
            customer = obj.get("customer", "")
            usuario  = banco.buscar_por_stripe_customer(customer)
            if usuario:
                banco.atualizar_plano(usuario["user_id"], "free")
        elif event_type == "customer.subscription.updated":
            customer = obj.get("customer", "")
            status   = obj.get("status", "")
            usuario  = banco.buscar_por_stripe_customer(customer)
            if usuario and status != "active":
                banco.atualizar_plano(usuario["user_id"], "free")
        return JSONResponse({"ok": True})
    except Exception as e:
        log(f"Stripe webhook erro: {e}", "stripe")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/mp/criar_pix")
async def mp_criar_pix(request: Request):
    """Cria pagamento PIX via Mercado Pago — retorna QR Code"""
    try:
        import mercadopago
        data    = await request.json()
        user_id = data.get("user_id", "")
        plano   = data.get("plano", "pro")
        email   = data.get("email", "") or "cliente@orbiby.com"

        if not MP_ACCESS_TOKEN:
            return JSONResponse({"erro": "Mercado Pago não configurado"}, status_code=500)

        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

        planos = {
            "pro":      {"titulo": "Margo Pro — 20 msgs/dia",      "valor": 9.90},
            "pro_plus": {"titulo": "Margo Pro+ — 50 msgs/dia",     "valor": 19.90},
            "avulso":   {"titulo": "Margo — 50 interações extras", "valor": 9.90},
        }
        p = planos.get(plano, planos["pro"])

        payment_data = {
            "transaction_amount": p["valor"],
            "description": p["titulo"],
            "payment_method_id": "pix",
            "payer": {"email": email},
            "external_reference": f"{user_id}|{plano}",
            "notification_url": "https://margo-production-98a9.up.railway.app/webhook/mp",
        }

        result = sdk.payment().create(payment_data)
        payment = result["response"]
        
        if "point_of_interaction" not in payment:
            log(f"MP PIX erro: {payment}", "mp")
            return JSONResponse({"erro": "Erro ao gerar PIX"}, status_code=500)

        qr_code = payment["point_of_interaction"]["transaction_data"]["qr_code"]
        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        payment_id = payment["id"]

        return JSONResponse({
            "ok": True,
            "payment_id": payment_id,
            "qr_code": qr_code,
            "qr_code_base64": qr_code_base64,
            "valor": p["valor"],
            "titulo": p["titulo"]
        })

        if result["status"] == 201:
            return JSONResponse({
                "ok": True,
                "url": preference["init_point"],        # produção
                "url_sandbox": preference["sandbox_init_point"],  # teste
                "preference_id": preference["id"],
            })
        else:
            return JSONResponse({"erro": str(preference)}, status_code=500)
    except Exception as e:
        log(f"MP checkout erro: {e}", "mp")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/mp/sucesso")
async def mp_sucesso(user_id: str = "", plano: str = ""):
    if user_id and plano and plano != "avulso":
        banco.atualizar_plano(user_id, plano)
        log(f"MP sucesso: plano {plano} para {user_id}", "mp")
    return JSONResponse({"ok": True, "msg": "Pagamento realizado! Seu plano foi atualizado."})

@app.post("/webhook/mp")
async def webhook_mp(request: Request):
    """Webhook do Mercado Pago — confirma pagamento e atualiza plano"""
    try:
        import mercadopago
        data = await request.json()
        log(f"MP webhook: {data}", "mp")

        # Suporte aos dois formatos do MP
        if data.get("type") == "payment":
            payment_id = data.get("data", {}).get("id")
        elif data.get("topic") == "payment":
            payment_id = data.get("resource") or data.get("data", {}).get("id")
        else:
            return JSONResponse({"ok": True})

        if not payment_id:
            return JSONResponse({"ok": True})

        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        result = sdk.payment().get(payment_id)
        payment = result["response"]

        if payment.get("status") != "approved":
            return JSONResponse({"ok": True})

        ref = payment.get("external_reference", "")
        if "|" not in ref:
            return JSONResponse({"ok": True})

        user_id, plano = ref.split("|", 1)
        plano = plano.replace("pro+", "pro_plus")  # normaliza

        if plano == "avulso":
            # Adiciona 50 interações extras
            conn = banco._get_conn()
            c = conn.cursor()
            ph = "%s" if banco._pg else "?"
            c.execute(f"UPDATE usuarios SET msgs_extras = COALESCE(msgs_extras,0) + 50 WHERE user_id={ph}", (user_id,))
            conn.commit()
            conn.close()
            log(f"MP: +50 interações extras para {user_id}", "mp")
        else:
            banco.atualizar_plano(user_id, plano, stripe_customer_id=None)
            log(f"MP: plano {plano} ativado para {user_id}", "mp")

        return JSONResponse({"ok": True})
    except Exception as e:
        log(f"MP webhook erro: {e}", "mp")
        return JSONResponse({"ok": True})

@app.post("/teste/simular_pagamento")
async def teste_simular_pagamento(request: Request):
    """Simula webhook de pagamento aprovado — apenas para testes"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "")
        plano = data.get("plano", "avulso")
        plano = plano.replace("pro+", "pro_plus")  # normaliza

        if not user_id:
            return JSONResponse({"erro": "user_id obrigatório"}, status_code=400)

        if plano == "avulso":
            conn = banco._get_conn()
            c = conn.cursor()
            ph = "%s" if banco._pg else "?"
            c.execute(f"UPDATE usuarios SET msgs_extras = COALESCE(msgs_extras,0) + 50 WHERE user_id={ph}", (user_id,))
            conn.commit()
            conn.close()
            log(f"TESTE: +50 interações extras para {user_id}", "teste")
        else:
            banco.atualizar_plano(user_id, plano, stripe_customer_id=None)
            log(f"TESTE: plano {plano} ativado para {user_id}", "teste")

        return JSONResponse({"ok": True, "user_id": user_id, "plano": plano})
    except Exception as e:
        log(f"TESTE simular_pagamento erro: {e}", "teste")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/fcm_token")
async def salvar_fcm_token(request: Request):
    """Salva o FCM token do dispositivo para push notifications."""
    try:
        data = await request.json()
        user_id = data.get("user_id", "")
        token = data.get("token", "")
        if user_id and token:
            banco.salvar_fcm_token(user_id, token)
            return JSONResponse({"ok": True})
        return JSONResponse({"erro": "user_id e token obrigatórios"}, status_code=400)
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)

# ── SCHEDULER DE LEMBRETES ────────────────────────────────────────────────────
import threading

@app.get("/agenda/pendentes/{user_id}")
async def agenda_pendentes(user_id: str):
    """Retorna lembretes pendentes de notificação (12h antes, 1h antes, na hora)."""
    try:
        conn = banco._get_conn()
        c = conn.cursor()
        ph = "%s" if banco._pg else "?"
        agora = datetime.now()
        pendentes = []

        if banco._pg:
            c.execute(f"""
                SELECT id, titulo, descricao, data_hora, lembrado_1d, lembrado_3h
                FROM agenda WHERE user_id={ph} AND data_hora > {ph}
                ORDER BY data_hora ASC
            """, (user_id, (agora - timedelta(minutes=5)).isoformat()))
        else:
            c.execute(f"""
                SELECT id, titulo, descricao, data_hora, lembrado_1d, lembrado_3h
                FROM agenda WHERE user_id={ph} AND data_hora > {ph}
                ORDER BY data_hora ASC
            """, (user_id, (agora - timedelta(minutes=5)).isoformat()))

        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        for row in rows:
            item = dict(zip(cols, row))
            try:
                dt = datetime.fromisoformat(item["data_hora"])
                diff_horas = (dt - agora).total_seconds() / 3600

                # Na hora (±5 min) e não lembrado ainda
                if -0.08 <= diff_horas <= 0.08 and not item["lembrado_3h"]:
                    pendentes.append({
                        "id": item["id"],
                        "tipo": "agora",
                        "titulo": item["titulo"],
                        "descricao": item["descricao"],
                        "data_hora": item["data_hora"]
                    })
                    c.execute(f"UPDATE agenda SET lembrado_3h=1 WHERE id={ph}", (item["id"],))

                # 1 hora antes (entre 55min e 65min) e não lembrado 3h
                elif 0.9 <= diff_horas <= 1.1 and not item["lembrado_3h"]:
                    pendentes.append({
                        "id": item["id"],
                        "tipo": "1h",
                        "titulo": item["titulo"],
                        "descricao": item["descricao"],
                        "data_hora": item["data_hora"]
                    })
                    c.execute(f"UPDATE agenda SET lembrado_3h=1 WHERE id={ph}", (item["id"],))

                # 12 horas antes (entre 11.5h e 12.5h) e não lembrado 1d
                elif 11.5 <= diff_horas <= 12.5 and not item["lembrado_1d"]:
                    pendentes.append({
                        "id": item["id"],
                        "tipo": "12h",
                        "titulo": item["titulo"],
                        "descricao": item["descricao"],
                        "data_hora": item["data_hora"]
                    })
                    c.execute(f"UPDATE agenda SET lembrado_1d=1 WHERE id={ph}", (item["id"],))

            except: pass

        conn.commit()
        conn.close()
        return JSONResponse({"pendentes": pendentes})
    except Exception as e:
        log(f"Agenda pendentes erro: {e}", "agenda")
        return JSONResponse({"pendentes": []})

_scheduler_rodando = False

def verificar_agenda():
    """Scheduler: executa ações smart home agendadas + envia push de lembretes a cada 60s."""
    global _scheduler_rodando
    if _scheduler_rodando:
        log("Scheduler já rodando — ignorando nova thread", "scheduler")
        return
    _scheduler_rodando = True
    import time
    while True:
        try:
            # ── SMART HOME AGENDADO ──
            vencidas = banco.acoes_smart_vencidas()
            for item in vencidas:
                try:
                    acao = json.loads(item.get("acao_smart", "{}"))
                    resultado = st_executar_acao(
                        item["user_id"],
                        acao.get("acao", "ligar"),
                        acao.get("dispositivo", ""),
                        acao.get("valor")
                    )
                    banco.marcar_acao_executada(item["id"])
                    log(f"Smart agendado executado: {item['titulo']} → {resultado}", "smart")
                except Exception as e:
                    banco.marcar_acao_executada(item["id"])
                    log(f"Erro executando smart agendado {item.get('id')}: {e}", "smart")

            # ── LEMBRETES NORMAIS — push notification ──
            pass  # tick silencioso
            try:
                conn = banco._get_conn()
                cur = conn.cursor()
                ph = "%s" if banco._pg else "?"
                agora = datetime.now()
                cur.execute(
                    f"SELECT id, user_id, titulo, descricao, data_hora, lembrado_3h"
                    f" FROM agenda"
                    f" WHERE acao_smart IS NULL AND lembrado_3h = 0"
                    f" AND data_hora != '' AND data_hora IS NOT NULL"
                    f" AND data_hora <= {ph}",
                    ((agora + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S"),)
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                for row in rows:
                    item = dict(zip(cols, row))
                    try:
                        dt = datetime.fromisoformat(item["data_hora"])
                        diff_min = (agora - dt).total_seconds() / 60
                        if diff_min > 5:
                            cur.execute(f"UPDATE agenda SET lembrado_3h=1 WHERE id={ph}", (item["id"],))
                            continue
                        usuario = banco.buscar_usuario_por_id(item["user_id"])
                        fcm_token = (usuario.get("fcm_token") or "") if usuario else ""
                        titulo_lembrete = item.get("titulo", "Lembrete")
                        descricao_lembrete = item.get("descricao", "")
                        if fcm_token:
                            enviar_push(fcm_token, f"⏰ {titulo_lembrete}", descricao_lembrete or titulo_lembrete)
                            log(f"Push lembrete enviado: {titulo_lembrete} user={item['user_id']}", "agenda")
                        else:
                            log(f"Lembrete venceu sem FCM token: {titulo_lembrete} user={item['user_id']}", "agenda")
                        cur.execute(f"UPDATE agenda SET lembrado_3h=1 WHERE id={ph}", (item["id"],))
                    except Exception as e:
                        log(f"Erro notificando lembrete {item.get('id')}: {e}", "agenda")
                        cur.execute(f"UPDATE agenda SET lembrado_3h=1 WHERE id={ph}", (item["id"],))
                conn.commit()
                conn.close()
            except Exception as e:
                log(f"Scheduler lembretes erro: {e}", "agenda")

        except Exception as e:
            log(f"Scheduler erro: {e}", "smart")
        time.sleep(60)

# Inicia scheduler em background
scheduler_thread = threading.Thread(target=verificar_agenda, daemon=True)
scheduler_thread.start()
print(">>> SCHEDULER AGENDA INICIADO <<<")
log("Scheduler de agenda iniciado", "agenda")

GOOGLE_TTS_API_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")

def falar_google_tts(texto, idioma="pt-br", genero="F"):
    """Google Cloud TTS — voz Standard-C (free tier 4M chars/mês)"""
    if not GOOGLE_TTS_API_KEY:
        return None
    try:
        vozes = {
            ("pt-br", "F"): ("pt-BR", "pt-BR-Standard-C"),
            ("pt-br", "M"): ("pt-BR", "pt-BR-Standard-B"),
            ("en", "F"):    ("en-US", "en-US-Standard-F"),
            ("en", "M"):    ("en-US", "en-US-Standard-D"),
        }
        lang_code, voice_name = vozes.get((idioma, genero), ("pt-BR", "pt-BR-Standard-C"))
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_TTS_API_KEY}"
        payload = json.dumps({
            "input": {"text": texto},
            "voice": {"languageCode": lang_code, "name": voice_name},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.05}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload,
              headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        audio_b64 = data.get("audioContent", "")
        if audio_b64:
            return base64.b64decode(audio_b64)
        return None
    except Exception as e:
        log(f"Google TTS erro: {e}", "gtts")
        return None

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

@app.post("/stt")
async def stt_endpoint(request: Request):
    """Transcreve audio via Groq Whisper (multilingue, deteccao automatica de idioma).
    Body: { user_id, audio_base64, formato ('m4a'|'wav'|'mp3') }
    Retorna: { texto, idioma } ou { erro }"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "")
        audio_b64 = data.get("audio_base64", "")
        formato = data.get("formato", "m4a")
        if not audio_b64:
            return JSONResponse({"erro": "audio_base64 obrigatorio"}, status_code=400)
        if not GROQ_API_KEY:
            return JSONResponse({"erro": "STT indisponivel"}, status_code=503)

        # Gating: multilingue so para premium, tester e admin
        usuario = banco.buscar_usuario_por_id(user_id)
        plano = (usuario.get("plano", "free") if usuario else "free")
        if plano not in ("premium", "tester", "admin"):
            log(f"STT 403: user_id='{user_id}' plano='{plano}'", "stt")
            return JSONResponse({"erro": "plano_sem_stt", "upgrade": True}, status_code=403)

        audio_bytes = base64.b64decode(audio_b64)

        # Multipart form para a API do Groq (compativel com OpenAI Whisper API)
        boundary = "----MargoBoundary7MA4YWxkTrZu0gW"
        corpo = b""
        corpo += f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-large-v3-turbo\r\n".encode()
        corpo += f"--{boundary}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\nverbose_json\r\n".encode()
        corpo += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.{formato}\"\r\nContent-Type: audio/{formato}\r\n\r\n".encode()
        corpo += audio_bytes
        corpo += f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=corpo,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Margo/1.0 (Orbiby; +https://orbiby.com)"
            }
        )
        resp = urllib.request.urlopen(req, timeout=30)
        resultado = json.loads(resp.read())
        texto = resultado.get("text", "").strip()
        idioma = resultado.get("language", "")
        # Filtra alucinações clássicas do Whisper em áudio de silêncio
        alucinacoes = ["next video", "thanks for watching", "thank you for watching",
                       "thank you", "thank you.", "thanks.", "you're welcome",
                       "legendas pela comunidade", "obrigado por assistir", "inscreva-se",
                       "e aí", "e ai", "tchau", "bye", "okay",
                       "ご視聴ありがとう", "ありがとうございます",
                       "subtitles", "subscribe", "like and subscribe"]
        texto_limpo = texto.lower().strip().rstrip('.!? ')
        if not texto or len(texto) < 3 or (len(texto) < 40 and any(texto_limpo == a or texto_limpo.startswith(a + ' ') for a in alucinacoes)):
            log(f"STT descartado (alucinacao/vazio): {texto[:60]}", "stt")
            return JSONResponse({"texto": "", "idioma": idioma})
        log(f"STT Groq: [{idioma}] {texto[:80]}", "stt")
        return JSONResponse({"texto": texto, "idioma": idioma})
    except urllib.error.HTTPError as e:
        try:
            corpo_erro = e.read().decode()[:200]
        except:
            corpo_erro = ""
        log(f"STT Groq HTTP {e.code}: {corpo_erro}", "stt")
        return JSONResponse({"erro": f"stt_falhou_{e.code}", "detalhe": corpo_erro}, status_code=500)
    except Exception as e:
        log(f"STT erro: {e}", "stt")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/teste_edge_tts")
async def teste_edge_tts():
    """Testa se edge-tts conecta no Railway"""
    try:
        import edge_tts, asyncio, base64
        comm = edge_tts.Communicate("Teste de voz", "pt-BR-FranciscaNeural")
        audio_data = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        if len(audio_data) > 0:
            return {"ok": True, "bytes": len(audio_data), "preview_b64": base64.b64encode(audio_data[:200]).decode()}
        return {"ok": False, "erro": "sem audio"}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@app.post("/kokoro_tts")
async def kokoro_tts_endpoint(request: Request):
    """Gera áudio TTS via Kokoro. Body: { texto, idioma, genero }"""
    try:
        data = await request.json()
        texto = data.get("texto", "")
        idioma = data.get("idioma", "pt-br")
        genero = data.get("genero", "F")
        if not texto:
            return JSONResponse({"erro": "texto obrigatório"}, status_code=400)

        # Edge TTS — PT-BR e JA-JP (gratuito e neural)
        _edge_voices = {
            "pt-br": {"F": "pt-BR-FranciscaNeural", "M": "pt-BR-AntonioNeural"},
            "ja-jp": {"F": "ja-JP-NanamiNeural", "M": "ja-JP-KeitaNeural"},
            "ja":    {"F": "ja-JP-NanamiNeural", "M": "ja-JP-KeitaNeural"},
        }
        _edge_map = _edge_voices.get(idioma)
        if _edge_map:
            try:
                import edge_tts, asyncio, io
                voz = _edge_map.get(genero, _edge_map["F"])
                comm = edge_tts.Communicate(texto, voz)
                audio_data = b""
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                if audio_data:
                    import base64
                    audio_b64 = base64.b64encode(audio_data).decode()
                    log(f"Edge TTS OK: {voz} ({len(audio_data)} bytes)", "tts")
                    return JSONResponse({"audio_base64": audio_b64, "formato": "mp3"})
                log("Edge TTS sem audio — usando Kokoro como fallback", "tts")
            except Exception as e:
                log(f"Edge TTS falhou: {e} — usando Kokoro como fallback", "tts")

        if not _kokoro_ready:
            return JSONResponse({"erro": "Kokoro não está pronto ainda"}, status_code=503)
        audio_bytes = kokoro_tts(texto, idioma, genero)
        if not audio_bytes:
            return JSONResponse({"erro": "Falha ao gerar áudio"}, status_code=500)
        import base64
        audio_b64 = base64.b64encode(audio_bytes).decode()
        return JSONResponse({"audio_base64": audio_b64, "formato": "wav"})
    except Exception as e:
        log(f"Kokoro TTS endpoint erro: {e}", "kokoro")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/boas_vindas")
async def boas_vindas(request: Request):
    """Retorna mensagem de boas-vindas personalizada"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "")
        usuario = banco.buscar_usuario_por_id(user_id) if user_id else None
        nome = ""
        nome_assistente = "Margo"
        if usuario:
            perfil = usuario.get("perfil", {})
            config_u = usuario.get("config", {})
            if isinstance(perfil, str):
                import json as _j
                try: perfil = _j.loads(perfil)
                except: perfil = {}
            if isinstance(config_u, str):
                import json as _j
                try: config_u = _j.loads(config_u)
                except: config_u = {}
            nome = perfil.get("nome", "")
            nome_assistente = config_u.get("nome_assistente", "Margo")

        idioma = data.get("idioma", "") or (config_u.get("idioma", "") if usuario else "") or "pt-BR"

        if idioma == "en-US":
            if nome_assistente == "Margo":
                saudacao = f"Hi{', ' + nome if nome else ''}! I'm Margo, your personal AI assistant."
            else:
                saudacao = f"Hi{', ' + nome if nome else ''}! I'm {nome_assistente}, your personal AI assistant powered by Margo."
            mensagem = f"""{saudacao} 🌟

Here's everything I can help you with:

💬 *Chat & Search* — Ask me anything! I search the web, answer questions, translate languages and much more.

🗺️ *Navigation* — Just say "take me to..." or "find a restaurant nearby" and I'll trace the route. You can even say "by bus" or "walking" for different transport modes!

🎵 *Music* — "Play [song] on Spotify" and I'll open it for you. Works with YouTube and SoundCloud too.

📅 *Reminders* — "Remind me to call the doctor at 3pm" or "remind me in 30 minutes to check the oven." I'll send you a notification when it's time!

🏠 *Smart Home* — Control your SmartThings devices: "turn on the living room light", "turn off the AC at 10pm." Connect your SmartThings account in settings.

📱 *WhatsApp* — "Send a message to Maria on WhatsApp" and I'll open the conversation for you.

🌤️ *Weather* — "What's the weather like?" and I'll tell you the forecast for your area.

✈️ *Travel* — Search for flights and hotels: "find flights to Tokyo" or "hotels near the beach."

━━━━━━━━━━━━━━━━━━
⚙️ *Getting Started — Settings*

Tap the ⚙️ icon in the top right corner to personalize your experience:

1️⃣ *About You* — Tell me your name so I can greet you properly.

2️⃣ *Your Assistant* — Give me a custom name and describe my personality! Example: "fun, uses emojis, talks like a close friend, loves music."

3️⃣ *Voice* — Choose between male and female voice. You can also connect your own Fish Audio or ElevenLabs key for premium voices.

4️⃣ *Navigation* — Choose your preferred map app (Google Maps or Waze).

5️⃣ *Spotify* — Connect your Spotify account to play music directly.

6️⃣ *Smart Home* — Connect your Samsung SmartThings account to control lights, AC, TV and more by voice.

━━━━━━━━━━━━━━━━━━
💡 *Tips:*
• You can type or use the microphone 🎤 to talk to me
• I understand Portuguese, English, and many other languages
• Try: "What can you do?" anytime for a quick recap

How can I help you today?"""
        elif idioma == "ja-JP":
            if nome_assistente == "Margo":
                saudacao = f"こんにちは{('、' + nome) if nome else ''}！MargoはあなただけのAIアシスタントです。"
            else:
                saudacao = f"こんにちは{('、' + nome) if nome else ''}！{nome_assistente}はMargoが提供するあなただけのAIアシスタントです。"
            mensagem = f"""{saudacao} 🌟

できることはこちらです：

💬 *会話と検索* — 何でも聞いてください！ウェブ検索、質問への回答、翻訳など、幅広くお手伝いします。

🗺️ *ナビゲーション* — 「〜まで連れて行って」や「近くのレストランを探して」と言えば、ルートを案内します。「バスで」「歩いて」など移動手段も指定できます！

🎵 *音楽* — 「Spotifyで〜を再生して」と言えば開きます。YouTubeやSoundCloudにも対応しています。

📅 *リマインダー* — 「15時に歯医者に電話するのを思い出させて」や「30分後にオーブンを確認するのを思い出させて」と言えば、時間になったら通知します！

🏠 *スマートホーム* — SmartThingsデバイスを操作：「リビングの電気をつけて」「22時にエアコンを消して」。設定でSmartThingsアカウントを接続してください。

📱 *WhatsApp* — 「マリアさんにWhatsAppでメッセージを送って」と言えば、会話を開きます。

🌤️ *天気* — 「今日の天気は？」と聞けば、お住まいの地域の天気予報をお伝えします。

✈️ *旅行* — フライトやホテルを検索：「東京行きのフライトを探して」「ビーチ近くのホテル」。

━━━━━━━━━━━━━━━━━━
⚙️ *はじめに — 設定*

右上の⚙️アイコンをタップして、体験をカスタマイズしてください：

1️⃣ *あなたについて* — お名前を教えてください。

2️⃣ *アシスタント* — カスタム名と性格を設定できます！例：「明るい、絵文字を使う、親しい友達のように話す」

3️⃣ *音声* — 男性または女性の声を選択。Fish AudioやElevenLabsのキーでプレミアム音声も使えます。

4️⃣ *ナビゲーション* — お好みの地図アプリを選択（GoogleマップまたはWaze）。

5️⃣ *Spotify* — Spotifyアカウントを接続して、アプリから直接音楽を再生。

6️⃣ *スマートホーム* — Samsung SmartThingsアカウントを接続して、音声で照明やエアコン、テレビなどを操作。

━━━━━━━━━━━━━━━━━━
💡 *ヒント：*
• テキスト入力またはマイク🎤で話しかけることができます
• 日本語、ポルトガル語、英語など多言語に対応しています
• いつでも「何ができる？」と聞いてみてください

何かお手伝いできることはありますか？"""

        else:
            if nome_assistente == "Margo":
                saudacao = f"Olá{', ' + nome if nome else ''}! Sou a Margo, sua assistente pessoal com IA."
            else:
                saudacao = f"Olá{', ' + nome if nome else ''}! Sou {nome_assistente}, seu assistente pessoal com IA da Margo."
            mensagem = f"""{saudacao} 🌟

Aqui está tudo que posso fazer por você:

💬 *Conversa e Pesquisa* — Me pergunte qualquer coisa! Pesquiso na web, respondo dúvidas, traduzo idiomas e muito mais.

🗺️ *Navegação* — Diga "me leva até..." ou "acha um restaurante perto" e eu traço a rota. Pode até pedir "de ônibus" ou "a pé" pra diferentes meios de transporte!

🎵 *Música* — "Toca [música] no Spotify" e eu abro pra você. Funciona com YouTube e SoundCloud também.

📅 *Lembretes* — "Me lembra de ligar pro dentista às 15h" ou "me lembra daqui a 30 minutos de olhar o forno." Eu te mando uma notificação quando chegar a hora!

🏠 *Casa Inteligente* — Controle seus dispositivos SmartThings: "liga a luz da sala", "desliga o ar às 22h." Conecte sua conta SmartThings nas configurações.

📱 *WhatsApp* — "Manda mensagem pra Maria no WhatsApp" e eu abro a conversa pra você.

🌤️ *Clima* — "Como tá o tempo?" e eu te digo a previsão da sua região.

✈️ *Viagens* — Busque voos e hotéis: "procura voos pra Tóquio" ou "hotéis perto da praia."

━━━━━━━━━━━━━━━━━━
⚙️ *Começando — Configurações*

Toque no ícone ⚙️ no canto superior direito para personalizar sua experiência:

1️⃣ *Sobre Você* — Me diga seu nome pra eu te cumprimentar direitinho.

2️⃣ *Seu Assistente* — Me dê um nome personalizado e descreva minha personalidade! Exemplo: "divertida, usa emojis, fala como amiga próxima, adora música."

3️⃣ *Voz* — Escolha entre voz masculina e feminina. Você também pode conectar sua própria chave Fish Audio ou ElevenLabs para vozes premium.

4️⃣ *Navegação* — Escolha seu app de mapa preferido (Google Maps ou Waze).

5️⃣ *Spotify* — Conecte sua conta Spotify para tocar músicas direto pelo app.

6️⃣ *Casa Inteligente* — Conecte sua conta Samsung SmartThings para controlar luzes, ar, TV e mais por voz.

━━━━━━━━━━━━━━━━━━
💡 *Dicas:*
• Você pode digitar ou usar o microfone 🎤 pra falar comigo
• Eu entendo português, inglês e muitos outros idiomas
• Experimente: "O que você pode fazer?" a qualquer momento

Como posso te ajudar hoje?"""
        return JSONResponse({"mensagem": mensagem})
    except Exception as e:
        return JSONResponse({"mensagem": "Olá! Sou sua assistente pessoal. Como posso te ajudar?"})

@app.post("/verificar_device")
async def verificar_device(request: Request):
    """Verifica se device já tem conta free cadastrada"""
    try:
        data = await request.json()
        device_id = data.get("device_id", "")
        if not device_id:
            return JSONResponse({"pode_criar": True})
        conn = banco._get_conn()
        cur = conn.cursor()
        ph = "%s" if banco._pg else "?"
        cur.execute(f"SELECT user_id, plano FROM usuarios WHERE device_id={ph}", (device_id,))
        row = cur.fetchone()
        if banco._pg: conn.close()
        if row:
            user_id, plano = row[0], row[1]
            if plano == 'free':
                return JSONResponse({"pode_criar": False, "user_id": user_id})
        return JSONResponse({"pode_criar": True})
    except Exception as e:
        log(f"verificar_device erro: {e}", "erro")
        return JSONResponse({"pode_criar": True})

@app.get("/ping")
def ping():
    return {"pong": True, "ts": datetime.now().isoformat()}

@app.post("/verificar_email")
async def verificar_email(request: Request):
    """Verifica código e finaliza cadastro."""
    try:
        import hashlib, uuid
        data = await request.json()
        email = data.get("email", "").strip().lower()
        codigo = data.get("codigo", "").strip()
        senha_hash = data.get("senha_hash", "")
        device_id = data.get("device_id", "")

        conn = banco._get_conn()
        c = conn.cursor()
        ph = "%s" if banco._pg else "?"
        c.execute(f"SELECT codigo, expira_em FROM email_verificacao WHERE email={ph}", (email,))
        row = c.fetchone()
        conn.close()

        if not row:
            return JSONResponse({"erro": "Código não encontrado. Cadastre-se novamente."}, status_code=400)

        cod_salvo, expira_em = row[0], row[1]
        if datetime.now() > datetime.fromisoformat(expira_em):
            return JSONResponse({"erro": "Código expirado. Cadastre-se novamente."}, status_code=400)
        if codigo != cod_salvo:
            return JSONResponse({"erro": "Código incorreto."}, status_code=400)

        # Cria a conta
        agora = datetime.now().isoformat()
        user_id = "u_" + str(uuid.uuid4()).replace("-", "")[:16]
        ip_cadastro = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
        conn2 = banco._get_conn()
        c2 = conn2.cursor()
        ph = "%s" if banco._pg else "?"
        if banco._pg:
            c2.execute("""INSERT INTO usuarios (user_id, email, nome, plano, status, senha_hash, criado_em, ultimo_acesso, device_id, ip_cadastro)
                VALUES (%s,%s,%s,'free','ativo',%s,%s,%s,%s,%s)""",
                (user_id, email, "", senha_hash, agora, agora, device_id, ip_cadastro))
        else:
            c2.execute("INSERT INTO usuarios (user_id, email, nome, plano, status, senha_hash, criado_em, ultimo_acesso, device_id) VALUES (?,?,?,'free','ativo',?,?,?,?)",
                (user_id, email, "", senha_hash, agora, agora, device_id))
        # Remove código usado
        c2.execute(f"DELETE FROM email_verificacao WHERE email={ph}", (email,))
        conn2.commit()
        conn2.close()
        log(f"Cadastro verificado: {email} → {user_id}", "usuarios")
        return JSONResponse({"ok": True, "user_id": user_id, "email": email, "plano": "free", "tem_perfil": False})
    except Exception as e:
        log(f"Erro verificar_email: {e}", "usuarios")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/cadastro")
async def cadastro(request: Request):
    """
    Cria nova conta com email e senha.
    Body: { email, senha }
    Retorna: { ok, user_id, email, plano, tem_perfil }
    """
    try:
        import hashlib
        data  = await request.json()
        email = data.get("email", "").strip().lower()
        senha = data.get("senha", "").strip()
        device_id = data.get("device_id", "")
        device_id = data.get("device_id", "")

        if not email or "@" not in email:
            return JSONResponse({"erro": "Email inválido"}, status_code=400)
        if len(senha) < 6:
            return JSONResponse({"erro": "Senha deve ter pelo menos 6 caracteres"}, status_code=400)

        # Valida email
        valido, erro_email = validar_email(email)
        if not valido:
            return JSONResponse({"erro": erro_email}, status_code=400)

        # Verifica se email já existe
        existente = banco.buscar_usuario_por_email(email)
        if existente:
            return JSONResponse({"erro": "Email já cadastrado. Use a opção Entrar."}, status_code=400)

        # Gera código de verificação 6 dígitos
        import random
        codigo = str(random.randint(100000, 999999))
        expira_em = (datetime.now() + timedelta(minutes=15)).isoformat()
        conn2 = banco._get_conn()
        c2 = conn2.cursor()
        ph2 = "%s" if banco._pg else "?"
        if banco._pg:
            c2.execute(f"INSERT INTO email_verificacao (email, codigo, expira_em, criado_em) VALUES ({ph2},{ph2},{ph2},{ph2}) ON CONFLICT (email) DO UPDATE SET codigo=EXCLUDED.codigo, expira_em=EXCLUDED.expira_em", (email, codigo, expira_em, datetime.now().isoformat()))
        else:
            c2.execute(f"INSERT OR REPLACE INTO email_verificacao (email, codigo, expira_em, criado_em) VALUES ({ph2},{ph2},{ph2},{ph2})", (email, codigo, expira_em, datetime.now().isoformat()))
        conn2.commit()
        conn2.close()
        enviar_email_verificacao(email, codigo)
        # Salva senha para usar após verificação
        senha_hash_temp = hashlib.sha256((email + data.get("senha","") + "margo_orbiby_salt").encode()).hexdigest()
        return JSONResponse({"ok": True, "verificacao_pendente": True, "email": email, "senha_hash": senha_hash_temp, "device_id": device_id, "msg": "Código enviado para seu email!"})

        # Hash da senha com salt
        senha_hash = hashlib.sha256((email + senha + "margo_orbiby_salt").encode()).hexdigest()

        import uuid
        agora = datetime.now().isoformat()
        user_id = "u_" + str(uuid.uuid4()).replace("-", "")[:16]
        conn = banco._get_conn()
        c = conn.cursor()
        ph = "%s" if banco._pg else "?"
        ip_cadastro = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
        if banco._pg:
            c.execute('''INSERT INTO usuarios
                (user_id, email, nome, plano, status, senha_hash, criado_em, ultimo_acesso, device_id, ip_cadastro)
                VALUES (%s,%s,%s,'free','ativo',%s,%s,%s,%s,%s)''',
                (user_id, email, "", senha_hash, agora, agora, device_id, ip_cadastro))
        else:
            c.execute('''INSERT INTO usuarios
                (user_id, email, nome, plano, status, senha_hash, criado_em, ultimo_acesso, device_id)
                VALUES (?,?,?,'free','ativo',?,?,?,?)''',
                (user_id, email, "", senha_hash, agora, agora, device_id))
        conn.commit()
        conn.close()
        log(f"Novo cadastro: {email} → {user_id}", "usuarios")

        return JSONResponse({
            "ok": True,
            "user_id": user_id,
            "email": email,
            "plano": "free",
            "novo": True,
            "tem_perfil": False,
        })
    except Exception as e:
        log(f"Erro /cadastro: {e}", "usuarios")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/login")
async def login(request: Request):
    """
    Login com email e senha.
    Body: { email, senha }
    Retorna: { ok, user_id, email, plano, tem_perfil }
    """
    try:
        import hashlib
        data  = await request.json()
        email = data.get("email", "").strip().lower()
        senha = data.get("senha", "").strip()
        device_id = data.get("device_id", "")
        device_id = data.get("device_id", "")

        if not email or "@" not in email:
            return JSONResponse({"erro": "Email inválido"}, status_code=400)
        if not senha:
            return JSONResponse({"erro": "Senha obrigatória"}, status_code=400)

        usuario = banco.buscar_usuario_por_email(email)
        if not usuario:
            return JSONResponse({"erro": "Email não encontrado. Crie uma conta primeiro."}, status_code=401)

        # Verifica senha
        senha_hash = hashlib.sha256((email + senha + "margo_orbiby_salt").encode()).hexdigest()
        if usuario.get("senha_hash") != senha_hash:
            return JSONResponse({"erro": "Senha incorreta."}, status_code=401)

        # Atualiza último acesso
        agora = datetime.now().isoformat()
        conn = banco._get_conn()
        c = conn.cursor()
        ph = "%s" if banco._pg else "?"
        c.execute(f'UPDATE usuarios SET ultimo_acesso={ph} WHERE email={ph}', (agora, email))
        conn.commit()
        conn.close()

        user_id = usuario["user_id"]
        perfil  = banco.buscar_perfil(user_id)
        config  = banco.buscar_config(user_id)
        tem_perfil = bool(perfil.get("nome") and config.get("onboarding_completo"))

        return JSONResponse({
            "ok":        True,
            "user_id":   user_id,
            "email":     email,
            "plano":     usuario.get("plano", "free"),
            "novo":      False,
            "tem_perfil": tem_perfil,
        })
    except Exception as e:
        log(f"Erro /login: {e}", "usuarios")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/usuario/{user_id}")
def get_usuario(user_id: str):
    """Retorna dados completos do usuário para carregar em novo dispositivo"""
    usuario = banco.buscar_usuario_por_id(user_id)
    if not usuario:
        return JSONResponse({"erro": "Usuário não encontrado"}, status_code=404)
    perfil  = banco.buscar_perfil(user_id)
    config  = banco.buscar_config(user_id)
    return JSONResponse({
        "user_id":        user_id,
        "email":          usuario.get("email", ""),
        "nome":           usuario.get("nome", ""),
        "plano":          usuario.get("plano", "free"),
        "perfil":         perfil,
        "config":         {k: v for k, v in config.items() if k != "voz_chave"},
    })

@app.post("/mensagem")
async def mensagem(request: Request):
    try:
        data = await request.json()
        user_id   = data.get("user_id", "default")
        mensagem_ = data.get("mensagem", "").strip()
        latitude  = data.get("latitude")
        longitude = data.get("longitude")
        hora_local = data.get("hora_local", "")
        idioma_falado = data.get("idioma_falado", "")
        if idioma_falado:
            log(f"idioma_falado recebido: {idioma_falado}", "stt")
        imagem_base64 = data.get("imagem_base64", "")
        if not mensagem_ and not imagem_base64:
            return JSONResponse({"erro": "mensagem vazia"}, status_code=400)
        if not mensagem_ and imagem_base64:
            mensagem_ = "O que voce ve nessa imagem? Descreva detalhadamente."

            # Verifica limite diário
        uso = banco.verificar_limite(user_id)
        if not uso["pode"]:
            if uso.get("trial"):
                msg_limite = "Você usou todas as 50 interações do seu trial gratuito! Assine um plano para continuar."
            else:
                msg_limite = f"Você atingiu seu limite de {uso['limite']} mensagens hoje. Volte amanhã ou compre interações extras!"
            return JSONResponse({
                "resposta": msg_limite,
                "limite_atingido": True,
                "plano": uso.get("plano", "free"),
                "ferramenta": None
            })

        resultado = processar_mensagem(user_id, mensagem_, latitude, longitude, hora_local=hora_local, imagem_base64=imagem_base64, idioma_falado=idioma_falado)
        banco.registrar_uso(user_id, usando_extras=uso.get("usando_extras", False))
        return JSONResponse(resultado)
    except Exception as e:
        log(f"Erro /mensagem: {e}")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/falar")
async def falar(request: Request):
    """
    Gera áudio TTS via Fish Audio ou ElevenLabs.
    Body: { texto, provider ('fishaudio'|'elevenlabs'), chave, voz_id, genero ('F'|'M'), user_id }
    Retorna: { audio_base64, formato }
    Se não houver chave/voz_id válidos, retorna { device_tts: true } para o frontend usar voz local.
    """
    try:
        data     = await request.json()
        texto    = data.get("texto", "").strip()
        provider = data.get("provider", "").lower()
        chave    = data.get("chave", "").strip()
        voz_id   = data.get("voz_id", "").strip()
        genero   = data.get("genero", "F")
        user_id  = data.get("user_id", "default")

        if not texto:
            return JSONResponse({"erro": "texto vazio"}, status_code=400)

        # Se não tem chave, manda usar voz do dispositivo
        if not chave:
            return JSONResponse({"device_tts": True})

        audio_bytes = None

        if provider == "fishaudio":
            audio_bytes = falar_fishaudio(texto, chave, voz_id, genero)
        elif provider == "elevenlabs":
            audio_bytes = falar_elevenlabs(texto, chave, voz_id, genero)
        else:
            return JSONResponse({"device_tts": True})

        if not audio_bytes:
            # Falhou — manda usar voz local como fallback
            return JSONResponse({"device_tts": True, "erro": "TTS falhou, usando voz local"})

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return JSONResponse({"audio_base64": audio_b64, "formato": "mp3"})

    except Exception as e:
        log(f"Erro /falar: {e}", "voz")
        return JSONResponse({"device_tts": True, "erro": str(e)})

@app.get("/status/{user_id}")
def status(user_id: str):
    config = banco.buscar_config(user_id)
    perfil = banco.buscar_perfil(user_id)
    return {
        "user_id":             user_id,
        "onboarding_completo": bool(config.get("onboarding_completo")),
        "nome_usuario":        perfil.get("nome", ""),
        "nome_assistente":     config.get("nome_assistente", "Margo"),
        "genero":              config.get("genero", "F"),
        "banco":               "postgres" if usar_postgres() else "sqlite"
    }

@app.post("/limpar_sessao")
async def limpar_sessao(request: Request):
    data    = await request.json()
    user_id = data.get("user_id", "default")
    sessoes.resumir_e_limpar(user_id)
    return {"ok": True}

@app.post("/salvar_voz")
async def salvar_voz(request: Request):
    """Salva configuração de voz customizada (ElevenLabs / Fish Audio)"""
    data    = await request.json()
    user_id = data.get("user_id", "default")
    banco.salvar_config(user_id, {
        "voz_provider": data.get("provider", "device"),
        "voz_chave":    data.get("chave", ""),
        "voz_id":       data.get("voz_id", ""),
    })
    return {"ok": True}

@app.post("/salvar_perfil_completo")
async def salvar_perfil_completo(request: Request):
    """
    Salva perfil do usuário + config da assistente de uma vez.
    Chamado pelo painel de configurações do app.
    Body: { user_id, nome, idade, profissao, musica, comida, hobbies, extra,
            nome_assistente, genero, personalidade, voz_provider, voz_chave, voz_id }
    """
    try:
        data    = await request.json()
        user_id = data.get("user_id", "default")

        # Salva perfil do usuário
        banco.salvar_perfil(user_id, {
            "nome":       data.get("nome", "").strip(),
            "idade":      data.get("nascimento", data.get("idade", "")).strip(),
            "profissao":  data.get("profissao", "").strip(),
            "musica":     data.get("musica", "").strip(),
            "comida":     data.get("comida", "").strip(),
            "hobbies":    data.get("hobbies", "").strip(),
            "extra":      data.get("extra", "").strip(),
        })

        # Salva config da assistente
        banco.salvar_config(user_id, {
            "nome_assistente":     data.get("nome_assistente", "Margo").strip(),
            "genero":              data.get("genero", "F"),
            "personalidade":       data.get("personalidade", "").strip(),
            "voz_provider":        data.get("voz_provider", "device"),
            "voz_chave":           "",  # NUNCA salvar chave API no banco — fica só no device
            "voz_id":              data.get("voz_id", "").strip(),
            "onboarding_completo": True,
        })

        log(f"Perfil completo salvo para {user_id}", "perfil")
        return JSONResponse({"ok": True})
    except Exception as e:
        log(f"Erro /salvar_perfil_completo: {e}")
        return JSONResponse({"erro": str(e)}, status_code=500)



# ── RECUPERAÇÃO DE SENHA ─────────────────────────────────────────────────────
_reset_codes = {}  # email -> {"code": "123456", "expires": datetime}

@app.post("/recuperar_senha")
async def recuperar_senha(request: Request):
    """Envia código de 6 dígitos por email para redefinir senha."""
    import random
    try:
        data = await request.json()
        email = (data.get("email") or "").strip().lower()
        if not email:
            return JSONResponse({"erro": "Email obrigatório"}, status_code=400)
        # Verifica se email existe
        conn = banco._get_conn()
        cur = conn.cursor()
        ph = "%s" if banco._pg else "?"
        cur.execute(f"SELECT user_id FROM usuarios WHERE email={ph}", (email,))
        row = cur.fetchone()
        conn.close()
        if not row:
            # Não revela se email existe ou não (segurança)
            return JSONResponse({"ok": True, "msg": "Se o email estiver cadastrado, enviaremos um código."})
        code = str(random.randint(100000, 999999))
        _reset_codes[email] = {"code": code, "expires": datetime.now() + timedelta(minutes=15)}
        # Envia email
        try:
            import resend
            resend.api_key = RESEND_API_KEY
            resend.Emails.send({
                "from": "Margo by Orbiby <noreply@orbiby.com>",
                "to": email,
                "subject": "Código para redefinir senha — Margo",
                "html": f"""
                <div style="font-family:Arial; max-width:400px; margin:auto; padding:20px;">
                    <h2 style="color:#2196F3;">Redefinição de senha</h2>
                    <p>Seu código de redefinição:</p>
                    <div style="font-size:32px; font-weight:bold; letter-spacing:8px; color:#2196F3; text-align:center; padding:20px; background:#f5f5f5; border-radius:8px;">{code}</div>
                    <p style="color:#666; font-size:13px; margin-top:20px;">Este código expira em 15 minutos.</p>
                    <p style="color:#666; font-size:13px;">Se você não solicitou, ignore este email.</p>
                </div>"""
            })
            log(f"Código reset enviado para {email}", "auth")
        except Exception as e:
            log(f"Erro enviar email reset: {e}", "auth")
            return JSONResponse({"erro": "Erro ao enviar email"}, status_code=500)
        return JSONResponse({"ok": True, "msg": "Se o email estiver cadastrado, enviaremos um código."})
    except Exception as e:
        log(f"Erro /recuperar_senha: {e}", "auth")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/redefinir_senha")
async def redefinir_senha(request: Request):
    """Valida código e redefine a senha."""
    try:
        data = await request.json()
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()
        nova_senha = data.get("nova_senha", "")
        if not email or not code or not nova_senha:
            return JSONResponse({"erro": "Email, código e nova senha obrigatórios"}, status_code=400)
        if len(nova_senha) < 6:
            return JSONResponse({"erro": "Senha deve ter no mínimo 6 caracteres"}, status_code=400)
        entry = _reset_codes.get(email)
        if not entry or entry["code"] != code:
            return JSONResponse({"erro": "Código inválido"}, status_code=400)
        if datetime.now() > entry["expires"]:
            del _reset_codes[email]
            return JSONResponse({"erro": "Código expirado. Solicite um novo."}, status_code=400)
        # Atualiza senha
        import hashlib
        senha_hash = hashlib.sha256(nova_senha.encode()).hexdigest()
        conn = banco._get_conn()
        cur = conn.cursor()
        ph = "%s" if banco._pg else "?"
        cur.execute(f"UPDATE usuarios SET senha_hash={ph} WHERE email={ph}", (senha_hash, email))
        conn.commit()
        conn.close()
        del _reset_codes[email]
        log(f"Senha redefinida para {email}", "auth")
        return JSONResponse({"ok": True, "msg": "Senha redefinida com sucesso!"})
    except Exception as e:
        log(f"Erro /redefinir_senha: {e}", "auth")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.post("/admin/plano")
async def admin_atualizar_plano(request: Request):
    """Admin: atualiza plano de um usuário"""
    try:
        data = await request.json()
        admin_key = data.get("key", "")
        if admin_key != "orbiby2026admin":
            return JSONResponse({"erro": "Não autorizado"}, status_code=401)
        user_id = data.get("user_id", "")
        plano = data.get("plano", "")
        if not user_id or not plano:
            return JSONResponse({"erro": "user_id e plano obrigatórios"}, status_code=400)
        banco.atualizar_plano(user_id, plano)
        # Se voltou pra free, limpar tokens de billing pra não restaurar
        if plano == 'free':
            try:
                conn_a = banco._get_conn()
                cur_a = conn_a.cursor()
                ph_a = "%s" if banco._pg else "?"
                cur_a.execute(f"UPDATE usuarios SET purchase_token=NULL, billing_product_id=NULL, billing_provider='free' WHERE user_id={ph_a}", (user_id,))
                conn_a.commit()
                if banco._pg: conn_a.close()
            except Exception as ea:
                log(f"Admin: erro limpando billing: {ea}", "admin")
        log(f"Admin: plano de {user_id} → {plano}", "admin")
        return JSONResponse({"ok": True, "msg": f"Plano atualizado para {plano}"})
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/uso/{user_id}")
def uso(user_id: str):
    """Retorna uso diário do usuário — para o frontend mostrar msgs restantes"""
    dados = banco.verificar_limite(user_id)
    # Adiciona msgs_extras explicitamente
    try:
        conn = banco._get_conn()
        c = conn.cursor()
        ph = "%s" if banco._pg else "?"
        c.execute(f"SELECT msgs_extras FROM usuarios WHERE user_id={ph}", (user_id,))
        row = c.fetchone()
        conn.close()
        dados["msgs_extras"] = row[0] if row and row[0] else 0
    except:
        dados["msgs_extras"] = 0
    return JSONResponse(dados)

@app.get("/agenda/{user_id}")
def agenda(user_id: str):
    return {"lembretes": banco.buscar_lembretes(user_id)}

@app.post("/reset_onboarding")
async def reset_onboarding(request: Request):
    data    = await request.json()
    user_id = data.get("user_id", "default")
    conn = banco._get_conn()
    c = conn.cursor()
    ph = "%s" if usar_postgres() else "?"
    c.execute(f'DELETE FROM config_assistente WHERE user_id={ph}', (user_id,))
    c.execute(f'DELETE FROM perfil_usuario WHERE user_id={ph}', (user_id,))
    c.execute(f'DELETE FROM resumos_sessao WHERE user_id={ph}', (user_id,))
    conn.commit()
    conn.close()
    sessoes.limpar(user_id)
    return {"ok": True, "msg": "Onboarding resetado"}

# ── MAIN ───────────────────────────────────────────────────────────────────────


# ── Google Play Billing — verificação de compra ───────────────────────────────
@app.post("/verificar_compra")
async def verificar_compra(request: Request):
    """Recebe purchaseToken do app, verifica com Google Play API, ativa plano."""
    try:
        body = await request.json()
        user_id = body.get("user_id", "")
        product_id = body.get("product_id", "")
        purchase_token = body.get("purchase_token", "")
        is_subscription = body.get("is_subscription", True)

        if not all([user_id, product_id, purchase_token]):
            return JSONResponse({"ok": False, "error": "Dados incompletos"}, status_code=400)

        log(f"[BILLING] Verificando: user={user_id} product={product_id} sub={is_subscription}", "billing")

        # Verificar com Google Play API
        api = _get_play_api()

        if is_subscription:
            result = api.purchases().subscriptionsv2().get(
                packageName=BILLING_PACKAGE,
                token=purchase_token
            ).execute()

            # subscriptionState: ACTIVE, CANCELED, EXPIRED, etc
            state = result.get("subscriptionState", "")
            log(f"[BILLING] Sub state: {state}", "billing")
            if state not in ["SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"]:
                log(f"[BILLING] Sub não ativa: {state}", "billing")
                return JSONResponse({"ok": False, "error": f"Assinatura não ativa: {state}"}, status_code=400)

            # Pegar product_id dos lineItems
            line_items = result.get("lineItems", [])
            actual_product = line_items[0].get("productId", product_id) if line_items else product_id

            # Mapear product_id → plano
            if actual_product == "pro_monthly":
                plano = "pro"
            elif actual_product == "pro_plus_monthly":
                plano = "pro_plus"
            else:
                plano = "pro"

            banco.atualizar_plano(user_id, plano)
            # Salvar purchase_token pra upgrade futuro
            try:
                conn2 = banco._get_conn()
                cur2 = conn2.cursor()
                ph2 = "%s" if banco._pg else "?"
                cur2.execute(f"UPDATE usuarios SET billing_provider='google_play', purchase_token={ph2}, billing_product_id={ph2} WHERE user_id={ph2}", (purchase_token, product_id, user_id))
                conn2.commit()
                if banco._pg: conn2.close()
            except Exception as e2:
                log(f"[BILLING] Erro salvando token: {e2}", "billing")
            log(f"[BILLING] Plano ativado: {user_id} → {plano}", "billing")
            return JSONResponse({"ok": True, "message": f"Plano {plano} ativado!"})

        else:
            # Produto consumível (extra_50)
            result = api.purchases().products().get(
                packageName=BILLING_PACKAGE,
                productId=product_id,
                token=purchase_token
            ).execute()

            purchase_state = result.get("purchaseState", -1)
            if purchase_state != 0:  # 0 = purchased
                log(f"[BILLING] Compra não confirmada: purchaseState={purchase_state}", "billing")
                return JSONResponse({"ok": False, "error": "Compra não confirmada"}, status_code=400)

            # Acknowledge se necessário
            if result.get("acknowledgementState", 0) == 0:
                try:
                    api.purchases().products().acknowledge(
                        packageName=BILLING_PACKAGE,
                        productId=product_id,
                        token=purchase_token,
                        body={}
                    ).execute()
                except Exception as ack_err:
                    log(f"[BILLING] Acknowledge erro (não fatal): {ack_err}", "billing")

            # Incrementar msgs_extras (+50)
            conn = banco._get_conn()
            try:
                cur = conn.cursor()
                ph = "%s" if banco._pg else "?"
                cur.execute(f"SELECT msgs_extras FROM usuarios WHERE user_id={ph}", (user_id,))
                row = cur.fetchone()
                atual = (row[0] or 0) if row else 0
                novo = atual + 50
                cur.execute(f"UPDATE usuarios SET msgs_extras={ph} WHERE user_id={ph}", (novo, user_id))
                conn.commit()
                log(f"[BILLING] Extras: {user_id} → +50 (total: {novo})", "billing")
            finally:
                if banco._pg:
                    conn.close()

            return JSONResponse({"ok": True, "message": f"50 consultas extras adicionadas! Total: {novo}"})

    except Exception as e:
        log(f"[BILLING] Erro: {e}", "billing")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
# ── Fim Google Play Billing endpoint ──────────────────────────────────────────


@app.get("/billing/token/{user_id}")
def billing_token(user_id: str):
    """Retorna purchase_token atual do usuário pra upgrade de plano."""
    try:
        conn = banco._get_conn()
        cur = conn.cursor()
        ph = "%s" if banco._pg else "?"
        cur.execute(f"SELECT purchase_token, billing_product_id, plano FROM usuarios WHERE user_id={ph}", (user_id,))
        row = cur.fetchone()
        if banco._pg: conn.close()
        if row and row[0]:
            return JSONResponse({"ok": True, "purchase_token": row[0], "product_id": row[1], "plano": row[2]})
        return JSONResponse({"ok": True, "purchase_token": None, "plano": row[2] if row else "free"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/billing/verificar_status")
async def billing_verificar_status(request: Request):
    """Verifica se assinatura do usuário ainda está ativa no Google Play."""
    try:
        body = await request.json()
        user_id = body.get("user_id", "")
        if not user_id:
            return JSONResponse({"ok": False, "error": "user_id obrigatório"}, status_code=400)

        # Buscar token salvo
        conn = banco._get_conn()
        cur = conn.cursor()
        ph = "%s" if banco._pg else "?"
        cur.execute(f"SELECT purchase_token, billing_product_id, plano, billing_provider FROM usuarios WHERE user_id={ph}", (user_id,))
        row = cur.fetchone()
        if banco._pg: conn.close()

        if not row:
            return JSONResponse({"ok": True, "plano": "free", "changed": False})

        purchase_token = row[0]
        product_id = row[1]
        plano_atual = row[2]
        provider = row[3]

        # Se não tem token ou não é google_play, nada a verificar
        if not purchase_token or provider != "google_play":
            return JSONResponse({"ok": True, "plano": plano_atual, "changed": False})

        # Se é plano free, nada a verificar
        if plano_atual in ["free", "admin"]:
            return JSONResponse({"ok": True, "plano": plano_atual, "changed": False})

        # Verificar com Google
        api = _get_play_api()
        try:
            result = api.purchases().subscriptionsv2().get(
                packageName=BILLING_PACKAGE,
                token=purchase_token
            ).execute()

            state = result.get("subscriptionState", "")
            log(f"[BILLING CHECK] {user_id}: state={state} plano={plano_atual}", "billing")

            # Estados ativos
            if state in ["SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"]:
                return JSONResponse({"ok": True, "plano": plano_atual, "changed": False})

            # Cancelado/expirado — rebaixar pra free
            banco.atualizar_plano(user_id, "free")
            log(f"[BILLING CHECK] Plano rebaixado: {user_id} → free (state={state})", "billing")
            return JSONResponse({"ok": True, "plano": "free", "changed": True, "reason": state})

        except Exception as google_err:
            log(f"[BILLING CHECK] Erro Google API: {google_err}", "billing")
            # Em caso de erro na API, mantém o plano atual (não punir o usuário)
            return JSONResponse({"ok": True, "plano": plano_atual, "changed": False})

    except Exception as e:
        log(f"[BILLING CHECK] Erro: {e}", "billing")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

if __name__ == "__main__":
    print("=" * 55)
    print("  MARGO SERVER v1.1 — by Orbiby")
    print("=" * 55)
    print(f"  Porta:  {PORT}")
    print(f"  Banco:  {'Postgres (Supabase)' if usar_postgres() else f'SQLite ({DB_FILE})'}")
    print(f"  DeepSeek key: {'OK' if DEEPSEEK_API_KEY else 'FALTANDO!'}")
    print("-" * 55)
    print("  Endpoints:")
    print("  POST /mensagem         — chat principal")
    print("  POST /falar            — TTS (Fish Audio / ElevenLabs / device)")
    print("  GET  /status/{user_id} — estado do usuário")
    print("  GET  /ping             — keep-alive")
    print("  POST /limpar_sessao    — encerra e resume sessão")
    print("  POST /salvar_voz       — configura voz customizada")
    print("  GET  /agenda/{user_id} — lembretes futuros")
    print("  POST /reset_onboarding — reseta (dev)")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
# deploy Fri Jul 17 15:35:12 JST 2026
