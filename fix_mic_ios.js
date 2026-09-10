const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

const old = `  useSpeechRecognitionEvent('result', (e) => {
    if (multilingueRef.current) return;
    const transcript = e.results?.[0]?.transcript;
    if (!transcript || !e.isFinal) return;
    micErroCountRef.current = 0; // Funcionou — reseta contador
    micRodandoRef.current = true;
    // Acumula fragmentos em vez de enviar cada um separado
    micBufferRef.current = micBufferRef.current
      ? micBufferRef.current + ' ' + transcript
      : transcript;
    // Reseta timer — só envia após 1.5s sem novo fragmento
    if (micTimerRef.current) clearTimeout(micTimerRef.current);
    micTimerRef.current = setTimeout(() => {
      if (micBufferRef.current.trim()) {
        enviar(micBufferRef.current.trim());
        micBufferRef.current = '';
      }
      micTimerRef.current = null;
    }, 3000);
  });`;

const neu = `  useSpeechRecognitionEvent('result', (e) => {
    if (multilingueRef.current) return;
    const transcript = e.results?.[0]?.transcript;
    if (!transcript) return;
    // Android: espera isFinal. iOS: aceita parciais (Speech Framework envia texto completo a cada update)
    if (Platform.OS === 'android' && !e.isFinal) return;
    micErroCountRef.current = 0;
    micRodandoRef.current = true;
    if (Platform.OS === 'ios') {
      // iOS: substitui buffer com transcript mais recente (não acumula, pois cada resultado já é o texto completo)
      micBufferRef.current = transcript;
    } else {
      // Android: acumula fragmentos finais
      micBufferRef.current = micBufferRef.current
        ? micBufferRef.current + ' ' + transcript
        : transcript;
    }
    // Reseta timer — envia após silêncio (iOS: 2s, Android: 3s)
    if (micTimerRef.current) clearTimeout(micTimerRef.current);
    micTimerRef.current = setTimeout(() => {
      if (micBufferRef.current.trim()) {
        enviar(micBufferRef.current.trim());
        micBufferRef.current = '';
      }
      micTimerRef.current = null;
    }, Platform.OS === 'ios' ? 2000 : 3000);
  });`;

if (c.includes(old)) {
  c = c.replace(old, neu);
  fs.writeFileSync('App.js', c, 'utf8');
  console.log('OK - microfone ajustado para iOS');
} else {
  console.log('ERRO - bloco nao encontrado, pode ter mudado');
}
