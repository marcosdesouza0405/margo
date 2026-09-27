const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

const old = `      // iOS: para o mic antes de tocar pra liberar a sessão de áudio pro alto-falante principal
      if (Platform.OS === 'ios' && ExpoSpeechRecognitionModule) {
        try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
      }
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false, shouldDuckAndroid: false, playThroughEarpieceAndroid: false, staysActiveInBackground: true, interruptionModeIOS: InterruptionModeIOS.DoNotMix, interruptionModeAndroid: InterruptionModeAndroid.DoNotMix });`;

const neu = `      // iOS: para o mic e espera a sessão de áudio resetar pro alto-falante principal
      if (Platform.OS === 'ios') {
        if (ExpoSpeechRecognitionModule) {
          try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
        }
        await new Promise(r => setTimeout(r, 300));
        await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false, shouldDuckAndroid: false, playThroughEarpieceAndroid: false, staysActiveInBackground: true, interruptionModeIOS: InterruptionModeIOS.DoNotMix, interruptionModeAndroid: InterruptionModeAndroid.DoNotMix });
        await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false, shouldDuckAndroid: false, playThroughEarpieceAndroid: false, staysActiveInBackground: true, interruptionModeIOS: InterruptionModeIOS.DoNotMix, interruptionModeAndroid: InterruptionModeAndroid.DoNotMix });
      } else {
        await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false, shouldDuckAndroid: false, playThroughEarpieceAndroid: false, staysActiveInBackground: true, interruptionModeIOS: InterruptionModeIOS.DoNotMix, interruptionModeAndroid: InterruptionModeAndroid.DoNotMix });
      }`;

if (c.includes(old)) {
  c = c.replace(old, neu);
  fs.writeFileSync('App.js', c, 'utf8');
  console.log('OK - delay adicionado antes do TTS no iOS');
} else {
  console.log('ERRO - bloco nao encontrado');
}
