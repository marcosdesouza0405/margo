package com.orbiby.margo

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.util.Log
import com.facebook.react.ReactActivity
import com.facebook.react.ReactActivityDelegate
import com.facebook.react.defaults.DefaultNewArchitectureEntryPoint.fabricEnabled
import com.facebook.react.defaults.DefaultReactActivityDelegate
import expo.modules.ReactActivityDelegateWrapper

class MainActivity : ReactActivity() {

  private var screenWakeLock: PowerManager.WakeLock? = null

  companion object {
    private const val TAG = "MainActivity"
  }

  override fun getMainComponentName(): String = "main"

  override fun createReactActivityDelegate(): ReactActivityDelegate {
    return ReactActivityDelegateWrapper(
      this,
      BuildConfig.IS_NEW_ARCHITECTURE_ENABLED,
      object : DefaultReactActivityDelegate(this, mainComponentName, fabricEnabled) {}
    )
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    setTheme(R.style.AppTheme)
    super.onCreate(null)
    // Permite abrir sobre tela bloqueada
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
      setShowWhenLocked(true)
      setTurnScreenOn(true)
    } else {
      window.addFlags(
        android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
        android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
      )
    }
    Log.d(TAG, "onCreate")
    // Mantem tela acesa enquanto app estiver aberto
    val pm = getSystemService(POWER_SERVICE) as PowerManager
    screenWakeLock = pm.newWakeLock(
      PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
      "Margo::ScreenLock"
    )
    screenWakeLock?.acquire(30 * 60 * 1000L) // 30 minutos max
    handleWakeWordIntent(intent)
  }

  override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    setIntent(intent)
    Log.d(TAG, "onNewIntent: ${intent.action}")
    handleWakeWordIntent(intent)
  }

  private fun handleWakeWordIntent(intent: Intent?) {
    val isWakeWord = intent?.getBooleanExtra("WAKE_WORD_DETECTED", false) == true
    if (isWakeWord) {
      Log.d(TAG, "Wake word detectada! Salvando no SharedPreferences...")
      val prefs = getSharedPreferences("wakeword", MODE_PRIVATE)
      prefs.edit()
        .putBoolean("detectada", true)
        .putString("modelo", intent?.getStringExtra("WAKE_WORD_MODEL") ?: "margo")
        .putFloat("score", intent?.getFloatExtra("WAKE_WORD_SCORE", 0f) ?: 0f)
        .putLong("timestamp", System.currentTimeMillis())
        .apply()
      Log.d(TAG, "Flag salva. JS vai detectar via checkWakeWordPendente()")
    }
  }

  override fun onDestroy() {
    super.onDestroy()
    screenWakeLock?.release()
    screenWakeLock = null
  }

  override fun invokeDefaultOnBackPressed() {
    if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.R) {
      if (!moveTaskToBack(false)) {
        super.invokeDefaultOnBackPressed()
      }
      return
    }
    super.invokeDefaultOnBackPressed()
  }
}
