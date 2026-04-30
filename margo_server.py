#!/usr/bin/env python3
"""
margo_server.py — Margo Server v1.2
Assistente de IA com personalidade — produto comercial da Orbiby
"""

import os, re, json, time, sqlite3, threading
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import urllib.request
import uvicorn

MARGO_DIR  = os.path.expanduser("~/margo")
DB_FILE    = os.path.join(MARGO_DIR, "margo_memoria.db")
ESTADO_DIR = os.path.join(MARGO_DIR, "estado")
LOGS_DIR   = os.path.join(MARGO_DIR, "logs")
PORT       = 8000

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

def log(msg, arquivo="geral"):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  [{arquivo.upper()}] {msg}")
    with open(os.path.join(LOGS_DIR, f"{arquivo}.log"), "a") as f:
        f.write(f"[{agora}] {msg}\n")

# ── BANCO DE DADOS ────────────────────────────────────────────────────────────
class BancoMargo:
    def __init__(self):
        self.db_path = DB_FILE
        self.database_url = os.environ.get("DATABASE_URL", "")
        self.usar_postgres = bool(self.database_url)
        self._inicializar()

    def _get_conn(self):
        if self.usar_postgres:
            import psycopg2
            return psycopg2.connect(self.database_url)
        return sqlite3.connect(self.db_path)


    def _execute(self, query, params=(), fetchone=False, fetchall=False, commit=False):
        """Executa query compatível com SQLite e PostgreSQL"""
        if self.usar_postgres:
            query = query.replace("?", "%s")
            query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        conn = self._get_conn()
        try:
            if self.usar_postgres and (fetchone or fetchall):
                from psycopg2.extras import RealDictCursor
                c = conn.cursor(cursor_factory=RealDictCursor)
            else:
                if not self.usar_postgres:
                    conn.row_factory = sqlite3.Row
                c = conn.cursor()
            c.execute(query, params)
            if commit:
                conn.commit()
            if fetchone:
                row = c.fetchone()
                return dict(row) if row else {}
            if fetchall:
                return [dict(r) for r in c.fetchall()]
            return None
        finally:
            conn.close()

    def _inicializar(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            PK = "SERIAL PRIMARY KEY" if self.usar_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
            c.execute(f'''CREATE TABLE IF NOT EXISTS perfil_usuario (
                user_id TEXT PRIMARY KEY,
                nome TEXT, idade TEXT, profissao TEXT, musica TEXT,
                comida TEXT, hobbies TEXT, extra TEXT,
                criado_em TEXT, atualizado_em TEXT
            )''')
            c.execute(f'''CREATE TABLE IF NOT EXISTS config_assistente (
                user_id TEXT PRIMARY KEY,
                nome_assistente TEXT DEFAULT 'Margo',
                genero TEXT DEFAULT 'F',
                personalidade TEXT,
                voz_provider TEXT DEFAULT 'edge_tts',
                voz_chave TEXT,
                voz_id TEXT,
                onboarding_completo INTEGER DEFAULT 0,
                criado_em TEXT, atualizado_em TEXT
            )''')
            c.execute(f'''CREATE TABLE IF NOT EXISTS resumos_sessao (
                id {PK},
                user_id TEXT, resumo TEXT, criado_em TEXT
            )''')
            c.execute(f'''CREATE TABLE IF NOT EXISTS meta_resumos (
                id {PK},
                user_id TEXT, resumo TEXT, criado_em TEXT
            )''')
            c.execute(f'''CREATE TABLE IF NOT EXISTS agenda (
                id {PK},
                user_id TEXT, titulo TEXT, descricao TEXT, data_hora TEXT,
                lembrado_1d INTEGER DEFAULT 0, lembrado_3h INTEGER DEFAULT 0,
                criado_em TEXT
            )''')
            conn.commit()
        finally:
            conn.close()

    def salvar_perfil(self, user_id, dados):
        agora = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO perfil_usuario
                (user_id, nome, idade, profissao, musica, comida, hobbies, extra, criado_em, atualizado_em)
                VALUES (?,?,?,?,?,?,?,?,
                        COALESCE((SELECT criado_em FROM perfil_usuario WHERE user_id=?), ?), ?)''',
                (user_id,
                 dados.get("nome",""), dados.get("idade",""), dados.get("profissao",""),
                 dados.get("musica",""), dados.get("comida",""), dados.get("hobbies",""),
                 dados.get("extra",""), user_id, agora, agora))
            conn.commit()
        finally:
            conn.close()

    def buscar_perfil(self, user_id):
        conn = self._get_conn()
        try:
            if self.usar_postgres:
                from psycopg2.extras import RealDictCursor
                c = conn.cursor(cursor_factory=RealDictCursor)
                c.execute('SELECT * FROM perfil_usuario WHERE user_id=%s', (user_id,))
            else:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute('SELECT * FROM perfil_usuario WHERE user_id=?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def salvar_config(self, user_id, dados):
        agora = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO config_assistente
                (user_id, nome_assistente, genero, personalidade, voz_provider,
                 voz_chave, voz_id, onboarding_completo, criado_em, atualizado_em)
                VALUES (?,?,?,?,?,?,?,?,
                        COALESCE((SELECT criado_em FROM config_assistente WHERE user_id=?), ?), ?)''',
                (user_id,
                 dados.get("nome_assistente","Margo"), dados.get("genero","F"),
                 dados.get("personalidade",""), dados.get("voz_provider","edge_tts"),
                 dados.get("voz_chave",""), dados.get("voz_id",""),
                 1 if dados.get("onboarding_completo") else 0,
                 user_id, agora, agora))
            conn.commit()
        finally:
            conn.close()

    def buscar_config(self, user_id):
        conn = self._get_conn()
        try:
            if self.usar_postgres:
                from psycopg2.extras import RealDictCursor
                c = conn.cursor(cursor_factory=RealDictCursor)
                c.execute('SELECT * FROM config_assistente WHERE user_id=%s', (user_id,))
            else:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute('SELECT * FROM config_assistente WHERE user_id=?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def salvar_resumo(self, user_id, resumo):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM resumos_sessao WHERE user_id=?', (user_id,))
            if c.fetchone()[0] >= 5:
                c.execute('''DELETE FROM resumos_sessao WHERE id=(
                    SELECT id FROM resumos_sessao WHERE user_id=? ORDER BY criado_em ASC LIMIT 1)''', (user_id,))
            c.execute('INSERT INTO resumos_sessao (user_id, resumo, criado_em) VALUES (?,?,?)',
                      (user_id, resumo[:100], datetime.now().isoformat()))
            conn.commit()
        finally:
            conn.close()

    def buscar_resumos(self, user_id):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT resumo FROM resumos_sessao WHERE user_id=? ORDER BY criado_em DESC LIMIT 10', (user_id,))
            return [r[0] for r in c.fetchall()]
        finally:
            conn.close()

    def buscar_meta_resumos(self, user_id):
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute('SELECT resumo FROM meta_resumos WHERE user_id=? ORDER BY criado_em DESC LIMIT 5', (user_id,))
            return [r[0] for r in c.fetchall()]
        finally:
            conn.close()

    def salvar_lembrete(self, user_id, titulo, descricao, data_hora):
        conn = self._get_conn()
        try:
            conn.cursor().execute(
                'INSERT INTO agenda (user_id, titulo, descricao, data_hora, criado_em) VALUES (?,?,?,?,?)',
                (user_id, titulo, descricao, data_hora, datetime.now().isoformat()))
            conn.commit()
        finally:
            conn.close()

    def buscar_lembretes(self, user_id):
        conn = self._get_conn()
        try:
            if self.usar_postgres:
                from psycopg2.extras import RealDictCursor
                c = conn.cursor(cursor_factory=RealDictCursor)
                c.execute('SELECT * FROM agenda WHERE user_id=%s AND data_hora > %s ORDER BY data_hora ASC',
                          (user_id, datetime.now().isoformat()))
            else:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute('SELECT * FROM agenda WHERE user_id=? AND data_hora > ? ORDER BY data_hora ASC',
                          (user_id, datetime.now().isoformat()))
            return [dict(r) for r in c.fetchall()]
        finally:
            conn.close()

    def lembretes_proximos(self, user_id):
        agora = datetime.now()
        res = []
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('SELECT * FROM agenda WHERE user_id=?', (user_id,))
            for row in c.fetchall():
                item = dict(row)
                try:
                    dt = datetime.fromisoformat(item["data_hora"])
                    diff = (dt - agora).total_seconds() / 3600
                    if 0 < diff <= 3 and not item["lembrado_3h"]:
                        res.append({**item, "tipo": "3h"})
                        conn.cursor().execute('UPDATE agenda SET lembrado_3h=1 WHERE id=?', (item["id"],))
                    elif 20 < diff <= 25 and not item["lembrado_1d"]:
                        res.append({**item, "tipo": "1d"})
                        conn.cursor().execute('UPDATE agenda SET lembrado_1d=1 WHERE id=?', (item["id"],))
                except:
                    pass
            conn.commit()
        finally:
            conn.close()
        return res

