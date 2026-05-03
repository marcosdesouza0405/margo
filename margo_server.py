#!/usr/bin/env python3
"""
margo_server.py — Margo Server v1.2
Assistente de IA com personalidade — produto comercial da Orbiby
Arquitetura: FastAPI + DeepSeek + SQLite/Postgres + Fish Audio / ElevenLabs / Web Speech
"""

import os, re, json, time, sqlite3, threading, asyncio, base64
from datetime import datetime, timedelta
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import urllib.request
import urllib.parse
import uvicorn

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

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DATABASE_URL     = os.environ.get("DATABASE_URL", "")
BRAVE_API_KEY    = os.environ.get("BRAVE_API_KEY", "")

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
            return self._psycopg2.connect(self._conn_str)
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

        # ── TABELA USUARIOS (base para login + cobrança futura) ────────────────
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            nome TEXT,
            plano TEXT DEFAULT 'free',
            status TEXT DEFAULT 'ativo',
            senha_hash TEXT,
            email_verificado INTEGER DEFAULT 0,
            stripe_customer_id TEXT,
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
        if count >= 5:
            if self._pg:
                c.execute(f'DELETE FROM resumos_sessao WHERE id = (SELECT id FROM resumos_sessao WHERE user_id={ph} ORDER BY criado_em ASC LIMIT 1)', (user_id,))
            else:
                c.execute('DELETE FROM resumos_sessao WHERE id = (SELECT id FROM resumos_sessao WHERE user_id=? ORDER BY criado_em ASC LIMIT 1)', (user_id,))
        resumo_curto = resumo[:100]
        c.execute(f'INSERT INTO resumos_sessao (user_id, resumo, criado_em) VALUES ({ph},{ph},{ph})',
                  (user_id, resumo_curto, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def buscar_resumos(self, user_id) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'SELECT resumo FROM resumos_sessao WHERE user_id={ph} ORDER BY criado_em DESC LIMIT 5', (user_id,))
        result = [r[0] for r in c.fetchall()]
        conn.close()
        return result

    # ── AGENDA ─────────────────────────────────────────────────────────────────

    def salvar_lembrete(self, user_id, titulo, descricao, data_hora):
        conn = self._get_conn()
        c = conn.cursor()
        ph = "%s" if self._pg else "?"
        c.execute(f'INSERT INTO agenda (user_id, titulo, descricao, data_hora, criado_em) VALUES ({ph},{ph},{ph},{ph},{ph})',
                  (user_id, titulo, descricao, data_hora, datetime.now().isoformat()))
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
        log_txt = " | ".join([f"U:{i['user']} A:{i['assistant']}" for i in historico])
        resumo = chamar_deepseek_simples(
            f"Resuma em 1 frase (max 100 chars) essa conversa: {log_txt[:600]}",
            max_tokens=80
        )
        if resumo:
            banco.salvar_resumo(user_id, resumo)
        self.limpar(user_id)

sessoes = SessaoUsuario()

# ── BRAVE SEARCH ──────────────────────────────────────────────────────────────

def buscar_brave(query: str, max_results: int = 3) -> str:
    """Chama Brave Search e retorna resumo dos resultados para o DeepSeek usar."""
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

def chamar_deepseek_simples(mensagem, max_tokens=150):
    try:
        body = json.dumps({
            "model": "deepseek-chat",
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
        resp = urllib.request.urlopen(req, timeout=20)
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
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
            "model": "deepseek-chat",
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
    pronome = "ela" if genero == "F" else "ele"

    return f"""Você é {nome_assistente}, assistente pessoal de {nome_usuario}.

===============================================================================
SUA PERSONALIDADE
===============================================================================
{personalidade}

Você é {"calorosa" if genero == "F" else "caloroso"}, inteligente e {"prestativa" if genero == "F" else "prestativo"}.
Fala de forma natural, direta e com leveza — como um amigo próximo e confiável.
Nunca usa markdown, asteriscos ou formatação estranha. Só texto simples.
Respostas curtas e diretas — máximo 3-4 frases, exceto quando o usuário pede detalhes.

===============================================================================
QUEM É {nome_usuario.upper()}
===============================================================================
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

MÚSICA — "toca", "coloca uma música", "coloca no spotify", "quero ouvir":
{{"ferramenta": "spotify_play", "query": "artista ou música ou playlist"}}
{{"ferramenta": "soundcloud_play", "query": "artista ou música"}}
→ Prefira Spotify. Use SoundCloud só se o usuário pedir explicitamente.

BUSCA LOCAL — "tem restaurante", "onde posso", "procura um lugar":
{{"ferramenta": "maps_search", "query": "tipo de lugar"}}

CHAMADA — "liga para", "chama o/a":
{{"ferramenta": "phone_call", "contato": "nome ou número"}}

AGENDA — "me lembra de", "agenda isso", "quais meus compromissos":
{{"ferramenta": "agenda_add", "titulo": "...", "descricao": "...", "data_hora": "ISO8601"}}
{{"ferramenta": "agenda_list"}}

CASA INTELIGENTE — "apaga a luz", "liga o ar", "coloca o termostato":
{{"ferramenta": "smart_home", "acao": "ligar|desligar|ajustar", "dispositivo": "...", "valor": "..."}}

PESQUISA WEB — "pesquisa", "o que é", "me fala sobre":
{{"ferramenta": "web_search", "query": "..."}}

YOUTUBE — "abre um vídeo", "coloca no youtube":
{{"ferramenta": "youtube_search", "query": "..."}}

EXEMPLOS CORRETOS:
Usuário: "coloca no spotify um sertanejo"
Você: {{"ferramenta": "spotify_play", "query": "sertanejo"}}
Colocando sertanejo pra você!

Usuário: "traça a rota pra casa"
Você: {{"ferramenta": "maps_navigate", "destino": "casa"}}
Rota traçada, pode ir!

===============================================================================
ESTILO DE RESPOSTA
===============================================================================

- SEMPRE emita o JSON antes do texto quando for usar uma ferramenta
- Se não sabe: fale honestamente, ofereça pesquisar
- Sempre no idioma que o usuário usou
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
    return texto.strip()

def extrair_ferramenta(texto):
    match = re.search(r'\{[^{}]*"ferramenta"[^{}]*\}', texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
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

def processar_mensagem(user_id, mensagem):
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

    # ── MODO NORMAL ────────────────────────────────────────────────────────────
    historico = sessoes.get_historico(user_id)
    resumos   = banco.buscar_resumos(user_id)
    lembretes = banco.lembretes_proximos(user_id)

    contexto_extra = ""
    if resumos:
        contexto_extra += "\nConversas anteriores:\n" + "\n".join(f"- {r}" for r in resumos)
    if lembretes:
        for l in lembretes:
            contexto_extra += f"\n[LEMBRETE AGORA] {l['titulo']} — {l['tipo']}"

    system = build_system_prompt(perfil, config)
    if contexto_extra:
        system += f"\n\n{contexto_extra}"

    resposta = chamar_deepseek(system, mensagem, historico, max_tokens=500)

    ferramenta = extrair_ferramenta(resposta)
    if ferramenta:
        resposta = re.sub(r'\{[^{}]*"ferramenta"[^{}]*\}', '', resposta).strip()

        # ── WEB SEARCH: busca real e resposta enriquecida ───────────────────────
        if ferramenta.get("ferramenta") == "web_search" and BRAVE_API_KEY:
            query = ferramenta.get("query", mensagem)
            log(f"Brave Search: {query}", "busca")
            resultados = buscar_brave(query)
            if resultados:
                # Manda os resultados pro DeepSeek formular uma resposta natural
                prompt_busca = f"""O usuário perguntou: "{mensagem}"

Aqui estão os resultados da busca na internet:
{resultados}

Responda de forma natural e conversacional em português, usando essas informações.
Seja conciso — máximo 3 frases. Não cite as fontes explicitamente."""
                resposta = chamar_deepseek_simples(prompt_busca, max_tokens=300) or resposta

        # ── AGENDA ─────────────────────────────────────────────────────────────
        elif ferramenta.get("ferramenta") == "agenda_add":
            banco.salvar_lembrete(
                user_id,
                ferramenta.get("titulo", "Compromisso"),
                ferramenta.get("descricao", ""),
                ferramenta.get("data_hora", "")
            )

    sessoes.adicionar(user_id, mensagem, resposta)
    return {
        "resposta":   limpar_resposta(resposta),
        "onboarding": False,
        "ferramenta": ferramenta
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
                "Content-Type": "application/json"
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
    return {"status": "online", "app": "Margo by Orbiby", "versao": "1.4.0",
            "banco": "postgres" if usar_postgres() else "sqlite",
            "busca": "brave" if BRAVE_API_KEY else "desabilitada"}

@app.get("/ping")
def ping():
    return {"pong": True, "ts": datetime.now().isoformat()}

@app.post("/login")
async def login(request: Request):
    """
    Cadastro ou login por email.
    Body: { email, nome }
    Retorna: { user_id, email, nome, plano, novo (bool), tem_perfil (bool) }
    """
    try:
        data  = await request.json()
        email = data.get("email", "").strip().lower()
        nome  = data.get("nome", "").strip()

        if not email or "@" not in email:
            return JSONResponse({"erro": "Email inválido"}, status_code=400)

        usuario = banco.cadastrar_ou_login(email, nome)
        user_id = usuario["user_id"]

        # Verifica se já tem perfil configurado
        perfil = banco.buscar_perfil(user_id)
        config = banco.buscar_config(user_id)
        tem_perfil = bool(perfil.get("nome") and config.get("onboarding_completo"))

        return JSONResponse({
            "ok":       True,
            "user_id":  user_id,
            "email":    usuario.get("email", email),
            "nome":     usuario.get("nome", nome),
            "plano":    usuario.get("plano", "free"),
            "novo":     usuario.get("novo", False),
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
        if not mensagem_:
            return JSONResponse({"erro": "mensagem vazia"}, status_code=400)
        resultado = processar_mensagem(user_id, mensagem_)
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
            "nome":     data.get("nome", "").strip(),
            "idade":    data.get("idade", "").strip(),
            "profissao":data.get("profissao", "").strip(),
            "musica":   data.get("musica", "").strip(),
            "comida":   data.get("comida", "").strip(),
            "hobbies":  data.get("hobbies", "").strip(),
            "extra":    data.get("extra", "").strip(),
        })

        # Salva config da assistente
        banco.salvar_config(user_id, {
            "nome_assistente":     data.get("nome_assistente", "Margo").strip(),
            "genero":              data.get("genero", "F"),
            "personalidade":       data.get("personalidade", "").strip(),
            "voz_provider":        data.get("voz_provider", "device"),
            "voz_chave":           data.get("voz_chave", "").strip(),
            "voz_id":              data.get("voz_id", "").strip(),
            "onboarding_completo": True,
        })

        log(f"Perfil completo salvo para {user_id}", "perfil")
        return JSONResponse({"ok": True})
    except Exception as e:
        log(f"Erro /salvar_perfil_completo: {e}")
        return JSONResponse({"erro": str(e)}, status_code=500)

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
