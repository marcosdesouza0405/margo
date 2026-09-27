package com.orbiby.margo

import ai.onnxruntime.*
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import org.tensorflow.lite.Interpreter
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class WakeWordService : Service() {

    companion object {
        const val TAG = "WakeWordService"
        const val NOTIFICATION_ID = 1001
        const val CHANNEL_ID = "wakeword_channel"
        const val SAMPLE_RATE = 16000
        const val CHUNK_SIZE = 1280
        const val BUFFER_SIZE = 48000
        const val MELSPEC_FRAMES = 297
        const val EMBED_WINDOW = 76
        const val EMBED_STRIDE = 8
        const val NUM_EMBEDDINGS = 28
        const val EMBED_FEATURES = 96
        const val TFLITE_INPUT = 2688
        const val DETECTION_THRESHOLD = 0.9f
        const val DEBOUNCE_MS = 5000L
        const val ACTION_STOP = "com.orbiby.margo.STOP_WAKEWORD"
        const val ACTION_PAUSE = "com.orbiby.margo.PAUSE_WAKEWORD"
        const val ACTION_RESUME = "com.orbiby.margo.RESUME_WAKEWORD"
    }

    private lateinit var ortEnvironment: OrtEnvironment
    private lateinit var melspecSession: OrtSession
    private lateinit var embeddingSession: OrtSession
    private lateinit var tfliteInterpreter: Interpreter

    private val audioBuffer = FloatArray(BUFFER_SIZE)
    private var bufferWriteIndex = 0
    private val bufferLock = Object()

    private val isRunning = AtomicBoolean(false)
    private var audioRecord: AudioRecord? = null
    private var processingThread: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var lastDetectionTime = 0L
    private var scoreConsecutivo = 0
    private val coordinator = MicrophoneCoordinator.getInstance()
    private var modelName = "margo"

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "onCreate")
        criarCanalNotificacao()
        // NAO chama startForeground aqui — Android 14+ exige app visivel
        // startForeground sera chamado no onStartCommand
    }

    private fun carregarModelos() {
        ortEnvironment = OrtEnvironment.getEnvironment()
        assets.open("onnx/melspectrogram.onnx").use { input ->
            val bytes = input.readBytes()
            melspecSession = ortEnvironment.createSession(bytes, OrtSession.SessionOptions())
            Log.d(TAG, "melspectrogram.onnx carregado")
        }
        assets.open("onnx/embedding_model.onnx").use { input ->
            val bytes = input.readBytes()
            embeddingSession = ortEnvironment.createSession(bytes, OrtSession.SessionOptions())
            Log.d(TAG, "embedding_model.onnx carregado")
        }
        carregarModeloWakeWord(modelName)
    }

    private fun carregarModeloWakeWord(nome: String) {
        modelName = nome
        assets.open("wakeword/$nome.tflite").use { input ->
            val bytes = input.readBytes()
            val buffer = ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder())
            buffer.put(bytes)
            buffer.rewind()
            if (::tfliteInterpreter.isInitialized) tfliteInterpreter.close()
            tfliteInterpreter = Interpreter(buffer, Interpreter.Options().apply { setNumThreads(2) })
            Log.d(TAG, "wakeword/$nome.tflite carregado")
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: "null"
        Log.d(TAG, "onStartCommand: $action")

        when (action) {
            ACTION_STOP -> {
                pararTudo()
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_PAUSE -> {
                Log.d(TAG, "PAUSE: parando AudioRecord — servico continua vivo")
                isRunning.set(false)
                audioRecord?.stop()
                synchronized(bufferLock) {
                    audioBuffer.fill(0f)
                    bufferWriteIndex = 0
                }
            }
            ACTION_RESUME -> {
                Log.d(TAG, "RESUME: retomando AudioRecord")
                isRunning.set(false)
                synchronized(bufferLock) {
                    audioBuffer.fill(0f)
                    bufferWriteIndex = 0
                }
                lastDetectionTime = 0L
                thread(name = "ResumeLoader") {
                    try {
                        Thread.sleep(300)
                        if (!::tfliteInterpreter.isInitialized) carregarModelos()
                        iniciarDeteccao()
                    } catch (e: Exception) {
                        Log.e(TAG, "Erro ao retomar: ${e.message}")
                    }
                }
            }

            else -> {
                modelName = intent?.getStringExtra("MODEL_NAME") ?: "migoo"
                Log.d(TAG, "Iniciando com modelo: $modelName")
                val autorizado = coordinator.requestWakeWord()
                if (!autorizado) {
                    val state = coordinator.getState()
                    if (state == MicrophoneCoordinator.MicState.DISABLED) {
                        Log.d(TAG, "Wake word desativada — encerrando")
                        stopSelf()
                        return START_NOT_STICKY
                    }
                    if (state != MicrophoneCoordinator.MicState.WAKEWORD_ACTIVE) {
                        Log.w(TAG, "Coordinator negou — estado: $state")
                        stopSelf()
                        return START_NOT_STICKY
                    }
                }
                // startForeground aqui — app esta visivel (chamado do JS)
                val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
                if (wakeLock == null) {
                    wakeLock = powerManager.newWakeLock(
                        PowerManager.PARTIAL_WAKE_LOCK, "Margo::WakeWordLock"
                    ).apply {
                        setReferenceCounted(false)
                        acquire(10 * 60 * 1000L)
                    }
                }
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                        startForeground(NOTIFICATION_ID, criarNotificacao(),
                            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
                    } else {
                        startForeground(NOTIFICATION_ID, criarNotificacao())
                    }
                    Log.d(TAG, "startForeground concluido no onStartCommand")
                } catch (e: SecurityException) {
                    Log.e(TAG, "startForeground negado: ${e.message} — encerrando servico")
                    stopSelf()
                    return START_NOT_STICKY
                }
                // Sempre reinicia deteccao — servico pode estar vivo mas loop morto
                thread(name = "ModelLoader") {
                    try {
                        isRunning.set(false)
                        audioRecord?.stop()
                        processingThread?.interrupt()
                        Thread.sleep(200)
                        if (!::tfliteInterpreter.isInitialized) carregarModelos()
                        Log.d(TAG, "Reiniciando deteccao")
                        iniciarDeteccao()
                    } catch (e: Exception) {
                        Log.e(TAG, "Erro ao carregar modelos: ${e.message}")
                    }
                }
            }
        }
        return START_STICKY
    }

    private fun iniciarDeteccao() {
        if (isRunning.get()) return
        Log.d(TAG, "Iniciando deteccao")
        isRunning.set(true)
        iniciarAudioRecord()
        iniciarLoopProcessamento()
    }

    private fun iniciarAudioRecord() {
        // Libera AudioRecord anterior se existir
        try { audioRecord?.stop() } catch (e: Exception) {}
        try { audioRecord?.release() } catch (e: Exception) {}
        audioRecord = null
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC, SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            minBuf.coerceAtLeast(CHUNK_SIZE * 2)
        ).apply { startRecording() }
        Log.d(TAG, "AudioRecord iniciado")
    }

    private fun iniciarLoopProcessamento() {
        // Para thread anterior se existir
        processingThread?.interrupt()
        processingThread = thread(name = "WakeWordProcessor") {
            Log.d(TAG, "Loop iniciado — modelo: $modelName")
            val tempBuffer = ShortArray(CHUNK_SIZE)
            while (isRunning.get()) {
                try {
                    if (audioRecord?.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
                        Thread.sleep(100)
                        continue
                    }
                    val read = audioRecord?.read(tempBuffer, 0, CHUNK_SIZE) ?: 0
                    if (read > 0) {
                        adicionarAoBuffer(FloatArray(read) { tempBuffer[it] / 32768.0f })
                        if (bufferWriteIndex >= BUFFER_SIZE) {
                            val score = processarPipeline()
                            if (score >= 0.5f) {
                                Log.d(TAG, "Score alto: $score — salvando audio para analise")
                                salvarAudioDebug(score)
                            }
                            if (score >= DETECTION_THRESHOLD) {
                                val now = System.currentTimeMillis()
                                if (now - lastDetectionTime > DEBOUNCE_MS) {
                                    lastDetectionTime = now
                                    onWakeWordDetectada(score)
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Erro no loop: ${e.message}")
                    Thread.sleep(100)
                }
            }
            Log.d(TAG, "Loop encerrado")
        }
    }

    private fun adicionarAoBuffer(chunk: FloatArray) {
        synchronized(bufferLock) {
            for (sample in chunk) {
                audioBuffer[bufferWriteIndex % BUFFER_SIZE] = sample
                bufferWriteIndex++
            }
        }
    }

    private var debugAudioCount = 0
    private fun salvarAudioDebug(score: Float) {
        try {
            val dir = getExternalFilesDir(null) ?: return
            val debugDir = java.io.File(dir, "wakeword_debug")
            debugDir.mkdirs()
            // Maximo 50 arquivos para nao encher o armazenamento
            if (debugAudioCount >= 50) return
            val window = synchronized(bufferLock) {
                val w = FloatArray(BUFFER_SIZE)
                val start = maxOf(0, bufferWriteIndex - BUFFER_SIZE)
                for (i in 0 until BUFFER_SIZE) w[i] = audioBuffer[(start + i) % BUFFER_SIZE]
                w
            }
            val scoreStr = String.format("%.2f", score).replace(".", "_")
            val countStr = String.format("%03d", debugAudioCount)
            val file = java.io.File(debugDir, "debug_${scoreStr}_${countStr}.wav")
            // Escreve WAV 16kHz mono
            val pcm = ShortArray(BUFFER_SIZE) { (window[it] * 32767).toInt().toShort() }
            java.io.RandomAccessFile(file, "rw").use { raf ->
                val dataSize = pcm.size * 2
                fun writeIntLE(v: Int) { raf.write(v and 0xFF); raf.write((v shr 8) and 0xFF); raf.write((v shr 16) and 0xFF); raf.write((v shr 24) and 0xFF) }
                fun writeShortLE(v: Int) { raf.write(v and 0xFF); raf.write((v shr 8) and 0xFF) }
                raf.writeBytes("RIFF"); writeIntLE(36 + dataSize)
                raf.writeBytes("WAVEfmt "); writeIntLE(16)
                writeShortLE(1); writeShortLE(1)
                writeIntLE(16000); writeIntLE(32000)
                writeShortLE(2); writeShortLE(16)
                raf.writeBytes("data"); writeIntLE(dataSize)
                for (s in pcm) writeShortLE(s.toInt())
            }
            debugAudioCount++
            Log.d(TAG, "Audio debug salvo: ${file.name}")
        } catch (e: Exception) {
            Log.e(TAG, "Erro ao salvar debug: ${e.message}")
        }
    }

    private fun processarPipeline(): Float {
        // Verifica se modelos estao prontos antes de processar
        if (!::ortEnvironment.isInitialized || !::melspecSession.isInitialized ||
            !::embeddingSession.isInitialized || !::tfliteInterpreter.isInitialized) {
            return 0f
        }
        // Verifica se sessoes estao abertas
        if (melspecSession.inputNames == null || embeddingSession.inputNames == null) {
            return 0f
        }

        val window = synchronized(bufferLock) {
            val w = FloatArray(BUFFER_SIZE)
            val start = maxOf(0, bufferWriteIndex - BUFFER_SIZE)
            for (i in 0 until BUFFER_SIZE) {
                w[i] = audioBuffer[(start + i) % BUFFER_SIZE]
            }
            w
        }
        return try {
            val melspec = rodarMelspec(window)
            val embeddings = rodarEmbeddings(melspec)
            val score = rodarTFLite(embeddings)
            if (score > 0.1f) Log.d(TAG, "Score: $score")
            score
        } catch (e: Exception) {
            Log.e(TAG, "Erro pipeline: ${e.message}")
            0f
        }
    }

    private fun rodarMelspec(audio: FloatArray): Array<*> {
        val shape = longArrayOf(1, BUFFER_SIZE.toLong())
        OnnxTensor.createTensor(ortEnvironment, FloatBuffer.wrap(audio), shape).use { t ->
            val name = melspecSession.inputNames.iterator().next()
            melspecSession.run(mapOf(name to t)).use { r ->
                return r[0].value as Array<*>
            }
        }
    }

    private fun rodarEmbeddings(melspec: Array<*>): Array<FloatArray> {
        val embeddings = Array(NUM_EMBEDDINGS) { FloatArray(EMBED_FEATURES) }
        val inputName = embeddingSession.inputNames.iterator().next()

        // melspec output: [1, 1, 297, 32] — ONNX retorna como array 4D flat
        // Extrai frames navegando pela estrutura real
        val frames = extrairFramesMelspec(melspec)

        for (w in 0 until NUM_EMBEDDINGS) {
            val start = w * EMBED_STRIDE
            val windowData = Array(1) {
                Array(EMBED_WINDOW) { f ->
                    Array(32) { m -> floatArrayOf(frames[start + f][m]) }
                }
            }
            OnnxTensor.createTensor(ortEnvironment, windowData).use { t ->
                embeddingSession.run(mapOf(inputName to t)).use { r ->
                    embeddings[w] = extrairEmbedding(r[0].value)
                }
            }
        }
        return embeddings
    }

    private fun extrairFramesMelspec(melspec: Array<*>): Array<FloatArray> {
        // Log do tipo real para diagnostico
        val tipoRaiz = melspec.javaClass.name
        val tipo0 = melspec[0]?.javaClass?.name ?: "null"
        Log.d(TAG, "Melspec tipo raiz: $tipoRaiz, tipo[0]: $tipo0, size: ${melspec.size}")

        return try {
            val b = melspec[0] as Array<*>
            val tipo1 = b[0]?.javaClass?.name ?: "null"
            Log.d(TAG, "Melspec[0] size: ${b.size}, tipo[0][0]: $tipo1")
            val c = b[0] as Array<*>
            val tipo2 = c[0]?.javaClass?.name ?: "null"
            Log.d(TAG, "Melspec[0][0] size: ${c.size}, tipo[0][0][0]: $tipo2")
            Array(MELSPEC_FRAMES) { i -> (c[i] as FloatArray).clone() }
        } catch (e: ClassCastException) {
            // Fallback: melspec e FloatArray flat — ordem: [batch, channel, frames, mel_bins]
            // Total: 1*1*297*32 = 9504 floats
            Log.w(TAG, "Melspec flat fallback — tipo: $tipo0")
            val flat = when (val v = melspec[0]) {
                is FloatArray -> {
                    Log.d(TAG, "Melspec flat size: ${v.size} (esperado: ${MELSPEC_FRAMES * 32})")
                    v
                }
                is Array<*> -> FloatArray(v.size) { i -> v[i] as Float }
                else -> FloatArray(MELSPEC_FRAMES * 32)
            }
            // Reorganiza na ordem correta: [frames][mel_bins]
            Array(MELSPEC_FRAMES) { i ->
                FloatArray(32) { j -> flat[i * 32 + j] }
            }
        }
    }

    private fun extrairEmbedding(value: Any?): FloatArray {
        // Output embedding: [1, 1, 1, 96]
        return try {
            val b = (value as Array<*>)[0] as Array<*>
            val d1 = b[0] as Array<*>
            val d2 = d1[0]
            when (d2) {
                is FloatArray -> d2.clone()
                is Array<*> -> FloatArray(EMBED_FEATURES) { i -> d2[i] as Float }
                else -> FloatArray(EMBED_FEATURES)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Embedding cast fallback: ${e.message}")
            FloatArray(EMBED_FEATURES)
        }
    }

    private fun rodarTFLite(embeddings: Array<FloatArray>): Float {
        val buf = ByteBuffer.allocateDirect(TFLITE_INPUT * 4).order(ByteOrder.nativeOrder())
        embeddings.forEach { e -> e.forEach { buf.putFloat(it) } }
        buf.rewind()
        val out = Array(1) { FloatArray(1) }
        tfliteInterpreter.run(buf, out)
        return out[0][0]
    }

    private fun onWakeWordDetectada(score: Float) {
        Log.e(TAG, "=== WAKE WORD DETECTADA! Score: $score | Modelo: $modelName ===")
        // Pausa AudioRecord mas mantem servico vivo (token BAL ativo)
        audioRecord?.stop()
        synchronized(bufferLock) {
            audioBuffer.fill(0f)
            bufferWriteIndex = 0
        }
        lastDetectionTime = System.currentTimeMillis()
        Log.d(TAG, "AudioRecord pausado — abrindo app")
        abrirApp()
    }

    private var deteccaoRecente = false

    private fun abrirApp() {
        Log.e(TAG, "=== ABRINDO APP ===")
        deteccaoRecente = true

        val mainIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("WAKE_WORD_DETECTED", true)
            putExtra("WAKE_WORD_MODEL", modelName)
        }

        val pendingIntent = PendingIntent.getActivity(
            this, 0, mainIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, "wakeword_call_v3")
            .setContentTitle("Margo ouviu voce!")
            .setContentText("Toque para falar")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setFullScreenIntent(pendingIntent, true)
            .build()

        getSystemService(NotificationManager::class.java).notify(9999, notification)
        Log.d(TAG, "Notificacao fullScreenIntent disparada!")

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                val options = android.app.ActivityOptions.makeBasic().apply {
                    pendingIntentBackgroundActivityStartMode =
                        android.app.ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED
                }
                startActivity(mainIntent, options.toBundle())
            } else {
                startActivity(mainIntent)
            }
            Log.d(TAG, "startActivity executado!")
        } catch (e: Exception) {
            Log.e(TAG, "startActivity falhou: ${e.message}")
        }
    }

    private fun pararTudo() {
        isRunning.set(false)
        coordinator.releaseWakeWord()
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        processingThread?.join(1000)
        processingThread = null
        wakeLock?.release()
        wakeLock = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        Log.d(TAG, "Tudo parado")
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "onDestroy")
        isRunning.set(false)
        try { processingThread?.join(1000) } catch (e: Exception) {}
        processingThread = null
        try { audioRecord?.stop(); audioRecord?.release() } catch (e: Exception) {}
        audioRecord = null
        try { wakeLock?.release() } catch (e: Exception) {}
        wakeLock = null
        if (::melspecSession.isInitialized) try { melspecSession.close() } catch (e: Exception) {}
        if (::embeddingSession.isInitialized) try { embeddingSession.close() } catch (e: Exception) {}
        if (::ortEnvironment.isInitialized) try { ortEnvironment.close() } catch (e: Exception) {}
        if (::tfliteInterpreter.isInitialized) try { tfliteInterpreter.close() } catch (e: Exception) {}
    }

    private fun dispararNotificacaoWakeWord() {
        Log.d(TAG, "Disparando notificacao de wake word...")
        val mainIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("WAKE_WORD_DETECTED", true)
            putExtra("WAKE_WORD_MODEL", modelName)
        }
        val pi = PendingIntent.getActivity(this, 999, mainIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Margo ouviu voce!")
            .setContentText("Toque para responder")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setFullScreenIntent(pi, true)
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(1002, notif)
        Log.d(TAG, "Notificacao disparada!")
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
        Log.d(TAG, "onTaskRemoved — reagendando servico")
        val restart = Intent(applicationContext, WakeWordService::class.java).apply {
            putExtra("MODEL_NAME", modelName)
        }
        val pi = android.app.PendingIntent.getService(
            applicationContext, 1, restart,
            android.app.PendingIntent.FLAG_ONE_SHOT or android.app.PendingIntent.FLAG_IMMUTABLE
        )
        val alarm = getSystemService(ALARM_SERVICE) as android.app.AlarmManager
        alarm.set(android.app.AlarmManager.ELAPSED_REALTIME,
            android.os.SystemClock.elapsedRealtime() + 1000, pi)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun criarCanalNotificacao() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Canal silencioso para notificacao persistente do servico
            val channel = NotificationChannel(CHANNEL_ID, "Margo Wake Word",
                NotificationManager.IMPORTANCE_LOW).apply {
                setShowBadge(false)
                enableVibration(false)
            }
            // Canal silencioso para wake word
            val alertChannel = NotificationChannel("wakeword_call_v3", "Migoo Ativacao",
                NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Migoo detectou sua voz"
                enableVibration(true)
                setShowBadge(true)
                setBypassDnd(true)
                lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.deleteNotificationChannel("wakeword_alert")
            manager.deleteNotificationChannel("wakeword_call")
            manager.deleteNotificationChannel("wakeword_call_v2")
            manager.createNotificationChannel(channel)
            manager.createNotificationChannel(alertChannel)
        }
    }

    private fun criarNotificacao(): Notification {
        val nome = when (modelName) { "margo" -> "Margo"; "max" -> "Max"; "migoo" -> "Migoo"; else -> "Migoo" }
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pi = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Margo")
            .setContentText("Diga \"$nome\" para ativar")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pi)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }
}
