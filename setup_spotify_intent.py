#!/usr/bin/env python3
"""
Setup SpotifyIntentModule — módulo nativo Kotlin pra tocar Spotify via Intent
Rode: python3 ~/margo-app/setup_spotify_intent.py
"""

import os

base = os.path.expanduser("~/margo-app")
kotlin_dir = os.path.join(base, "android/app/src/main/java/com/orbiby/margo")

# 1. Registrar no MainApplication.kt
main_app = os.path.join(kotlin_dir, "MainApplication.kt")
with open(main_app, 'r') as f:
    content = f.read()

if 'SpotifyIntentPackage' not in content:
    content = content.replace(
        'add(GroqSTTPackage())',
        'add(GroqSTTPackage())\n              add(SpotifyIntentPackage())'
    )
    with open(main_app, 'w') as f:
        f.write(content)
    print("✅ 1. SpotifyIntentPackage registrado no MainApplication.kt")
else:
    print("⏭️  1. Já registrado")

# 2. Patch App.js — usar SpotifyIntentModule como fallback
app_js = os.path.join(base, "App.js")
with open(app_js, 'r') as f:
    content = f.read()

changes = 0

# Achar o bloco de spotify_play no App.js e adicionar fallback
# O bloco atual abre o Spotify via Linking quando spotifyPlayDireto falha
old_spotify = '''    } else if (t === 'spotify_play') {
      // Dispara o play no backend JÁ (ele tem retry esperando o device aparecer)
      // e abre o Spotify em paralelo — assim o fetch não congela em background
      const promessaPlay = spotifyPlayDireto(f.query);
      try {
        const acordou = await Linking.canOpenURL('spotify:').catch(() => false);
        if (acordou) await Linking.openURL('spotify:');
      } catch(e) {}
      const tocou = await promessaPlay;
      if (!tocou) {'''

new_spotify = '''    } else if (t === 'spotify_play') {
      // Tenta via API (pra quem tem OAuth conectado)
      const promessaPlay = spotifyPlayDireto(f.query);
      const tocou = await promessaPlay;
      if (!tocou) {
        // Fallback: Intent nativo (funciona pra qualquer usuário com Spotify)
        try {
          const resultado = await NativeModules.SpotifyIntentModule.play(f.query);
          console.log('[Spotify Intent]', resultado);
          if (resultado !== 'not_installed' && resultado !== 'failed') {
            // Deu certo via intent, não precisa fazer mais nada
          }
        } catch(e) { console.log('[Spotify Intent] erro:', e); }'''

if 'SpotifyIntentModule.play' not in content:
    if old_spotify in content:
        content = content.replace(old_spotify, new_spotify)
        changes += 1
        print("✅ 2. App.js: fallback Spotify via Intent adicionado")
    else:
        print("⚠️  2. Bloco spotify_play não encontrado no App.js — verificar manualmente")
else:
    print("⏭️  2. Já existe no App.js")

# Salvar
if changes > 0:
    with open(app_js, 'w') as f:
        f.write(content)

print(f"\n🎉 Setup concluído! {changes} mudanças no App.js")
print("📌 Próximo: build com ./gradlew :app:bundleRelease")