banco = BancoMargo()

# ── SESSÃO ────────────────────────────────────────────────────────────────────
class SessaoUsuario:
    def __init__(self):
        self._sessoes = {}
        self._lock = threading.Lock()

    def adicionar(self, user_id, user_msg, assistant_msg):
        with self._lock:
            if user_id not in self._sessoes:
                self._sessoes[user_id] = deque(maxlen=20)
            self._sessoes[user_id].append({"user": user_msg[:200], "assistant": assistant_msg[:200]})

    def get_historico(self, user_id):
        with self._lock:
            return list(self._sessoes.get(user_id, []))

    def limpar(self, user_id):
        with self._lock:
            self._sessoes.pop(user_id, None)

    def resumir_e_limpar(self, user_id):
        hist = self.get_historico(user_id)
        if not hist:
            return
        txt = " | ".join([f"U:{i['user']} A:{i['assistant']}" for i in hist])
        resumo = chamar_deepseek_simples(f"Resuma em 1 frase (max 100 chars): {txt[:600]}", max_tokens=80)
        if resumo:
            banco.salvar_resumo(user_id, resumo)
        self.limpar(user_id)

sessoes = SessaoUsuario()

# ── DEEPSEEK ──────────────────────────────────────────────────────────────────
def chamar_deepseek_simples(mensagem, max_tokens=150):
    try:
        body = json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": mensagem}],
            "temperature": 0.4,
            "max_tokens": max_tokens
        }).encode()
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"})
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
        }).encode()
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"})
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"DeepSeek erro: {e}")
        return "Desculpe, tive um problema. Pode repetir?"

