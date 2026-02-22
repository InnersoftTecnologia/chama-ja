const EDGE_BASE = (window.EDGE_BASE || `${window.location.protocol}//${window.location.hostname}:7071`).replace(/\/$/, "");
const EDGE_TOKEN = window.EDGE_TOKEN || "dev-edge-token";

const state = {
  playlist: [],
  filteredPlaylist: [], // Playlist filtrada baseada no tipo selecionado
  announcements: [],
  current: null,
  ytPlayer: null,
  ytIndex: 0,
  ytMounted: false,
  isPlayingCallAudio: false,
  overlayTimer: null,
  seenCallIds: new Set(), // Track calls that existed on page load to avoid showing overlay
  audioEnabled: true, // TV audio setting from tenant config
  callSoundFile: "notification-1.mp3", // Som da chamada (arquivo em sounds/), configurável no admin
  ttsEnabled: false, // Anúncio de voz TTS após a campainha
  ttsVoice: "pf_dora", // Voz do TTS (pf_dora, pm_alex, pm_santa)
  ttsSpeed: 0.85, // Velocidade da fala (0.25–4.0)
  ttsVolume: 1.0, // Volume multiplicador (0.1–4.0)
  slideTimer: null, // Timer for slide transitions
  mediaFilter: null, // null = "all", "videos" ou "slides" - carregado do backend
  lastTenant: null, // Último tenant do /tv/state (para aplicar play/pause no onReady do player)
};

let ytApiPromise = null;

function ensureYouTubeApiLoaded() {
  if (window.YT && window.YT.Player) {
    console.log("YouTube API already loaded");
    return Promise.resolve();
  }
  if (ytApiPromise) {
    console.log("YouTube API loading in progress");
    return ytApiPromise;
  }

  console.log("Starting YouTube API load");
  ytApiPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[src*="youtube.com/iframe_api"]');
    if (existing) {
      console.log("YouTube API script tag already exists");
      // If script exists, wait for callback
    } else {
      console.log("Creating YouTube API script tag");
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      s.async = true;
      s.onerror = () => {
        console.error("Failed to load YouTube IFrame API script");
        reject(new Error("Failed to load YouTube IFrame API"));
      };
      document.head.appendChild(s);
      console.log("YouTube API script tag added to document");
    }

    // YouTube calls this when ready
    window.onYouTubeIframeAPIReady = () => {
      console.log("YouTube IFrame API Ready callback triggered");
      resolve();
    };
    // Safety timeout
    setTimeout(() => {
      if (window.YT && window.YT.Player) {
        console.log("YouTube API loaded (via timeout check)");
        resolve();
      } else {
        console.error("YouTube API failed to load within 5 seconds");
        reject(new Error("YouTube API timeout"));
      }
    }, 5000);
  });

  return ytApiPromise;
}

function showEnableAudioButton() {
  const btn = document.getElementById("enableAudioBtn");
  if (!btn) {
    console.error("enableAudioBtn not found in DOM");
    return;
  }
  console.log("Showing audio enable button");
  btn.classList.remove("hidden");
}

function hideEnableAudioButton() {
  const btn = document.getElementById("enableAudioBtn");
  if (!btn) {
    console.error("enableAudioBtn not found in DOM");
    return;
  }
  console.log("Hiding audio enable button");
  btn.classList.add("hidden");
}

function tryEnableYouTubeAudio() {
  const p = state.ytPlayer;
  if (!p) {
    console.error("tryEnableYouTubeAudio: No player available");
    return;
  }
  try {
    console.log("User clicked to enable audio - unmuting and resuming playback");
    p.unMute();
    p.setVolume(60);

    // Resume playback if paused
    const playerState = p.getPlayerState();
    console.log("Current player state:", playerState); // 1=playing, 2=paused
    if (playerState !== 1) { // If not playing
      console.log("Video was paused, resuming playback");
      p.playVideo();
    }

    // Verify after a moment
    setTimeout(() => {
      const isMuted = p.isMuted();
      const state = p.getPlayerState();
      console.log("After unmute - Muted:", isMuted, "State:", state);
      if (!isMuted && state === 1) {
        console.log("✓ Audio enabled and video playing successfully!");
      }
    }, 500);
  } catch (err) {
    console.error("Error enabling audio:", err);
  }
}

function authHeaders() {
  return { Authorization: `Bearer ${EDGE_TOKEN}` };
}

function fmtDateTime(d) {
  const pad = (n) => `${n}`.padStart(2, "0");
  return {
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
    date: d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" }),
  };
}

