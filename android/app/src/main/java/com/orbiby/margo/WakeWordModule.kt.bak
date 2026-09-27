package com.orbiby.margo

import android.content.Intent
import android.os.Build
import android.util.Log
import com.facebook.react.bridge.*

class WakeWordModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    private val coordinator = MicrophoneCoordinator.getInstance()

    override fun getName() = "WakeWordModule"

    @ReactMethod
    fun iniciar(modelName: String, promise: Promise) {
        try {
            val intent = Intent(reactContext, WakeWordService::class.java).apply {
                putExtra("MODEL_NAME", modelName)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                reactContext.startForegroundService(intent)
            } else {
                reactContext.startService(intent)
            }
            promise.resolve("OK")
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun parar(promise: Promise) {
        try {
            val intent = Intent(reactContext, WakeWordService::class.java).apply {
                action = WakeWordService.ACTION_STOP
            }
            reactContext.startService(intent)
            promise.resolve("OK")
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun pausar(promise: Promise) {
        try {
            val intent = Intent(reactContext, WakeWordService::class.java).apply {
                action = WakeWordService.ACTION_PAUSE
            }
            reactContext.startService(intent)
            promise.resolve("OK")
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun retomar(promise: Promise) {
        try {
            val intent = Intent(reactContext, WakeWordService::class.java).apply {
                action = WakeWordService.ACTION_RESUME
            }
            reactContext.startService(intent)
            promise.resolve("OK")
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun requestSTT(promise: Promise) {
        try {
            val autorizado = coordinator.requestSTT()
            promise.resolve(autorizado)
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun releaseSTT(promise: Promise) {
        try {
            val liberado = coordinator.releaseSTT()
            promise.resolve(liberado)
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun requestTTS(promise: Promise) {
        try {
            val autorizado = coordinator.requestTTS()
            promise.resolve(autorizado)
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun releaseTTS(promise: Promise) {
        try {
            val liberado = coordinator.releaseTTS()
            // Reinicia WakeWordService apos TTS
            if (liberado) {
                val intent = Intent(reactContext, WakeWordService::class.java).apply {
                    action = WakeWordService.ACTION_RESUME
                }
                reactContext.startService(intent)
            }
            promise.resolve(liberado)
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun getState(promise: Promise) {
        try {
            promise.resolve(coordinator.getState().name)
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }

    @ReactMethod
    fun verificarPermissaoFullScreen(promise: Promise) {
        try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val nm = reactContext.getSystemService(android.app.NotificationManager::class.java)
                val temPermissao = nm.canUseFullScreenIntent()
                android.util.Log.d("WakeWordModule", "USE_FULL_SCREEN_INTENT: $temPermissao")
                promise.resolve(temPermissao)
            } else {
                promise.resolve(true)
            }
        } catch (e: Exception) {
            promise.reject("ERRO", e.message)
        }
    }

    @ReactMethod
    fun abrirConfiguracoesFullScreen(promise: Promise) {
        try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val intent = android.content.Intent(
                    android.provider.Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,
                    android.net.Uri.parse("package:${reactContext.packageName}")
                ).apply {
                    flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                }
                reactContext.startActivity(intent)
            }
            promise.resolve("OK")
        } catch (e: Exception) {
            promise.reject("ERRO", e.message)
        }
    }

    @ReactMethod
    fun verificarPermissaoOverlay(promise: Promise) {
        try {
            val temPermissao = android.provider.Settings.canDrawOverlays(reactContext)
            android.util.Log.d("WakeWordModule", "SYSTEM_ALERT_WINDOW: $temPermissao")
            promise.resolve(temPermissao)
        } catch (e: Exception) {
            promise.reject("ERRO", e.message)
        }
    }

    @ReactMethod
    fun checkWakeWordPendente(promise: Promise) {
        try {
            val prefs = reactContext.getSharedPreferences("wakeword", android.content.Context.MODE_PRIVATE)
            val detectada = prefs.getBoolean("detectada", false)
            if (detectada) {
                prefs.edit().putBoolean("detectada", false).apply()
                Log.d("WakeWordModule", "Wake word pendente encontrada e limpa!")
            }
            promise.resolve(detectada)
        } catch (e: Exception) { promise.reject("ERRO", e.message) }
    }
}