# ── ONBOARDING ────────────────────────────────────────────────────────────────
ETAPAS = [
    ("nome",            "Qual é o seu nome?"),
    ("idade",           "Quantos anos você tem?"),
    ("profissao",       "O que você faz da vida?"),
    ("musica",          "Que tipo de música você curte?"),
    ("comida",          "Qual é a sua comida favorita?"),
    ("hobbies",         "O que você gosta de fazer no tempo livre?"),
    ("extra",           "Mais algo que queira contar? (opcional, pode pular)"),
    ("nome_assistente", "Como quer me chamar? (pode ser Margo)"),
    ("genero",          "Prefere voz feminina ou masculina?"),
    ("personalidade",   "Me descreva em até 3 palavras (ex: divertida, objetiva, carinhosa)")
]

def etapa_atual(perfil, config={}):
    for i, (chave, _) in enumerate(ETAPAS):
        if chave in ["nome_assistente", "genero", "personalidade"]:
            if not config.get(chave, "").strip():
                return i
        else:
            if not perfil.get(chave, "").strip():
                return i
    return len(ETAPAS)

def extrair_valor(chave, resposta, pergunta):
    if chave == "genero":
        r = resposta.lower().strip()
        if any(p in r for p in ["masculi", "homem", "menino", "masculina", "masculino"]):
            return "M"
        return "F"
    if chave == "nome_assistente":
        val = chamar_deepseek_simples(
            f"O usuário respondeu: '{resposta}'. Extraia APENAS o nome próprio do assistente (1 palavra). "
            f"Se não houver nome claro ou disser Margo, responda: Margo. Responda APENAS o nome.", max_tokens=10)
        return (val or "Margo").strip().split()[0]
    if chave == "extra":
        if any(w in resposta.lower() for w in ["não", "nao", "nada", "pular", "skip", "passar"]):
            return "-"
        return resposta.strip() or "-"
    val = chamar_deepseek_simples(
        f"Pergunta: '{pergunta}'\nResposta: '{resposta}'\n"
        f"Extraia apenas o valor pedido, conciso (máx 50 chars). Só o valor.", max_tokens=40)
    return (val or resposta).strip()[:100]

