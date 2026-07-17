import { useState, useEffect, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, AppState, NativeModules,
  StyleSheet, KeyboardAvoidingView, Platform, StatusBar,
  ActivityIndicator, Linking, Alert, SafeAreaView, Modal, Image,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Speech from 'expo-speech';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import * as Contacts from 'expo-contacts';
import { Audio } from 'expo-av';
import * as Notifications from 'expo-notifications';
import * as Localization from 'expo-localization';
import * as TaskManager from 'expo-task-manager';
// WakeWordService importado via NativeModules diretamente

// Configura canal de notificação Android
if (Platform.OS === 'android') {
  Notifications.setNotificationChannelAsync('default', {
    name: 'Margo',
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 250, 250, 250],
    lightColor: '#2E9AAF',
  });
  Notifications.setNotificationChannelAsync('lembretes', {
    name: 'Lembretes',
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 250, 250, 250],
  });
}

// Configura notificação persistente (foreground service)
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

const MARGO_TASK = 'margo-foreground-task';
import * as Device from 'expo-device';

// Módulo nativo de microfone (Expo Modules API)
let ExpoMicrophoneModule = null;
let micEmitter = null;
try {
  const micMod = require('./modules/modules/expo-microphone');
  ExpoMicrophoneModule = micMod.default || micMod;
  const { EventEmitter } = require('expo-modules-core');
  if (ExpoMicrophoneModule) micEmitter = new EventEmitter(ExpoMicrophoneModule);
} catch(e) { console.log('Módulo nativo não disponível:', e.message); }

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
  bg:      '#0D1A1C', bg2: '#112225', bg3: '#1A3035',
  cyan:    '#2E9AAF', cyanDim: 'rgba(46,154,175,0.15)',
  text:    '#E8E8F0', text2: '#8888A0', text3: '#555568',
  border:  'rgba(46,154,175,0.15)', red: '#FF6B6B',
};

const CFG_PADRAO = {
  assistantName: 'Margo', voiceGender: 'F', voiceProvider: 'device',
  apiKey: '', voiceId: '',
  apiKeyFish: '', voiceIdFish: '',
  apiKeyEleven: '', voiceIdEleven: '',
  navApp: 'waze',
  personalidade: '', perfilNome: '', perfilNascimento: '',
  perfilProfissao: '', perfilMusica: '', perfilComida: '',
  perfilHobbies: '', perfilExtra: '',
  wakeWordOn: false,
  idioma: 'pt-BR',
  idioma: 'pt-BR',
  backendUrl: BACKEND,
};

const hora = () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

async function verificarLembretesPendentes(userId, backendUrl, agendarNotificacao) {
  try {
    const r = await fetch(`${backendUrl}/agenda/pendentes/${userId}`);
    const d = await r.json();
    for (const lembrete of d.pendentes || []) {
      let prefixo = '';
      if (lembrete.tipo === '12h') prefixo = '📅 Amanhã: ';
      else if (lembrete.tipo === '1h') prefixo = '⏰ Em 1 hora: ';
      else prefixo = '🔔 Agora: ';
      
      await Notifications.scheduleNotificationAsync({
        content: {
          title: `${prefixo}${lembrete.titulo}`,
          body: lembrete.descricao || lembrete.titulo,
          sound: true,
        },
        trigger: { type: "timeInterval", seconds: 2, repeats: false },
      });
    }
  } catch(e) { console.log('Lembretes pendentes erro:', e); }
}

// ── TRADUÇÕES ─────────────────────────────────────────────────────────────────
const STRINGS = {
  'pt-BR': {
    // Boas vindas
    app_desc: 'Sua assistente pessoal de IA\ncom personalidade única',
    criar_conta: 'Criar conta',
    ja_tenho_conta: 'Já tenho conta',
    by_orbiby: 'by Orbiby',
    // Cadastro
    voltar: '← Voltar',
    titulo_cadastro: 'Criar conta',
    sub_cadastro: 'Crie sua conta para acessar a Margo em qualquer dispositivo.',
    placeholder_email: 'Seu email',
    placeholder_senha: 'Senha (mínimo 6 caracteres)',
    placeholder_confirmar: 'Confirmar senha',
    // Login
    titulo_login: 'Entrar',
    sub_login: 'Entre com sua conta para continuar.',
    placeholder_senha_login: 'Sua senha',
    btn_entrar: 'Entrar',
    // Configurações
    titulo_config: 'Configurações',
    sobre_voce: 'SOBRE VOCÊ',
    sua_assistente: 'SUA ASSISTENTE',
    placeholder_nome_assistente: 'Nome da assistente',
    placeholder_personalidade: 'Personalidade — ex: divertida, fala gírias, adora música, sempre bem-humorada, usa emojis, fala como amiga próxima...',
    voz: 'VOZ',
    genero_voz: 'Escolha o gênero da voz do assistente.',
    provedor_voz: 'Provedor de voz:',
    kokoro_desc: '✨ Voz neural gratuita com tecnologia Kokoro AI',
    fish_link: '📖 Como criar conta no Fish Audio',
    eleven_link: '📖 Como criar conta no ElevenLabs',
    spotify_label: 'SPOTIFY',
    spotify_desc: 'Conecte sua conta para tocar músicas direto pelo app.',
    salvar: 'Salvar configurações',
    sair: 'Sair / Trocar conta',
    // Chat
    placeholder_msg: 'Digite uma mensagem...',
    online: 'online',
    ouvindo: 'ouvindo...',
    pensando: 'pensando...',
    // Planos
    plano_free: 'Free trial (50 interações)',
    plano_pro: 'Pro ✓ (20 msgs/dia)',
    plano_pro_plus: 'Pro+ ✓ (50 msgs/dia)',
    plano_admin: 'Admin ✓',
    // Alerts
    sair_titulo: 'Sair',
    sair_msg: 'Tem certeza?',
    sair_btn: 'Sair',
    cancelar: 'Cancelar',
    contato_nao_encontrado: 'Contato não encontrado na agenda.',
    numero_invalido: 'Número inválido.',
    pagamento_titulo: 'Forma de pagamento',
    pagamento_msg: 'Como deseja pagar?',
    pagamento_cartao: '💳 Cartão de crédito',
    pagamento_pix: '🏦 PIX',
    paywall_trial_titulo: '🎉 Trial encerrado!',
    paywall_trial_msg: 'Você usou todas as 50 interações gratuitas. Assine um plano para continuar!',
    paywall_limite_titulo: '⚠️ Limite atingido!',
    paywall_limite_msg: 'Você atingiu seu limite diário. Assine um plano superior ou compre interações extras!',
    btn_pro: '🔥 Pro — R$9,90/mês',
    btn_pro_plus: '🚀 Pro+ — R$19,90/mês',
    btn_avulso: '💊 50 interações — R$9,90',
  },
  'en-US': {
    app_desc: 'Your personal AI assistant\nwith a unique personality',
    criar_conta: 'Create account',
    ja_tenho_conta: 'I already have an account',
    by_orbiby: 'by Orbiby',
    voltar: '← Back',
    titulo_cadastro: 'Create account',
    sub_cadastro: 'Create your account to access Margo on any device.',
    placeholder_email: 'Your email',
    placeholder_senha: 'Password (minimum 6 characters)',
    placeholder_confirmar: 'Confirm password',
    titulo_login: 'Sign in',
    sub_login: 'Sign in to your account to continue.',
    placeholder_senha_login: 'Your password',
    btn_entrar: 'Sign in',
    titulo_config: 'Settings',
    sobre_voce: 'ABOUT YOU',
    sua_assistente: 'YOUR ASSISTANT',
    placeholder_nome_assistente: 'Assistant name',
    placeholder_personalidade: 'Personality — ex: fun, uses slang, loves music, always cheerful, uses emojis, talks like a close friend...',
    voz: 'VOICE',
    genero_voz: 'Choose the voice gender for your assistant.',
    provedor_voz: 'Voice provider:',
    kokoro_desc: '✨ Free neural voice powered by Kokoro AI',
    fish_link: '📖 How to create a Fish Audio account',
    eleven_link: '📖 How to create an ElevenLabs account',
    spotify_label: 'SPOTIFY',
    spotify_desc: 'Connect your account to play music directly from the app.',
    salvar: 'Save settings',
    sair: 'Sign out / Switch account',
    placeholder_msg: 'Type a message...',
    online: 'online',
    ouvindo: 'listening...',
    pensando: 'thinking...',
    plano_free: 'Free trial (50 interactions)',
    plano_pro: 'Pro ✓ (20 msgs/day)',
    plano_pro_plus: 'Pro+ ✓ (50 msgs/day)',
    plano_admin: 'Admin ✓',
    sair_titulo: 'Sign out',
    sair_msg: 'Are you sure?',
    sair_btn: 'Sign out',
    cancelar: 'Cancel',
    contato_nao_encontrado: 'Contact not found in your contacts.',
    numero_invalido: 'Invalid number.',
    pagamento_titulo: 'Payment method',
    pagamento_msg: 'How would you like to pay?',
    pagamento_cartao: '💳 Credit card',
    pagamento_pix: '🏦 PIX',
    paywall_trial_titulo: '🎉 Trial ended!',
    paywall_trial_msg: 'You used all 50 free interactions. Subscribe to continue!',
    paywall_limite_titulo: '⚠️ Limit reached!',
    paywall_limite_msg: 'You reached your daily limit. Subscribe or buy extra interactions!',
    btn_pro: '🔥 Pro — R$9.90/mo',
    btn_pro_plus: '🚀 Pro+ — R$19.90/mo',
    btn_avulso: '💊 50 interactions — R$9.90',
  }
};

