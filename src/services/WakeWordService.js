import { NativeModules, Platform } from 'react-native';

const { WakeWordModule } = NativeModules;

export async function iniciarWakeWord(modelName = 'toktok') {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.iniciar(modelName);
    console.log('[WakeWord] Servico iniciado:', modelName);
  } catch (e) {
    console.error('[WakeWord] Erro ao iniciar:', e);
  }
}

export async function pararWakeWord() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.parar();
    console.log('[WakeWord] Servico parado');
  } catch (e) {
    console.error('[WakeWord] Erro ao parar:', e);
  }
}

export async function pausarWakeWord() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.pausar();
    console.log('[WakeWord] Servico pausado');
  } catch (e) {
    console.error('[WakeWord] Erro ao pausar:', e);
  }
}

export async function retomarWakeWord() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.retomar();
    console.log('[WakeWord] Servico retomado');
  } catch (e) {
    console.error('[WakeWord] Erro ao retomar:', e);
  }
}

export async function requestSTT() {
  if (Platform.OS !== 'android') return true;
  try {
    const autorizado = await WakeWordModule.requestSTT();
    console.log('[WakeWord] requestSTT:', autorizado);
    return autorizado;
  } catch (e) {
    console.error('[WakeWord] Erro requestSTT:', e);
    return false;
  }
}

export async function releaseSTT() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.releaseSTT();
    console.log('[WakeWord] releaseSTT OK');
  } catch (e) {
    console.error('[WakeWord] Erro releaseSTT:', e);
  }
}

export async function requestTTS() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.requestTTS();
    console.log('[WakeWord] requestTTS OK');
  } catch (e) {
    console.error('[WakeWord] Erro requestTTS:', e);
  }
}

export async function releaseTTS() {
  if (Platform.OS !== 'android') return;
  try {
    await WakeWordModule.releaseTTS();
    console.log('[WakeWord] releaseTTS OK');
  } catch (e) {
    console.error('[WakeWord] Erro releaseTTS:', e);
  }
}

export async function getWakeWordState() {
  if (Platform.OS !== 'android') return 'IDLE';
  try {
    const state = await WakeWordModule.getState();
    console.log('[WakeWord] Estado atual:', state);
    return state;
  } catch (e) {
    console.error('[WakeWord] Erro getState:', e);
    return 'IDLE';
  }
}
