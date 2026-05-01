#!/usr/bin/env python3
"""
margo_server.py — Margo Server v1.0
Assistente de IA com personalidade — produto comercial da Orbiby
Arquitetura: FastAPI + DeepSeek + SQLite + Edge TTS
"""

import os, re, json, time, sqlite3, threading, asyncio
from datetime import datetime, timedelta
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import urllib.request
import uvicorn

# ── CONFIG ─────────────────────────────────────────────────────────────────────

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

# ── LOG ────────────────────────────────────────────────────────────────────────

def log(msg, arquivo="geral"):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] {msg}"
    print(f"  [{arquivo.upper()}] {msg}")
    with open(os.path.join(LOGS_DIR, f"{arquivo}.log"), "a") as f:
        f.write(linha + "\n")

# ── BANCO DE DADOS ─────────────────────────────────────────────────────────────

class BancoMargo:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._inicializar()

    def _inicializar(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()

            # Perfil permanente do usuário (max 500 chars)
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

            # Configuração do assistente personalizado
            c.execute('''CREATE TABLE IF NOT EXISTS config_assistente (
                user_id TEXT PRIMARY KEY,
                nome_assistente TEXT DEFAULT "Margo",
                genero TEXT DEFAULT "F",
                personalidade TEXT,
                voz_provider TEXT DEFAULT "edge_tts",
                voz_chave TEXT,
                voz_id TEXT,
                onboarding_completo INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT
            )''')

            # Resumos de sessão (max 5 por usuário, 100 chars cada)
            c.execute('''CREATE TABLE IF NOT EXISTS resumos_sessao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                resumo TEXT,
                criado_em TEXT
            )''')

            # Agenda e lembretes
            c.execute('''CREATE TABLE IF NOT EXISTS agenda (
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

    # ── PERFIL ─────────────────────────────────────────────────────────────────

    def salvar_perfil(self, user_id, dados: dict):
        agora = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Verifica se já existe
            c.execute('SELECT criado_em FROM perfil_usuario WHERE user_id=?', (user_id,))
            row = c.fetchone()
            if row:
                c.execute('''UPDATE perfil_usuario SET
                    nome=?, idade=?, profissao=?, musica=?, comida=?, hobbies=?, extra=?, atualizado_em=?
                    WHERE user_id=?''',
                    (dados.get("nome", ""),
                     dados.get("idade", ""),
                     dados.get("profissao", ""),
                     dados.get("musica", ""),
                     dados.get("comida", ""),
                     dados.get("hobbies", ""),
                     dados.get("extra", ""),
                     agora,
                     user_id))
            else:
                c.execute('''INSERT INTO perfil_usuario
                    (user_id, nome, idade, profissao, musica, comida, hobbies, extra, criado_em, atualizado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (user_id,
                     dados.get("nome", ""),
                     dados.get("idade", ""),
                     dados.get("profissao", ""),
                     dados.get("musica", ""),
                     dados.get("comida", ""),
                     dados.get("hobbies", ""),
                     dados.get("extra", ""),
                     agora,
                     agora))
            conn.commit()

    def buscar_perfil(self, user_id) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('SELECT * FROM perfil_usuario WHERE user_id=?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else {}

    # ── CONFIG ASSISTENTE ──────────────────────────────────────────────────────

    def salvar_config(self, user_id, dados: dict):
        agora = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO config_assistente
                (user_id, nome_assistente, genero, personalidade, voz_provider,
                 voz_chave, voz_id, onboarding_completo, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT criado_em FROM config_assistente WHERE user_id=?), ?), ?)''',
                (user_id,
                 dados.get("nome_assistente", "Margo"),
                 dados.get("genero", "F"),
                 dados.get("personalidade", ""),
                 dados.get("voz_provider", "edge_tts"),
                 dados.get("voz_chave", ""),
                 dados.get("voz_id", ""),
                 1 if dados.get("onboarding_completo") else 0,
                 user_id, agora, agora))
            conn.commit()

    def buscar_config(self, user_id) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('SELECT * FROM config_assistente WHERE user_id=?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else {}

    def onboarding_completo(self, user_id) -> bool:
        config = self.buscar_config(user_id)
        return bool(config.get("onboarding_completo", 0))

    # ── RESUMOS ────────────────────────────────────────────────────────────────

    def salvar_resumo(self, user_id, resumo):
        """Mantém max 5 resumos por usuário — substitui o mais antigo"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM resumos_sessao WHERE user_id=?', (user_id,))
            count = c.fetchone()[0]
            if count >= 5:
                c.execute('''DELETE FROM resumos_sessao WHERE id = (
                    SELECT id FROM resumos_sessao WHERE user_id=? ORDER BY criado_em ASC LIMIT 1)''', (user_id,))
            resumo_curto = resumo[:100]
            c.execute('INSERT INTO resumos_sessao (user_id, resumo, criado_em) VALUES (?, ?, ?)',
                      (user_id, resumo_curto, datetime.now().isoformat()))
            conn.commit()

    def buscar_resumos(self, user_id) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT resumo FROM resumos_sessao WHERE user_id=? ORDER BY criado_em DESC LIMIT 5', (user_id,))
            return [r[0] for r in c.fetchall()]

    # ── AGENDA ─────────────────────────────────────────────────────────────────

    def salvar_lembrete(self, user_id, titulo, descricao, data_hora):
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute('''INSERT INTO agenda
                (user_id, titulo, descricao, data_hora, criado_em)
                VALUES (?, ?, ?, ?, ?)''',
                (user_id, titulo, descricao, data_hora, datetime.now().isoformat()))
            conn.commit()

    def buscar_lembretes(self, user_id) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('''SELECT * FROM agenda WHERE user_id=? AND data_hora > ?
                ORDER BY data_hora ASC''', (user_id, datetime.now().isoformat()))
            return [dict(r) for r in c.fetchall()]

    def lembretes_proximos(self, user_id) -> list:
        """Retorna lembretes que precisam ser disparados agora"""
        agora = datetime.now()
        resultado = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute('SELECT * FROM agenda WHERE user_id=?', (user_id,))
            for row in c.fetchall():
                item = dict(row)
                try:
                    dt = datetime.fromisoformat(item["data_hora"])
                    diff = (dt - agora).total_seconds() / 3600  # horas
                    if 0 < diff <= 3 and not item["lembrado_3h"]:
                        resultado.append({**item, "tipo": "3h"})
                        conn.cursor().execute('UPDATE agenda SET lembrado_3h=1 WHERE id=?', (item["id"],))
                    elif 20 < diff <= 25 and not item["lembrado_1d"]:
                        resultado.append({**item, "tipo": "1d"})
                        conn.cursor().execute('UPDATE agenda SET lembrado_1d=1 WHERE id=?', (item["id"],))
                except:
                    pass
            conn.commit()
        return resultado

banco = BancoMargo()

# ── GERENCIADOR DE SESSÃO ──────────────────────────────────────────────────────

class SessaoUsuario:
    """Gerencia sessão de até 10 interações por usuário"""
    def __init__(self):
        self._sessoes = {}  # user_id -> deque(maxlen=10)
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
        """Gera resumo da sessão e limpa"""
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
            for item in historico[-6:]:  # últimas 6 trocas do histórico
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
3. Perguntar a profissão o que faz da vida
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
FERRAMENTAS DISPONÍVEIS
===============================================================================

Quando o usuário pedir algo que envolve uma dessas ações, responda com o JSON
da ferramenta antes da sua resposta em linguagem natural.

NAVEGAÇÃO:
{{"ferramenta": "maps_navigate", "destino": "endereço ou lugar"}}
→ Quando: "quero ir para...", "me leva até...", "rota para..."

MÚSICA:
{{"ferramenta": "spotify_play", "query": "artista ou música ou playlist"}}
{{"ferramenta": "soundcloud_play", "query": "artista ou música"}}
→ Quando: "toca...", "coloca uma música...", "quero ouvir..."
→ Prefira Spotify. Use SoundCloud se o usuário pedir explicitamente.

BUSCA LOCAL:
{{"ferramenta": "maps_search", "query": "tipo de lugar", "contexto": "preferências do usuário"}}
→ Quando: "tem algum restaurante...", "onde posso...", "procura um..."
→ Use o perfil do usuário pra personalizar a busca (comida: {comida})

CHAMADA:
{{"ferramenta": "phone_call", "contato": "nome ou número"}}
→ Quando: "liga para...", "chama o/a..."

AGENDA:
{{"ferramenta": "agenda_add", "titulo": "...", "descricao": "...", "data_hora": "ISO8601"}}
{{"ferramenta": "agenda_list"}}
→ Quando: "me lembra de...", "agenda...", "quais meus compromissos..."

CASA INTELIGENTE:
{{"ferramenta": "smart_home", "acao": "ligar|desligar|ajustar", "dispositivo": "...", "valor": "..."}}
→ Quando: "apaga a luz...", "liga o ar...", "coloca o termostato em..."

WEB:
{{"ferramenta": "web_search", "query": "..."}}
→ Quando: "pesquisa...", "o que é...", "me fala sobre..." (informações que você não tem)

YOUTUBE:
{{"ferramenta": "youtube_search", "query": "..."}}
→ Quando: "abre um vídeo de...", "coloca no YouTube..."

===============================================================================
ESTILO DE RESPOSTA
===============================================================================

- Se acionou uma ferramenta: confirme brevemente o que fez
- Se não sabe: fale honestamente, ofereça pesquisar
- Sempre no idioma que o usuário usou
- Sem emojis em excesso — 1 por mensagem no máximo, só se natural
- Nunca markdown. Nunca asteriscos. Texto limpo.

EXEMPLOS:
"Quero ir pra casa" → aciona maps_navigate + "Rota iniciada!"
"Toca um sertanejo" → aciona spotify_play + "Colocando sertanejo pra você."
"Tem restaurante japonês perto?" → aciona maps_search + "Procurando restaurantes japoneses aqui perto..."
"Me lembra da reunião amanhã às 10h" → aciona agenda_add + "Anotado! Te aviso um dia antes e 3 horas antes."
"""

# ── PROCESSAMENTO ──────────────────────────────────────────────────────────────

def limpar_resposta(texto):
    """Remove markdown e símbolos que atrapalham o TTS"""
    texto = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
    texto = re.sub(r'\*(.+?)\*',     r'\1', texto)
    texto = re.sub(r'`(.+?)`',       r'\1', texto)
    texto = re.sub(r'#{1,6}\s*',     '',    texto)
    texto = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', texto)
    texto = re.sub(r'<[^>]+>',       '',    texto)
    texto = texto.replace('•', '').replace('→', 'para').replace('|', '')
    return texto.strip()

def extrair_ferramenta(texto):
    """Extrai JSON de ferramenta da resposta se houver"""
    match = re.search(r'\{[^{}]*"ferramenta"[^{}]*\}', texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None

def extrair_onboarding_completo(texto):
    """Detecta se o onboarding foi concluído"""
    match = re.search(r'ONBOARDING_COMPLETO:(\{.+?\})', texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    return None

def processar_mensagem(user_id, mensagem):
    """Processa mensagem de um usuário"""

    config = banco.buscar_config(user_id)
    perfil = banco.buscar_perfil(user_id)

    # ── ONBOARDING ─────────────────────────────────────────────────────────────
    if not config.get("onboarding_completo"):
        historico = sessoes.get_historico(user_id)
        resposta = chamar_deepseek(SYSTEM_ONBOARDING, mensagem, historico, max_tokens=300)

        # Verifica se onboarding foi concluído
        dados = extrair_onboarding_completo(resposta)
        if dados:
            # Salva perfil e config
            banco.salvar_perfil(user_id, dados)
            banco.salvar_config(user_id, {
                "nome_assistente":    dados.get("nome_assistente", "Margo"),
                "genero":             dados.get("genero", "F"),
                "personalidade":      dados.get("personalidade", ""),
                "onboarding_completo": True
            })
            # Remove o bloco JSON da resposta
            resposta = re.sub(r'ONBOARDING_COMPLETO:\{.+?\}', '', resposta).strip()
            log(f"Onboarding concluído para user {user_id}", "onboarding")

        sessoes.adicionar(user_id, mensagem, resposta)
        return {"resposta": limpar_resposta(resposta), "onboarding": not dados, "ferramenta": None}

    # ── MODO NORMAL ────────────────────────────────────────────────────────────
    historico  = sessoes.get_historico(user_id)
    resumos    = banco.buscar_resumos(user_id)
    lembretes  = banco.lembretes_proximos(user_id)

    # Monta contexto extra
    contexto_extra = ""
    if resumos:
        contexto_extra += f"\nConversas anteriores:\n" + "\n".join(f"- {r}" for r in resumos)
    if lembretes:
        for l in lembretes:
            contexto_extra += f"\n[LEMBRETE AGORA] {l['titulo']} — {l['tipo']}"

    system = build_system_prompt(perfil, config)
    if contexto_extra:
        system += f"\n\n{contexto_extra}"

    resposta = chamar_deepseek(system, mensagem, historico, max_tokens=500)

    # Detecta ferramenta
    ferramenta = extrair_ferramenta(resposta)
    if ferramenta:
        # Remove JSON da resposta falada
        resposta = re.sub(r'\{[^{}]*"ferramenta"[^{}]*\}', '', resposta).strip()

        # Agenda: salva no banco
        if ferramenta.get("ferramenta") == "agenda_add":
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

# ── FASTAPI ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Margo Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "online", "app": "Margo by Orbiby", "versao": "1.0.0"}

@app.get("/ping")
def ping():
    """Keep-alive endpoint — o scheduler chama a cada 25min"""
    return {"pong": True, "ts": datetime.now().isoformat()}

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

@app.get("/status/{user_id}")
def status(user_id: str):
    config = banco.buscar_config(user_id)
    perfil = banco.buscar_perfil(user_id)
    return {
        "user_id":              user_id,
        "onboarding_completo":  bool(config.get("onboarding_completo")),
        "nome_usuario":         perfil.get("nome", ""),
        "nome_assistente":      config.get("nome_assistente", "Margo"),
        "genero":               config.get("genero", "F"),
    }

@app.post("/limpar_sessao")
async def limpar_sessao(request: Request):
    data    = await request.json()
    user_id = data.get("user_id", "default")
    sessoes.resumir_e_limpar(user_id)
    return {"ok": True}

@app.post("/salvar_voz")
async def salvar_voz(request: Request):
    """Salva configuração de voz customizada (ElevenLabs/Fish Audio)"""
    data    = await request.json()
    user_id = data.get("user_id", "default")
    banco.salvar_config(user_id, {
        "voz_provider": data.get("provider", "edge_tts"),
        "voz_chave":    data.get("chave", ""),
        "voz_id":       data.get("voz_id", ""),
        **banco.buscar_config(user_id)
    })
    return {"ok": True}

@app.get("/agenda/{user_id}")
def agenda(user_id: str):
    return {"lembretes": banco.buscar_lembretes(user_id)}

@app.post("/reset_onboarding")
async def reset_onboarding(request: Request):
    """Reseta onboarding para um usuário (útil em dev/testes)"""
    data    = await request.json()
    user_id = data.get("user_id", "default")
    with sqlite3.connect(DB_FILE) as conn:
        conn.cursor().execute('DELETE FROM config_assistente WHERE user_id=?', (user_id,))
        conn.cursor().execute('DELETE FROM perfil_usuario WHERE user_id=?', (user_id,))
        conn.cursor().execute('DELETE FROM resumos_sessao WHERE user_id=?', (user_id,))
        conn.commit()
    sessoes.limpar(user_id)
    return {"ok": True, "msg": "Onboarding resetado"}

# ── MAIN ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  MARGO SERVER v1.0 — by Orbiby")
    print("=" * 55)
    print(f"  Porta:  {PORT}")
    print(f"  Banco:  {DB_FILE}")
    print(f"  DeepSeek key: {'OK' if DEEPSEEK_API_KEY else 'FALTANDO!'}")
    print("-" * 55)
    print("  Endpoints:")
    print("  POST /mensagem         — chat principal")
    print("  GET  /status/{user_id} — estado do usuário")
    print("  GET  /ping             — keep-alive")
    print("  POST /limpar_sessao    — encerra e resume sessão")
    print("  POST /salvar_voz       — configura voz customizada")
    print("  GET  /agenda/{user_id} — lembretes futuros")
    print("  POST /reset_onboarding — reseta (dev)")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
