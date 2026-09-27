package com.orbiby.margo

import android.app.Activity
import android.content.Context
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.google.android.gms.ads.AdError
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.MobileAds
import com.google.android.gms.ads.rewarded.RewardedAd
import com.google.android.gms.ads.rewarded.RewardedAdLoadCallback

class RewardedAdModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    override fun getName(): String = "RewardedAdModule"

    private var initialized = false

    private fun ensureInit() {
        if (!initialized) {
            MobileAds.initialize(reactApplicationContext) {}
            initialized = true
        }
    }

    @ReactMethod
    fun showRewardedAd(adUnitId: String, promise: Promise) {
        ensureInit()
        val activity: Activity? = reactApplicationContext.currentActivity
        if (activity == null) {
            promise.reject("NO_ACTIVITY", "No activity")
            return
        }

        activity.runOnUiThread {
            val context: Context = activity as Context
            val adRequest = AdRequest.Builder().build()

            RewardedAd.load(context, adUnitId, adRequest,
                object : RewardedAdLoadCallback() {
                    override fun onAdLoaded(ad: RewardedAd) {
                        var rewarded = false
                        ad.fullScreenContentCallback = object : FullScreenContentCallback() {
                            override fun onAdDismissedFullScreenContent() {
                                if (!rewarded) {
                                    promise.reject("DISMISSED", "User dismissed ad")
                                }
                            }
                            override fun onAdFailedToShowFullScreenContent(adError: AdError) {
                                promise.reject("SHOW_FAILED", adError.message)
                            }
                        }
                        ad.show(activity) { rewardItem ->
                            rewarded = true
                            val result = Arguments.createMap()
                            result.putInt("amount", rewardItem.amount)
                            result.putString("type", rewardItem.type)
                            promise.resolve(result)
                        }
                    }
                    override fun onAdFailedToLoad(loadAdError: LoadAdError) {
                        promise.reject("LOAD_FAILED", loadAdError.message)
                    }
                }
            )
        }
    }
}