function tickClock() {
  const { time, date } = fmtDateTime(new Date());
  document.getElementById("clock").textContent = time;
  document.getElementById("date").textContent = date.toUpperCase();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setCurrent(call) {
  state.current = call;
  // Compatibility: if single call passed, render it in the container
  if (call) {
    renderCurrentCalls([call]);
  } else {
    renderCurrentCalls([]);
  }
}

function renderCurrentCalls(calls) {
  const container = document.getElementById("currentCallsContainer");
  if (!container) return;

  container.innerHTML = "";

  if (!calls || calls.length === 0) {
    const html = `
      <div class="flex-1 flex flex-col items-center justify-center">
        <h2 class="text-6xl font-black leading-none tracking-tighter text-white/30">---</h2>
        <div class="px-6 py-3 bg-white/10 text-white/50 rounded-xl font-bold text-xl uppercase tracking-tighter mt-4">
          AGUARDANDO
        </div>
      </div>
    `;
    container.insertAdjacentHTML("beforeend", html);
    return;
  }

  for (const call of calls) {
    // Only show truly "in service" tickets here. Legacy calls don't have the correct lifecycle.
    if (call.status && call.status !== "in_service") {
      continue;
    }
    const isPrefer = call.priority === "preferential";
    const ticketColor = isPrefer ? "text-accent" : "text-white";
    const op = (call.operator_name || "").trim();
    const startedAt = call.service_started_at ? new Date(call.service_started_at) : null;
    const startedTxt = startedAt ? startedAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
    const html = `
      <div class="flex flex-col items-center justify-center p-4 bg-white/5 rounded-2xl border border-white/10">
        <h2 class="text-5xl sm:text-6xl font-black leading-none tracking-tighter ${ticketColor} drop-shadow-[0_0_18px_rgba(0,212,255,0.25)] whitespace-nowrap">
          ${escapeHtml(call.ticket_code || "---")}
        </h2>
        <div class="px-6 py-3 bg-primary text-background-dark rounded-xl font-black text-xl uppercase tracking-tighter shadow-lg shadow-primary/20 mt-3">
          ${escapeHtml((call.counter_name || "GUICHÊ --").toUpperCase())}
        </div>
        <span class="text-xs font-medium text-white/50 mt-2">${escapeHtml(call.service_name || "")}</span>
        ${op || startedTxt ? `<span class="text-[10px] font-bold text-white/40 mt-2 uppercase tracking-widest">${escapeHtml(op)}${op && startedTxt ? " • " : ""}${escapeHtml(startedTxt ? `Início ${startedTxt}` : "")}</span>` : ""}
      </div>
    `;
    container.insertAdjacentHTML("beforeend", html);
  }
}

// ─── Painel direito: Fila de Espera ↔ Histórico ─────────────────────────────
let panelMode = "queue"; // "queue" | "history"
let panelToggleTimer = null;
let lastWaitingQueue = [];
let lastHistory = [];

function renderPanelHeader(mode) {
  const bar = document.getElementById("panelHeaderBar");
  if (!bar) return;
  if (mode === "queue") {
    bar.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span class="material-symbols-outlined text-primary text-3xl">group</span>
          <h4 class="text-xl font-bold tracking-tight">Fila de Espera</h4>
        </div>
        <span class="text-xs font-black uppercase text-primary tracking-[0.15em] bg-primary/10 px-3 py-1.5 rounded-lg border border-primary/20 whitespace-nowrap">AGUARDANDO</span>
      </div>`;
  } else {
    bar.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span class="material-symbols-outlined text-accent text-3xl">history</span>
          <h4 class="text-xl font-bold tracking-tight">Últimas Senhas</h4>
        </div>
        <span class="text-xs font-black uppercase text-accent tracking-[0.15em] bg-accent/10 px-3 py-1.5 rounded-lg border border-accent/20 whitespace-nowrap">HISTÓRICO</span>
      </div>`;
  }
}

function renderQueueItem(item, pos) {
  const isPrefer = item.priority === "preferential";
  const ticketColor = isPrefer ? "text-accent" : "text-white";
  const issuedAt = item.issued_at ? new Date(item.issued_at) : null;
  const timeTxt = issuedAt ? issuedAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
  return `
    <div class="flex items-center justify-between px-3 py-2 bg-white/5 rounded-xl border border-white/5">
      <div class="flex items-center gap-2">
        <span style="color:rgba(255,255,255,0.18);font-size:10px;font-weight:900;width:14px;text-align:center">${pos}</span>
        <div class="flex flex-col">
          <span class="text-xl font-black ${ticketColor} tracking-tighter">${escapeHtml(item.ticket_code || "")}</span>
          <span class="text-[9px] font-bold uppercase" style="color:rgba(255,255,255,0.35)">${escapeHtml(item.service_name || "")}</span>
        </div>
      </div>
      <span class="text-[9px] font-bold" style="color:rgba(255,255,255,0.22)">${escapeHtml(timeTxt)}</span>
    </div>`;
}

function renderHistoryItem(item) {
  const isPrefer = item.priority === "preferential";
  const ticketColor = isPrefer ? "text-accent" : "text-white";
  const opacity = isPrefer ? "" : "opacity:0.8";
  const endedAt = item.completed_at ? new Date(item.completed_at) : null;
  const endedTxt = endedAt ? endedAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
  const startedAt = item.service_started_at ? new Date(item.service_started_at) : null;
  let durTxt = "";
  if (startedAt && endedAt && endedAt >= startedAt) {
    const secs = Math.floor((endedAt.getTime() - startedAt.getTime()) / 1000);
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    durTxt = `${mins}m${rem.toString().padStart(2, "0")}s`;
  }
  return `
    <div class="flex items-center justify-between px-3 py-2 bg-white/5 rounded-xl border border-white/5" style="${opacity}">
      <div class="flex flex-col">
        <span class="text-xl font-black ${ticketColor} tracking-tighter">${escapeHtml(item.ticket_code || "")}</span>
        <span class="text-[9px] font-bold uppercase" style="color:rgba(255,255,255,0.4)">${escapeHtml((item.counter_name || "").toUpperCase())}</span>
        ${(endedTxt || durTxt) ? `<span class="text-[9px] font-bold uppercase" style="color:rgba(255,255,255,0.25)">${escapeHtml(endedTxt ? `Fim ${endedTxt}` : "")}${endedTxt && durTxt ? " • " : ""}${escapeHtml(durTxt ? `Dur. ${durTxt}` : "")}</span>` : ""}
      </div>
      <span class="text-[9px] font-bold text-right" style="color:rgba(255,255,255,0.2);max-width:60px;word-break:break-word">${escapeHtml(item.service_name || "")}</span>
    </div>`;
}

function renderPanel() {
  renderPanelHeader(panelMode);

  const normalEl = document.getElementById("panel-normal");
  const preferEl = document.getElementById("panel-preferential");
  if (!normalEl || !preferEl) return;

  const items = panelMode === "queue" ? lastWaitingQueue : lastHistory;
  const renderFn = panelMode === "queue" ? renderQueueItem : renderHistoryItem;

  const normal = items.filter((i) => i.priority !== "preferential");
  const prefer = items.filter((i) => i.priority === "preferential");

  const emptyNormal = `<div style="color:rgba(255,255,255,0.18);font-size:11px;text-align:center;padding:14px 0">Nenhuma senha</div>`;
  const emptyPrefer = `<div style="color:rgba(255,215,0,0.25);font-size:11px;text-align:center;padding:14px 0">Nenhuma senha</div>`;

  normalEl.innerHTML = normal.length ? normal.map((item, i) => renderFn(item, i + 1)).join("") : emptyNormal;
  preferEl.innerHTML = prefer.length ? prefer.map((item, i) => renderFn(item, i + 1)).join("") : emptyPrefer;

  // Animação de fade ao trocar conteúdo
  [normalEl, preferEl].forEach((el) => {
    el.classList.remove("panel-fade-in");
    void el.offsetWidth; // força reflow
    el.classList.add("panel-fade-in");
  });
}

function renderHistory(history) {
  lastHistory = (history || []).filter(
    (item) => !item.status || ["completed", "no_show", "cancelled"].includes(item.status)
  );
  renderPanel();
}

function renderWaitingQueue(queue) {
  lastWaitingQueue = queue || [];
  renderPanel();
}

function startPanelToggle() {
  if (panelToggleTimer) clearInterval(panelToggleTimer);
  panelToggleTimer = setInterval(() => {
    panelMode = panelMode === "queue" ? "history" : "queue";
    renderPanel();
  }, 9000); // alterna a cada 9 segundos
}
// ─────────────────────────────────────────────────────────────────────────────

let tickerTimer = null;
let tickerIndex = 0;
let tickerMessagesSig = "";

function tickerSignature(announcements) {
  return (announcements || [])
    .map((a) => `${a.id || ""}:${a.position || ""}:${a.message || ""}`)
    .join("|");
}

function pickRandomTickerAnim() {
  const classes = ["ticker-anim-fade", "ticker-anim-slide-left", "ticker-anim-slide-right", "ticker-anim-pop"];
  return classes[Math.floor(Math.random() * classes.length)];
}

function renderTicker(announcements) {
  const root = document.getElementById("ticker");
  if (!root) return;

  const msgs = (announcements || [])
    .map((a) => String(a.message || "").trim())
    .filter((m) => m.length > 0);

  const sig = tickerSignature(announcements);
  if (sig === tickerMessagesSig) return;
  tickerMessagesSig = sig;
  tickerIndex = 0;

  if (tickerTimer) {
    clearInterval(tickerTimer);
    tickerTimer = null;
  }

  if (!msgs.length) {
    root.innerHTML = "";
    return;
  }

  const show = () => {
    const msg = msgs[tickerIndex % msgs.length];
    tickerIndex++;
    const anim = pickRandomTickerAnim();
    root.innerHTML = `
      <div class="ticker-text ${anim}">
        <span class="material-symbols-outlined text-primary text-3xl" style="vertical-align: middle;">info</span>
        <span class="text-2xl font-bold text-white" style="margin-left: 12px;">${escapeHtml(msg)}</span>
      </div>
    `;
  };

  show();
  tickerTimer = setInterval(show, 8000);
}

async function fetchState() {
  const res = await fetch(`${EDGE_BASE}/tv/state`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`state ${res.status}`);
  return await res.json();
}

function applyTenantBranding(tenant) {
  if (!tenant) return;
  state.lastTenant = tenant;
  const name = (tenant.nome_fantasia || tenant.nome_razao_social || "Chamador").toString();
  const nameEl = document.getElementById("tenantName");
  if (nameEl) nameEl.textContent = name;

  const logoEl = document.getElementById("tenantLogo");
  if (logoEl && tenant.logo_base64 && typeof tenant.logo_base64 === "string") {
    const v = tenant.logo_base64.trim();
    // If it already includes data: prefix, keep it. Otherwise assume SVG base64.
    if (v.startsWith("data:")) {
      logoEl.src = v;
    } else {
      // Backward compatibility (older seeds stored raw base64)
      logoEl.src = `data:image/svg+xml;base64,${v}`;
    }
  }

  // Apply TV theme
  applyTVTheme(tenant.tv_theme);
  // Store audio setting
  state.audioEnabled = tenant.tv_audio_enabled !== false && tenant.tv_audio_enabled !== 0;
  // Som da chamada (arquivo configurável no admin)
  state.callSoundFile = (tenant.tv_call_sound || "notification-1.mp3").trim() || "notification-1.mp3";
  // TTS: anúncio de voz após a campainha
  state.ttsEnabled = tenant.tts_enabled === true || tenant.tts_enabled === 1;
  state.ttsVoice = (tenant.tts_voice || "pf_dora").trim() || "pf_dora";
  state.ttsSpeed = parseFloat(tenant.tts_speed) || 0.85;
  state.ttsVolume = parseFloat(tenant.tts_volume) || 1.0;
  // Apply video controls
  applyVideoControls(tenant);
  
  // Apply playlist filter from backend
  // Convert "all" → null (show all), "videos" → "videos", "slides" → "slides"
  const backendFilter = tenant.admin_playlist_filter || "all";
  const newFilter = backendFilter === "all" ? null : backendFilter;
  
  // Only update if filter changed to avoid unnecessary reinitialization
  if (state.mediaFilter !== newFilter) {
    state.mediaFilter = newFilter;
    // Reinitialize playlist with new filter if playlist is already loaded
    if (state.playlist && state.playlist.length > 0) {
      initPlaylist(state.playlist);
    }
  }
}

function applyTVTheme(theme) {
  if (theme === "light") {
    document.body.classList.add("theme-light");
  } else {
    document.body.classList.remove("theme-light");
  }
}

function applyVideoControls(tenant) {
  const p = state.ytPlayer;
  if (!p || typeof p.isMuted !== "function") return;

  try {
    // Video mute/unmute
    const shouldMute = tenant.tv_video_muted !== false && tenant.tv_video_muted !== 0;
    const isMuted = p.isMuted();
    if (shouldMute && !isMuted) {
      p.mute();
      console.log("Remote control: muting video");
    } else if (!shouldMute && isMuted) {
      p.unMute();
      p.setVolume(60);
      hideEnableAudioButton();
      console.log("Remote control: unmuting video");
    }

    // Video play/pause — YT: 1=playing, 2=paused, 3=buffering, 5=cued
    const shouldPause = tenant.tv_video_paused === true || tenant.tv_video_paused === 1;
    const playerState = p.getPlayerState();
    if (shouldPause && (playerState === 1 || playerState === 3)) {
      p.pauseVideo();
      console.log("Remote control: pausing video");
    } else if (!shouldPause && playerState === 2) {
      p.playVideo();
      console.log("Remote control: resuming video");
    }
  } catch (e) {
    console.warn("Error applying video controls:", e);
  }
}

function openOverlay(call) {
  const overlay = document.getElementById("overlay");
  overlay.classList.add("is-open");
  document.getElementById("overlayTicket").textContent = call.ticket_code || "---";
  document.getElementById("overlayCounter").textContent = (call.counter_name || "Guichê --").toUpperCase();
  document.getElementById("overlayService").textContent = (call.service_name || "Atendimento").toUpperCase();

  if (state.overlayTimer) clearTimeout(state.overlayTimer);
  state.overlayTimer = setTimeout(() => {
    overlay.classList.remove("is-open");
  }, 7000);
}

async function playCallAudio(call) {
  if (state.audioEnabled === false) {
    return;
  }
  state.isPlayingCallAudio = true;
  try {
    pauseYouTubeForCall();
    const soundFile = state.callSoundFile || "notification-1.mp3";
    const soundUrl = `${EDGE_BASE}/api/sounds/${encodeURIComponent(soundFile)}`;
    try {
      const audio = new Audio(soundUrl);
      await new Promise((resolve, reject) => {
        audio.onended = () => resolve();
        audio.onerror = () => reject(audio.error);
        audio.play().catch(reject);
      });
    } catch (e) {
      // Fallback: beep com oscillator (offline ou arquivo indisponível)
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = 880;
      g.gain.value = 0.08;
      o.connect(g);
      g.connect(ctx.destination);
      o.start();
      await new Promise((r) => setTimeout(r, 800));
      o.frequency.value = 660;
      await new Promise((r) => setTimeout(r, 500));
      o.stop();
      await ctx.close();
    }
    // Após a campainha, anunciar em voz TTS (se habilitado)
    if (state.ttsEnabled && call?.ticket_code && call?.counter_name) {
      try {
        const ttsUrl = `${EDGE_BASE}/api/tts/call?` +
          `ticket_code=${encodeURIComponent(call.ticket_code)}` +
          `&counter_name=${encodeURIComponent(call.counter_name)}` +
          `&voice=${encodeURIComponent(state.ttsVoice || "pf_dora")}` +
          `&speed=${state.ttsSpeed || 0.85}` +
          `&volume=${state.ttsVolume || 1.0}`;
        const ttsAudio = new Audio(ttsUrl);
        await new Promise((resolve) => {
          ttsAudio.onended = resolve;
          ttsAudio.onerror = resolve; // falha silenciosa — não quebra o fluxo
          ttsAudio.play().catch(resolve);
        });
      } catch (_) {
        // Falha silenciosa
      }
    }
  } catch (e) {
    // ignore
  } finally {
    state.isPlayingCallAudio = false;
    resumeYouTubeAfterCall();
  }
}

function pauseYouTubeForCall() {
  const p = state.ytPlayer;
  if (!p) return;
  try {
    p.mute();
    p.pauseVideo();
  } catch {}
}

function resumeYouTubeAfterCall() {
  const p = state.ytPlayer;
  if (!p) return;
  try {
    p.playVideo();
    // Try to restore sound for kiosk use-cases; if browser blocks, it stays muted.
    setTimeout(() => {
      try {
        p.unMute();
        p.setVolume(60);
      } catch {}
    }, 400);
  } catch {}
}

function onCallCreated(call) {
  setCurrent(call);
  openOverlay(call);
  playCallAudio(call);
}

function normalizeCallFromTicket(call) {
  // Keep same shape as legacy call: {id, ticket_code, service_name, priority, counter_name, called_at, ...}
  if (!call) return null;
  return {
    id: call.id,
    ticket_code: call.ticket_code,
    service_name: call.service_name,
    priority: call.priority,
    counter_name: call.counter_name,
    operator_name: call.operator_name,
    called_at: call.called_at,
  };
}

function connectSSE() {
  const url = `${EDGE_BASE}/tv/events`;
  const es = new EventSource(url, { withCredentials: false });

  es.addEventListener("call.created", (ev) => {
    try {
      const payload = JSON.parse(ev.data);
      const call = payload?.call;
      if (call) onCallCreated(call);
    } catch {}
  });

  es.addEventListener("ticket.called", (ev) => {
    try {
      const payload = JSON.parse(ev.data);
      const call = normalizeCallFromTicket(payload?.call);
      if (call) onCallCreated(call);
    } catch {}
  });

  es.addEventListener("edge.error", (ev) => {
    console.warn("edge.error", ev.data);
  });

  es.onerror = () => {
    // EventSource will auto-reconnect; we keep it simple.
  };

  // NOTE: EventSource cannot set Authorization headers.
  // MVP workaround: Edge token is expected to be relaxed for /tv/events, OR use query token.
  // We'll append token as query param for now.
}

function connectSSEWithToken() {
  // Because EventSource can't send headers, we pass token as query param in MVP.
  const url = `${EDGE_BASE}/tv/events?token=${encodeURIComponent(EDGE_TOKEN)}`;
  const es = new EventSource(url);

  es.addEventListener("call.created", (ev) => {
    try {
      const payload = JSON.parse(ev.data);
      const call = payload?.call;
      if (call) {
        // Only trigger overlay/audio for truly NEW calls (not already in history on page load)
        if (state.seenCallIds.has(call.id)) {
          console.log("Call already seen on page load, skipping overlay:", call.id);
          setCurrent(call); // Update display only
        } else {
          console.log("NEW call detected, showing overlay:", call.id);
          onCallCreated(call); // Full experience: overlay + audio
          state.seenCallIds.add(call.id); // Track it
        }
      }
    } catch {}
  });

  es.addEventListener("ticket.called", (ev) => {
    try {
      const payload = JSON.parse(ev.data);
      const call = normalizeCallFromTicket(payload?.call);
      if (call) {
        if (state.seenCallIds.has(call.id)) {
          console.log("Ticket call already seen on page load, skipping overlay:", call.id);
          setCurrent(call);
        } else {
          console.log("NEW ticket call detected, showing overlay:", call.id);
          onCallCreated(call);
          state.seenCallIds.add(call.id);
        }
      }
    } catch {}
  });

  es.addEventListener("edge.error", (ev) => console.warn("edge.error", ev.data));
  es.onerror = () => {};
}

function playlistSignature(pl) {
  return (pl || [])
    .map((x) => `${x.media_type || "youtube"}:${x.youtube_id || x.image_url || ""}:${x.position || ""}:${x.enabled || ""}`)
    .join("|");
}

function filterPlaylist(playlist, filterType) {
  if (!playlist || !playlist.length) return [];
  // filterType === null means "all" (show everything)
  if (filterType === null || filterType === undefined) {
    return playlist;
  }
  if (filterType === "videos") {
    return playlist.filter(item => item.media_type !== "slide");
  } else if (filterType === "slides") {
    return playlist.filter(item => item.media_type === "slide");
  }
  return playlist;
}

function initPlaylist(playlist) {
  state.playlist = playlist || [];
  console.log("initPlaylist called with playlist:", state.playlist);

  // Filter playlist based on current filter
  state.filteredPlaylist = filterPlaylist(state.playlist, state.mediaFilter);
  console.log("Filtered playlist:", state.filteredPlaylist);

  if (!state.filteredPlaylist.length) {
    const ph = document.getElementById("videoPlaceholder");
    if (ph) {
      if (state.mediaFilter === "videos") {
        ph.textContent = "Sem vídeos configurados.";
      } else {
        ph.textContent = "Sem slides configurados.";
      }
    }
    console.warn("No items in filtered playlist");
    return;
  }

  // Clear any existing slide timer
  if (state.slideTimer) {
    clearTimeout(state.slideTimer);
    state.slideTimer = null;
  }

  state.ytIndex = 0; // Reset index when filtering
  const first = state.filteredPlaylist[0];
  console.log("First item to play:", first);

  const container = document.getElementById("youtubeContainer");
  if (!container) {
    console.error("youtubeContainer not found");
    return;
  }

  console.log("youtubeContainer found:", container);

  // Don't nuke the whole container (keeps button/placeholder stable)
  let ytEl = document.getElementById("ytPlayer");
  if (ytEl) {
    console.log("Removing existing ytPlayer element");
    ytEl.remove();
  }

  console.log("Creating new ytPlayer element");
  ytEl = document.createElement("div");
  ytEl.id = "ytPlayer";
  ytEl.className = "w-full h-full";
  ytEl.style.position = "absolute";
  ytEl.style.inset = "0";
  ytEl.style.zIndex = "2";
  container.appendChild(ytEl);

  console.log("ytPlayer element created and appended:", ytEl);
  console.log("Verifying ytPlayer in DOM:", document.getElementById("ytPlayer"));

  // Ensure placeholder/button exist
  if (!document.getElementById("videoPlaceholder")) {
    const ph = document.createElement("div");
    ph.id = "videoPlaceholder";
    ph.className = "h-full w-full flex items-center justify-center text-white/30 text-sm";
    ph.textContent = "Carregando vídeos…";
    container.appendChild(ph);
  }
  if (!document.getElementById("enableAudioBtn")) {
    const btn = document.createElement("button");
    btn.id = "enableAudioBtn";
    btn.type = "button";
    btn.className =
      "hidden absolute bottom-6 right-6 px-4 py-3 rounded-xl bg-primary/90 backdrop-blur-sm border border-primary shadow-lg text-background-dark font-bold text-sm uppercase tracking-wide hover:bg-primary hover:scale-105 transition-all z-50 flex items-center gap-2";
    btn.setAttribute("aria-label", "Ativar áudio do vídeo");
    btn.setAttribute("title", "Clique para ativar o áudio");
    btn.innerHTML = '<span class="material-symbols-outlined text-xl">volume_up</span>Ativar Áudio';
    container.appendChild(btn);
  }
  hideEnableAudioButton();
  state.ytMounted = true;

  // Check if first item is a slide or video
  if (first.media_type === "slide") {
    showSlide(first);
    return;
  }

  // YouTube video
  console.log("Creating YT.Player with video ID:", first.youtube_id);
  console.log("Target element 'ytPlayer' exists:", !!document.getElementById("ytPlayer"));

  try {
    state.ytPlayer = new YT.Player("ytPlayer", {
      width: "100%",
      height: "100%",
      videoId: first.youtube_id,
      playerVars: {
        autoplay: 1,
        controls: 0,
        modestbranding: 1,
        rel: 0,
        playsinline: 1,
        enablejsapi: 1,
        // Start muted to satisfy autoplay policies
        mute: 1,
      },
      events: {
      onReady: (e) => {
        try {
          // Remove placeholder once the player is ready
          const ph = document.getElementById("videoPlaceholder");
          if (ph) {
            console.log("Removing video placeholder");
            ph.remove();
          } else {
            console.log("Video placeholder not found (already removed)");
          }

          console.log("YouTube player ready, starting playback");

          // Start playing video (muted to comply with autoplay policies)
          e.target.playVideo();

          // Set volume for when user enables audio
          e.target.setVolume(60);

          // Apply remote play/pause from tenant (so "Pausar" in admin takes effect immediately)
          if (state.lastTenant) {
            applyVideoControls(state.lastTenant);
          }

          // Show button immediately - user MUST interact to enable audio
          console.log("Video is playing muted. User must click button to enable audio.");
          showEnableAudioButton();

        } catch (err) {
          console.error("Error in onReady:", err);
        }
      },
      onStateChange: (e) => {
        const states = {
          "-1": "unstarted",
          0: "ended",
          1: "playing",
          2: "paused",
          3: "buffering",
          5: "video cued",
        };
        const stateName = states[e.data] || `unknown(${e.data})`;
        console.log("YouTube player state changed:", stateName);

        // 0 = ended
        if (e.data === 0) {
          console.log("Video ended, loading next item");
          nextItem();
        }
        // 1 = playing
        if (e.data === 1) {
          console.log("✓ Video is now PLAYING");
        }
      },
      onError: (e) => {
        const errorCodes = {
          2: "ID de vídeo inválido",
          5: "Erro no player HTML5",
          100: "Vídeo não encontrado ou privado",
          101: "Vídeo não permite reprodução embutida",
          150: "Vídeo não permite reprodução embutida",
        };
        const errorMsg = errorCodes[e.data] || `Erro desconhecido (${e.data})`;
        console.error("YouTube player error:", errorMsg, "Code:", e.data);

        const ph = document.getElementById("videoPlaceholder");
        if (ph) {
          const vid = state.playlist?.[state.ytIndex]?.youtube_id || "";
          const watchUrl = vid ? `https://www.youtube.com/watch?v=${encodeURIComponent(vid)}` : "https://www.youtube.com/";
          ph.innerHTML = `
            <div class="text-center max-w-md">
              <div class="text-white/60 text-sm mb-3">Falha ao reproduzir vídeo no embed (YouTube).</div>
              <div class="text-red-400 text-xs mb-3">${errorMsg}</div>
              <a class="inline-block px-4 py-2 rounded-xl bg-white/10 border border-white/20 backdrop-blur text-white font-bold" href="${watchUrl}" target="_blank" rel="noreferrer">
                Assistir no YouTube
              </a>
            </div>
          `;
        }
        showEnableAudioButton();
      },
    },
  });

  console.log("YT.Player instance created successfully:", state.ytPlayer);
  } catch (err) {
    console.error("CRITICAL ERROR creating YT.Player:", err);
    const ph = document.getElementById("videoPlaceholder");
    if (ph) {
      ph.textContent = "Erro ao criar player do YouTube: " + err.message;
      ph.style.color = "red";
    }
  }
}

function showSlide(slide) {
  const container = document.getElementById("youtubeContainer");
  if (!container) return;

  // Remove YouTube player if exists
  let ytEl = document.getElementById("ytPlayer");
  if (ytEl) {
    try {
      if (state.ytPlayer && typeof state.ytPlayer.destroy === "function") {
        state.ytPlayer.destroy();
      }
    } catch {}
    ytEl.remove();
    state.ytPlayer = null;
  }

  // Remove placeholder
  const ph = document.getElementById("videoPlaceholder");
  if (ph) ph.remove();

  // Remove existing slide display
  const existingSlide = document.getElementById("slideDisplay");
  if (existingSlide) existingSlide.remove();

  // Create slide image element
  const slideEl = document.createElement("div");
  slideEl.id = "slideDisplay";
  slideEl.className = "w-full h-full";
  slideEl.style.position = "absolute";
  slideEl.style.inset = "0";
  slideEl.style.zIndex = "2";
  slideEl.style.display = "flex";
  slideEl.style.alignItems = "center";
  slideEl.style.justifyContent = "center";
  slideEl.style.background = "#000";

  const imageUrl = slide.image_url || "";
  
  if (imageUrl) {
    // Try to load the image
    const img = document.createElement("img");
    // If it's a relative URL, prepend the Edge API base
    if (imageUrl.startsWith("/")) {
      img.src = `${EDGE_BASE}${imageUrl}`;
    } else {
      img.src = imageUrl;
    }
    img.style.maxWidth = "100%";
    img.style.maxHeight = "100%";
    img.style.objectFit = "contain";
    img.alt = slide.title || "Slide";
    
    img.onerror = () => {
      // Image failed to load, show placeholder
      showSlidePlaceholder(slideEl, slide);
    };
    
    img.onload = () => {
      // Image loaded successfully
      slideEl.appendChild(img);
    };
    
    container.appendChild(slideEl);
  } else {
    // No image URL, show placeholder immediately
    showSlidePlaceholder(slideEl, slide);
    container.appendChild(slideEl);
  }

  // Schedule next item
  const duration = (slide.slide_duration_seconds || 10) * 1000;
  if (state.slideTimer) clearTimeout(state.slideTimer);
  state.slideTimer = setTimeout(() => {
    nextItem();
  }, duration);
}

function showSlidePlaceholder(container, slide) {
  // Get tenant logo if available
  const logoEl = document.getElementById("tenantLogo");
  const logoSrc = logoEl ? logoEl.src : null;
  const tenantNameEl = document.getElementById("tenantName");
  const tenantName = tenantNameEl ? tenantNameEl.textContent : "Chamador";
  
  container.innerHTML = `
    <div class="flex flex-col items-center justify-center text-center p-8" style="color: rgba(255, 255, 255, 0.6);">
      ${logoSrc ? `<img src="${escapeHtml(logoSrc)}" alt="Logo" style="max-width: 200px; max-height: 150px; margin-bottom: 24px; opacity: 0.7;" />` : ""}
      <div style="font-size: 2rem; font-weight: bold; margin-bottom: 12px; color: rgba(255, 255, 255, 0.8);">
        ${escapeHtml(tenantName)}
      </div>
      <div style="font-size: 1.25rem; margin-bottom: 8px;">
        ${escapeHtml(slide.title || "Slide")}
      </div>
      <div style="font-size: 0.875rem; opacity: 0.5;">
        Aguarde...
      </div>
    </div>
  `;
}

function nextItem() {
  if (!state.filteredPlaylist.length) return;
  
  // Clear slide timer
  if (state.slideTimer) {
    clearTimeout(state.slideTimer);
    state.slideTimer = null;
  }

  state.ytIndex = (state.ytIndex + 1) % state.filteredPlaylist.length;
  const item = state.filteredPlaylist[state.ytIndex];

  if (item.media_type === "slide") {
    showSlide(item);
  } else {
    // YouTube video
    if (!state.ytPlayer) {
      // Need to initialize YouTube player
      ensureYouTubeApiLoaded().then(() => {
        initPlaylist(state.playlist);
      });
      return;
    }
    try {
      state.ytPlayer.loadVideoById(item.youtube_id);
      // Keep audio enabled when switching videos
      setTimeout(() => {
        try {
          state.ytPlayer.unMute();
          state.ytPlayer.setVolume(60);
        } catch {}
      }, 500);
    } catch {}
  }
}

// Keep nextVideo for backward compatibility (called by YouTube player)
function nextVideo() {
  nextItem();
}

async function main() {
  console.log("main() started");
  tickClock();
  setInterval(tickClock, 1000);

  // Load initial state (also used to render ticker/history before YT loads)
  let initialPlaylist = [];
  try {
    console.log("Fetching initial state from API...");
    const data = await fetchState();
    console.log("State received:", data);
    applyTenantBranding(data.tenant);
    // Use current_calls if available (all calls in service), fallback to current_call
    if (data.current_calls && data.current_calls.length > 0) {
      renderCurrentCalls(data.current_calls);
      state.current = data.current_calls[0];
    } else {
      setCurrent(data.current_call);
    }
    renderHistory(data.history);
    renderWaitingQueue(data.waiting_queue || []);
    renderTicker(data.announcements);
    initialPlaylist = data.playlist || [];
    state.playlist = initialPlaylist;
    console.log("Initial playlist set:", initialPlaylist);
    

    // Mark all existing calls as "seen" to avoid showing overlay on page load
    if (data.current_calls && Array.isArray(data.current_calls)) {
      data.current_calls.forEach(call => {
        if (call?.id) state.seenCallIds.add(call.id);
      });
      console.log(`Marked ${data.current_calls.length} current calls as seen`);
    } else if (data.current_call?.id) {
      state.seenCallIds.add(data.current_call.id);
      console.log("Marked current call as seen:", data.current_call.id);
    }
    if (data.history && Array.isArray(data.history)) {
      data.history.forEach(call => {
        if (call?.id) state.seenCallIds.add(call.id);
      });
      console.log(`Marked ${data.history.length} history calls as seen`);
    }
  } catch (e) {
    console.error("state fetch failed", e);
  }

  // Load YouTube API deterministically, then mount the player
  try {
    // Check if filtered playlist has YouTube videos
    const filtered = filterPlaylist(initialPlaylist, state.mediaFilter);
    const hasYouTube = filtered.some(item => item.media_type !== "slide");
    if (hasYouTube) {
      console.log("Loading YouTube IFrame API...");
      await ensureYouTubeApiLoaded();
      console.log("YouTube API loaded successfully, window.YT:", window.YT);
    }
    initPlaylist(initialPlaylist);
  } catch (e) {
    const ph = document.getElementById("videoPlaceholder");
    if (ph) ph.textContent = "Falha ao carregar YouTube.";
    console.error("YT API failed", e);
  }

  // Poll state periodically to refresh history/ticker
  // Initialize with current playlist signature to avoid re-initialization on first poll
  let lastPlaylistSig = playlistSignature(initialPlaylist);
  let lastMediaFilter = state.mediaFilter; // Track filter changes
  setInterval(async () => {
    try {
      const data = await fetchState();
      applyTenantBranding(data.tenant);
      renderHistory(data.history);
      renderWaitingQueue(data.waiting_queue || []);
      renderTicker(data.announcements);
      // Use current_calls if available (all calls in service)
      if (data.current_calls && data.current_calls.length > 0) {
        renderCurrentCalls(data.current_calls);
        state.current = data.current_calls[0];
      } else if (data.current_call?.id && data.current_call.id !== state.current?.id) {
        setCurrent(data.current_call);
      } else if (!data.current_calls || data.current_calls.length === 0) {
        renderCurrentCalls([]);
      }

      // Check if media filter changed (applyTenantBranding already updates state.mediaFilter)
      if (state.mediaFilter !== lastMediaFilter) {
        lastMediaFilter = state.mediaFilter;
        console.log("Media filter changed to:", state.mediaFilter);
        // Reinitialize playlist with new filter
        state.ytIndex = 0;
        if (state.ytPlayer && typeof state.ytPlayer.destroy === "function") {
          try {
            state.ytPlayer.destroy();
          } catch {}
          state.ytPlayer = null;
        }
        const slideEl = document.getElementById("slideDisplay");
        if (slideEl) slideEl.remove();
        if (state.slideTimer) {
          clearTimeout(state.slideTimer);
          state.slideTimer = null;
        }
        // Check if filtered playlist has YouTube videos
        const filtered = filterPlaylist(data.playlist, state.mediaFilter);
        const hasYouTube = filtered.some(item => item.media_type !== "slide");
        if (hasYouTube) {
          await ensureYouTubeApiLoaded();
        }
        initPlaylist(data.playlist);
      }

      // If playlist changes, rebuild player (simple + reliable for MVP)
      const sig = playlistSignature(data.playlist);
      if (sig && sig !== lastPlaylistSig) {
        lastPlaylistSig = sig;
        state.ytIndex = 0;
        if (state.ytPlayer && typeof state.ytPlayer.destroy === "function") {
          try {
            state.ytPlayer.destroy();
          } catch {}
          state.ytPlayer = null;
        }
        // Check if filtered playlist has YouTube videos
        const filtered = filterPlaylist(data.playlist, state.mediaFilter);
        const hasYouTube = filtered.some(item => item.media_type !== "slide");
        if (hasYouTube) {
          await ensureYouTubeApiLoaded();
        }
        initPlaylist(data.playlist);
      }
    } catch {}
  }, 3000);

  connectSSEWithToken();
  startPanelToggle();
  renderPanel(); // garante header renderizado imediatamente
}

// One-tap audio enable (needed for some browsers)
document.addEventListener("click", (ev) => {
  const t = ev.target;
  if (t && t.id === "enableAudioBtn") {
    tryEnableYouTubeAudio();
    hideEnableAudioButton();
  }
});

// Debug function - call from console: debugYT()
window.debugYT = function() {
  console.group("=== YouTube Player Debug ===");
  console.log("state.ytPlayer:", state.ytPlayer);
  console.log("state.playlist:", state.playlist);
  console.log("state.ytIndex:", state.ytIndex);
  console.log("state.ytMounted:", state.ytMounted);

  const ytEl = document.getElementById("ytPlayer");
  console.log("ytPlayer element:", ytEl);

  if (ytEl) {
    console.log("ytPlayer computed styles:", window.getComputedStyle(ytEl));
    console.log("ytPlayer innerHTML length:", ytEl.innerHTML.length);
    console.log("ytPlayer children:", ytEl.children);

    const iframe = ytEl.querySelector("iframe");
    console.log("iframe element:", iframe);
    if (iframe) {
      console.log("iframe src:", iframe.src);
      console.log("iframe computed styles:", window.getComputedStyle(iframe));
    }
  }

  const container = document.getElementById("youtubeContainer");
  console.log("youtubeContainer:", container);
  if (container) {
    console.log("youtubeContainer children:", container.children);
  }

  if (state.ytPlayer && typeof state.ytPlayer.getPlayerState === "function") {
    try {
      console.log("Player state:", state.ytPlayer.getPlayerState());
      console.log("Player video URL:", state.ytPlayer.getVideoUrl());
      console.log("Player is muted:", state.ytPlayer.isMuted());
      console.log("Player volume:", state.ytPlayer.getVolume());
    } catch (e) {
      console.error("Error getting player info:", e);
    }
  }

  console.groupEnd();
};

main();