const useStrings = (idioma) => STRINGS[idioma] || STRINGS['pt-BR'];

// ── NOTIFICAÇÃO PERSISTENTE ───────────────────────────────────────────────────
let _notifId = null;

async function testarNotificacao() {
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: '🔔 Teste Margo',
        body: 'Notificação funcionando! ✅',
        sound: true,
      },
      trigger: { type: "timeInterval", seconds: 5, repeats: false },
    });
    Alert.alert('OK', 'Notificação em 5 segundos!');
  } catch(e) { Alert.alert('Erro', String(e)); }
}

async function iniciarNotificacaoPersistente(nomeAssistente) {
  try {
    if (_notifId) return;
    const { status } = await Notifications.getPermissionsAsync();
    if (status !== 'granted') return;
    _notifId = await Notifications.scheduleNotificationAsync({
      content: {
        title: nomeAssistente || 'Margo',
        body: 'Ouvindo... Toque para abrir',
        sticky: true,
        autoDismiss: false,
        data: { type: 'foreground' },
      },
      trigger: null,
    });
  } catch(e) { console.log('Notif persistente erro:', e); }
}

async function pararNotificacaoPersistente() {
  try {
    if (_notifId) {
      await Notifications.dismissNotificationAsync(_notifId);
      _notifId = null;
    }
  } catch(e) {}
}

function limpar(txt) {
  return txt
    .replace(/(https?:\/\/|www\.)[^\s]+/g, '')
    .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
    .replace(/[\u2600-\u27BF]/g, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/#{1,6}\s*/g, '')
    .replace(/\s+/g, ' ').trim();
}

// ── TELA SELEÇÃO DE IDIOMA ───────────────────────────────────────────────────
function TelaIdioma({ onSelecionar }) {
  return (
    <View style={s.fullCenter}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <View style={s.logoCircle}>
        <Image source={ICON} style={{ width: 80, height: 80, borderRadius: 40 }} />
      </View>
      <Text style={s.welcomeName}>Margo</Text>
      <Text style={[s.welcomeDesc, { marginBottom: 48 }]}>Choose your language / Escolha seu idioma</Text>
      <View style={{ width: '100%', gap: 16 }}>
        <TouchableOpacity style={s.btnP} onPress={() => onSelecionar('pt-BR')}>
          <Text style={s.btnPTxt}>🇧🇷  Português</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.btnP} onPress={() => onSelecionar('en-US')}>
          <Text style={s.btnPTxt}>🇺🇸  English</Text>
        </TouchableOpacity>
      </View>
      <Text style={{ color: C.text3, fontSize: 11, marginTop: 48 }}>by Orbiby</Text>
    </View>
  );
}

// ── TELA BOAS-VINDAS ──────────────────────────────────────────────────────────
function TelaBoasVindas({ onEntrar, onCadastrar, idioma }) {
  const s_ = useStrings(idioma);
  return (
    <View style={s.fullCenter}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <View style={s.logoCircle}>
        <Image source={ICON} style={{ width: 80, height: 80, borderRadius: 40 }} />
      </View>
      <Text style={s.welcomeName}>Margo</Text>
      <Text style={s.welcomeDesc}>{s_['app_desc']}</Text>
      <View style={{ width: '100%', gap: 12, marginTop: 48 }}>
        <TouchableOpacity style={s.btnP} onPress={onCadastrar}>
          <Text style={s.btnPTxt}>{s_['criar_conta']}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.btnS} onPress={onEntrar}>
          <Text style={s.btnSTxt}>{s_['ja_tenho_conta']}</Text>
        </TouchableOpacity>
      </View>
      <Text style={{ color: C.text3, fontSize: 11, marginTop: 48 }}>{s_['by_orbiby']}</Text>
    </View>
  );
}

