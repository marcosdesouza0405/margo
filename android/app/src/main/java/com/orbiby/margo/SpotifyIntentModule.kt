package com.orbiby.margo

import android.app.SearchManager
import android.content.Intent
import android.net.Uri
import android.provider.MediaStore
import com.facebook.react.bridge.*

class SpotifyIntentModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "SpotifyIntentModule"

    /**
     * Tenta tocar música no Spotify via MEDIA_PLAY_FROM_SEARCH.
     * Se falhar, abre busca no Spotify via deep link.
     * Zero API, zero OAuth — funciona pra qualquer usuário com Spotify instalado.
     */
    @ReactMethod
    fun play(query: String, promise: Promise) {
        try {
            val activity = reactApplicationContext.currentActivity
            if (activity == null) {
                promise.resolve("no_activity")
                return
            }

            // Verifica se Spotify está instalado
            val pm = activity.packageManager
            try {
                pm.getPackageInfo("com.spotify.music", 0)
            } catch (e: Exception) {
                promise.resolve("not_installed")
                return
            }

            // Caminho 1: MEDIA_PLAY_FROM_SEARCH (busca + autoplay)
            try {
                val intent = Intent(MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH).apply {
                    putExtra(MediaStore.EXTRA_MEDIA_FOCUS, "vnd.android.cursor.item/*")
                    putExtra(SearchManager.QUERY, query)
                    setPackage("com.spotify.music")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                if (intent.resolveActivity(pm) != null) {
                    activity.startActivity(intent)
                    promise.resolve("play_from_search")
                    return
                }
            } catch (e: Exception) {
                // Falhou, tenta deep link
            }

            // Caminho 2: Deep link spotify:search (fallback)
            try {
                val searchUri = "spotify:search:${Uri.encode(query)}"
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(searchUri)).apply {
                    setPackage("com.spotify.music")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                activity.startActivity(intent)
                promise.resolve("deep_link")
                return
            } catch (e: Exception) {
                // Último fallback: URL web
            }

            // Caminho 3: Abre no browser (último recurso)
            try {
                val webUrl = "https://open.spotify.com/search/${Uri.encode(query)}"
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(webUrl)).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                activity.startActivity(intent)
                promise.resolve("web_fallback")
            } catch (e: Exception) {
                promise.resolve("failed")
            }

        } catch (e: Exception) {
            promise.resolve("error")
        }
    }

    /**
     * Verifica se o Spotify está instalado no dispositivo.
     */
    @ReactMethod
    fun isInstalled(promise: Promise) {
        try {
            val pm = reactContext.packageManager
            pm.getPackageInfo("com.spotify.music", 0)
            promise.resolve(true)
        } catch (e: Exception) {
            promise.resolve(false)
        }
    }
}