def gerar_resposta_etapa(chave, valor, proxima_pergunta, perfil, fim=False):
    if fim:
        nome = perfil.get("nome", "você")
        assistente = perfil.get("nome_assistente", "Margo")
        return chamar_deepseek_simples(
            f"Usuário {nome} terminou o onboarding e quer te chamar de {assistente}. "
            f"Diga algo caloroso e animado, máx 2 frases, sem markdown.", max_tokens=80
        ) or f"Tudo pronto, {nome}! Agora sou sua {assistente} e estou aqui pra te ajudar!"

    confirmacoes = {
        "nome":            f"Que nome bonito, {valor}!",
        "idade":           "Anotado!",
        "profissao":       "Interessante!",
        "musica":          "Bom gosto!",
        "comida":          "Ótimo!",
        "hobbies":         "Legal!",
        "extra":           "Obrigada por compartilhar!" if valor != "-" else "Tudo bem!",
        "nome_assistente": f"Pode me chamar de {valor}!",
        "genero":          "Perfeito!",
        "personalidade":   "Vou ser exatamente assim!",
    }
    confirmacao = confirmacoes.get(chave, "Anotado!")
    return f"{confirmacao} {proxima_pergunta}"


# ── MODO TRADUTOR ─────────────────────────────────────────────────────────────

TRADUTOR_FILE = "/tmp/margo_modo_tradutor"
_tradutor_estado = {"aguardando_idiomas": False}

def tradutor_ativo():
    return os.path.exists(TRADUTOR_FILE)

def tradutor_idiomas():
    try:
        with open(TRADUTOR_FILE) as f:
            dados = json.load(f)
        return dados.get("idioma_origem",""), dados.get("idioma_destino","")
    except:
        return "", ""

def ativar_tradutor(idioma_origem, idioma_destino):
    with open(TRADUTOR_FILE, "w") as f:
        json.dump({"idioma_origem": idioma_origem, "idioma_destino": idioma_destino}, f)
    _tradutor_estado["aguardando_idiomas"] = False

def desativar_tradutor():
    if os.path.exists(TRADUTOR_FILE):
        os.remove(TRADUTOR_FILE)
    _tradutor_estado["aguardando_idiomas"] = False

def traduzir_texto(texto, idioma_origem, idioma_destino):
    return chamar_deepseek_simples(
        f"Traduza o texto abaixo entre {idioma_origem} e {idioma_destino}. "
        f"Se estiver em {idioma_origem}, traduza para {idioma_destino}. "
        f"Se estiver em {idioma_destino}, traduza para {idioma_origem}. "
        f"Responda APENAS com a traducao:\n\n{texto}",
        max_tokens=500
    ) or texto

