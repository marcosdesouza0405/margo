#!/usr/bin/env python3
"""
Patch cirúrgico do App.js para Google Play Billing.
Rode: python3 ~/margo-app/patch_billing_app.py

Mudanças:
1. Adiciona import do BillingManager
2. Adiciona hook useBilling no componente App
3. Substitui handleUpgrade (Stripe/PIX → Google Play)
4. Ativa botões de upgrade (false → true) com novos preços
5. Atualiza paywall alert com novos preços
"""

import re

filepath = __file__.replace('patch_billing_app.py', 'App.js')
print(f"📄 Lendo: {filepath}")

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Backup
with open(filepath + '.bak_pre_billing', 'w', encoding='utf-8') as f:
    f.write(content)
print("💾 Backup criado: App.js.bak_pre_billing")

changes = 0

# ── 1. Adicionar import do BillingManager (depois de "import * as Device from 'expo-device';")
old_import = "import * as Device from 'expo-device';"
new_import = "import * as Device from 'expo-device';\nimport { useBilling } from './BillingManager';"
if 'useBilling' not in content:
    content = content.replace(old_import, new_import)
    changes += 1
    print("✅ 1. Import do BillingManager adicionado")
else:
    print("⏭️  1. Import já existe")

# ── 2. Adicionar hook useBilling no componente App (depois de vozAtiva useState)
old_hook = "const [vozAtiva, setVozAtiva]   = useState(true);"
new_hook = "const [vozAtiva, setVozAtiva]   = useState(true);\n  const billing = useBilling(userId);"
if 'useBilling(userId)' not in content:
    content = content.replace(old_hook, new_hook)
    changes += 1
    print("✅ 2. Hook useBilling adicionado")
else:
    print("⏭️  2. Hook já existe")

# ── 3. Substituir handleUpgrade (Stripe/PIX → Google Play)
old_handle_start = "  async function handleUpgrade(planoEscolhido) {"
old_handle_end = "  }\n\n  async function sair()"

# Encontrar o bloco inteiro
idx_start = content.find(old_handle_start)
idx_end = content.find(old_handle_end)

if idx_start != -1 and idx_end != -1:
    new_handle = """  function handleUpgrade(planoEscolhido) {
    if (planoEscolhido === 'pro') {
      billing.buySub('pro_monthly');
    } else if (planoEscolhido === 'pro_plus') {
      billing.buySub('pro_plus_monthly');
    } else if (planoEscolhido === 'avulso') {
      billing.buyExtra();
    }
  }

  async function sair()"""
    content = content[:idx_start] + new_handle + content[idx_end + len(old_handle_end):]
    changes += 1
    print("✅ 3. handleUpgrade substituído (Stripe/PIX → Google Play)")
else:
    print("⚠️  3. handleUpgrade não encontrado — verificar manualmente")

# ── 4. Ativar botões de upgrade e atualizar preços
old_buttons = """{false && (plano === 'free' || plano === 'pro') && (
              <View style={{ gap: 8 }}>
                {plano === 'free' && (
                  <TouchableOpacity style={[s.btnP, { backgroundColor: '#7C3AED' }]}
                    onPress={() => onUpgrade('pro')}>
                    <Text style={s.btnPTxt}>🔥 Pro — 20 msgs/dia{'  '}
                      <Text style={{ textDecorationLine: 'line-through', opacity: 0.7 }}>R$14,90</Text>
                      {' '}R$9,90/mês
                    </Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#059669' }]}
                  onPress={() => onUpgrade('pro_plus')}>
                  <Text style={s.btnPTxt}>🔥 Pro+ — 50 msgs/dia{'  '}
                    <Text style={{ textDecorationLine: 'line-through', opacity: 0.7 }}>R$29,90</Text>
                    {' '}R$19,90/mês
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#2E9AAF' }]}
                  onPress={() => onUpgrade('avulso')}>
                  <Text style={s.btnPTxt}>{s_['btn_avulso']}</Text>
                </TouchableOpacity>
              </View>
            )}"""

new_buttons = """{(plano === 'free' || plano === 'pro') && (
              <View style={{ gap: 8 }}>
                {plano === 'free' && (
                  <TouchableOpacity style={[s.btnP, { backgroundColor: '#7C3AED' }]}
                    onPress={() => onUpgrade('pro')}>
                    <Text style={s.btnPTxt}>🔥 Pro — 20 msgs/dia  R$14,90/mês</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#059669' }]}
                  onPress={() => onUpgrade('pro_plus')}>
                  <Text style={s.btnPTxt}>🚀 Pro+ — 50 msgs/dia  R$29,90/mês</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#2E9AAF' }]}
                  onPress={() => onUpgrade('avulso')}>
                  <Text style={s.btnPTxt}>💊 +50 consultas  R$12,90</Text>
                </TouchableOpacity>
              </View>
            )}"""

if old_buttons in content:
    content = content.replace(old_buttons, new_buttons)
    changes += 1
    print("✅ 4. Botões de upgrade ativados e preços atualizados")
else:
    print("⚠️  4. Bloco de botões não encontrado — verificar manualmente")

# ── 5. Atualizar paywall alert com novos preços
old_paywall_pro = "'🔥 Pro — 20 msgs/dia  R$14,90 ➜ R$9,90'"
new_paywall_pro = "'🔥 Pro — 20 msgs/dia  R$14,90/mês'"
if old_paywall_pro in content:
    content = content.replace(old_paywall_pro, new_paywall_pro)
    changes += 1
    print("✅ 5a. Paywall Pro atualizado")

old_paywall_plus = "'🚀 Pro+ — 50 msgs/dia  R$29,90 ➜ R$19,90'"
new_paywall_plus = "'🚀 Pro+ — 50 msgs/dia  R$29,90/mês'"
if old_paywall_plus in content:
    content = content.replace(old_paywall_plus, new_paywall_plus)
    changes += 1
    print("✅ 5b. Paywall Pro+ atualizado")

# ── 6. Atualizar STRINGS com novos preços
old_btn_pro = "btn_pro: '\uD83D\uDD25 Pro — R$9,90/mês'"
new_btn_pro = "btn_pro: '\uD83D\uDD25 Pro — R$14,90/mês'"
if old_btn_pro in content:
    content = content.replace(old_btn_pro, new_btn_pro)
    changes += 1
    print("✅ 6a. String btn_pro atualizada")

old_btn_plus = "btn_pro_plus: '\uD83D\uDE80 Pro+ — R$19,90/mês'"
new_btn_plus = "btn_pro_plus: '\uD83D\uDE80 Pro+ — R$29,90/mês'"
if old_btn_plus in content:
    content = content.replace(old_btn_plus, new_btn_plus)
    changes += 1
    print("✅ 6b. String btn_pro_plus atualizada")

# Salvar
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n🎉 Patch concluído! {changes} mudanças aplicadas.")
print("📌 Backup em: App.js.bak_pre_billing")
print("📌 Próximo: testar build com ./gradlew :app:bundleRelease")
