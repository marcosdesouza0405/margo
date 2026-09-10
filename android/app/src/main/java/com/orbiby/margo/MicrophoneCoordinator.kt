package com.orbiby.margo

import android.util.Log
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicReference

class MicrophoneCoordinator private constructor() {

    // ── ESTADOS ──────────────────────────────────────────────────────────────
    enum class MicState {
        IDLE,
        DISABLED,
        WAKEWORD_ACTIVE,
        TRANSITION_TO_STT,
        STT_ACTIVE,
        STT_TIMEOUT,
        TRANSITION_TO_WAKEWORD,
        TTS_ACTIVE
    }

    // ── SINGLETON ─────────────────────────────────────────────────────────────
    companion object {
        const val TAG = "MicCoordinator"
        const val TRANSITION_TIMEOUT_MS = 2000L
        const val STT_TIMEOUT_MS = 5000L

        @Volatile
        private var instance: MicrophoneCoordinator? = null

        fun getInstance(): MicrophoneCoordinator {
            return instance ?: synchronized(this) {
                instance ?: MicrophoneCoordinator().also { instance = it }
            }
        }
    }

    // ── ESTADO ATUAL ──────────────────────────────────────────────────────────
    private val currentState = AtomicReference(MicState.IDLE)
    private val currentOwner = AtomicReference("none")
    private val listeners = CopyOnWriteArrayList<StateListener>()
    private var transitionTimer: java.util.Timer? = null
    private var sttTimeoutTimer: java.util.Timer? = null

    // ── INTERFACE LISTENER ────────────────────────────────────────────────────
    interface StateListener {
        fun onStateChanged(oldState: MicState, newState: MicState)
    }

    // ── LOGS ──────────────────────────────────────────────────────────────────
    private fun log(action: String, detail: String = "") {
        Log.e(TAG, "[$action] state=${currentState.get()} owner=${currentOwner.get()} $detail ts=${System.currentTimeMillis()}")
    }

    // ── GERENCIAMENTO DE ESTADO ───────────────────────────────────────────────
    private fun setState(newState: MicState, owner: String = currentOwner.get()) {
        val oldState = currentState.getAndSet(newState)
        currentOwner.set(owner)
        log("STATE_CHANGE", "$oldState -> $newState owner=$owner")
        listeners.forEach { it.onStateChanged(oldState, newState) }
    }

    fun addListener(listener: StateListener) {
        listeners.add(listener)
    }

    fun removeListener(listener: StateListener) {
        listeners.remove(listener)
    }

    fun getState(): MicState = currentState.get()

    // ── REQUESTS ──────────────────────────────────────────────────────────────

    fun requestWakeWord(): Boolean {
        val state = currentState.get()
        return when (state) {
            MicState.IDLE,
            MicState.STT_TIMEOUT,
            MicState.TRANSITION_TO_WAKEWORD -> {
                cancelTransitionTimer()
                setState(MicState.WAKEWORD_ACTIVE, "wakeword_service")
                log("WAKEWORD_ACQUIRED")
                true
            }
            MicState.DISABLED -> {
                log("WAKEWORD_REJECTED", "app desativado pelo usuario")
                false
            }
            else -> {
                log("WAKEWORD_REJECTED", "estado atual nao permite: $state")
                false
            }
        }
    }

    fun requestSTT(): Boolean {
        val state = currentState.get()
        return when (state) {
            MicState.TRANSITION_TO_STT -> {
                cancelTransitionTimer()
                cancelSttTimeout()
                setState(MicState.STT_ACTIVE, "expo_speech")
                log("STT_ACQUIRED")
                startSttTimeoutTimer()
                true
            }
            else -> {
                log("STT_REJECTED", "estado atual nao permite: $state")
                false
            }
        }
    }

    fun releaseWakeWord(): Boolean {
        val state = currentState.get()
        return when (state) {
            MicState.WAKEWORD_ACTIVE -> {
                setState(MicState.TRANSITION_TO_STT, "none")
                log("WAKEWORD_RELEASED", "iniciando transicao para STT")
                startTransitionTimer {
                    log("TRANSITION_TIMEOUT", "TRANSITION_TO_STT expirou sem confirmacao")
                    setState(if (currentState.get() == MicState.DISABLED) MicState.DISABLED else MicState.IDLE, "none")
                }
                true
            }
            else -> {
                log("RELEASE_WAKEWORD_REJECTED", "estado atual: $state")
                false
            }
        }
    }

