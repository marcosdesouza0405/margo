const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

// Adicionar função que remove emojis no iOS
const emojiStripper = `
// Remove emojis de texto no iOS (Hermes não renderiza)
function limparEmojis(texto) {
  if (Platform.OS !== 'ios' || !texto) return texto;
  return texto.replace(/[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}\\u{2300}-\\u{23FF}\\u{2B50}\\u{FE0F}\\u{200D}\\u{20E3}\\u{1F1E0}-\\u{1F1FF}\\u{E0020}-\\u{E007F}\\u{0031}-\\u{0039}\\u{2716}\\u{2714}\\u{2022}\\u{25CF}\\u{25B6}\\u{2B07}\\u{2934}\\u{2935}\\u{3030}\\u{00A9}\\u{00AE}\\u{2122}\\u{23F0}-\\u{23FA}\\u{231A}\\u{231B}\\u{2328}\\u{23CF}\\u{2702}-\\u{27B0}\\u{2639}\\u{263A}\\u{0023}\\u{002A}]/gu, '').replace(/  +/g, ' ').trim();
}
`;

// Inserir a função depois dos imports
c = c.replace(
  "// WakeWordService importado via NativeModules diretamente",
  emojiStripper + "\n// WakeWordService importado via NativeModules diretamente"
);

// Aplicar limparEmojis nas mensagens do sistema/assistente ao renderizar
// Encontrar onde addMsg é chamada ou onde as mensagens são renderizadas
// Melhor aplicar na função addMsg
const oldAddMsg = c.match(/function addMsg\([^)]+\)\s*\{[^}]+\}/);
if (!oldAddMsg) {
  // Alternativa: aplicar no render da mensagem
  // Procura onde msg.text é renderizado
  c = c.replace(
    /\{msg\.text\}/g,
    '{Platform.OS === "ios" ? limparEmojis(msg.text) : msg.text}'
  );
  console.log('OK - limparEmojis aplicado no render');
} else {
  console.log('OK - addMsg encontrado');
}

fs.writeFileSync('App.js', c, 'utf8');
