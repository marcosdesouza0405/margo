package com.orbiby.margo

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.util.Log

class WakeWordLaunchActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.d("WakeWordLaunch", "Abrindo MainActivity via ponte...")
        // Acorda a tela antes de abrir
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            window.addFlags(
                android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            )
        }
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
            putExtra("WAKE_WORD_DETECTED", true)
            putExtra("WAKE_WORD_MODEL", this@WakeWordLaunchActivity.intent?.getStringExtra("WAKE_WORD_MODEL") ?: "margo")
        }
        startActivity(intent)
        finish()
    }
}
