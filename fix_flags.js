const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

// Onboarding - botões de idioma
c = c.replace("<Text style={s.btnPTxt}>🇧🇷  Português</Text>", "<Text style={s.btnPTxt}>PT  Português</Text>");
c = c.replace("<Text style={s.btnPTxt}>🇺🇸  English</Text>", "<Text style={s.btnPTxt}>EN  English</Text>");
c = c.replace("<Text style={s.btnPTxt}>🇯🇵  日本語</Text>", "<Text style={s.btnPTxt}>JA  日本語</Text>");

// Configurações - seletor de idioma
c = c.replace("['pt-BR','🇧🇷 Português']", "['pt-BR','PT Português']");
c = c.replace("['en-US','🇺🇸 English']", "['en-US','EN English']");
c = c.replace("['ja-JP','🇯🇵 日本語']", "['ja-JP','JA 日本語']");

fs.writeFileSync('App.js', c, 'utf8');
console.log('OK - bandeiras substituidas por siglas');
