const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

// 1. Adicionar import do FileSystem se não tiver
if (!c.includes("expo-file-system")) {
  c = c.replace(
    "import { Audio } from 'expo-av';",
    "import { Audio } from 'expo-av';\nimport * as FileSystem from 'expo-file-system';"
  );
}

// 2. Substituir tocarAudioBase64 pra salvar em arquivo temp no iOS
const old = `  async function tocarAudioBase64(base64, onFim) {
    try {
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false });
      const { sound } = await Audio.Sound.createAsync(
        { uri: \`data:audio/mpeg;base64,\${base64}\` },
        { shouldPlay: true, volume: 1.0 }
      );`;

const neu = `  async function tocarAudioBase64(base64, onFim) {
    try {
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false });
      let audioSource;
      if (Platform.OS === 'ios') {
        const tmpFile = FileSystem.cacheDirectory + 'margo_tts_' + Date.now() + '.mp3';
        await FileSystem.writeAsStringAsync(tmpFile, base64, { encoding: FileSystem.EncodingType.Base64 });
        audioSource = { uri: tmpFile };
      } else {
        audioSource = { uri: \`data:audio/mpeg;base64,\${base64}\` };
      }
      const { sound } = await Audio.Sound.createAsync(
        audioSource,
        { shouldPlay: true, volume: 1.0 }
      );`;

// 3. Proteger WakeWordModule
const oldWake = "try { NativeModules.WakeWordModule.releaseTTS(); } catch(e) {}";
const neuWake = "if (Platform.OS === 'android') { try { NativeModules.WakeWordModule.releaseTTS(); } catch(e) {} }";

if (c.includes(old)) {
  c = c.replace(old, neu);
  c = c.replace(new RegExp(oldWake.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), neuWake);
  fs.writeFileSync('App.js', c, 'utf8');
  console.log('OK - TTS e WakeWord corrigidos para iOS');
} else {
  console.log('ERRO - bloco TTS nao encontrado');
}