def detectar_intencao_tradutor(mensagem):
    msg = mensagem.lower()
    desativar = any(p in msg for p in ["desativar", "desative", "desligar", "desligue", "parar", "pare"])
    ativar = any(p in msg for p in ["ativar", "ative", "ligar", "ligue", "modo tradutor", "tradutor"])
    if desativar and "tradutor" in msg:
        return "desativar"
    if ativar and "tradutor" in msg:
        return "ativar"
    return None

def processar_mensagem(user_id, mensagem):
    config = banco.buscar_config(user_id)
    perfil = banco.buscar_perfil(user_id)

    # ── MODO TRADUTOR ─────────────────────────────────────────────────────────
    if _tradutor_estado["aguardando_idiomas"]:
        idiomas = chamar_deepseek_simples("Extraia os dois idiomas da frase. Responda so JSON com origem e destino. Frase: " + mensagem, max_tokens=40)
        try:
            dados = json.loads(idiomas.strip())
            ativar_tradutor(dados.get("origem","portugues"), dados.get("destino","ingles"))
            return {"resposta": f"Tradutor ativado! Traduzindo entre {dados.get('origem')} e {dados.get('destino')}. Pode falar!", "onboarding": False, "ferramenta": None}
        except:
            return {"resposta": "Não entendi os idiomas. Ex: português e inglês", "onboarding": False, "ferramenta": None}

    intencao = detectar_intencao_tradutor(mensagem)
    if intencao == "desativar":
        desativar_tradutor()
        return {"resposta": "Modo tradutor desativado!", "onboarding": False, "ferramenta": None}
    if intencao == "ativar":
        _tradutor_estado["aguardando_idiomas"] = True
        return {"resposta": "Claro! Quais idiomas quer traduzir?", "onboarding": False, "ferramenta": None}

    if tradutor_ativo():
        origem, destino = tradutor_idiomas()
        traducao = traduzir_texto(mensagem, origem, destino)
        return {"resposta": traducao, "onboarding": False, "ferramenta": None}

    # ── ONBOARDING ─────────────────────────────────────────────────────────────
    if not config.get("onboarding_completo"):
        idx = etapa_atual(perfil, config)
        historico = sessoes.get_historico(user_id)

        # Primeira mensagem — apresentação
        if idx == 0 and not historico:
            resp = "Oi! Sou a Margo, prazer! Antes de começarmos, qual é o seu nome?"
            sessoes.adicionar(user_id, mensagem, resp)
            return {"resposta": resp, "onboarding": True, "ferramenta": None}

        # Extrai e salva valor da etapa atual
        if idx < len(ETAPAS):
            chave, pergunta = ETAPAS[idx]
            valor = extrair_valor(chave, mensagem, pergunta)
            if chave in ["nome_assistente", "genero", "personalidade"]:
                config_atual = banco.buscar_config(user_id)
                config_atual[chave] = valor
                banco.salvar_config(user_id, config_atual)
            else:
                banco.salvar_perfil(user_id, {**perfil, chave: valor})
                perfil = banco.buscar_perfil(user_id)
            idx += 1

        # Onboarding completo
        if idx >= len(ETAPAS):
            banco.salvar_config(user_id, {
                "nome_assistente":     perfil.get("nome_assistente", "Margo"),
                "genero":              perfil.get("genero", "F"),
                "personalidade":       perfil.get("personalidade", "gentil, prestativa e inteligente"),
                "onboarding_completo": True
            })
            resp = gerar_resposta_etapa(chave, valor, "", perfil, fim=True)
            sessoes.adicionar(user_id, mensagem, resp)
            log(f"Onboarding concluído: {user_id}", "onboarding")
            return {"resposta": resp, "onboarding": False, "ferramenta": None}

        # Próxima pergunta
        prox_chave, prox_pergunta = ETAPAS[idx]
        resp = gerar_resposta_etapa(chave, valor, prox_pergunta, perfil)
        sessoes.adicionar(user_id, mensagem, resp)
        return {"resposta": resp, "onboarding": True, "ferramenta": None}

    # ── MODO NORMAL ────────────────────────────────────────────────────────────
    historico = sessoes.get_historico(user_id)
    resumos   = banco.buscar_resumos(user_id)
    lembretes = banco.lembretes_proximos(user_id)

    ctx_extra = ""
    meta_resumos = banco.buscar_meta_resumos(user_id)
    if meta_resumos:
        ctx_extra += "\nHistorico profundo:\n" + "\n".join(f"- {r}" for r in meta_resumos)
    if resumos:
        ctx_extra += "\nConversas recentes:\n" + "\n".join(f"- {r}" for r in resumos)
    if lembretes:
        for l in lembretes:
            ctx_extra += f"\n[LEMBRETE AGORA] {l['titulo']} — {l['tipo']}"

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    system = f"""Você é {config.get('nome_assistente','Margo')}, assistente pessoal de {perfil.get('nome','você')}.
Data e hora atual: {agora} — use para calcular datas relativas como amanhã, depois, semana que vem.
Personalidade: {config.get('personalidade','gentil, prestativa e inteligente')}
Importante: expresse sua personalidade de forma natural. Se for flertadora, solte um elogio ou comentário levemente insinuante de vez em quando — sutil, não exagerado.
Perfil: música={perfil.get('musica','?')}, comida={perfil.get('comida','?')}, hobbies={perfil.get('hobbies','?')}
Responda de forma natural, curta e direta. Sem markdown. Sem asteriscos.{ctx_extra}

FERRAMENTAS — OBRIGATORIO usar JSON quando detectar a intenção. Coloque o JSON no inicio da resposta, antes do texto:
{{"ferramenta":"maps_navigate","destino":"..."}}
{{"ferramenta":"spotify_play","query":"..."}}
{{"ferramenta":"soundcloud_play","query":"..."}}
{{"ferramenta":"maps_search","query":"..."}}
{{"ferramenta":"phone_call","contato":"..."}}
{{"ferramenta":"agenda_add","titulo":"...","descricao":"...","data_hora":"ISO8601"}}
{{"ferramenta":"agenda_list"}}
{{"ferramenta":"smart_home","acao":"ligar|desligar","dispositivo":"..."}}
{{"ferramenta":"web_search","query":"..."}}
{{"ferramenta":"youtube_search","query":"..."}}"""

    resposta = chamar_deepseek(system, mensagem, historico)

    # Extrai ferramenta se houver
    tool_json = None
    match = re.search(r'\{[^{}]*"ferramenta"[^{}]*\}', resposta)
    if match:
        try:
            tool_json = json.loads(match.group(0))
            resposta = resposta.replace(match.group(0), "").strip()
            if tool_json.get("ferramenta") == "agenda_add":
                banco.salvar_lembrete(user_id,
                    tool_json.get("titulo",""), tool_json.get("descricao",""), tool_json.get("data_hora",""))
        except:
            pass

    sessoes.adicionar(user_id, mensagem, resposta)
    return {"resposta": resposta, "onboarding": False, "ferramenta": tool_json}

# ── FASTAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Margo Server v1.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True, expose_headers=["*"])

@app.get("/ping")
def ping():
    return {"pong": True, "ts": datetime.now().isoformat()}

@app.get("/testar_voz")
def testar_voz():
    import subprocess, tempfile, os
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        result = subprocess.run(
            ["edge-tts", "--voice", "pt-BR-FranciscaNeural", "--text", "teste", "--write-media", tmp],
            capture_output=True, text=True, timeout=30
        )
        tamanho = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        return {"ok": result.returncode == 0, "tamanho": tamanho, "stderr": result.stderr[:200]}
    except Exception as e:
        return {"erro": str(e)}

@app.post("/mensagem")
async def mensagem(req: Request):
    try:
        data = await req.json()
        user_id = data.get("user_id", "default")
        msg = data.get("mensagem", "").strip()
        if not msg:
            return JSONResponse({"erro": "mensagem vazia"}, status_code=400)
        return JSONResponse(processar_mensagem(user_id, msg))
    except Exception as e:
        log(f"Erro /mensagem: {e}")
        return JSONResponse({"erro": str(e)}, status_code=500)

@app.get("/status/{user_id}")
def status(user_id: str):
    c = banco.buscar_config(user_id)
    p = banco.buscar_perfil(user_id)
    return {
        "user_id":             user_id,
        "nome":                p.get("nome", ""),
        "assistente":          c.get("nome_assistente", "Margo"),
        "onboarding_completo": bool(c.get("onboarding_completo", 0))
    }

