const { withAndroidManifest, withDangerousMod } = require('@expo/config-plugins');
const path = require('path');
const fs = require('fs');

// Copia os arquivos Java para o projeto Android
const withMicrophoneModule = (config) => {
  config = withDangerousMod(config, [
    'android',
    async (config) => {
      const projectRoot = config.modRequest.projectRoot;
      const androidSrcDir = path.join(
        projectRoot,
        'android/app/src/main/java/com/orbiby/margo'
      );

      // Cria o diretório se não existir
      if (!fs.existsSync(androidSrcDir)) {
        fs.mkdirSync(androidSrcDir, { recursive: true });
      }

      // Copia MicrophoneModule.java
      const srcModule = path.join(projectRoot, 'modules/MicrophoneModule/MicrophoneModule.java');
      const dstModule = path.join(androidSrcDir, 'MicrophoneModule.java');
      if (fs.existsSync(srcModule)) {
        fs.copyFileSync(srcModule, dstModule);
      }

      // Copia MicrophoneModulePackage.java
      const srcPackage = path.join(projectRoot, 'modules/MicrophoneModule/MicrophoneModulePackage.java');
      const dstPackage = path.join(androidSrcDir, 'MicrophoneModulePackage.java');
      if (fs.existsSync(srcPackage)) {
        fs.copyFileSync(srcPackage, dstPackage);
      }

      // Registra o package no MainApplication.java
      const mainAppPath = path.join(androidSrcDir, 'MainApplication.kt');
      const mainAppPathJava = path.join(androidSrcDir, 'MainApplication.java');
      
      // Verifica qual arquivo existe
      const mainApp = fs.existsSync(mainAppPath) ? mainAppPath : mainAppPathJava;
      
      if (fs.existsSync(mainApp)) {
        let content = fs.readFileSync(mainApp, 'utf8');
        if (!content.includes('MicrophoneModulePackage')) {
          content = content.replace(
            'packages.add(new ModuleRegistryAdapter(mModuleRegistryProvider));',
            'packages.add(new ModuleRegistryAdapter(mModuleRegistryProvider));\n        packages.add(new MicrophoneModulePackage());'
          );
          // Para Kotlin
          content = content.replace(
            'add(ModuleRegistryAdapter(moduleRegistryProvider))',
            'add(ModuleRegistryAdapter(moduleRegistryProvider))\n        add(MicrophoneModulePackage())'
          );
          fs.writeFileSync(mainApp, content);
        }
      }

      return config;
    },
  ]);

  // Adiciona permissões no AndroidManifest
  config = withAndroidManifest(config, (config) => {
    const manifest = config.modResults.manifest;
    if (!manifest['uses-permission']) {
      manifest['uses-permission'] = [];
    }
    const permissions = [
      'android.permission.RECORD_AUDIO',
      'android.permission.FOREGROUND_SERVICE',
      'android.permission.FOREGROUND_SERVICE_MICROPHONE',
    ];
    permissions.forEach((perm) => {
      const exists = manifest['uses-permission'].some(
        (p) => p.$['android:name'] === perm
      );
      if (!exists) {
        manifest['uses-permission'].push({ $: { 'android:name': perm } });
      }
    });
    return config;
  });

  return config;
};

module.exports = withMicrophoneModule;
