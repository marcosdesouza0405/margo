import { useState, useEffect, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, KeyboardAvoidingView, Platform, StatusBar,
  ActivityIndicator, Linking, Alert, SafeAreaView, Modal, Image,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Speech from 'expo-speech';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import * as Contacts from 'expo-contacts';
import { Audio } from 'expo-av';

// Módulo nativo de microfone
import { NativeModules, NativeEventEmitter } from 'react-native';
const { MicrophoneModule } = NativeModules;
const micEmitter = MicrophoneModule ? new NativeEventEmitter(MicrophoneModule) : null;

// expo-speech-recognition — mantido como fallback
let ExpoSpeechRecognitionModule = null;
let useSpeechRecognitionEvent = () => {};
try {
  const mod = require('expo-speech-recognition');
  ExpoSpeechRecognitionModule = mod.ExpoSpeechRecognitionModule;
  useSpeechRecognitionEvent = mod.useSpeechRecognitionEvent;
} catch(e) {}

const ICON = require('./assets/icon.png');
const BACKEND = 'https://margo-production-98a9.up.railway.app';

const C = {
  bg:      '#0A0A0F', bg2: '#111118', bg3: '#1A1A24',
  cyan:    '#00D4FF', cyanDim: 'rgba(0,212,255,0.12)',
  text:    '#E8E8F0', text2: '#8888A0', text3: '#555568',
  border:  'rgba(255,255,255,0.07)', red: '#FF6B6B',
};

const CFG_PADRAO = {
  assistantName: 'Margo', voiceGender: 'F', voiceProvider: 'device',
  apiKey: '', voiceId: '',
  apiKeyFish: '', voiceIdFish: '',
  apiKeyEleven: '', voiceIdEleven: '',
  personalidade: '', perfilNome: '', perfilNascimento: '',
  perfilProfissao: '', perfilMusica: '', perfilComida: '',
  perfilHobbies: '', perfilExtra: '',
  wakeWordOn: true,
  backendUrl: BACKEND,
};

const hora = () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

function limpar(txt) {
  return txt
    .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
    .replace(/[\u2600-\u27BF]/g, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/#{1,6}\s*/g, '')
    .replace(/\s+/g, ' ').trim();
}

// ── TELA BOAS-VINDAS ──────────────────────────────────────────────────────────
function TelaBoasVindas({ onEntrar, onCadastrar }) {
  return (
    <View style={s.fullCenter}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <View style={s.logoCircle}>
        <Image source={ICON} style={{ width: 80, height: 80, borderRadius: 40 }} />
      </View>
      <Text style={s.welcomeName}>Margo</Text>
      <Text style={s.welcomeDesc}>Sua assistente pessoal de IA{'\n'}com personalidade única</Text>
      <View style={{ width: '100%', gap: 12, marginTop: 48 }}>
        <TouchableOpacity style={s.btnP} onPress={onCadastrar}>
          <Text style={s.btnPTxt}>Criar conta</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.btnS} onPress={onEntrar}>
          <Text style={s.btnSTxt}>Já tenho conta</Text>
        </TouchableOpacity>
      </View>
      <Text style={{ color: C.text3, fontSize: 11, marginTop: 48 }}>by Orbiby</Text>
    </View>
  );
}

// ── TELA CADASTRO ─────────────────────────────────────────────────────────────
function TelaCadastro({ onSuccess, onVoltar, backendUrl }) {
  const [email, setEmail]       = useState('');
  const [senha, setSenha]       = useState('');
  const [confirma, setConfirma] = useState('');
  const [erro, setErro]         = useState('');
  const [loading, setLoading]   = useState(false);
  const [verSenha, setVerSenha] = useState(false);
  const [verConf, setVerConf]   = useState(false);

  async function cadastrar() {
    if (!email.includes('@'))   { setErro('Email inválido.'); return; }
    if (senha.length < 6)       { setErro('Senha deve ter pelo menos 6 caracteres.'); return; }
    if (senha !== confirma)     { setErro('As senhas não coincidem.'); return; }
    setLoading(true); setErro('');
    try {
      const r = await fetch(`${backendUrl}/cadastro`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.toLowerCase().trim(), senha })
      });
      const d = await r.json();
      if (d.ok) {
        await AsyncStorage.setItem('margo_user_id', d.user_id);
        await AsyncStorage.setItem('margo_email', d.email);
        onSuccess(d);
      } else setErro(d.erro || 'Erro ao criar conta.');
    } catch(e) { setErro('Sem conexão com o servidor.'); }
    setLoading(false);
  }

  return (
    <KeyboardAvoidingView style={s.authWrap} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <TouchableOpacity onPress={onVoltar}><Text style={s.voltarTxt}>← Voltar</Text></TouchableOpacity>
      <Text style={s.authTitle}>Criar conta</Text>
      <Text style={s.authSub}>Crie sua conta para acessar a Margo em qualquer dispositivo.</Text>
      <TextInput style={s.authInput} placeholder="Seu email" placeholderTextColor={C.text3}
        value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
      <View style={s.senhaWrap}>
        <TextInput style={[s.authInput, { flex: 1, marginBottom: 0 }]} placeholder="Senha (mínimo 6 caracteres)"
          placeholderTextColor={C.text3} value={senha} onChangeText={setSenha} secureTextEntry={!verSenha} />
        <TouchableOpacity style={s.olho} onPress={() => setVerSenha(v => !v)}>
          <Text style={{ fontSize: 18 }}>{verSenha ? '🙈' : '👁️'}</Text>
        </TouchableOpacity>
      </View>
      <View style={s.senhaWrap}>
        <TextInput style={[s.authInput, { flex: 1, marginBottom: 0 }]} placeholder="Confirmar senha"
          placeholderTextColor={C.text3} value={confirma} onChangeText={setConfirma} secureTextEntry={!verConf} />
        <TouchableOpacity style={s.olho} onPress={() => setVerConf(v => !v)}>
          <Text style={{ fontSize: 18 }}>{verConf ? '🙈' : '👁️'}</Text>
        </TouchableOpacity>
      </View>
      {!!erro && <Text style={s.authErro}>{erro}</Text>}
      <TouchableOpacity style={s.btnP} onPress={cadastrar} disabled={loading}>
        {loading ? <ActivityIndicator color="#000" /> : <Text style={s.btnPTxt}>Criar conta</Text>}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

// ── TELA LOGIN ────────────────────────────────────────────────────────────────
function TelaLogin({ onSuccess, onVoltar, backendUrl }) {
  const [email, setEmail]       = useState('');
  const [senha, setSenha]       = useState('');
  const [erro, setErro]         = useState('');
  const [loading, setLoading]   = useState(false);
  const [verSenha, setVerSenha] = useState(false);

  async function entrar() {
    if (!email.includes('@')) { setErro('Email inválido.'); return; }
    if (!senha)               { setErro('Digite sua senha.'); return; }
    setLoading(true); setErro('');
    try {
      const r = await fetch(`${backendUrl}/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.toLowerCase().trim(), senha })
      });
      const d = await r.json();
      if (d.ok) {
        await AsyncStorage.setItem('margo_user_id', d.user_id);
        await AsyncStorage.setItem('margo_email', d.email);
        onSuccess(d);
      } else setErro(d.erro || 'Erro ao entrar.');
    } catch(e) { setErro('Sem conexão com o servidor.'); }
    setLoading(false);
  }

  return (
    <KeyboardAvoidingView style={s.authWrap} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <TouchableOpacity onPress={onVoltar}><Text style={s.voltarTxt}>← Voltar</Text></TouchableOpacity>
      <Text style={s.authTitle}>Entrar</Text>
      <Text style={s.authSub}>Entre com sua conta para continuar.</Text>
      <TextInput style={s.authInput} placeholder="Seu email" placeholderTextColor={C.text3}
        value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
      <View style={s.senhaWrap}>
        <TextInput style={[s.authInput, { flex: 1, marginBottom: 0 }]} placeholder="Sua senha"
          placeholderTextColor={C.text3} value={senha} onChangeText={setSenha} secureTextEntry={!verSenha} />
        <TouchableOpacity style={s.olho} onPress={() => setVerSenha(v => !v)}>
          <Text style={{ fontSize: 18 }}>{verSenha ? '🙈' : '👁️'}</Text>
        </TouchableOpacity>
      </View>
      {!!erro && <Text style={s.authErro}>{erro}</Text>}
      <TouchableOpacity style={s.btnP} onPress={entrar} disabled={loading}>
        {loading ? <ActivityIndicator color="#000" /> : <Text style={s.btnPTxt}>Entrar</Text>}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

// ── PAINEL CONFIGURAÇÕES ──────────────────────────────────────────────────────
function PainelCfg({ visivel, onFechar, config, onSalvar, onSair, onUpgrade, email, plano, userId }) {
  const [cfg, setCfg]             = useState(config);
  const [verApiKey, setVerApiKey] = useState(false);
  useEffect(() => setCfg(config), [config]);
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }));

  return (
    <Modal visible={visivel} animationType="slide" presentationStyle="pageSheet" onRequestClose={onFechar}>
      <View style={{ flex: 1, backgroundColor: C.bg2 }}>
        <View style={s.modalHead}>
          <Text style={s.modalTitle}>Configurações</Text>
          <TouchableOpacity onPress={onFechar} style={s.iconBtn}>
            <Text style={{ color: C.text2, fontSize: 20 }}>✕</Text>
          </TouchableOpacity>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 24 }}
          keyboardShouldPersistTaps="handled">

          {/* SOBRE VOCÊ */}
          <View style={s.secao}>
            <Text style={s.secLabel}>SOBRE VOCÊ</Text>
            {[
              ['perfilNome','Seu nome'],['perfilNascimento','Data de nascimento (DD/MM/AAAA)'],
              ['perfilProfissao','Sua profissão'],['perfilMusica','Música favorita'],
              ['perfilComida','Comida favorita'],['perfilHobbies','Hobbies e interesses'],
              ['perfilExtra','Algo mais sobre você (opcional)'],
            ].map(([k, ph]) => (
              <TextInput key={k} style={s.cfgInput} placeholder={ph} placeholderTextColor={C.text3}
                value={cfg[k] || ''} onChangeText={v => set(k, v)}
                keyboardType={k === 'perfilNascimento' ? 'numeric' : 'default'}
                autoComplete="off" autoCorrect={false} />
            ))}
          </View>

          {/* SUA ASSISTENTE */}
          <View style={s.secao}>
            <Text style={s.secLabel}>SUA ASSISTENTE</Text>
            <TextInput style={s.cfgInput} placeholder="Nome da assistente"
              placeholderTextColor={C.text3} value={cfg.assistantName || 'Margo'}
              onChangeText={v => set('assistantName', v)}
              autoComplete="off" autoCorrect={false} autoCapitalize="words" />
            <TextInput style={[s.cfgInput, { height: 90, textAlignVertical: 'top' }]}
              placeholder="Personalidade — descreva como quiser..."
              placeholderTextColor={C.text3} value={cfg.personalidade || ''}
              onChangeText={v => set('personalidade', v)} multiline />
            <TouchableOpacity
              style={[s.cfgInput, { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }]}
              onPress={() => set('wakeWordOn', !cfg.wakeWordOn)}>
              <View>
                <Text style={{ color: C.text, fontSize: 13 }}>Palavra-chave</Text>
                <Text style={s.secSub}>
                  {cfg.wakeWordOn
                    ? `Ativa — diga "${cfg.assistantName || 'Margo'}" antes do comando`
                    : 'Desativada — responde tudo que ouve'}
                </Text>
              </View>
              <View style={[s.toggleBase, cfg.wakeWordOn && s.toggleOn]}>
                <View style={[s.toggleDot, cfg.wakeWordOn && s.toggleDotOn]} />
              </View>
            </TouchableOpacity>
            <Text style={s.secSub}>Gênero da voz</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {['F','M'].map(g => (
                <TouchableOpacity key={g} style={[s.chip, cfg.voiceGender === g && s.chipOn]}
                  onPress={() => set('voiceGender', g)}>
                  <Text style={[s.chipTxt, cfg.voiceGender === g && s.chipTxtOn]}>
                    {g === 'F' ? 'Feminina' : 'Masculina'}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* VOZ PREMIUM */}
          <View style={s.secao}>
            <Text style={s.secLabel}>VOZ PREMIUM (opcional)</Text>
            <Text style={s.secSub}>Sem chave, usa voz do dispositivo.</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {[['device','Dispositivo'],['fishaudio','Fish Audio'],['elevenlabs','ElevenLabs']].map(([p, label]) => (
                <TouchableOpacity key={p} style={[s.chip, cfg.voiceProvider === p && s.chipOn]}
                  onPress={() => set('voiceProvider', p)}>
                  <Text style={[s.chipTxt, cfg.voiceProvider === p && s.chipTxtOn]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Fish Audio */}
            <View style={[s.cfgInput, { gap: 6, backgroundColor: cfg.voiceProvider === 'fishaudio' ? C.cyanDim : C.bg3 }]}>
              <Text style={[s.secSub, { color: cfg.voiceProvider === 'fishaudio' ? C.cyan : C.text2 }]}>Fish Audio</Text>
              <View style={s.senhaWrap}>
                <TextInput style={[s.cfgInput, { flex: 1, backgroundColor: 'transparent', borderWidth: 0 }]}
                  placeholder="Chave de API" placeholderTextColor={C.text3}
                  value={cfg.apiKeyFish || ''} onChangeText={v => set('apiKeyFish', v)}
                  secureTextEntry={!verApiKey} />
                <TouchableOpacity style={s.olho} onPress={() => setVerApiKey(v => !v)}>
                  <Text>{verApiKey ? '🙈' : '👁️'}</Text>
                </TouchableOpacity>
              </View>
              <TextInput style={[s.cfgInput, { backgroundColor: 'transparent', borderWidth: 0 }]}
                placeholder="ID da voz" placeholderTextColor={C.text3}
                value={cfg.voiceIdFish || ''} onChangeText={v => set('voiceIdFish', v)} />
              <TouchableOpacity onPress={() => Linking.openURL('https://fish.audio')}>
                <Text style={{ color: C.cyan, fontSize: 11 }}>📖 Como criar conta no Fish Audio</Text>
              </TouchableOpacity>
            </View>

            {/* ElevenLabs */}
            <View style={[s.cfgInput, { gap: 6, backgroundColor: cfg.voiceProvider === 'elevenlabs' ? C.cyanDim : C.bg3, marginTop: 8 }]}>
              <Text style={[s.secSub, { color: cfg.voiceProvider === 'elevenlabs' ? C.cyan : C.text2 }]}>ElevenLabs</Text>
              <View style={s.senhaWrap}>
                <TextInput style={[s.cfgInput, { flex: 1, backgroundColor: 'transparent', borderWidth: 0 }]}
                  placeholder="Chave de API" placeholderTextColor={C.text3}
                  value={cfg.apiKeyEleven || ''} onChangeText={v => set('apiKeyEleven', v)}
                  secureTextEntry={!verApiKey} />
                <TouchableOpacity style={s.olho} onPress={() => setVerApiKey(v => !v)}>
                  <Text>{verApiKey ? '🙈' : '👁️'}</Text>
                </TouchableOpacity>
              </View>
              <TextInput style={[s.cfgInput, { backgroundColor: 'transparent', borderWidth: 0 }]}
                placeholder="ID da voz" placeholderTextColor={C.text3}
                value={cfg.voiceIdEleven || ''} onChangeText={v => set('voiceIdEleven', v)} />
              <TouchableOpacity onPress={() => Linking.openURL('https://elevenlabs.io')}>
                <Text style={{ color: C.cyan, fontSize: 11 }}>📖 Como criar conta no ElevenLabs (10.000 chars/mês grátis)</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* SPOTIFY */}
          <View style={s.secao}>
            <Text style={s.secLabel}>SPOTIFY</Text>
            <Text style={s.secSub}>Conecte sua conta para tocar músicas direto pelo app.</Text>
            <TouchableOpacity
              style={[s.btnS, { borderColor: '#1DB954' }]}
              onPress={async () => {
                try {
                  const r = await fetch(`${cfg.backendUrl}/spotify/status/${userId}`);
                  const d = await r.json();
                  if (d.conectado) {
                    Alert.alert('Spotify conectado! ✓', 'Sua conta já está vinculada. A Margo pode tocar músicas diretamente.');
                  } else {
                    const r2 = await fetch(`${cfg.backendUrl}/spotify/auth/${userId}`);
                    const d2 = await r2.json();
                    if (d2.url) Linking.openURL(d2.url);
                  }
                } catch(e) {
                  Alert.alert('Erro', 'Não foi possível conectar ao Spotify.');
                }
              }}>
              <Text style={[s.btnSTxt, { color: '#1DB954' }]}>🎵 Conectar Spotify</Text>
            </TouchableOpacity>
          </View>

          {/* CASA INTELIGENTE */}
          <View style={s.secao}>
            <Text style={s.secLabel}>CASA INTELIGENTE</Text>
            <Text style={s.secSub}>Controle dispositivos via SmartThings (Samsung).</Text>
            <TouchableOpacity style={[s.btnS, { borderColor: C.cyan }]}
              onPress={async () => {
                try {
                  const r = await fetch(`${cfg.backendUrl}/smartthings/dispositivos/${userId}`);
                  const d = await r.json();
                  if (d.conectado) {
                    const nomes = d.dispositivos.map(x => x.nome).join(', ');
                    Alert.alert('SmartThings conectado!', `Dispositivos: ${nomes || 'nenhum'}`);
                  } else {
                    const r2 = await fetch(`${cfg.backendUrl}/smartthings/auth/${userId}`);
                    const d2 = await r2.json();
                    if (d2.url) Linking.openURL(d2.url);
                  }
                } catch(e) {
                  Alert.alert('Erro', 'Não foi possível conectar ao SmartThings.');
                }
              }}>
              <Text style={[s.btnSTxt, { color: C.cyan }]}>🏠 Conectar SmartThings</Text>
            </TouchableOpacity>
          </View>

          {/* CONTA */}
          <View style={s.secao}>
            <Text style={s.secLabel}>CONTA</Text>
            <View style={[s.cfgInput, { gap: 2 }]}>
              <Text style={{ color: C.text, fontSize: 13 }}>{email}</Text>
              <Text style={{ color: C.text2, fontSize: 11 }}>
                Plano: {plano === 'free' ? 'Free (10 msgs/dia)' : plano === 'pro' ? 'Pro ✓ (50 msgs/dia)' : plano === 'pro_plus' ? 'Pro+ ✓ (90 msgs/dia)' : 'Admin ✓'}
              </Text>
            </View>
            {(plano === 'free' || plano === 'pro') && (
              <View style={{ gap: 8 }}>
                {plano === 'free' && (
                  <TouchableOpacity style={[s.btnP, { backgroundColor: '#7C3AED' }]}
                    onPress={() => onUpgrade('pro')}>
                    <Text style={s.btnPTxt}>⬆ Upgrade Pro — R$19,90/mês (50 msgs/dia)</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#059669' }]}
                  onPress={() => onUpgrade('pro_plus')}>
                  <Text style={s.btnPTxt}>⬆ Upgrade Pro+ — R$29,90/mês (90 msgs/dia)</Text>
                </TouchableOpacity>
              </View>
            )}
            <TouchableOpacity style={s.btnS} onPress={onSair}>
              <Text style={s.btnSTxt}>Sair / Trocar conta</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={s.btnP} onPress={() => onSalvar(cfg)}>
            <Text style={s.btnPTxt}>Salvar configurações</Text>
          </TouchableOpacity>
          <View style={{ height: 60 }} />
        </ScrollView>
      </View>
    </Modal>
  );
}

// ── BOLHA DE MENSAGEM ─────────────────────────────────────────────────────────
function Bolha({ msg, avatarUri }) {
  if (msg.de === 'sistema') return <Text style={s.msgSys}>{msg.texto}</Text>;
  const isUser = msg.de === 'user';
  return (
    <View style={[s.row, isUser && { flexDirection: 'row-reverse' }]}>
      <View style={[s.av, isUser && { backgroundColor: C.cyan, borderColor: C.cyan }]}>
        {isUser
          ? <Text style={{ color: C.bg, fontSize: 9, fontWeight: '700' }}>EU</Text>
          : <Image source={avatarUri ? { uri: avatarUri } : ICON} style={{ width: 22, height: 22, borderRadius: 11 }} />
        }
      </View>
      <View style={[s.bubble, isUser ? s.bubbleU : s.bubbleM]}>
        <Text style={[{ fontSize: 14, lineHeight: 22, color: C.text }, isUser && { color: '#000', fontWeight: '500' }]}>
          {msg.texto}
        </Text>
        <Text style={{ fontSize: 10, color: isUser ? 'rgba(0,0,0,0.5)' : C.text3, marginTop: 4 }}>{msg.hora}</Text>
      </View>
    </View>
  );
}

// ── APP PRINCIPAL ─────────────────────────────────────────────────────────────
export default function App() {
  const [tela, setTela]           = useState('boas_vindas');
  const [userId, setUserId]       = useState(null);
  const [email, setEmail]         = useState('');
  const [plano, setPlano]         = useState('free');
  const [msgs, setMsgs]           = useState([]);
  const [input, setInput]         = useState('');
  const [pensando, setPensando]   = useState(false);
  const [micAtivo, setMicAtivo]   = useState(false);
  const [location, setLocation]   = useState(null);
  const [faltam, setFaltam]       = useState(null);
  const [cfgAberto, setCfgAberto] = useState(false);
  const [config, setConfig]       = useState(CFG_PADRAO);
  const [avatarUri, setAvatarUri] = useState(null);
  const [vozAtiva, setVozAtiva]   = useState(true);
  const [wakeDetected, setWakeDetected] = useState(false);
  const scrollRef                 = useRef(null);
  const micAtivoRef               = useRef(false);
  const wakeWordRef               = useRef(true); // ref para usar dentro de callbacks

  // ── INIT ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    iniciar();
    pedirLocalizacao();
    Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false });
  }, []);

  // Heartbeat — só para garantir que não travou, a cada 60s
  useEffect(() => {
    micAtivoRef.current = micAtivo;
    wakeWordRef.current = config.wakeWordOn;
    if (!micAtivo) return;
    const interval = setInterval(() => {
      // Só reinicia se não está ouvindo ativamente
      if (micAtivoRef.current && ExpoSpeechRecognitionModule) {
        try {
          ExpoSpeechRecognitionModule.start({ lang: 'pt-BR', interimResults: false });
        } catch(e) {}
      }
    }, 60000);
    return () => clearInterval(interval);
  }, [micAtivo, config.wakeWordOn]);

  async function iniciar() {
    const uid  = await AsyncStorage.getItem('margo_user_id');
    const em   = await AsyncStorage.getItem('margo_email');
    const av   = await AsyncStorage.getItem('margo_avatar');
    let cfg    = await AsyncStorage.getItem('margo_config');
    if (!cfg) cfg = await AsyncStorage.getItem('margo_settings');
    if (av) setAvatarUri(av);
    if (cfg) { try { setConfig(c => ({ ...c, ...JSON.parse(cfg) })); } catch(e) {} }
    if (uid) {
      setUserId(uid); setEmail(em || ''); setTela('chat');
      const hist = await AsyncStorage.getItem('margo_chat');
      if (hist) { try { setMsgs(JSON.parse(hist)); } catch(e) {} }
      contarMsgs(uid);
    }
  }

  async function pedirLocalizacao() {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status === 'granted') {
      const loc = await Location.getCurrentPositionAsync({});
      setLocation({ lat: loc.coords.latitude, lng: loc.coords.longitude });
    }
  }

  async function contarMsgs(uid) {
    try {
      const r = await fetch(`${config.backendUrl}/uso/${uid}`);
      const d = await r.json();
      setFaltam(d.plano === 'free' ? d.faltam : null);
      setPlano(d.plano || 'free');
    } catch(e) {}
  }

  // ── CONTATOS ──────────────────────────────────────────────────────────────
  async function buscarContato(nome) {
    try {
      const { status } = await Contacts.requestPermissionsAsync();
      if (status !== 'granted') return null;
      const { data } = await Contacts.getContactsAsync({
        fields: [Contacts.Fields.PhoneNumbers, Contacts.Fields.Name],
      });
      const nomeLower = nome.toLowerCase();
      const contato = data.find(c =>
        c.name && c.name.toLowerCase().includes(nomeLower)
      );
      if (contato && contato.phoneNumbers && contato.phoneNumbers.length > 0) {
        return contato.phoneNumbers[0].number;
      }
    } catch(e) { console.log('Contatos erro:', e); }
    return null;
  }

  // ── MENSAGENS ─────────────────────────────────────────────────────────────
  function addMsg(de, texto) {
    const nova = { de, texto, hora: hora(), id: Date.now() + Math.random() };
    setMsgs(prev => {
      const novas = [...prev, nova];
      AsyncStorage.setItem('margo_chat', JSON.stringify(novas.slice(-30)));
      return novas;
    });
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }

  // ── ENVIAR ────────────────────────────────────────────────────────────────
  async function enviar(msg) {
    msg = (msg || input).trim();
    if (!msg || pensando || !userId) return;
    setInput('');
    addMsg('user', msg);
    setPensando(true);
    try {
      const body = { user_id: userId, mensagem: msg };
      if (location) { body.latitude = location.lat; body.longitude = location.lng; }
      // Passa hora local do dispositivo
      body.hora_local = new Date().toLocaleString('pt-BR', { timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone });
      const r = await fetch(`${config.backendUrl}/mensagem`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      const d = await r.json();
      const texto = d.resposta || 'Sem resposta.';
      addMsg('margo', texto);
      falar(limpar(texto));
      // Delay para Margo terminar de falar antes de abrir apps
      if (d.ferramenta) {
        const t = d.ferramenta.ferramenta;
        const precisaDelay = ['maps_navigate','maps_search','spotify_play','youtube_search','soundcloud_play'].includes(t);
        if (precisaDelay) {
          setTimeout(() => executarFerramenta(d.ferramenta), 3000);
        } else {
          await executarFerramenta(d.ferramenta);
        }
      }
      contarMsgs(userId);
    } catch(e) { addMsg('margo', 'Sem conexão com o servidor.'); }
    setPensando(false);
  }

  // Spotify play direto via backend OAuth
  async function spotifyPlayDireto(query) {
    try {
      const r = await fetch(`${config.backendUrl}/spotify/play`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, query })
      });
      const d = await r.json();
      return d.ok === true;
    } catch(e) { return false; }
  }

  // ── FERRAMENTAS ───────────────────────────────────────────────────────────
  async function executarFerramenta(f) {
    const t = f.ferramenta;

    if (t === 'maps_navigate') {
      const dest = encodeURIComponent(f.destino);
      const origin = location ? `&origin=${location.lat},${location.lng}` : '';
      // Tenta app nativo primeiro
      const appUrl = `google.navigation:q=${dest}`;
      const webUrl = `https://www.google.com/maps/dir/?api=1&destination=${dest}${origin}`;
      const supported = await Linking.canOpenURL(appUrl).catch(() => false);
      Linking.openURL(supported ? appUrl : webUrl).catch(() => {});

    } else if (t === 'maps_search') {
      const q = encodeURIComponent(f.query);
      const coords = location ? `${location.lat},${location.lng}` : '0,0';
      const appUrl = `geo:${coords}?q=${q}`;
      const webUrl = `https://www.google.com/maps/search/${q}`;
      const supported = await Linking.canOpenURL(appUrl).catch(() => false);
      Linking.openURL(supported ? appUrl : webUrl).catch(() => {});

    } else if (t === 'spotify_play') {
      // Tenta tocar via OAuth primeiro
      const tocou = await spotifyPlayDireto(f.query);
      if (!tocou) {
        // Usa URI direto se disponível (abre música exata), senão busca
        const uri = f.spotify_uri || f.spotify_id
          ? `spotify:track:${f.spotify_id}`
          : null;
        const appUrl = uri || `spotify:search:${encodeURIComponent(f.query)}`;
        const webUrl = f.spotify_id
          ? `https://open.spotify.com/track/${f.spotify_id}`
          : `https://open.spotify.com/search/${encodeURIComponent(f.query)}`;
        const supported = await Linking.canOpenURL(appUrl).catch(() => false);
        Linking.openURL(supported ? appUrl : webUrl).catch(() => {});
      }

    } else if (t === 'soundcloud_play') {
      Linking.openURL(`https://soundcloud.com/search?q=${encodeURIComponent(f.query)}`).catch(() => {});

    } else if (t === 'youtube_search') {
      const q = encodeURIComponent(f.query);
      const appUrl = `vnd.youtube:///results?search_query=${q}`;
      const webUrl = `https://www.youtube.com/results?search_query=${q}`;
      const supported = await Linking.canOpenURL(appUrl).catch(() => false);
      Linking.openURL(supported ? appUrl : webUrl).catch(() => {});

    } else if (t === 'phone_call') {
      // Busca nos contatos primeiro
      let numero = f.contato;
      if (isNaN(f.contato.replace(/\D/g, ''))) {
        const encontrado = await buscarContato(f.contato);
        if (encontrado) numero = encontrado;
      }
      Linking.openURL(`tel:${numero}`).catch(() => {});

    } else if (t === 'web_search') {
      // Não abre browser — backend já fez a busca e incluiu na resposta
    }
  }

  // ── TTS ───────────────────────────────────────────────────────────────────
  async function tocarAudioBase64(base64, onFim) {
    try {
      await Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false });
      const { sound } = await Audio.Sound.createAsync(
        { uri: `data:audio/mpeg;base64,${base64}` },
        { shouldPlay: true, volume: 1.0 }
      );
      sound.setOnPlaybackStatusUpdate(st => {
        if (st.didJustFinish) {
          sound.unloadAsync().catch(() => {});
          if (onFim) onFim();
        }
      });
      return true;
    } catch(e) {
      console.log('Áudio erro:', e);
      return false;
    }
  }

  function religarMic() {
    if (micAtivoRef.current && ExpoSpeechRecognitionModule) {
      setTimeout(() => {
        try { ExpoSpeechRecognitionModule.start({ lang: 'pt-BR', interimResults: false }); } catch(e) {}
      }, 500);
    }
  }

  async function falar(texto) {
    if (!vozAtiva) return;
    if (micAtivoRef.current && ExpoSpeechRecognitionModule) {
      try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
    }
    Speech.stop();

    const chave = config.voiceProvider === 'fishaudio'
      ? (config.apiKeyFish || config.apiKey)
      : config.voiceProvider === 'elevenlabs'
      ? (config.apiKeyEleven || config.apiKey)
      : '';
    const vozId = config.voiceProvider === 'fishaudio'
      ? (config.voiceIdFish || config.voiceId)
      : config.voiceProvider === 'elevenlabs'
      ? (config.voiceIdEleven || config.voiceId)
      : '';

    if (config.voiceProvider === 'fishaudio' && chave && vozId) {
      try {
        const r = await fetch('https://api.fish.audio/v1/tts', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${chave}`,
            'Content-Type': 'application/json',
            'model': 's2-pro',
          },
          body: JSON.stringify({
            text: texto.substring(0, 500), // limita tamanho para evitar timeout
            reference_id: vozId,
            format: 'mp3',
            mp3_bitrate: 128,
          })
        });
        if (r.ok) {
          const buffer = await r.arrayBuffer();
          const bytes = new Uint8Array(buffer);
          let binary = '';
          const chunkSize = 8192;
          for (let i = 0; i < bytes.length; i += chunkSize) {
            binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
          }
          const base64 = btoa(binary);
          const ok = await tocarAudioBase64(base64, religarMic);
          if (ok) return;
        } else {
          console.log('Fish Audio status:', r.status);
        }
      } catch(e) { console.log('Fish Audio direto erro:', e); }
    }

    if (config.voiceProvider === 'elevenlabs' && chave && vozId) {
      try {
        // Chama ElevenLabs DIRETAMENTE
        const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${vozId}`, {
          method: 'POST',
          headers: {
            'xi-api-key': chave,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            text: texto,
            model_id: 'eleven_multilingual_v2',
            voice_settings: { stability: 0.5, similarity_boost: 0.75 }
          })
        });
        if (r.ok) {
          const buffer = await r.arrayBuffer();
          const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
          const ok = await tocarAudioBase64(base64, religarMic);
          if (ok) return;
        }
      } catch(e) { console.log('ElevenLabs direto erro:', e); }
    }

    // Fallback: voz do dispositivo
    Speech.speak(texto, {
      language: 'pt-BR',
      pitch: config.voiceGender === 'F' ? 1.2 : 0.8,
      rate: 1.0,
      onDone: religarMic,
    });
  }

  // ── MICROFONE ─────────────────────────────────────────────────────────────
  useSpeechRecognitionEvent('result', (e) => {
    const transcript = e.results?.[0]?.transcript;
    if (!transcript || !e.isFinal) return;
    if (wakeWordRef.current) {
      const nome = config.assistantName.toLowerCase();
      if (transcript.toLowerCase().includes(nome)) {
        const semNome = transcript.toLowerCase().replace(nome, '').trim();
        if (semNome) enviar(semNome);
      }
    } else {
      enviar(transcript);
    }
  });

  useSpeechRecognitionEvent('error', (e) => {
    console.log('Mic erro:', e.error);
    if (e.error === 'not-allowed') {
      setMicAtivo(false);
      micAtivoRef.current = false;
    }
  });

  useSpeechRecognitionEvent('end', () => {
    // Não reinicia automaticamente — evita pipoco
    // Usuário aperta o botão quando quiser falar
    setMicAtivo(false);
    micAtivoRef.current = false;
  });

  // Eventos do módulo nativo
  useEffect(() => {
    if (!micEmitter) return;
    const sub = micEmitter.addListener('onSpeechResult', (e) => {
      const text = e.text;
      if (!text) return;
      if (e.wakeWordDetected || !wakeWordRef.current) {
        enviar(text);
      }
    });
    return () => sub.remove();
  }, []);

  async function iniciarMicrofone() {
    if (MicrophoneModule) {
      // Usa módulo nativo
      try {
        const nome = config.assistantName || 'Margo';
        await MicrophoneModule.startListening(nome, true);
        setMicAtivo(true);
        micAtivoRef.current = true;
      } catch(e) { console.log('Mic nativo erro:', e); }
    } else if (ExpoSpeechRecognitionModule) {
      // Fallback expo
      try {
        const perm = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
        if (!perm.granted) return;
        ExpoSpeechRecognitionModule.start({ lang: 'pt-BR', interimResults: false });
        setMicAtivo(true);
        micAtivoRef.current = true;
      } catch(e) { console.log('Mic expo erro:', e); }
    }
  }

  async function pararMicrofone() {
    micAtivoRef.current = false;
    setMicAtivo(false);
    if (MicrophoneModule) {
      try { await MicrophoneModule.stopListening(); } catch(e) {}
    } else if (ExpoSpeechRecognitionModule) {
      try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
    }
  }

  async function toggleMic() {
    if (!ExpoSpeechRecognitionModule) {
      Alert.alert('Microfone', 'Use o teclado no Expo Go. O microfone funciona no app instalado.');
      return;
    }
    if (micAtivo) await pararMicrofone();
    else await iniciarMicrofone();
  }

  // ── AUTH ──────────────────────────────────────────────────────────────────
  async function onAuthSuccess(data) {
    setUserId(data.user_id); setEmail(data.email); setPlano(data.plano || 'free'); setTela('chat');
    contarMsgs(data.user_id);
    if (data.novo) {
      setTimeout(() => {
        addMsg('margo', `Olá! Sou a ${config.assistantName}. Preencha seu perfil nas configurações — toque em ⚙ acima!`);
        setCfgAberto(true);
      }, 500);
    } else {
      try {
        const r = await fetch(`${config.backendUrl}/usuario/${data.user_id}`);
        const u = await r.json();
        const novoConfig = { ...config };
        // Lê chaves salvas localmente primeiro (não vêm do servidor)
        const cfgLocal = await AsyncStorage.getItem('margo_config');
        const cfgLocalParsed = cfgLocal ? JSON.parse(cfgLocal) : {};

        if (u.perfil) {
          Object.assign(novoConfig, {
            perfilNome: u.perfil.nome || '', perfilNascimento: u.perfil.idade || '',
            perfilProfissao: u.perfil.profissao || '', perfilMusica: u.perfil.musica || '',
            perfilComida: u.perfil.comida || '', perfilHobbies: u.perfil.hobbies || '',
            perfilExtra: u.perfil.extra || '',
          });
        }
        if (u.config) {
          Object.assign(novoConfig, {
            assistantName: u.config.nome_assistente || 'Margo',
            voiceGender:   u.config.genero || 'F',
            personalidade: u.config.personalidade || '',
            voiceProvider: u.config.voz_provider || 'device',
            voiceId:       u.config.voz_id || '',
            // Preserva chaves locais do AsyncStorage
            apiKey:        cfgLocalParsed.apiKey || '',
            apiKeyFish:    cfgLocalParsed.apiKeyFish || '',
            voiceIdFish:   cfgLocalParsed.voiceIdFish || u.config.voz_id || '',
            apiKeyEleven:  cfgLocalParsed.apiKeyEleven || '',
            voiceIdEleven: cfgLocalParsed.voiceIdEleven || '',
          });
        }
        setConfig(novoConfig);
        await AsyncStorage.setItem('margo_config', JSON.stringify(novoConfig));
        const hist = await AsyncStorage.getItem('margo_chat');
        const nome = u.perfil?.nome || '';
        if (!hist) addMsg('margo', `Olá${nome ? ', ' + nome : ''}! Tô aqui e pronta pra te ajudar. O que vamos fazer?`);
        else { try { setMsgs(JSON.parse(hist)); } catch(e) {} }
      } catch(e) {
        addMsg('margo', `Olá! Tô aqui e pronta pra te ajudar. O que vamos fazer?`);
      }
    }
  }

  async function salvarConfig(cfg) {
    setConfig(cfg);
    await AsyncStorage.setItem('margo_config', JSON.stringify(cfg));
    setCfgAberto(false);
    try {
      const chaveEnviar = cfg.voiceProvider === 'fishaudio'
        ? (cfg.apiKeyFish || '')
        : cfg.voiceProvider === 'elevenlabs'
        ? (cfg.apiKeyEleven || '')
        : '';
      const vozIdEnviar = cfg.voiceProvider === 'fishaudio'
        ? (cfg.voiceIdFish || '')
        : cfg.voiceProvider === 'elevenlabs'
        ? (cfg.voiceIdEleven || '')
        : '';
      await fetch(`${cfg.backendUrl}/salvar_perfil_completo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId, nome: cfg.perfilNome, nascimento: cfg.perfilNascimento,
          profissao: cfg.perfilProfissao, musica: cfg.perfilMusica,
          comida: cfg.perfilComida, hobbies: cfg.perfilHobbies, extra: cfg.perfilExtra,
          nome_assistente: cfg.assistantName, genero: cfg.voiceGender,
          personalidade: cfg.personalidade, voz_provider: cfg.voiceProvider,
          voz_chave: chaveEnviar, voz_id: vozIdEnviar,
        })
      });
      addMsg('sistema', `Configurações salvas!${cfg.perfilNome ? ' Olá, ' + cfg.perfilNome + '!' : ''}`);
    } catch(e) { addMsg('sistema', 'Salvo localmente.'); }
  }

  async function trocarAvatar() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert('Permissão negada', 'Permite acesso à galeria nas configurações.'); return; }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true, aspect: [1, 1], quality: 0.7,
    });
    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      setAvatarUri(uri);
      await AsyncStorage.setItem('margo_avatar', uri);
    }
  }

  async function handleUpgrade(planoEscolhido) {
    try {
      const r = await fetch(`${config.backendUrl}/stripe/criar_checkout`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, plano: planoEscolhido, email })
      });
      const d = await r.json();
      if (d.url) {
        setCfgAberto(false);
        Linking.openURL(d.url);
      }
    } catch(e) { console.log('Upgrade erro:', e); }
  }

  async function sair() {
    Alert.alert('Sair', 'Tem certeza?', [
      { text: 'Cancelar' },
      { text: 'Sair', style: 'destructive', onPress: async () => {
        await pararMicrofone();
        await AsyncStorage.multiRemove(['margo_user_id', 'margo_email', 'margo_chat', 'margo_config', 'margo_avatar']);
        setConfig(CFG_PADRAO);
        setAvatarUri(null);
        setUserId(null); setMsgs([]); setCfgAberto(false); setTela('boas_vindas');
      }}
    ]);
  }

  // ── RENDER ────────────────────────────────────────────────────────────────
  if (tela === 'boas_vindas') return <TelaBoasVindas onEntrar={() => setTela('login')} onCadastrar={() => setTela('cadastro')} />;
  if (tela === 'cadastro')    return <TelaCadastro onSuccess={onAuthSuccess} onVoltar={() => setTela('boas_vindas')} backendUrl={config.backendUrl} />;
  if (tela === 'login')       return <TelaLogin    onSuccess={onAuthSuccess} onVoltar={() => setTela('boas_vindas')} backendUrl={config.backendUrl} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg2} />

      {/* HEADER */}
      <View style={s.header}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <TouchableOpacity onPress={trocarAvatar} style={s.headerAv}>
            <Image source={avatarUri ? { uri: avatarUri } : ICON}
              style={{ width: 36, height: 36, borderRadius: 18 }} />
          </TouchableOpacity>
          <View>
            <Text style={s.headerName}>{config.assistantName}</Text>
            <Text style={s.headerSub}>{pensando ? 'pensando...' : micAtivo ? 'ouvindo...' : 'online'}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity style={[s.iconBtn, !vozAtiva && { borderColor: C.red }]}
            onPress={() => setVozAtiva(v => !v)}>
            <Text style={{ fontSize: 16 }}>{vozAtiva ? '🔊' : '🔇'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.iconBtn} onPress={() => {
            setMsgs([]); AsyncStorage.removeItem('margo_chat');
            addMsg('sistema', 'Conversa reiniciada');
          }}>
            <Text style={{ color: C.text2, fontSize: 18 }}>↺</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.iconBtn} onPress={() => setCfgAberto(true)}>
            <Text style={{ color: C.text2, fontSize: 18 }}>⚙</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* CHAT + INPUT */}
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}>

        <ScrollView ref={scrollRef} style={{ flex: 1 }}
          contentContainerStyle={{ padding: 14, gap: 10 }}
          keyboardShouldPersistTaps="handled">
          {msgs.map(m => <Bolha key={m.id} msg={m} avatarUri={avatarUri} />)}
          {pensando && (
            <View style={s.row}>
              <View style={s.av}>
                <Image source={avatarUri ? { uri: avatarUri } : ICON}
                  style={{ width: 22, height: 22, borderRadius: 11 }} />
              </View>
              <View style={[s.bubble, s.bubbleM, { paddingVertical: 14 }]}>
                <ActivityIndicator size="small" color={C.text3} />
              </View>
            </View>
          )}
        </ScrollView>

        {/* INPUT */}
        <View style={s.inputArea}>
          <View style={s.inputRow}>
            <TextInput
              style={s.inputTxt}
              placeholder="Digite uma mensagem..."
              placeholderTextColor={C.text3}
              value={input}
              onChangeText={setInput}
              onSubmitEditing={() => enviar()}
              returnKeyType="send"
              multiline={false}
            />
            <TouchableOpacity
              style={[s.micBtn, micAtivo && s.micBtnOn]}
              onPress={toggleMic}>
              <Text style={{ fontSize: 18 }}>{micAtivo ? '🎙️' : '🎤'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.sendBtn} onPress={() => enviar()}>
              <Text style={{ color: '#000', fontSize: 18, fontWeight: '700' }}>▶</Text>
            </TouchableOpacity>
          </View>
          {faltam !== null && (
            <Text style={[{ textAlign: 'center', fontSize: 10, color: C.text3, marginTop: 7 },
              faltam <= 5 && { color: C.red }]}>
              {faltam} mensagens restantes hoje
            </Text>
          )}
        </View>
      </KeyboardAvoidingView>

      {/* PAINEL CONFIG */}
      <PainelCfg
        visivel={cfgAberto}
        onFechar={() => setCfgAberto(false)}
        config={config}
        onSalvar={salvarConfig}
        onSair={sair}
        onUpgrade={handleUpgrade}
        email={email}
        plano={plano}
        userId={userId}
      />
    </SafeAreaView>
  );
}

// ── ESTILOS ───────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  fullCenter:  { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center', padding:32 },
  logoCircle:  { width:90, height:90, borderRadius:45, backgroundColor:C.bg3, borderWidth:2, borderColor:C.cyan, alignItems:'center', justifyContent:'center', marginBottom:24 },
  welcomeName: { fontSize:36, fontWeight:'700', color:C.text, marginBottom:8 },
  welcomeDesc: { fontSize:15, color:C.text2, textAlign:'center', lineHeight:22 },
  authWrap:    { flex:1, backgroundColor:C.bg, padding:24, paddingTop:64 },
  voltarTxt:   { color:C.cyan, fontSize:15, marginBottom:32 },
  authTitle:   { fontSize:26, fontWeight:'700', color:C.text, marginBottom:8 },
  authSub:     { fontSize:13, color:C.text2, marginBottom:32, lineHeight:20 },
  authInput:   { backgroundColor:C.bg3, borderWidth:0.5, borderColor:C.border, borderRadius:10, padding:14, fontSize:15, color:C.text, marginBottom:12 },
  authErro:    { fontSize:12, color:C.red, marginBottom:12 },
  senhaWrap:   { flexDirection:'row', alignItems:'center', gap:8, marginBottom:12 },
  olho:        { padding:8 },
  btnP:        { backgroundColor:C.cyan, borderRadius:26, padding:15, alignItems:'center' },
  btnPTxt:     { fontSize:15, fontWeight:'700', color:'#000' },
  btnS:        { backgroundColor:'transparent', borderRadius:26, padding:15, alignItems:'center', borderWidth:0.5, borderColor:C.border },
  btnSTxt:     { fontSize:15, color:C.text2 },
  header:      { flexDirection:'row', alignItems:'center', justifyContent:'space-between', padding:14, backgroundColor:C.bg2, borderBottomWidth:0.5, borderBottomColor:C.border },
  headerAv:    { width:42, height:42, borderRadius:21, backgroundColor:C.bg3, borderWidth:1.5, borderColor:C.cyan, alignItems:'center', justifyContent:'center', overflow:'hidden' },
  headerName:  { fontSize:15, fontWeight:'700', color:C.text },
  headerSub:   { fontSize:11, color:C.text2, marginTop:2 },
  iconBtn:     { width:36, height:36, borderRadius:18, backgroundColor:C.bg3, borderWidth:0.5, borderColor:C.border, alignItems:'center', justifyContent:'center' },
  row:         { flexDirection:'row', gap:8, alignItems:'flex-end' },
  av:          { width:30, height:30, borderRadius:15, backgroundColor:C.bg3, borderWidth:1, borderColor:C.border, alignItems:'center', justifyContent:'center', overflow:'hidden' },
  bubble:      { maxWidth:'78%', padding:11, borderRadius:16 },
  bubbleM:     { backgroundColor:C.bg3, borderWidth:0.5, borderColor:C.border, borderBottomLeftRadius:4 },
  bubbleU:     { backgroundColor:C.cyan, borderBottomRightRadius:4 },
  msgSys:      { textAlign:'center', fontSize:11, color:C.text3, paddingVertical:4 },
  inputArea:   { padding:10, paddingBottom:Platform.OS === 'ios' ? 20 : 12, backgroundColor:C.bg2, borderTopWidth:0.5, borderTopColor:C.border },
  inputRow:    { flexDirection:'row', alignItems:'center', gap:8, backgroundColor:C.bg3, borderWidth:0.5, borderColor:C.border, borderRadius:26, paddingLeft:14, paddingRight:4 },
  inputTxt:    { flex:1, fontSize:14, color:C.text, paddingVertical:12 },
  micBtn:      { width:38, height:38, borderRadius:19, backgroundColor:C.bg, borderWidth:1, borderColor:C.border, alignItems:'center', justifyContent:'center' },
  micBtnOn:    { backgroundColor:C.cyanDim, borderColor:C.cyan },
  sendBtn:     { width:38, height:38, borderRadius:19, backgroundColor:C.cyan, alignItems:'center', justifyContent:'center' },
  modalHead:   { flexDirection:'row', alignItems:'center', justifyContent:'space-between', padding:16, borderBottomWidth:0.5, borderBottomColor:C.border },
  modalTitle:  { fontSize:17, fontWeight:'700', color:C.text },
  secao:       { gap:10 },
  secLabel:    { fontSize:11, fontWeight:'600', color:C.text2, letterSpacing:1 },
  secSub:      { fontSize:12, color:C.text3 },
  cfgInput:    { backgroundColor:C.bg3, borderWidth:0.5, borderColor:C.border, borderRadius:10, padding:12, fontSize:13, color:C.text },
  toggleBase:  { width:44, height:24, borderRadius:12, backgroundColor:C.bg, borderWidth:1, borderColor:C.border, justifyContent:'center', padding:2 },
  toggleOn:    { backgroundColor:C.cyanDim, borderColor:C.cyan },
  toggleDot:   { width:18, height:18, borderRadius:9, backgroundColor:C.text3 },
  toggleDotOn: { backgroundColor:C.cyan, alignSelf:'flex-end' },
  chipOn:      { borderColor:C.cyan, backgroundColor:C.cyanDim },
  chipTxt:     { fontSize:12, color:C.text2 },
  chipTxtOn:   { color:C.cyan },
});
