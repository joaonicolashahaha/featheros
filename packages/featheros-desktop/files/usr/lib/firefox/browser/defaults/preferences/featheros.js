// FeatherOS defaults for Firefox on a Core 2 Duo / 3 GB RAM / HDD laptop.
// These are default values: anything changed in about:config wins.

// RAM: 2 web-content processes instead of 8 (site isolation stays on).
pref("dom.ipc.processCount", 2);
// No spare pre-launched content process (~20-40 MB).
pref("dom.ipc.processPrelaunch.enabled", false);
// The GMA 4500M is too old for Firefox's GPU renderer; render in software
// from the start. WebGL off: probing it loads Mesa/LLVM into the main process
// (+130 MB measured with claude.ai open). Re-enable in about:config
// (webgl.disabled = false) if a site needs 3D.
pref("gfx.webrender.software", true);
pref("webgl.disabled", true);
// No speech synthesis (its missing-library notice shows on every start).
pref("media.webspeech.synth.enabled", false);
// Unload background tabs when memory runs low instead of swapping.
pref("browser.tabs.unloadOnLowMemory", true);
// No on-device AI models (hundreds of MB of RAM when used).
pref("browser.ml.enable", false);
pref("browser.ml.chat.enabled", false);

// Video: the GMA 4500M has no hardware decoder for H.264/VP9/AV1, and the
// CPU decodes H.264 far more cheaply than VP9/AV1. Disabling WebM/AV1 in MSE
// makes YouTube serve H.264, which is what the h264ify extension does, but
// without running an extension.
pref("media.mediasource.webm.enabled", false);
pref("media.av1.enabled", false);
pref("media.ffmpeg.vaapi.enabled", false);

// HDD: save the session every 60 s instead of 15 s; smaller disk cache.
pref("browser.sessionstore.interval", 60000);
pref("browser.cache.disk.capacity", 262144);

// No speculative network/CPU work in the background.
pref("network.prefetch-next", false);
pref("network.predictor.enabled", false);
pref("browser.urlbar.speculativeConnect.enabled", false);
pref("toolkit.cosmeticAnimations.enabled", false);

// Portuguese UI (firefox-i18n-pt-br), English as fallback.
pref("intl.locale.requested", "pt-BR,en-US");