    fun releaseSTT(): Boolean {
        val state = currentState.get()
        return when (state) {
            MicState.STT_ACTIVE,
            MicState.STT_TIMEOUT -> {
                cancelSttTimeout()
                setState(MicState.TRANSITION_TO_WAKEWORD, "none")
                log("STT_RELEASED", "iniciando transicao para WAKEWORD")
                startTransitionTimer {
                    log("TRANSITION_TIMEOUT", "TRANSITION_TO_WAKEWORD expirou sem confirmacao")
                    setState(if (currentState.get() == MicState.DISABLED) MicState.DISABLED else MicState.IDLE, "none")
                }
                true
            }
            else -> {
                log("RELEASE_STT_REJECTED", "estado atual: $state")
                false
            }
        }
    }

    fun requestTTS(): Boolean {
        val state = currentState.get()
        return when (state) {
            MicState.STT_ACTIVE,
            MicState.TRANSITION_TO_WAKEWORD -> {
                cancelSttTimeout()
                cancelTransitionTimer()
                setState(MicState.TTS_ACTIVE, "tts")
                log("TTS_ACQUIRED")
                true
            }
            else -> {
                log("TTS_REJECTED", "estado atual: $state")
                false
            }
        }
    }

    fun releaseTTS(): Boolean {
        val state = currentState.get()
        return when (state) {
            MicState.TTS_ACTIVE -> {
                setState(MicState.TRANSITION_TO_WAKEWORD, "none")
                log("TTS_RELEASED", "iniciando transicao para WAKEWORD")
                startTransitionTimer {
                    log("TRANSITION_TIMEOUT", "após TTS expirou sem confirmação")
                    setState(if (currentState.get() == MicState.DISABLED) MicState.DISABLED else MicState.IDLE, "none")
                }
                true
            }
            else -> {
                log("RELEASE_TTS_REJECTED", "estado atual: $state")
                false
            }
        }
    }

    fun disable() {
        cancelAll()
        setState(MicState.DISABLED, "user")
        log("DISABLED", "usuario desativou wake word")
    }

    fun enable() {
        if (currentState.get() == MicState.DISABLED) {
            setState(MicState.IDLE, "none")
            log("ENABLED", "usuario ativou wake word")
        }
    }

    // ── EMERGENCIA ────────────────────────────────────────────────────────────
    fun forceReset() {
        log("FORCE_RESET", "resetando para IDLE - usar apenas em emergencias")
        cancelAll()
        setState(MicState.IDLE, "none")
    }

    // ── TIMERS ────────────────────────────────────────────────────────────────
    private fun startTransitionTimer(onTimeout: () -> Unit) {
        cancelTransitionTimer()
        transitionTimer = java.util.Timer()
        transitionTimer?.schedule(object : java.util.TimerTask() {
            override fun run() { onTimeout() }
        }, TRANSITION_TIMEOUT_MS)
    }

    private fun cancelTransitionTimer() {
        transitionTimer?.cancel()
        transitionTimer = null
    }

    private fun startSttTimeoutTimer() {
        cancelSttTimeout()
        sttTimeoutTimer = java.util.Timer()
        sttTimeoutTimer?.schedule(object : java.util.TimerTask() {
            override fun run() {
                if (currentState.get() == MicState.STT_ACTIVE) {
                    log("STT_TIMEOUT", "usuario nao falou em ${STT_TIMEOUT_MS}ms")
                    setState(MicState.STT_TIMEOUT, "none")
                    releaseSTT()
                }
            }
        }, STT_TIMEOUT_MS)
    }

    private fun cancelSttTimeout() {
        sttTimeoutTimer?.cancel()
        sttTimeoutTimer = null
    }

    private fun cancelAll() {
        cancelTransitionTimer()
        cancelSttTimeout()
    }
}
