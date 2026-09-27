const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

const old = `  async function tocarAudioBase64(base64, onFim) {
    try {
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false, shouldDuckAndroid: false, playThroughEarpieceAndroid: false, staysActiveInBackground: true, interruptionModeIOS: InterruptionModeIOS.DoNotMix, interruptionModeAndroid: InterruptionModeAndroid.DoNotMix });`;

const neu = `  async function tocarAudioBase64(base64, onFim) {
    try {
      // iOS: para o mic antes de tocar pra liberar a sessão de áudio pro alto-falante principal
      if (Platform.OS === 'ios' && ExpoSpeechRecognitionModule) {
        try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
      }
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false, shouldDuckAndroid: false, playThroughEarpieceAndroid: false, staysActiveInBackground: true, interruptionModeIOS: InterruptionModeIOS.DoNotMix, interruptionModeAndroid: InterruptionModeAndroid.DoNotMix });`;

if (c.includes(old)) {
  c = c.replace(old, neu);
  fs.writeFileSync('App.js', c, 'utf8');
  console.log('OK - mic parado antes do TTS no iOS');
} else {
  console.log('ERRO - bloco nao encontrado');
}
