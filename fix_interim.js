const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');
const count = (c.match(/interimResults: false/g) || []).length;
c = c.replace(/interimResults: false/g, "interimResults: Platform.OS === 'ios'");
fs.writeFileSync('App.js', c, 'utf8');
console.log('OK - ' + count + ' ocorrencias substituidas');
