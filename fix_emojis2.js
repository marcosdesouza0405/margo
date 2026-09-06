const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');
let count = 0;
function r(old, neu) { if(c.includes(old)){c=c.replace(new RegExp(old.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'),neu);count++;} }

// ── MICROFONE (linha 2572) ──
r("<Text style={{ fontSize: 18 }}>{micAtivo ? '🎙️' : '🎤'}</Text>",
  '<Ionicons name={micAtivo ? "mic" : "mic-outline"} size={18} color={micAtivo ? C.cyan : C.text2} />');

// ── CÂMERA / GALERIA ──
r("text: '📷 Câmera'", "text: 'Câmera'");
r("text: '🖼️ Galeria'", "text: 'Galeria'");
r("addMsg('user', '📷 Imagem enviada')", "addMsg('user', 'Imagem enviada')");

// ── OLHO API KEY ──
c = c.replace(/<Text>\{verApiKey \? '🙈' : '👁️'\}<\/Text>/g,
  '<Ionicons name={verApiKey ? "eye-off" : "eye"} size={16} color={C.text2} />');

// ── WELCOME MESSAGE ──
r("こんにちは！${config.assistantName}です 👋 右上の⚙️をタップして設定してください。",
  "こんにちは！${config.assistantName}です。右上の設定アイコンをタップして設定してください。");
r("Hi! I'm ${config.assistantName} 👋 Tap ⚙️ above to set up your profile.",
  "Hi! I'm ${config.assistantName}. Tap the settings icon above to set up your profile.");
r("Olá! Sou a ${config.assistantName} 👋 Toque em ⚙️ acima para configurar seu perfil.",
  "Olá! Sou a ${config.assistantName}. Toque no ícone de configuração acima para configurar seu perfil.");

// ── WAKE WORD ──
c = c.replace(/🔔 Wake Word/g, 'Wake Word');

// ── WAZE / MAPS ──
r("['waze','🚗 Waze']", "['waze','Waze']");
r("['gmaps','🗺️ Google Maps']", "['gmaps','Google Maps']");

// ── VOICE PROVIDER ──
r("['device','🤖 Migoo Voice']", "['device','Migoo Voice']");

// ── PLANOS (remover emojis - fica mais limpo) ──
// PT-BR
r("'🔥 Pro — R$14,90/mês'", "'Pro — R$14,90/mês'");
r("'🚀 Pro+ — R$29,90/mês'", "'Pro+ — R$29,90/mês'");
r("'💊 50 interações — R$12,90'", "'50 interações — R$12,90'");
r("'🔥 Pro — 20 msgs/dia  R$14,90/mês'", "'Pro — 20 msgs/dia  R$14,90/mês'");
r("'🚀 Pro+ — 50 msgs/dia  R$29,90/mês'", "'Pro+ — 50 msgs/dia  R$29,90/mês'");
// EN
r("'🔥 Pro — R$14.90/mo'", "'Pro — R$14.90/mo'");
r("'🚀 Pro+ — R$29.90/mo'", "'Pro+ — R$29.90/mo'");
r("'💊 50 interactions — R$12.90'", "'50 interactions — R$12.90'");
r("'🔥 Pro — 20 msgs/day  R$14.90/mo'", "'Pro — 20 msgs/day  R$14.90/mo'");
r("'🚀 Pro+ — 50 msgs/day  R$29.90/mo'", "'Pro+ — 50 msgs/day  R$29.90/mo'");
// JA
r("'🔥 Pro — R$14.90/月'", "'Pro — R$14.90/月'");
r("'🚀 Pro+ — R$29.90/月'", "'Pro+ — R$29.90/月'");
r("'💊 50回追加 — R$12.90'", "'50回追加 — R$12.90'");
r("'🔥 Pro — 1日20回  R$14.90/月'", "'Pro — 1日20回  R$14.90/月'");
r("'🚀 Pro+ — 1日50回  R$29.90/月'", "'Pro+ — 1日50回  R$29.90/月'");

// ── BOTÕES PLANOS UI ──
r("🔥 Pro — 20 msgs/dia", "Pro — 20 msgs/dia");
r("🚀 Pro+ — 50 msgs/dia", "Pro+ — 50 msgs/dia");
r("💊 +50 consultas", "+50 consultas");

// ── i18n STRINGS (3 idiomas) ──
// Kokoro/Fish/Eleven
c = c.replace(/✨ /g, '');
c = c.replace(/📖 /g, '');

// Plano labels
c = c.replace(/Pro ✓/g, 'Pro ✓');  // ✓ é texto, mantém
r("'💳 Cartão de crédito'", "'Cartão de crédito'");
r("'🏦 PIX'", "'PIX'");
r("'💳 Credit card'", "'Credit card'");
r("'💳 クレジットカード'", "'クレジットカード'");
r("'🏦 PIX'", "'PIX'");

// Paywall títulos
r("'🎉 Trial encerrado!'", "'Trial encerrado!'");
r("'⚠️ Limite atingido!'", "'Limite atingido!'");
r("'🎉 Trial ended!'", "'Trial ended!'");
r("'⚠️ Limit reached!'", "'Limit reached!'");
r("'🎉 トライアル終了！'", "'トライアル終了！'");
r("'⚠️ 上限に達しました！'", "'上限に達しました！'");

// Gênero
r("'🙍‍♀️ Feminino'", "'Feminino'");
r("'🙍‍♂️ Masculino'", "'Masculino'");
r("'🙍‍♀️ Female'", "'Female'");
r("'🙍‍♂️ Male'", "'Male'");
r("'🙍‍♀️ 女性'", "'女性'");
r("'🙍‍♂️ 男性'", "'男性'");

// SmartThings / Spotify
r("'🏠 Conectar SmartThings'", "'Conectar SmartThings'");
r("'🎵 Conectar Spotify'", "'Conectar Spotify'");
r("'🏠 Connect SmartThings'", "'Connect SmartThings'");
r("'🎵 Connect Spotify'", "'Connect Spotify'");
r("'🏠 SmartThingsを接続'", "'SmartThingsを接続'");
r("'🎵 Spotifyを接続'", "'Spotifyを接続'");

// Verificar email
r("'✉️ Verifique seu email'", "'Verifique seu email'");
r("'✉️ Verify your email'", "'Verify your email'");
r("'✉️ メールを確認してください'", "'メールを確認してください'");

// Spotify conectado ✓ - mantém pois ✓ é texto
// Notificação teste
r("'🔔 Teste Margo'", "'Teste Margo'");
r("'Notificação funcionando! ✅'", "'Notificação funcionando!'");

fs.writeFileSync('App.js', c, 'utf8');
console.log('OK - ' + count + ' substituicoes feitas');