@app.post("/limpar_sessao")
async def limpar(req: Request):
    data = await req.json()
    sessoes.resumir_e_limpar(data.get("user_id", "default"))
    return {"ok": True}

@app.post("/salvar_voz")
async def salvar_voz(req: Request):
    data = await req.json()
    user_id = data.get("user_id", "default")
    config_atual = banco.buscar_config(user_id)
    config_atual.update({
        "voz_provider": data.get("provider", "edge_tts"),
        "voz_chave":    data.get("chave", ""),
        "voz_id":       data.get("voz_id", ""),
    })
    banco.salvar_config(user_id, config_atual)
    return {"ok": True}

@app.get("/agenda/{user_id}")
def agenda(user_id: str):
    return {"lembretes": banco.buscar_lembretes(user_id)}

@app.post("/reset_onboarding")
async def reset(req: Request):
    data = await req.json()
    u = data.get("user_id", "default")
    conn = banco._get_conn()
    try:
        c = conn.cursor()
        c.execute('DELETE FROM config_assistente WHERE user_id=?', (u,))
        c.execute('DELETE FROM perfil_usuario WHERE user_id=?', (u,))
        c.execute('DELETE FROM resumos_sessao WHERE user_id=?', (u,))
        conn.commit()
    finally:
        conn.close()
    sessoes.limpar(u)
    return {"ok": True, "msg": "Onboarding resetado"}

@app.post("/falar")
async def falar(req: Request):
    import edge_tts, aiofiles, tempfile, base64
    from asyncio import timeout as asyncio_timeout
    data = await req.json()
    texto = data.get("texto", "").strip()
    if not texto:
        return JSONResponse({"erro": "texto vazio"}, status_code=400)
    user_id = data.get("user_id", "default")
    config = banco.buscar_config(user_id)
    provider = config.get("voz_provider", "edge_tts")
    voz_id = config.get("voz_id", "") or ("pt-BR-FranciscaNeural" if config.get("genero","F") == "F" else "pt-BR-AntonioNeural")
    genero = data.get("genero", config.get("genero", "F"))
    if not voz_id:
        voz_id = "pt-BR-FranciscaNeural" if genero == "F" else "pt-BR-AntonioNeural"
    if provider == "edge_tts" or not config.get("voz_chave"):
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                caminho = tmp.name
            async with asyncio_timeout(30):
                communicate = edge_tts.Communicate(texto, voz_id)
                await communicate.save(caminho)
            async with aiofiles.open(caminho, "rb") as f:
                audio_bytes = await f.read()
            os.unlink(caminho)
            if len(audio_bytes) < 100:
                log(f"Audio vazio gerado: {len(audio_bytes)} bytes")
                return JSONResponse({"erro": "audio gerado vazio"}, status_code=500)
            return JSONResponse({"ok": True, "audio_base64": base64.b64encode(audio_bytes).decode("utf-8")})
        except Exception as e:
            log(f"Voz erro: {e}")
            return JSONResponse({"erro": str(e)}, status_code=500)
    return JSONResponse({"erro": "provedor nao implementado"}, status_code=501)

if __name__ == "__main__":
    print("=" * 50)
    print("  MARGO SERVER v1.2 — by Orbiby")
    print("=" * 50)
    print(f"  DeepSeek key: {'OK' if DEEPSEEK_API_KEY else 'FALTANDO!'}")
    print(f"  Banco: {DB_FILE}")
    print("=" * 50)
    threading.Thread(target=verificar_lembretes, daemon=True).start()
    print("  Scheduler: ativo")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
