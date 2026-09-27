const fs = require('fs');
let c = fs.readFileSync('App.js', 'utf8');

const old = `        } else {
          // Modo carro: IntentLauncher força Google Maps app direto
          try {
            const IntentLauncher = require('expo-intent-launcher');
            await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
              data: googleAppUrl,
              packageName: 'com.google.android.apps.maps'
            });
          } catch(e) {
            // Fallback: sempre Google Maps web, nunca Waze
            try { await Linking.openURL(googleWebUrl); } catch(e2) {}
          }
        }`;

const neu = `        } else {
          // Modo carro
          if (Platform.OS === 'android') {
            try {
              const IntentLauncher = require('expo-intent-launcher');
              await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
                data: googleAppUrl,
                packageName: 'com.google.android.apps.maps'
              });
            } catch(e) {
              try { await Linking.openURL(googleWebUrl); } catch(e2) {}
            }
          } else {
            // iOS: tenta Google Maps app, senão Apple Maps, senão web
            const gMapsIOS = \`comgooglemaps://?daddr=\${dest}&directionsmode=driving\`;
            const appleMaps = \`maps://?daddr=\${dest}&dirflg=d\`;
            try {
              const gSupported = await Linking.canOpenURL(gMapsIOS).catch(() => false);
              if (gSupported) {
                await Linking.openURL(gMapsIOS);
              } else {
                await Linking.openURL(appleMaps);
              }
            } catch(e) {
              try { await Linking.openURL(googleWebUrl); } catch(e2) {}
            }
          }
        }`;

if (c.includes(old)) {
  c = c.replace(old, neu);
  fs.writeFileSync('App.js', c, 'utf8');
  console.log('OK - Maps ajustado para iOS');
} else {
  console.log('ERRO - bloco nao encontrado');
}