// ── TELA CADASTRO ─────────────────────────────────────────────────────────────
function TelaCadastro({ onSuccess, onVoltar, backendUrl, idioma }) {
  const s_ = useStrings(idioma);
  const [email, setEmail]       = useState('');
  const [senha, setSenha]       = useState('');
  const [confirma, setConfirma] = useState('');
  const [erro, setErro]         = useState('');
  const [loading, setLoading]   = useState(false);
  const [verSenha, setVerSenha]     = useState(false);
  const [verConf, setVerConf]       = useState(false);
  const [etapa, setEtapa]           = useState('cadastro');
  const [codigo, setCodigo]         = useState('');
  const [senhaHash, setSenhaHash]   = useState('');
  const [deviceIdSalvo, setDeviceIdSalvo] = useState('');

  async function cadastrar() {
    if (!email.includes('@'))   { setErro('Email inválido.'); return; }
    if (senha.length < 6)       { setErro('Senha deve ter pelo menos 6 caracteres.'); return; }
    if (senha !== confirma)     { setErro('As senhas não coincidem.'); return; }
    setLoading(true); setErro('');
    try {
      // Verifica device ID antes de criar conta free
      const deviceId = await getDeviceId();
      const rv = await fetch(`${backendUrl}/verificar_device`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId })
      });
      const dv = await rv.json();
      if (!dv.pode_criar) {
        setErro('Este dispositivo já possui uma conta gratuita.');
        setLoading(false); return;
      }
      const r = await fetch(`${backendUrl}/cadastro`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.toLowerCase().trim(), senha, device_id: deviceId })
      });
      const d = await r.json();
      if (d.ok && d.verificacao_pendente) {
        // Mostra tela de verificação
        setEtapa('verificar');
        setSenhaHash(d.senha_hash);
        setDeviceIdSalvo(deviceId);
      } else if (d.ok) {
        await AsyncStorage.setItem('margo_user_id', d.user_id);
        await AsyncStorage.setItem('margo_email', d.email);
        onSuccess(d);
      } else setErro(d.erro || 'Erro ao criar conta.');
    } catch(e) { setErro('Sem conexão com o servidor.'); }
    setLoading(false);
  }

  // Tela de verificação de email
  if (etapa === 'verificar') {
    const verificar = async () => {
      if (codigo.length !== 6) { setErro('Digite o código de 6 dígitos.'); return; }
      setLoading(true); setErro('');
      try {
        const r = await fetch(`${backendUrl}/verificar_email`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email.toLowerCase().trim(), codigo, senha_hash: senhaHash, device_id: deviceIdSalvo })
        });
        const d = await r.json();
        if (d.ok) {
          await AsyncStorage.setItem('margo_user_id', d.user_id);
          await AsyncStorage.setItem('margo_email', d.email);
          onSuccess(d);
        } else setErro(d.erro || 'Código incorreto.');
      } catch(e) { setErro('Sem conexão.'); }
      setLoading(false);
    };
    return (
      <KeyboardAvoidingView style={s.authWrap} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <StatusBar barStyle="light-content" backgroundColor={C.bg} />
        <Text style={s.authTitle}>✉️ Verifique seu email</Text>
        <Text style={s.authSub}>Enviamos um código de 6 dígitos para {email}. Digite abaixo para ativar sua conta.</Text>
        <TextInput style={[s.authInput, { fontSize: 28, letterSpacing: 8, textAlign: 'center' }]}
          placeholder="000000" placeholderTextColor={C.text3}
          value={codigo} onChangeText={setCodigo} keyboardType="number-pad" maxLength={6} />
        {!!erro && <Text style={s.authErro}>{erro}</Text>}
        <TouchableOpacity style={s.btnP} onPress={verificar} disabled={loading}>
          {loading ? <ActivityIndicator color="#000" /> : <Text style={s.btnPTxt}>Confirmar</Text>}
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setEtapa('cadastro')}>
          <Text style={[s.voltarTxt, { marginTop: 16 }]}>← Voltar</Text>
        </TouchableOpacity>
      </KeyboardAvoidingView>
    );
  }

  return (
    <KeyboardAvoidingView style={s.authWrap} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <TouchableOpacity onPress={onVoltar}><Text style={s.voltarTxt}>{s_['voltar']}</Text></TouchableOpacity>
      <Text style={s.authTitle}>{s_['titulo_cadastro']}</Text>
      <Text style={s.authSub}>{s_['sub_cadastro']}</Text>
      <TextInput style={s.authInput} placeholder={s_['placeholder_email']} placeholderTextColor={C.text3}
        value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
      <View style={s.senhaWrap}>
        <TextInput style={[s.authInput, { flex: 1, marginBottom: 0 }]} placeholder={s_['placeholder_senha']}
          placeholderTextColor={C.text3} value={senha} onChangeText={setSenha} secureTextEntry={!verSenha} />
        <TouchableOpacity style={s.olho} onPress={() => setVerSenha(v => !v)}>
          <Text style={{ fontSize: 18 }}>{verSenha ? '🙈' : '👁️'}</Text>
        </TouchableOpacity>
      </View>
      <View style={s.senhaWrap}>
        <TextInput style={[s.authInput, { flex: 1, marginBottom: 0 }]} placeholder={s_['placeholder_confirmar']}
          placeholderTextColor={C.text3} value={confirma} onChangeText={setConfirma} secureTextEntry={!verConf} />
        <TouchableOpacity style={s.olho} onPress={() => setVerConf(v => !v)}>
          <Text style={{ fontSize: 18 }}>{verConf ? '🙈' : '👁️'}</Text>
        </TouchableOpacity>
      </View>
      {!!erro && <Text style={s.authErro}>{erro}</Text>}
      <TouchableOpacity style={s.btnP} onPress={cadastrar} disabled={loading}>
        {loading ? <ActivityIndicator color="#000" /> : <Text style={s.btnPTxt}>{s_['criar_conta']}</Text>}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

// ── TELA LOGIN ────────────────────────────────────────────────────────────────
function TelaLogin({ onSuccess, onVoltar, backendUrl, idioma }) {
  const s_ = useStrings(idioma);
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
      <TouchableOpacity onPress={onVoltar}><Text style={s.voltarTxt}>{s_['voltar']}</Text></TouchableOpacity>
      <Text style={s.authTitle}>{s_['titulo_login']}</Text>
      <Text style={s.authSub}>{s_['sub_login']}</Text>
      <TextInput style={s.authInput} placeholder={s_['placeholder_email']} placeholderTextColor={C.text3}
        value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
      <View style={s.senhaWrap}>
        <TextInput style={[s.authInput, { flex: 1, marginBottom: 0 }]} placeholder={s_['placeholder_senha_login']}
          placeholderTextColor={C.text3} value={senha} onChangeText={setSenha} secureTextEntry={!verSenha} />
        <TouchableOpacity style={s.olho} onPress={() => setVerSenha(v => !v)}>
          <Text style={{ fontSize: 18 }}>{verSenha ? '🙈' : '👁️'}</Text>
        </TouchableOpacity>
      </View>
      {!!erro && <Text style={s.authErro}>{erro}</Text>}
      <TouchableOpacity style={s.btnP} onPress={entrar} disabled={loading}>
        {loading ? <ActivityIndicator color="#000" /> : <Text style={s.btnPTxt}>{s_['btn_entrar']}</Text>}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

// ── PAINEL CONFIGURAÇÕES ──────────────────────────────────────────────────────
function PainelCfg({ visivel, onFechar, config, onSalvar, onSair, onUpgrade, email, plano, userId, idioma }) {
  const s_ = useStrings(idioma);
  const [cfg, setCfg]             = useState(config);
  const [verApiKey, setVerApiKey] = useState(false);
  useEffect(() => setCfg(config), [config]);
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }));

  return (
    <Modal visible={visivel} animationType="slide" presentationStyle="pageSheet" onRequestClose={onFechar}>
      <View style={{ flex: 1, backgroundColor: C.bg2 }}>
        <View style={s.modalHead}>
          <Text style={s.modalTitle}>{s_['titulo_config']}</Text>
          <TouchableOpacity onPress={onFechar} style={s.iconBtn}>
            <Text style={{ color: C.text2, fontSize: 20 }}>✕</Text>
          </TouchableOpacity>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 24 }}
          keyboardShouldPersistTaps="handled">

          {/* SOBRE VOCÊ */}
          <View style={s.secao}>
            <Text style={s.secLabel}>{s_['sobre_voce']}</Text>
            {[
              ['perfilNome','Seu nome'],['perfilNascimento','Data de nascimento (DD/MM/AAAA)'],
              ['perfilProfissao','Sua profissão'],['perfilMusica','Música favorita'],
              ['perfilComida','Comida favorita'],['perfilHobbies','Hobbies e interesses'],
              ['perfilExtra','Algo mais sobre você (opcional)'],
            ].map(([k, ph]) => (
              <View key={k}>
                <Text style={{ color: C.text3, fontSize: 12, marginBottom: 3, marginLeft: 4 }}>{ph}</Text>
                <TextInput style={s.cfgInput} placeholder={ph} placeholderTextColor={C.text3}
                  value={cfg[k] || ''} onChangeText={v => set(k, v)}
                  keyboardType={k === 'perfilNascimento' ? 'numeric' : 'default'}
                  autoComplete="off" autoCorrect={false} />
              </View>
            ))}
          </View>

          {/* SUA ASSISTENTE */}
          <View style={s.secao}>
            <Text style={s.secLabel}>{s_['sua_assistente']}</Text>
            <Text style={{ color: C.text3, fontSize: 12, marginBottom: 3, marginLeft: 4 }}>{s_['placeholder_nome_assistente']}</Text>
            <TextInput style={s.cfgInput} placeholder={s_['placeholder_nome_assistente']}
              placeholderTextColor={C.text3} value={cfg.assistantName}
              onChangeText={v => set('assistantName', v)}
              autoComplete="off" autoCorrect={false} autoCapitalize="words" />
            <Text style={{ color: C.text3, fontSize: 12, marginBottom: 3, marginLeft: 4 }}>Personalidade</Text>
            <TextInput style={[s.cfgInput, { height: 110, textAlignVertical: 'top' }]}
              placeholder="Personalidade — ex: divertida, fala gírias, adora música, sempre bem-humorada, usa emojis, fala como amiga próxima..."
              placeholderTextColor={C.text3} value={cfg.personalidade || ''}
              onChangeText={v => set('personalidade', v.slice(0, 300))} multiline
              maxLength={300} />
            <Text style={{ color: C.text3, fontSize: 10, textAlign: 'right', marginTop: -4 }}>
              {(cfg.personalidade || '').length}/300
            </Text>

            {/* WAKE WORD — oculto no lançamento (retorna em versão futura) */}
            {false && (
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.border }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>
                  {idioma === 'en-US' ? '🔔 Wake Word "Ok Migoo"' : '🔔 Wake Word "Ok Migoo"'}
                </Text>
                <Text style={{ color: C.text3, fontSize: 12, marginTop: 2 }}>
                  {idioma === 'en-US' ? 'Open app hands-free by voice (uses battery)' : 'Abre o app por voz sem tocar na tela (consome bateria)'}
                </Text>
              </View>
              <TouchableOpacity
                style={{ width: 50, height: 28, borderRadius: 14, backgroundColor: cfg.wakeWordOn ? C.cyan : C.border, justifyContent: 'center', paddingHorizontal: 3 }}
                onPress={() => set('wakeWordOn', !cfg.wakeWordOn)}>
                <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: C.text, alignSelf: cfg.wakeWordOn ? 'flex-end' : 'flex-start' }} />
              </TouchableOpacity>
            </View>
            )}

          </View>

          {/* IDIOMA */}
          <View style={s.secao}>
            <Text style={s.secLabel}>{idioma === 'en-US' ? 'LANGUAGE' : 'IDIOMA'}</Text>
            <Text style={s.secSub}>{idioma === 'en-US' ? 'Choose the app language.' : 'Escolha o idioma do app.'}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {[['pt-BR','🇧🇷 Português'],['en-US','🇺🇸 English']].map(([lang, label]) => (
                <TouchableOpacity key={lang} style={[s.chip, cfg.idioma === lang && s.chipOn]}
                  onPress={async () => {
                    set('idioma', lang);
                    const AsyncStorage = require('@react-native-async-storage/async-storage').default;
                    await AsyncStorage.setItem('margo_idioma', lang);
                  }}>
                  <Text style={[s.chipTxt, cfg.idioma === lang && s.chipTxtOn]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* NAVEGAÇÃO */}
          <View style={s.secao}>
            <Text style={s.secLabel}>NAVEGAÇÃO</Text>
            <Text style={s.secSub}>App de navegação preferido</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
              {[['waze','🚗 Waze'],['gmaps','🗺️ Google Maps']].map(([n, label]) => (
                <TouchableOpacity key={n} style={[s.chip, (cfg.navApp || 'waze') === n && s.chipOn]}
                  onPress={() => set('navApp', n)}>
                  <Text style={[s.chipTxt, (cfg.navApp || 'waze') === n && s.chipTxtOn]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* VOZ PREMIUM */}
          <View style={s.secao}>
            <Text style={s.secLabel}>{s_['voz']}</Text>
            <Text style={s.secSub}>{s_['genero_voz']}</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
              {[['F','🙍‍♀️ Feminino'],['M','🙍‍♂️ Masculino']].map(([g, label]) => (
                <TouchableOpacity key={g} style={[s.chip, cfg.voiceGender === g && s.chipOn]}
                  onPress={() => set('voiceGender', g)}>
                  <Text style={[s.chipTxt, cfg.voiceGender === g && s.chipTxtOn]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={[s.secSub, { marginBottom: 8 }]}>{s_['provedor_voz']}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {[['device','🤖 Migoo Voice'],['fishaudio','Fish Audio'],['elevenlabs','ElevenLabs']].map(([p, label]) => (
                <TouchableOpacity key={p} style={[s.chip, cfg.voiceProvider === p && s.chipOn]}
                  onPress={() => set('voiceProvider', p)}>
                  <Text style={[s.chipTxt, cfg.voiceProvider === p && s.chipTxtOn]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {cfg.voiceProvider === 'device' && (
              <Text style={[s.secSub, { marginTop: 6 }]}>{s_['kokoro_desc']}</Text>
            )}

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
                <Text style={{ color: C.cyan, fontSize: 11 }}>{s_['fish_link']}</Text>
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
                <Text style={{ color: C.cyan, fontSize: 11 }}>{s_['eleven_link']}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* SPOTIFY */}
          <View style={s.secao}>
            <Text style={s.secLabel}>{s_['spotify_label']}</Text>
            <Text style={s.secSub}>{s_['spotify_desc']}</Text>
            <TouchableOpacity
              style={[s.btnS, { borderColor: '#1DB954' }]}
              onPress={async () => {
                try {
                  const r = await fetch(`${cfg.backendUrl}/spotify/status/${userId}`);
                  const d = await r.json();
                  if (d.conectado) {
                    Alert.alert('Spotify conectado! ✓', 'Sua conta já está vinculada.', [
                      { text: 'OK' },
                      { text: 'Reconectar', onPress: async () => {
                        const r2 = await fetch(`${cfg.backendUrl}/spotify/auth/${userId}`);
                        const d2 = await r2.json();
                        if (d2.url) Linking.openURL(d2.url);
                      }}
                    ]);
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
                Plano: {plano === 'free' ? s_['plano_free'] : plano === 'pro' ? s_['plano_pro'] : plano === 'pro_plus' || plano === 'pro+' ? s_['plano_pro_plus'] : s_['plano_admin']}
              </Text>
            </View>
            {(plano === 'free' || plano === 'pro') && (
              <View style={{ gap: 8 }}>
                {plano === 'free' && (
                  <TouchableOpacity style={[s.btnP, { backgroundColor: '#7C3AED' }]}
                    onPress={() => onUpgrade('pro')}>
                    <Text style={s.btnPTxt}>🔥 Pro — 20 msgs/dia{'  '}
                      <Text style={{ textDecorationLine: 'line-through', opacity: 0.7 }}>R$14,90</Text>
                      {' '}R$9,90/mês
                    </Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#059669' }]}
                  onPress={() => onUpgrade('pro_plus')}>
                  <Text style={s.btnPTxt}>🔥 Pro+ — 50 msgs/dia{'  '}
                    <Text style={{ textDecorationLine: 'line-through', opacity: 0.7 }}>R$29,90</Text>
                    {' '}R$19,90/mês
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.btnP, { backgroundColor: '#2E9AAF' }]}
                  onPress={() => onUpgrade('avulso')}>
                  <Text style={s.btnPTxt}>💊 50 interações extras — R$9,90</Text>
                </TouchableOpacity>
              </View>
            )}
            <TouchableOpacity style={s.btnS} onPress={onSair}>
              <Text style={s.btnSTxt}>{s_['sair']}</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={s.btnP} onPress={() => onSalvar(cfg)}>
            <Text style={s.btnPTxt}>{s_['salvar']}</Text>
          </TouchableOpacity>
          <View style={{ height: 60 }} />
        </ScrollView>
      </View>
    </Modal>
  );
}

// ── BOLHA DE MENSAGEM ─────────────────────────────────────────────────────────
// Renderiza texto com URLs clicáveis
function TextoComLinks({ texto, estilo }) {
  const regex = /((?:https?:\/\/|www\.)[^\s]+)/g;
  const partes = String(texto).split(regex);
  return (
    <Text selectable={true} style={estilo}>
      {partes.map((parte, i) =>
        /^(https?:\/\/|www\.)/.test(parte) ? (
          <Text key={i} style={{ color: C.cyan, textDecorationLine: 'underline' }}
            onPress={() => {
              let url = parte.replace(/[.,;)]+$/, '');
              if (url.startsWith('www.')) url = 'https://' + url;
              Linking.openURL(url).catch(() => {});
            }}>
            {parte}
          </Text>
        ) : (
          <Text key={i}>{parte}</Text>
        )
      )}
    </Text>
  );
}

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
        <TextoComLinks texto={msg.texto}
          estilo={[{ fontSize: 14, lineHeight: 22, color: C.text }, isUser && { color: '#000', fontWeight: '500' }]} />
        <Text style={{ fontSize: 10, color: isUser ? 'rgba(0,0,0,0.5)' : C.text3, marginTop: 4 }}>{msg.hora}</Text>
      </View>
    </View>
  );
}

// ── APP PRINCIPAL ─────────────────────────────────────────────────────────────
// Gera Device ID único e persistente
async function getDeviceId() {
  try {
    let deviceId = await AsyncStorage.getItem('margo_device_id');
    if (!deviceId) {
      deviceId = 'dev_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      await AsyncStorage.setItem('margo_device_id', deviceId);
    }
    return deviceId;
  } catch(e) { return 'unknown'; }
}

export default function App() {
  const [tela, setTela]           = useState('idioma');
  const [userId, setUserId]       = useState(null);
  const s_i = useStrings(config?.idioma || 'pt-BR');
  const [email, setEmail]         = useState('');
  const [plano, setPlano]         = useState('free');
  const [msgs, setMsgs]           = useState([]);
  const [msgExtras, setMsgExtras]  = useState(0);
  const [input, setInput]         = useState('');
  const [imagemBase64, setImagemBase64] = useState(null);
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
  const ttsAtivoRef                = useRef(false);
  const wakeWordRef               = useRef(true); // ref para usar dentro de callbacks
  const wakeWordOnRef              = useRef(false); // ref do toggle wake word
  const micEstadoSalvoRef          = useRef(false); // mic estava ligado antes do background
  const multilingueRef             = useRef(false); // modo multilingue (Groq STT) — segue o plano
  const gravacaoRef                = useRef(null);  // gravacao multilingue em andamento
  const ultimoIdiomaRef            = useRef('');    // idioma da ultima fala (Groq)

  // Multilíngue (Groq STT) é automático para admin — depois: premium e tester
  useEffect(() => {
    multilingueRef.current = ['admin'].includes(plano);
    console.log('[Multilingue]', multilingueRef.current ? 'ATIVO (Groq)' : 'inativo (STT nativo)', '— plano:', plano);
  }, [plano]);
  const navAppRef                  = useRef('waze'); // ref do app de navegação

  // ── INIT ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    iniciar();
    pedirLocalizacao();
    Audio.setAudioModeAsync({ playsInSilentModeIOS: true, allowsRecordingIOS: false });
  }, []);

  // WakeWord — listener unificado
  useEffect(() => {
    const { pausarWakeWord, retomarWakeWord } = require('./src/services/WakeWordService');
    let timeoutId = null;

    async function verificarWakeWordPendente() {
      try {
        const pendente = await NativeModules.WakeWordModule.checkWakeWordPendente();
        if (pendente) {
          console.log('[WakeWord] Abrindo com saudacao — iniciando microfone...');
          setTimeout(async () => {
            await iniciarMicrofone();
          }, 2500);
        }
      } catch(e) {}
    }

    verificarWakeWordPendente();

    const sub = AppState.addEventListener('change', async (nextState) => {
      console.log('[AppState]', nextState);

      if (nextState === 'active') {
        console.log('[WakeWord] App em foreground — pausando wake word');
        try { await NativeModules.WakeWordModule.pausar(); } catch(e) {}
        await verificarWakeWordPendente();
        // Restaura o mic se estava ligado antes de sair (ex: voltou do Spotify)
        if (micEstadoSalvoRef.current && !micAtivoRef.current) {
          micEstadoSalvoRef.current = false;
          setTimeout(() => { iniciarMicrofone(); }, 800);
        }

      } else if (nextState === 'background') {
        console.log('[WakeWord] App em background — parando STT');
        micEstadoSalvoRef.current = micAtivoRef.current; // guarda pra restaurar na volta
        try { ExpoSpeechRecognitionModule?.stop(); } catch(e) {}
        micAtivoRef.current = false;
        setMicAtivo(false);
        if (wakeWordOnRef.current) {
          try { await NativeModules.WakeWordModule.iniciar('migoo'); } catch(e) {}
        }
      }
    });

    return () => {
      sub.remove();
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, []);

  // Reagenda lembretes ao abrir o app e verifica pendentes a cada 5 min
  useEffect(() => {
    if (!userId) return;

    async function reagendarLembretes() {
      try {
        // Cancela todas notificações antigas
        await Notifications.cancelAllScheduledNotificationsAsync();
        
        // Busca lembretes futuros do servidor
        const r = await fetch(`${config.backendUrl}/agenda/${userId}`);
        const d = await r.json();
        const lembretes = d.lembretes || [];
        const agora = new Date();

        for (const l of lembretes) {
          if (!l.data_hora) continue;
          // Backend salva em UTC — interpreta como UTC para calcular diff corretamente
          const dataHoraUTC = l.data_hora.endsWith('Z') ? l.data_hora : l.data_hora + 'Z';
          const dataHora = new Date(dataHoraUTC);
          const diffSegundos = Math.floor((dataHora - agora) / 1000);
          if (diffSegundos <= 0) continue;

          // Na hora
          await Notifications.scheduleNotificationAsync({
            content: { title: `⏰ ${l.titulo}`, body: l.descricao || l.titulo, sound: true },
            trigger: { type: "timeInterval", seconds: diffSegundos, repeats: false },
          });
          // 1h antes
          if (diffSegundos > 3600) {
            await Notifications.scheduleNotificationAsync({
              content: { title: `⏰ Em 1 hora: ${l.titulo}`, body: l.descricao || l.titulo, sound: true },
              trigger: { type: "timeInterval", seconds: diffSegundos - 3600, repeats: false },
            });
          }
          // 12h antes
          if (diffSegundos > 43200) {
            await Notifications.scheduleNotificationAsync({
              content: { title: `📅 Amanhã: ${l.titulo}`, body: l.descricao || l.titulo, sound: true },
              trigger: { type: "timeInterval", seconds: diffSegundos - 43200, repeats: false },
            });
          }
        }
        console.log(`${lembretes.length} lembretes reagendados`);
      } catch(e) { console.log('Reagendar erro:', e); }
    }

    reagendarLembretes();
    verificarLembretesPendentes(userId, config.backendUrl);
    const interval = setInterval(() => {
      verificarLembretesPendentes(userId, config.backendUrl);
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [userId]);

  // Heartbeat — só para garantir que não travou, a cada 60s
  useEffect(() => {
    micAtivoRef.current = micAtivo;
    wakeWordRef.current = config.wakeWordOn;
    navAppRef.current = config.navApp || 'waze';
    wakeWordOnRef.current = config.wakeWordOn;
    if (!micAtivo) return;
    const interval = setInterval(() => {
      if (micAtivoRef.current && !ttsAtivoRef.current && ExpoSpeechRecognitionModule) {
        try {
          ExpoSpeechRecognitionModule.start({ lang: config.idioma || 'pt-BR', interimResults: false, addsPunctuation: true, contextualStrings: [config.assistantName], continuous: true });
        } catch(e) {}
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [micAtivo, config.wakeWordOn]);

  async function iniciar() {
    // Registra token FCM para push notifications
    if (Device.isDevice) {
      try {
        const { status: existingStatus } = await Notifications.getPermissionsAsync();
        let finalStatus = existingStatus;
        if (existingStatus !== 'granted') {
          const { status } = await Notifications.requestPermissionsAsync();
          finalStatus = status;
        }
        if (finalStatus === 'granted') {
          const tokenData = await Notifications.getDevicePushTokenAsync();
          const fcmToken = tokenData.data;
          await AsyncStorage.setItem('margo_fcm_token', fcmToken);
          console.log('FCM token:', fcmToken);
        }
      } catch(e) { console.log('FCM token erro:', e); }
    }

    const idiomaSalvo = await AsyncStorage.getItem('margo_idioma');
    const locales = Localization.getLocales();
    const idiomaSistema = locales[0]?.languageTag || 'pt-BR';
    let idiomaDetectado;
    if (idiomaSistema.startsWith('pt')) idiomaDetectado = 'pt-BR';
    else if (idiomaSistema.startsWith('ja')) idiomaDetectado = 'ja-JP';
    else idiomaDetectado = 'en-US';
    // Usa idioma salvo só se for diferente do sistema (usuário escolheu manualmente)
    // Na primeira vez sempre usa o sistema
    const idiomaFinal = idiomaSalvo || idiomaDetectado;
    setConfig(c => ({ ...c, idioma: idiomaFinal }));
    await AsyncStorage.setItem('margo_idioma', idiomaFinal);
    setTela('boas_vindas');
    const uid  = await AsyncStorage.getItem('margo_user_id');
    const em   = await AsyncStorage.getItem('margo_email');
    const av   = await AsyncStorage.getItem('margo_avatar');
    let cfg    = await AsyncStorage.getItem('margo_config');
    if (!cfg) cfg = await AsyncStorage.getItem('margo_settings');
    if (av) setAvatarUri(av);
    if (cfg) { try { setConfig(c => ({ ...c, ...JSON.parse(cfg) })); } catch(e) {} }
    if (uid) {
      const idiomaLocal = await AsyncStorage.getItem('margo_idioma');
      if (idiomaLocal) setConfig(c => ({ ...c, idioma: idiomaLocal }));
      setUserId(uid); setEmail(em || ''); setTela('chat');
      const hist = await AsyncStorage.getItem('margo_chat');
      if (hist) { try { setMsgs(JSON.parse(hist)); } catch(e) {} }
      contarMsgs(uid);
      // Boas-vindas na primeira abertura
      const jaViu = await AsyncStorage.getItem('margo_boas_vindas');
      if (!jaViu) {
        try {
          const backendUrl = config.backendUrl || 'https://margo-production-98a9.up.railway.app';
          const rb = await fetch(`${backendUrl}/boas_vindas`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: uid })
          });
          const db = await rb.json();
          if (db.mensagem) {
            const msgBv = { id: Date.now(), role: 'assistant', text: db.mensagem };
            setMsgs([msgBv]);
            await AsyncStorage.setItem('margo_boas_vindas', '1');
          }
        } catch(e) {}
      }
    }
    // WakeWord Service temporariamente desativado
    // Inicia WakeWord Service com modelo baseado no nome do assistente
    if (config.wakeWordOn) {
      try {
        await NativeModules.WakeWordModule.iniciar('migoo');
        console.log('[WakeWord] Servico iniciado com modelo: migoo');
      } catch(e) {
        console.log('[WakeWord] Erro ao iniciar servico:', e);
      }
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
      setPlano(d.plano || 'free');
      setMsgExtras(d.msgs_extras || 0);
      const extras = d.msgs_extras || 0;
      const diarias = d.faltam || Math.max(0, (d.limite || 0) - (d.usado || 0));
      setFaltam(diarias + extras);
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
      // Remove emojis e caracteres especiais para comparação
      const limparTexto = (t) => t.toLowerCase().replace(/[^a-záàâãéèêíïóôõöúüçñ\s]/gi, '').trim();
      const nomeLower = limparTexto(nome);
      const encontrados = data.filter(c =>
        c.name && limparTexto(c.name).includes(nomeLower) &&
        c.phoneNumbers && c.phoneNumbers.length > 0
      );

      if (encontrados.length === 0) return null;
      if (encontrados.length === 1) return encontrados[0].phoneNumbers[0].number;
      // Mais de um contato — mostra opções
      return new Promise(resolve => {
        Alert.alert(
          'Qual contato?',
          'Encontrei mais de um contato com esse nome:',
          [
            ...encontrados.slice(0, 4).map(c => ({
              text: `${c.name} (${c.phoneNumbers[0].number})`,
              onPress: () => resolve(c.phoneNumbers[0].number)
            })),
            { text: 'Cancelar', style: 'cancel', onPress: () => resolve(null) }
          ]
        );
      });
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
  async function enviar(msg, idiomaFalado = '') {
    msg = (msg || input).trim();
    if (!msg || pensando || !userId || ttsAtivoRef.current) return;
    setInput('');
    addMsg('user', msg);
    setPensando(true);
    try {
      const body = { user_id: userId, mensagem: msg };
      if (location) { body.latitude = location.lat; body.longitude = location.lng; }
      if (idiomaFalado) { body.idioma_falado = idiomaFalado; }
      // Passa hora local do dispositivo
      const _now = new Date();
      const _off = -_now.getTimezoneOffset();
      const _sign = _off >= 0 ? '+' : '-';
      const _hh = String(Math.floor(Math.abs(_off)/60)).padStart(2,'0');
      const _mm = String(Math.abs(_off)%60).padStart(2,'0');
      const _local = new Date(_now.getTime() + _off * 60000);
      body.hora_local = _local.toISOString().replace('Z', '') + _sign + _hh + ':' + _mm;
      const r = await fetch(`${config.backendUrl}/mensagem`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      const d = await r.json();
      const texto = d.resposta || 'Sem resposta.';
      addMsg('margo', texto);
      falar(limpar(texto));

      // Encerra sessao — espera Margo terminar de falar antes de fechar
      if (d.encerrar_sessao) {
        console.log('[Sessao] Encerrando — aguardando resposta da Margo...');
        setTimeout(async () => {
          setMicAtivo(false);
          micAtivoRef.current = false;
          try { ExpoSpeechRecognitionModule?.stop(); } catch(e) {}
          try { await NativeModules.WakeWordModule.iniciar('migoo'); } catch(e) {}
          setTimeout(() => { BackHandler.exitApp(); }, 4000);
        }, 500);
      }

      // Paywall — limite atingido
      if (d.limite_atingido) {
        const isTrial = d.plano === 'free';
        setTimeout(() => {
          Alert.alert(
            isTrial ? s_i['paywall_trial_titulo'] : s_i['paywall_limite_titulo'],
            isTrial ? s_i['paywall_trial_msg'] : s_i['paywall_limite_msg'],
            [
              {
                text: '🔥 Pro — 20 msgs/dia  R$14,90 ➜ R$9,90',
                onPress: () => handleUpgrade('pro')
              },
              {
                text: '🚀 Pro+ — 50 msgs/dia  R$29,90 ➜ R$19,90',
                onPress: () => handleUpgrade('pro_plus')
              },
              {
                text: s_i['btn_avulso'],
                onPress: () => handleUpgrade('avulso')
              },
              { text: 'Agora não', style: 'cancel' }
            ]
          );
        }, 2000);
        setPensando(false);
        return;
      }

      // Delay para Margo terminar de falar antes de abrir apps
      if (d.ferramenta) {
        const t = d.ferramenta.ferramenta;
        // maps_search não abre nada — Margo já deu as dicas, aguarda confirmação do usuário
        if (t !== 'maps_search') {
          const precisaDelay = ['maps_navigate','spotify_play','youtube_search','soundcloud_play','flight_search','hotel_search','skyscanner_search','booking_search','web_search'].includes(t);
          if (precisaDelay) {
            setTimeout(() => executarFerramenta(d.ferramenta), 5000);
          } else {
            await executarFerramenta(d.ferramenta);
          }
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
    let t = f.ferramenta;

    // Redireciona web_search para ferramenta correta quando possível
    if (t === 'web_search') {
      const q = (f.query || '').toLowerCase();
      if (q.includes('hotel') || q.includes('hospedagem') || q.includes('pousada')) {
        t = 'hotel_search';
        f = { ...f, ferramenta: 'hotel_search', destino: f.query };
      } else if (q.includes('passagem') || q.includes('voo') || q.includes('aéreo') || q.includes('aereo') || q.includes('flight')) {
        t = 'flight_search';
        f = { ...f, ferramenta: 'flight_search', origem: '', destino: f.query };
      }
    }

    // Espera Margo terminar de falar antes de abrir apps
    if (ttsAtivoRef.current) {
      await new Promise(resolve => {
        const check = setInterval(() => {
          if (!ttsAtivoRef.current) { clearInterval(check); resolve(); }
        }, 200);
        setTimeout(() => { clearInterval(check); resolve(); }, 10000);
      });
    }

    if (t === 'maps_navigate') {
      const dest = encodeURIComponent(f.destino);
      const origin = location ? `&origin=${location.lat},${location.lng}` : '';
      const wazeUrl = `waze://?q=${dest}&navigate=yes`;
      const googleAppUrl = `google.navigation:q=${dest}`;
      const googleWebUrl = `https://www.google.com/maps/dir/?api=1&destination=${dest}${origin}`;
      // Respeita o app de navegação escolhido nas configurações
      if (navAppRef.current === 'gmaps') {
        // IntentLauncher com packageName força SÓ o Google Maps (sem popup)
        try {
          const IntentLauncher = require('expo-intent-launcher');
          await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
            data: googleAppUrl,
            packageName: 'com.google.android.apps.maps'
          });
        } catch(e) {
          // Google não abriu — tenta Waze, senão web
          const wazeSupported = await Linking.canOpenURL(wazeUrl).catch(() => false);
          Linking.openURL(wazeSupported ? wazeUrl : googleWebUrl).catch(() => {});
        }
      } else {
        // Padrão: Waze, com Google como fallback
        const wazeSupported = await Linking.canOpenURL(wazeUrl).catch(() => false);
        if (wazeSupported) {
          Linking.openURL(wazeUrl).catch(() => {});
        } else {
          const googleSupported = await Linking.canOpenURL(googleAppUrl).catch(() => false);
          Linking.openURL(googleSupported ? googleAppUrl : googleWebUrl).catch(() => {});
        }
      }

    } else if (t === 'maps_search') {
      // Não abre app — Margo já deu as dicas e vai perguntar se quer a rota
      // A navegação só acontece quando o usuário confirmar (maps_navigate)

    } else if (t === 'spotify_play') {
      // Dispara o play no backend JÁ (ele tem retry esperando o device aparecer)
      // e abre o Spotify em paralelo — assim o fetch não congela em background
      const promessaPlay = spotifyPlayDireto(f.query);
      try {
        const acordou = await Linking.canOpenURL('spotify:').catch(() => false);
        if (acordou) await Linking.openURL('spotify:');
      } catch(e) {}
      const tocou = await promessaPlay;
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

    } else if (t === 'flight_search' || t === 'skyscanner_search') {
      const origemIata = (f.origem_iata || '').toLowerCase();
      const destinoIata = (f.destino_iata || '').toLowerCase();
      const formatarData = (d) => {
        if (!d) return '';
        const anoAtual = new Date().getFullYear();
        let [ano, mes, dia] = d.split('-');
        if (parseInt(ano) < anoAtual) ano = String(anoAtual);
        return `${String(ano).slice(2)}${mes}${dia}`;
      };
      const dataIda = formatarData(f.data_ida);
      const dataVolta = formatarData(f.data_volta);
      let url = `https://www.skyscanner.com.br/transporte/passagens-aereas/${origemIata}/${destinoIata}/`;
      if (dataIda) url += `${dataIda}/`;
      if (dataVolta) url += `${dataVolta}/`;
      url += `?adultsv2=1&cabinclass=economy`;
      Linking.openURL(url).catch(() => {});

    } else if (t === 'hotel_search' || t === 'booking_search') {
      const destino = encodeURIComponent(f.destino || f.query || '');
      let url = `https://www.booking.com/searchresults.html?ss=${destino}&group_adults=2&no_rooms=1`;
      if (f.checkin) url += `&checkin=${f.checkin}`;
      if (f.checkout) url += `&checkout=${f.checkout}`;
      Linking.openURL(url).catch(() => {});

    } else if (t === 'phone_call') {
      // Busca contato e abre WhatsApp
      try {
        const { status } = await Contacts.requestPermissionsAsync();
        if (status !== 'granted') return;
        const { data } = await Contacts.getContactsAsync({
          fields: [Contacts.Fields.PhoneNumbers, Contacts.Fields.Name],
        });
        const limparTxt = (txt) => txt.toLowerCase().replace(/[^a-záàâãéèêíïóôõöúüçñ\s]/gi, '').trim();
        const nomeLower = limparTxt(f.contato);
        const encontrados = data.filter(c => c.name && limparTxt(c.name).includes(nomeLower) && c.phoneNumbers?.length > 0);

        if (encontrados.length === 0) {
          addMsg('sistema', `Contato "${f.contato}" não encontrado.`);
          return;
        }

        const abrirWhatsApp = async (contato) => {
          let tel = contato.phoneNumbers[0].number.replace(/\D/g, '');
          if (tel.startsWith('0')) tel = tel.replace(/^0+/, '');
          // Tenta scheme nativo primeiro, wa.me como fallback
          const appUrl = `whatsapp://send?phone=${tel}`;
          const webUrl = `https://wa.me/${tel}`;
          try {
            const suportado = await Linking.canOpenURL(appUrl).catch(() => false);
            await Linking.openURL(suportado ? appUrl : webUrl);
          } catch(e) {
            addMsg('sistema', 'Não foi possível abrir o WhatsApp');
          }
        };

        if (encontrados.length === 1) {
          abrirWhatsApp(encontrados[0]);
        } else {
          Alert.alert('Qual contato?', 'Encontrei mais de um:', [
            ...encontrados.slice(0, 4).map(c => ({
              text: c.name,
              onPress: () => abrirWhatsApp(c)
            })),
            { text: 'Cancelar', style: 'cancel' }
          ]);
        }
      } catch(e) { addMsg('sistema', 'Erro ao buscar contato.'); }

    } else if (t === 'agenda_add') {
      // Agenda notificação local
      try {
        const agora = new Date();
        // Backend salva em UTC — interpreta como UTC (adiciona Z se não tiver timezone)
        const dataHoraStr = (f.data_hora && !f.data_hora.includes('+') && !f.data_hora.includes('Z'))
          ? f.data_hora + 'Z'
          : f.data_hora;
        let dataHora = new Date(dataHoraStr);
        
        // Se ainda está no passado, agenda para amanhã mesmo horário
        if (dataHora < agora) {
          dataHora.setDate(dataHora.getDate() + 1);
        }
        
        const diffSegundos = Math.floor((dataHora - agora) / 1000);
        
        // Agenda notificação na hora
        if (diffSegundos > 0) {
          await Notifications.scheduleNotificationAsync({
            content: {
              title: `⏰ ${f.titulo}`,
              body: f.descricao || f.titulo,
              sound: true,
            },
            trigger: { type: "timeInterval", seconds: diffSegundos, repeats: false },
          });
        }

        // Agenda 1h antes
        const diff1h = diffSegundos - 3600;
        if (diff1h > 0) {
          await Notifications.scheduleNotificationAsync({
            content: {
              title: `⏰ Em 1 hora: ${f.titulo}`,
              body: f.descricao || f.titulo,
              sound: true,
            },
            trigger: { type: "timeInterval", seconds: diff1h, repeats: false },
          });
        }

        // Agenda 12h antes
        const diff12h = diffSegundos - 43200;
        if (diff12h > 0) {
          await Notifications.scheduleNotificationAsync({
            content: {
              title: `📅 Amanhã: ${f.titulo}`,
              body: f.descricao || f.titulo,
              sound: true,
            },
            trigger: { type: "timeInterval", seconds: diff12h, repeats: false },
          });
        }

        console.log(`Lembrete agendado: ${diffSegundos}s (+ avisos 1h e 12h antes)`);
      } catch(e) { console.log('Agenda notif erro:', e); }

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
    ttsAtivoRef.current = false;
    try { NativeModules.WakeWordModule.releaseTTS(); } catch(e) {}
    if (micAtivoRef.current && ExpoSpeechRecognitionModule) {
      // Religamento = MESMO caminho da abertura (ideia do Marcos, versao final):
      // marca como desligado e refaz o setup completo via iniciarMicrofone()
      try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
      micAtivoRef.current = false;
      setTimeout(() => {
        iniciarMicrofone();
      }, 700);
    }
  }

  async function falar(texto) {
    if (!vozAtiva) return;
    ttsAtivoRef.current = true;
    if (gravacaoRef.current) {
      try { await gravacaoRef.current.recording.stopAndUnloadAsync(); } catch(e) {}
      gravacaoRef.current = null;
    }
    try { await NativeModules.WakeWordModule.requestTTS(); } catch(e) {}
    if (micAtivoRef.current && ExpoSpeechRecognitionModule) {
      try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
    }
    Speech.stop();

    console.log('[Falar] provider:', config.voiceProvider, '| temChaveFish:', !!(config.apiKeyFish || config.apiKey), '| temVozFish:', !!(config.voiceIdFish || config.voiceId));
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

    console.log('TTS debug:', config.voiceProvider, '| chave:', chave ? 'ok' : 'vazia', '| vozId:', vozId ? 'ok' : 'vazio');
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
        console.log('ElevenLabs status:', r.status);
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
          console.log('ElevenLabs erro body:', await r.text());
        }
      } catch(e) { console.log('ElevenLabs direto erro:', e.message || e); }
    }

    // Tenta Kokoro no servidor (PT-BR e EN)
    const temJapones = /[\u3040-\u30FF\u4E00-\u9FFF]/.test(texto);
    const temPortugues = /[ãõáéíóúâêîôûàèìòùç]/i.test(texto) ||
      /\b(você|não|sim|olá|obrigado|para|com|uma|isso|aqui|está|minha|seu|sua)\b/i.test(texto);
    if (!temJapones) {
      try {
        // Prioridade: idioma detectado pelo Groq > acentos > config
        const idi = ultimoIdiomaRef.current;
        const idiomaKokoro = (idi === 'english' || idi === 'en') ? 'en'
          : (idi === 'portuguese' || idi === 'pt') ? 'pt-br'
          : temPortugues ? 'pt-br' : (config.idioma || 'pt-br').toLowerCase();
        const r = await fetch(`${config.backendUrl}/kokoro_tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            texto: limpar(texto),
            idioma: idiomaKokoro,
            genero: config.voiceGender || 'F'
          })
        });
        const d = await r.json();
        if (d.audio_base64) {
          const ok = await tocarAudioBase64(d.audio_base64, religarMic);
          if (ok) return;
        }
      } catch(e) { console.log('Kokoro erro:', e); }
    }
    // Fallback: voz do dispositivo
    const idiomaBase = config.idioma || 'en-US';
    const langTTS = temJapones ? 'ja-JP' : temPortugues ? 'pt-BR' : idiomaBase;
    Speech.speak(texto, {
      language: langTTS,
      pitch: config.voiceGender === 'F' ? 1.2 : 0.8,
      rate: 1.0,
      onDone: religarMic,
    });
  }

  // ── MICROFONE ─────────────────────────────────────────────────────────────
  useSpeechRecognitionEvent('result', (e) => {
    if (multilingueRef.current) return; // ouvido e o Groq — nativo mudo
    const transcript = e.results?.[0]?.transcript;
    if (!transcript || !e.isFinal) return;
    enviar(transcript);
  });

  useSpeechRecognitionEvent('error', (e) => {
    console.log('Mic erro:', e.error);
    if (e.error === 'not-allowed') {
      setMicAtivo(false);
      micAtivoRef.current = false;
    }
  });

  useSpeechRecognitionEvent('end', () => {
    // Reinício RÁPIDO no ocioso (300ms) — fecha o vão que cortava o início das frases.
    // O delay longo (4,5s) fica só no religarMic pós-TTS, onde é necessário.
    if (micAtivoRef.current && !ttsAtivoRef.current && !multilingueRef.current) {
      setTimeout(() => {
        if (micAtivoRef.current && !ttsAtivoRef.current && !multilingueRef.current && ExpoSpeechRecognitionModule) {
          try {
            ExpoSpeechRecognitionModule.start({ lang: config.idioma || 'pt-BR', interimResults: false, addsPunctuation: true, contextualStrings: [config.assistantName], continuous: true });
          } catch(e) { console.log('Reinicio mic erro:', e); }
        }
      }, 300);
    }
  });

  // Eventos do módulo nativo
  useEffect(() => {
    if (!micEmitter) return;
    const sub = micEmitter.addListener('onSpeechDetected', (e) => {
      if (!e.text || !e.isFinal) return;
      if (e.hasWakeWord || !wakeWordRef.current) enviar(e.text);
    });
    return () => sub.remove();
  }, []);

  // ══ MULTILINGUE v2 (Groq STT) — cada ciclo nasce do zero ══════════════════
  async function cicloMultilingue() {
    // Limpa QUALQUER resto de gravacao anterior (recomeco limpo — metrica do Marcos)
    if (gravacaoRef.current) {
      try { await gravacaoRef.current.recording.stopAndUnloadAsync(); } catch(e) {}
      gravacaoRef.current = null;
    }
    if (!micAtivoRef.current || ttsAtivoRef.current) return;
    if (!userId) { setTimeout(cicloMultilingue, 1000); return; }
    try {
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
        (status) => {
          if (!status.isRecording) return;
          const g = gravacaoRef.current;
          if (!g) return;
          const nivel = status.metering ?? -160;
          if (nivel > -35) { g.teveFala = true; g.silencios = 0; }
          else if (g.teveFala) {
            g.silencios = (g.silencios || 0) + 1;
            if (g.silencios >= 5) finalizarCicloMultilingue();
          }
          if (status.durationMillis > 15000) finalizarCicloMultilingue();
        },
        300
      );
      gravacaoRef.current = { recording, teveFala: false, silencios: 0, ts: Date.now() };
    } catch(e) {
      console.log('[Multilingue] Erro ao criar gravacao:', e);
      gravacaoRef.current = null;
      setTimeout(cicloMultilingue, 2000); // retry — nunca desiste em silencio
    }
  }

  async function finalizarCicloMultilingue() {
    const g = gravacaoRef.current;
    if (!g) return;
    gravacaoRef.current = null;
    let texto = '', idioma = '';
    try {
      await g.recording.stopAndUnloadAsync();
      const uri = g.recording.getURI();
      if (g.teveFala && uri) {
        const FileSystem = require('expo-file-system/legacy');
        const audioB64 = await FileSystem.readAsStringAsync(uri, { encoding: 'base64' });
        const r = await fetch(`${config.backendUrl}/stt`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, audio_base64: audioB64, formato: 'm4a' })
        });
        const d = await r.json();
        texto = d.texto || '';
        idioma = d.idioma || '';
      }
    } catch(e) { console.log('[Multilingue] Erro no envio:', e); }
    if (texto) {
      console.log('[Multilingue]', idioma, ':', texto);
      ultimoIdiomaRef.current = (idioma || '').toLowerCase();
      enviar(texto, idioma);
    } else if (micAtivoRef.current && !ttsAtivoRef.current) {
      setTimeout(cicloMultilingue, 300); // sem fala — proximo ciclo
    }
  }

  // Watchdog: se o ciclo morrer por qualquer motivo, renasce em ate 10s
  useEffect(() => {
    const wd = setInterval(() => {
      if (multilingueRef.current && micAtivoRef.current && !ttsAtivoRef.current && !gravacaoRef.current) {
        console.log('[Multilingue] Watchdog: ciclo morto — renascendo');
        cicloMultilingue();
      }
      // Gravacao travada ha mais de 25s? Descarta e recomeca
      if (gravacaoRef.current && Date.now() - gravacaoRef.current.ts > 25000) {
        console.log('[Multilingue] Watchdog: gravacao travada — recomecando');
        finalizarCicloMultilingue();
      }
    }, 10000);
    return () => clearInterval(wd);
  }, []);

  async function iniciarMicrofone() {
    if (!ExpoSpeechRecognitionModule) return;
    try {
      const perm = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!perm.granted) return;
      setMicAtivo(true);
      micAtivoRef.current = true;
      if (multilingueRef.current) {
        cicloMultilingue(); // ouvido Groq (admin/premium/tester)
      } else {
        ExpoSpeechRecognitionModule.start({ lang: config.idioma || 'pt-BR', interimResults: false, addsPunctuation: true, contextualStrings: [config.assistantName], continuous: true });
      }
      iniciarNotificacaoPersistente(config.assistantName);
    } catch(e) { console.log('Mic erro:', e); }
  }

  async function pararMicrofone() {
    micAtivoRef.current = false;
    setMicAtivo(false);
    pararNotificacaoPersistente();
    if (ExpoMicrophoneModule) {
      try { await ExpoMicrophoneModule.stopListening(); } catch(e) {}
    } else if (ExpoSpeechRecognitionModule) {
      try { ExpoSpeechRecognitionModule.stop(); } catch(e) {}
    }
    // Nao para o WakeWordService — apenas garante que vai retomar quando app for pro background
    console.log('[WakeWord] Microfone desligado pelo usuario — servico continua ativo');
  }

  async function selecionarImagem() {
    Alert.alert('Debug2', 'selecionarImagem chamado!');
    Alert.alert('Enviar imagem', 'Escolha a origem:', [
      {
        text: '📷 Câmera',
        onPress: async () => {
          const perm = await ImagePicker.requestCameraPermissionsAsync();
          if (!perm.granted) { Alert.alert('Permissão negada', 'Permite acesso à câmera nas configurações.'); return; }
          const result = await ImagePicker.launchCameraAsync({
            allowsEditing: true, quality: 0.5, base64: true,
          });
          if (!result.canceled && result.assets[0]) {
            addMsg('user', '📷 Imagem enviada');
            await enviarImagem(result.assets[0].base64);
          }
        }
      },
      {
        text: '🖼️ Galeria',
        onPress: async () => {
          const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
          if (!perm.granted) { Alert.alert('Permissão negada', 'Permite acesso à galeria nas configurações.'); return; }
          const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ImagePicker.MediaTypeOptions.Images,
            allowsEditing: true, quality: 0.5, base64: true,
          });
          if (!result.canceled && result.assets[0]) {
            addMsg('user', '📷 Imagem enviada');
            await enviarImagem(result.assets[0].base64);
          }
        }
      },
      { text: 'Cancelar', style: 'cancel' }
    ]);
  }

  async function enviarImagem(base64) {
    if (!userId) return;
    Alert.alert('Debug', `Enviando imagem... base64 length: ${base64?.length || 0}`);
    setPensando(true);
    try {
      const body = { user_id: userId, mensagem: 'O que você vê nessa imagem?', imagem_base64: base64 };
      const _now = new Date();
      const _off = -_now.getTimezoneOffset();
      const _sign = _off >= 0 ? '+' : '-';
      const _hh = String(Math.floor(Math.abs(_off)/60)).padStart(2,'0');
      const _mm = String(Math.abs(_off)%60).padStart(2,'0');
      const _local = new Date(_now.getTime() + _off * 60000);
      body.hora_local = _local.toISOString().replace('Z', '') + _sign + _hh + ':' + _mm;
      const r = await fetch(`${config.backendUrl}/mensagem`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      const d = await r.json();
      const texto = d.resposta || 'Sem resposta.';
      addMsg('margo', texto);
      falar(limpar(texto));
    } catch(e) { addMsg('margo', 'Erro ao processar imagem.'); }
    setPensando(false);
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
    // Envia FCM token para o servidor
    try {
      const fcmToken = await AsyncStorage.getItem('margo_fcm_token');
      if (fcmToken) {
        fetch(`${config.backendUrl}/fcm_token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: data.user_id, token: fcmToken })
        });
      }
    } catch(e) { console.log('FCM envio erro:', e); }
    if (data.novo) {
      setTimeout(() => {
        addMsg('margo', `Olá! Sou a ${config.assistantName} 👋 Antes de começar, configure seu perfil tocando em ⚙ acima.\n\nO que consigo fazer:\n🎙️ Voz e chat • 🌐 Busca na web • 📍 Maps • 🎵 Spotify/SoundCloud • ▶️ YouTube • ✈️ Passagens aéreas • 🏨 Hotéis • 🏠 Casa inteligente • 📞 Ligações e WhatsApp\n\nVamos lá? 😊`);
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
    const wakeWordAntes = config.wakeWordOn;
    setConfig(cfg);
    await AsyncStorage.setItem('margo_config', JSON.stringify(cfg));
    await AsyncStorage.setItem('margo_idioma', cfg.idioma || 'pt-BR');
    setCfgAberto(false);
    // Ativa ou desativa wake word conforme toggle
    if (cfg.wakeWordOn && !wakeWordAntes) {
      try { await NativeModules.WakeWordModule.iniciar('migoo'); } catch(e) {}
    } else if (!cfg.wakeWordOn && wakeWordAntes) {
      try { await NativeModules.WakeWordModule.parar(); } catch(e) {}
    }
    try {
      const chaveEnviar = cfg.voiceProvider === 'fishaudio'
        ? (cfg.apiKeyFish || '')
        : '';  // ElevenLabs: chave fica só local, nunca vai pro servidor
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
    const stripeLinks = {
      'pro':      'https://buy.stripe.com/fZu00icrB57V2ba84r2oE01',
      'pro_plus': 'https://buy.stripe.com/dRmfZgfDNfMzdTS2K72oE02',
      'avulso':   'https://buy.stripe.com/fZu00ibnx57V032acz2oE00',
    };

    Alert.alert(
      s_i['pagamento_titulo'],
      s_i['pagamento_msg'],
      [
        {
          text: s_i['pagamento_cartao'],
          onPress: () => {
            const url = `${stripeLinks[planoEscolhido]}?client_reference_id=${userId}&prefilled_email=${encodeURIComponent(email)}`;
            setCfgAberto(false);
            Linking.openURL(url);
          }
        },
        {
          text: s_i['pagamento_pix'],
          onPress: async () => {
            try {
              const r = await fetch(`${config.backendUrl}/mp/criar_pix`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, plano: planoEscolhido, email })
              });
              const d = await r.json();
              if (d.qr_code) {
                setCfgAberto(false);
                // Copia o código PIX para área de transferência
                const { Clipboard } = require('react-native');
                Alert.alert(
                  '💙 Pagar via PIX',
                  `${d.titulo}\nValor: R$${d.valor.toFixed(2)}\n\nCódigo PIX copiado! Cole no seu banco para pagar.\n\n${d.qr_code}`,
                  [
                    { text: '📋 Copiar código', onPress: () => {
                      Clipboard.setString(d.qr_code);
                      Alert.alert('✅ Copiado!', 'Cole o código no app do seu banco para pagar via PIX.');
                    }},
                    { text: 'Fechar', style: 'cancel' }
                  ]
                );
                // Polling para detectar pagamento aprovado
                const ru0 = await fetch(`${config.backendUrl}/uso/${userId}`);
                const du0 = await ru0.json();
                const saldoAntes = du0.msgs_extras || 0;
                let tentativas = 0;
                const intervalo = setInterval(async () => {
                  tentativas++;
                  if (tentativas > 36) { clearInterval(intervalo); return; } // 3 min
                  try {
                    const ru = await fetch(`${config.backendUrl}/uso/${userId}`);
                    const du = await ru.json();
                    const novoExtras = du.msgs_extras || 0;
                    console.log(`[POLLING] tentativa ${tentativas} saldoAntes=${saldoAntes} novoExtras=${novoExtras}`);
                    if (novoExtras > saldoAntes) {
                      clearInterval(intervalo);
                      setMsgExtras(novoExtras);
                      Alert.alert('✅ Pagamento confirmado!', `+50 interações adicionadas! Saldo: ${novoExtras}`);
                    }
                  } catch(e) { console.log('[POLLING] erro:', e); Alert.alert('POLLING ERRO', String(e)); }
                }, 5000);
              } else { Alert.alert('Erro', d.erro || 'Erro ao gerar PIX'); }
            } catch(e) { console.log('MP erro:', e); Alert.alert('Erro', 'Sem conexão'); }
          }
        },
        { text: 'Cancelar', style: 'cancel' }
      ]
    );
  }

  async function sair() {
    Alert.alert(s_i['sair_titulo'], s_i['sair_msg'], [
      { text: s_i['cancelar'] },
      { text: s_i['sair_btn'], style: 'destructive', onPress: async () => {
        await pararMicrofone();
        await AsyncStorage.multiRemove(['margo_user_id', 'margo_email', 'margo_chat', 'margo_config', 'margo_avatar']);
        setConfig(CFG_PADRAO);
        setAvatarUri(null);
        setUserId(null); setMsgs([]); setCfgAberto(false); setTela('idioma');
      }}
    ]);
  }

  // ── RENDER ────────────────────────────────────────────────────────────────

  if (tela === 'boas_vindas') return <TelaBoasVindas onEntrar={() => setTela('login')} onCadastrar={() => setTela('cadastro')} idioma={config.idioma} />;
  if (tela === 'cadastro')    return <TelaCadastro onSuccess={onAuthSuccess} onVoltar={() => setTela('boas_vindas')} backendUrl={config.backendUrl} idioma={config.idioma} />;
  if (tela === 'login')       return <TelaLogin    onSuccess={onAuthSuccess} onVoltar={() => setTela('boas_vindas')} backendUrl={config.backendUrl} idioma={config.idioma} />;

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
            <Text style={s.headerSub}>{pensando ? s_i['pensando'] : micAtivo ? s_i['ouvindo'] : s_i['online']}</Text>
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
              placeholder={s_i['placeholder_msg']}
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
              {msgExtras > 0
                ? plano === 'free' || plano === 'trial'
                  ? `${faltam - msgExtras} trial + ${msgExtras} extras`
                  : `${faltam - msgExtras} hoje + ${msgExtras} extras`
                : plano === 'free' || plano === 'trial'
                  ? `${faltam} msgs restantes (trial)`
                  : `${faltam} msgs restantes hoje`}
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
        idioma={config.idioma}
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
