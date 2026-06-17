import { NativeModules, Platform } from 'react-native';

const { WakeWordModule } = NativeModules;

export async function iniciarWakeWord(modelName = 'toktok') {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.iniciar(modelName);
    console.log('[WakeWord] Iniciado:', modelName);
  } catch (e) {
    console.error('[WakeWord] Erro ao iniciar:', e);
  }
}

export async function pararWakeWord() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.parar();
    console.log('[WakeWord] Parado');
  } catch (e) {
    console.error('[WakeWord] Erro ao parar:', e);
  }
}

export async function pausarWakeWord() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.pausar();
    console.log('[WakeWord] Pausado — app em foreground');
  } catch (e) {
    console.error('[WakeWord] Erro ao pausar:', e);
  }
}

export async function retomarWakeWord(modelName = 'toktok') {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.retomar();
    console.log('[WakeWord] Retomado — app em background');
  } catch (e) {
    console.error('[WakeWord] Erro ao retomar:', e);
  }
}
