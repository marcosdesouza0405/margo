package com.orbiby.margo;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;

import com.facebook.react.bridge.Arguments;
import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;
import com.facebook.react.bridge.WritableMap;
import com.facebook.react.modules.core.DeviceEventManagerModule;

import java.util.ArrayList;
import java.util.Locale;

public class MicrophoneModule extends ReactContextBaseJavaModule {

    private static final String TAG = "MicrophoneModule";
    private static final String CHANNEL_ID = "margo_mic_channel";
    private final ReactApplicationContext reactContext;
    private SpeechRecognizer speechRecognizer;
    private boolean isListening = false;
    private boolean continuousMode = false;
    private String wakeWord = "margo";

    public MicrophoneModule(ReactApplicationContext context) {
        super(context);
        this.reactContext = context;
    }

    @NonNull
    @Override
    public String getName() {
        return "MicrophoneModule";
    }

    private void sendEvent(String eventName, WritableMap params) {
        reactContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter.class)
            .emit(eventName, params);
    }

    @ReactMethod
    public void startListening(String wakeWordParam, boolean continuous, Promise promise) {
        this.wakeWord = wakeWordParam.toLowerCase();
        this.continuousMode = continuous;

        if (getCurrentActivity() == null) {
            promise.reject("ERROR", "Activity não encontrada");
            return;
        }

        getCurrentActivity().runOnUiThread(() -> {
            try {
                if (speechRecognizer != null) {
                    speechRecognizer.destroy();
                }

                speechRecognizer = SpeechRecognizer.createSpeechRecognizer(reactContext);
                speechRecognizer.setRecognitionListener(new RecognitionListener() {
                    @Override
                    public void onReadyForSpeech(Bundle params) {
                        isListening = true;
                        WritableMap map = Arguments.createMap();
                        map.putBoolean("listening", true);
                        sendEvent("onMicrophoneReady", map);
                    }

                    @Override
                    public void onBeginningOfSpeech() {}

                    @Override
                    public void onRmsChanged(float rmsdB) {}

                    @Override
                    public void onBufferReceived(byte[] buffer) {}

                    @Override
                    public void onEndOfSpeech() {}

                    @Override
                    public void onError(int error) {
                        Log.d(TAG, "Erro reconhecimento: " + error);
                        // Reinicia automaticamente em modo contínuo
                        if (continuousMode && isListening) {
                            restartListening();
                        }
                    }

                    @Override
                    public void onResults(Bundle results) {
                        ArrayList<String> matches = results.getStringArrayList(
                            SpeechRecognizer.RESULTS_RECOGNITION);
                        if (matches != null && !matches.isEmpty()) {
                            String text = matches.get(0).toLowerCase();
                            Log.d(TAG, "Reconhecido: " + text);

                            if (continuousMode) {
                                // Modo contínuo: verifica wake word
                                if (text.contains(wakeWord)) {
                                    String command = text.replace(wakeWord, "").trim();
                                    WritableMap map = Arguments.createMap();
                                    map.putString("text", command.isEmpty() ? text : command);
                                    map.putBoolean("wakeWordDetected", true);
                                    sendEvent("onSpeechResult", map);
                                }
                                // Reinicia para continuar ouvindo
                                restartListening();
                            } else {
                                // Modo simples: envia resultado e para
                                WritableMap map = Arguments.createMap();
                                map.putString("text", matches.get(0));
                                map.putBoolean("wakeWordDetected", false);
                                sendEvent("onSpeechResult", map);
                                isListening = false;
                            }
                        }
                    }

                    @Override
                    public void onPartialResults(Bundle partialResults) {}

                    @Override
                    public void onEvent(int eventType, Bundle params) {}
                });

                startRecognition();
                promise.resolve(true);
            } catch (Exception e) {
                promise.reject("ERROR", e.getMessage());
            }
        });
    }

    private void startRecognition() {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR");
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1500);
        speechRecognizer.startListening(intent);
    }

    private void restartListening() {
        if (!isListening) return;
        reactContext.getCurrentActivity().runOnUiThread(() -> {
            try {
                Thread.sleep(300);
                if (isListening && speechRecognizer != null) {
                    startRecognition();
                }
            } catch (Exception e) {
                Log.e(TAG, "Erro restart: " + e.getMessage());
            }
        });
    }

    @ReactMethod
    public void stopListening(Promise promise) {
        isListening = false;
        continuousMode = false;
        if (speechRecognizer != null) {
            speechRecognizer.stopListening();
            speechRecognizer.destroy();
            speechRecognizer = null;
        }
        promise.resolve(true);
    }

    @ReactMethod
    public void isListening(Promise promise) {
        promise.resolve(isListening);
    }

    @ReactMethod
    public void addListener(String eventName) {}

    @ReactMethod
    public void removeListeners(Integer count) {}
}
