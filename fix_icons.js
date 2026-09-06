const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

// 1. Adicionar import do Ionicons
c = c.replace(
  "import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';",
  "import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';\nimport { Ionicons } from '@expo/vector-icons';"
);

// 2. Volume (som on/off)
c = c.replace(
  "<Text style={{ fontSize: 16 }}>{vozAtiva ? '\u{1F50A}' : '\u{1F507}'}</Text>",
  '<Ionicons name={vozAtiva ? "volume-high" : "volume-off"} size={16} color={vozAtiva ? C.text2 : C.red} />'
);

// 3. Reiniciar conversa
c = c.replace(
  "<Text style={{ color: C.text2, fontSize: 18 }}>\u21BA</Text>",
  '<Ionicons name="refresh" size={18} color={C.text2} />'
);

// 4. Engrenagem config
c = c.replace(
  "<Text style={{ color: C.text2, fontSize: 18 }}>\u2699</Text>",
  '<Ionicons name="settings-sharp" size={18} color={C.text2} />'
);

// 5. Fechar (X)
c = c.replace(
  "<Text style={{ color: C.text2, fontSize: 20 }}>\u2715</Text>",
  '<Ionicons name="close" size={20} color={C.text2} />'
);

// 6. Olho senha - todas as variantes
const olhoReplace = (varName) => {
  const re = new RegExp(
    `<Text style=\\{\\{ fontSize: 18 \\}\\}>\\{${varName} \\? '.+?' : '.+?'\\}</Text>`,
    'g'
  );
  c = c.replace(re, `<Ionicons name={${varName} ? "eye-off" : "eye"} size={18} color={C.text2} />`);
};
olhoReplace('verSenha');
olhoReplace('verConf');
olhoReplace('verNova');

fs.writeFileSync('App.js', c, 'utf8');
console.log('OK - todos os emojis substituidos por Ionicons');
