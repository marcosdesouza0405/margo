package expo.modules.microphone

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class MicrophoneModule : Module() {
    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var wakeWord = "margo"
    private val pendingResults = mutableListOf<String>()
    private var lastPartialTime = 0L

    override fun definition() = ModuleDefinition {
        Name("ExpoMicrophone")

        AsyncFunction("startListening") {
            startListening()
        }

        AsyncFunction("stopListening") {
            stopListening()
        }

        AsyncFunction("setWakeWord") { word: String ->
            wakeWord = word.lowercase()
        }

        AsyncFunction("isListening") {
            isListening
        }

        Events("onSpeechDetected")

        AsyncFunction("hasPermission") {
            ActivityCompat.checkSelfPermission(
                appContext.reactContext!!,
                Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun hasPermission(): Boolean {
        return ActivityCompat.checkSelfPermission(
            appContext.reactContext!!,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun startListening() {
        if (!hasPermission()) {
            sendEvent("onSpeechDetected", mapOf("error" to "no_permission"))
            return
        }

        val context = appContext.reactContext ?: return

        if (speechRecognizer == null) {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context)
            speechRecognizer?.setRecognitionListener(recognitionListener)
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 3000)
        }

        speechRecognizer?.startListening(intent)
        isListening = true
        startForegroundService()
    }

    private fun stopListening() {
        speechRecognizer?.stopListening()
        speechRecognizer?.destroy()
        speechRecognizer = null
        isListening = false
        stopForegroundService()
    }

    private val recognitionListener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}

        override fun onEndOfSpeech() {
            val ctx = appContext.reactContext ?: return
            if (isListening) {
                android.os.Handler(ctx.mainLooper).postDelayed({
                    if (isListening) startListening()
                }, 300)
            }
        }

        override fun onError(error: Int) {
            val ctx = appContext.reactContext ?: return
            if (isListening) {
                android.os.Handler(ctx.mainLooper).postDelayed({
                    if (isListening) startListening()
                }, 500)
            }
        }

        override fun onResults(results: Bundle?) {
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull() ?: return

            pendingResults.add(text)

            android.os.Handler(appContext.reactContext!!.mainLooper).postDelayed({
                val finalText = pendingResults.joinToString(" ")
                pendingResults.clear()

                val lowerText = finalText.lowercase()
                val hasWakeWord = lowerText.contains(wakeWord)
                val cleanText = if (hasWakeWord) {
                    lowerText.replace(wakeWord, "").trim()
                } else {
                    finalText
                }

                sendEvent("onSpeechDetected", mapOf(
                    "text" to cleanText,
                    "isFinal" to true,
                    "hasWakeWord" to hasWakeWord
                ))
            }, 800)
        }

        override fun onPartialResults(results: Bundle?) {
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull() ?: return

            val now = System.currentTimeMillis()
            if (now - lastPartialTime > 500) {
                lastPartialTime = now
                sendEvent("onSpeechDetected", mapOf(
                    "text" to text,
                    "isFinal" to false,
                    "hasWakeWord" to false
                ))
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    private fun startForegroundService() {
        val context = appContext.reactContext ?: return
        val serviceIntent = Intent(context, MicrophoneService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }

    private fun stopForegroundService() {
        val context = appContext.reactContext ?: return
        context.stopService(Intent(context, MicrophoneService::class.java))
    }

    class MicrophoneService : Service() {
        override fun onBind(intent: Intent?): IBinder? = null

        override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
            val channelId = "microphone_channel"

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channel = NotificationChannel(
                    channelId,
                    "Microfone da Margo",
                    NotificationManager.IMPORTANCE_LOW
                )
                val manager = getSystemService(NotificationManager::class.java)
                manager?.createNotificationChannel(channel)
            }

            val notification = NotificationCompat.Builder(this, channelId)
                .setContentTitle("Margo")
                .setContentText("Ouvindo...")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .build()

            startForeground(1, notification)
            return START_STICKY
        }
    }
}
