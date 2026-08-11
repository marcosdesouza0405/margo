#!/usr/bin/env python3
"""
Patch cirúrgico do margo_server.py — adiciona endpoint /verificar_compra
Rode: python3 ~/margo/patch_billing_backend.py

Mudanças:
1. Adiciona imports do Google Play API (no topo, depois dos imports existentes)
2. Adiciona endpoint /verificar_compra (antes de 'if __name__')
NÃO mexe em nada existente.
"""

import os

filepath = os.path.expanduser("~/margo/margo_server.py")
print(f"📄 Lendo: {filepath}")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Backup
backup_path = filepath + '.bak_pre_billing'
with open(backup_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"💾 Backup criado: {backup_path}")

changes = 0

# ── 1. Adicionar imports do Google Play API ──
# Insere depois de "import uvicorn" (última linha de imports)
google_imports = '''
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
'''

if '_get_play_api' not in content:
    anchor = "import uvicorn"
    if anchor in content:
        content = content.replace(anchor, anchor + "\n" + google_imports)
        changes += 1
        print("✅ 1. Imports do Google Play API adicionados")
    else:
        print("⚠️  1. 'import uvicorn' não encontrado — verificar manualmente")
else:
    print("⏭️  1. Imports já existem")

# ── 2. Adicionar endpoint /verificar_compra ──
endpoint_code = '''
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
            result = api.purchases().subscriptions().get(
                packageName=BILLING_PACKAGE,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()

            # paymentState: 0=pendente, 1=pago, 2=trial
            payment_state = result.get("paymentState")
            if payment_state not in [1, 2]:
                log(f"[BILLING] Pagamento não confirmado: paymentState={payment_state}", "billing")
                return JSONResponse({"ok": False, "error": "Pagamento não confirmado"}, status_code=400)

            # Mapear product_id → plano
            if product_id == "pro_monthly":
                plano = "pro"
            elif product_id == "pro_plus_monthly":
                plano = "pro_plus"
            else:
                plano = "pro"

            banco.atualizar_plano(user_id, plano)
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

'''

if '/verificar_compra' not in content:
    anchor = 'if __name__ == "__main__":'
    if anchor in content:
        content = content.replace(anchor, endpoint_code + anchor)
        changes += 1
        print("✅ 2. Endpoint /verificar_compra adicionado")
    else:
        print("⚠️  2. 'if __name__' não encontrado — verificar manualmente")
else:
    print("⏭️  2. Endpoint já existe")

# Salvar
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n🎉 Patch concluído! {changes} mudanças aplicadas.")
print("📌 Backup em: margo_server.py.bak_pre_billing")
print("")
print("📌 Próximo passo — rodar no terminal:")
print('  cd ~/margo')
print('  echo "google-auth==2.29.0" >> requirements.txt')
print('  echo "google-api-python-client==2.127.0" >> requirements.txt')
print('  git add -A && git commit -m "feat: Google Play Billing - verificar_compra" && git push origin main')
