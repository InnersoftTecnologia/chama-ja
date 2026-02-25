/**
 * Totem de Atendimento - Chamador
 * Frontend para emissão de senhas
 * Usa Bootstrap 5.3.3
 */

const EDGE_BASE = (window.EDGE_BASE || `${window.location.protocol}//${window.location.hostname}:7071`).replace(/\/$/, "");
const EDGE_TOKEN = window.EDGE_TOKEN || "dev-edge-token";

// Service icons mapping (Material Icons)
const SERVICE_ICONS = {
  caixa: "payments",
  caixas: "payments",
  pagamento: "payments",
  credito: "credit_card",
  crédito: "credit_card",
  cobranca: "credit_card",
  cobrança: "credit_card",
  cartao: "credit_card",
  cartão: "credit_card",
  sac: "support_agent",
  atendimento: "support_agent",
  troca: "swap_horiz",
  trocas: "swap_horiz",
  devolucao: "swap_horiz",
  devolução: "swap_horiz",
  preferencial: "accessible",
  default: "confirmation_number",
};

function authHeaders() {
  return { Authorization: `Bearer ${EDGE_TOKEN}`, "Content-Type": "application/json" };
}

function setStatus(msg) {
  const el = document.getElementById("statusText");
  if (el) el.textContent = msg || "";
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Get appropriate icon for service name
function getServiceIcon(serviceName, isPriority) {
  if (isPriority) {
    const name = (serviceName || "").toLowerCase();
    if (name.includes("caixa") || name.includes("pagamento")) return "accessible";
    if (name.includes("credito") || name.includes("crédito") || name.includes("cartao") || name.includes("cartão")) return "volunteer_activism";
    return "accessible";
  }

  const name = (serviceName || "").toLowerCase();
  for (const [key, icon] of Object.entries(SERVICE_ICONS)) {
    if (name.includes(key)) return icon;
  }
  return SERVICE_ICONS.default;
}

// Get subtitle for service
function getServiceSubtitle(serviceName, isPriority) {
  const name = (serviceName || "").toLowerCase();

  if (isPriority) {
    return "Gestantes, Idosos e PCD";
  }

  if (name.includes("caixa") || name.includes("pagamento")) {
    return "Pagamento de Mercadorias";
  }
  if (name.includes("credito") || name.includes("crédito") || name.includes("cobranca") || name.includes("cobrança")) {
    return "Fatura e Cartão";
  }
  if (name.includes("sac") || name.includes("atendimento")) {
    return "Serviço de Atendimento";
  }
  if (name.includes("troca") || name.includes("devolucao") || name.includes("devolução")) {
    return "Trocas e Devoluções";
  }

  return "Toque para emitir senha";
}

function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString("pt-BR", { hour12: false });
  document.getElementById("clock").textContent = timeStr;

  const options = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
  document.getElementById("date").textContent = now.toLocaleDateString("pt-BR", options);
}

async function api(path, opts = {}) {
  const res = await fetch(`${EDGE_BASE}${path}`, opts);
  const txt = await res.text();
  let data;
  try {
    data = JSON.parse(txt);
  } catch {
    data = txt;
  }
  if (!res.ok) throw new Error(`${res.status}: ${typeof data === "string" ? data : JSON.stringify(data)}`);
  return data;
}

async function loadTenantBranding() {
  try {
    const data = await api("/tv/state", { headers: authHeaders() });
    const t = data?.tenant || {};
    const name = (t.nome_fantasia || t.nome_razao_social || "").toString();

    const logoEl = document.getElementById("tenantLogo");
    const logoWrap = document.getElementById("logoWrap");
    const nameEl = document.getElementById("tenantName");
    const subtitleEl = document.getElementById("tenantSubtitle");
    const nameWrap = document.getElementById("tenantNameWrap");

    // Logo estático SVG tem prioridade; fallback para base64 da API; fallback para nome texto
    if (logoEl && logoEl.src && logoEl.getAttribute("src")) {
      // Logo já definido no HTML (src estático) — apenas garante visibilidade
      if (logoWrap) { logoWrap.classList.remove("d-none"); logoWrap.classList.add("d-flex"); }
    } else if (logoEl && logoWrap && t.logo_base64 && typeof t.logo_base64 === "string") {
      const v = t.logo_base64.trim();
      logoEl.src = v.startsWith("data:") ? v : `data:image/svg+xml;base64,${v}`;
      logoWrap.classList.remove("d-none");
      logoWrap.classList.add("d-flex");
    } else if (name && nameWrap) {
      if (nameEl) nameEl.textContent = name.toUpperCase();
      if (subtitleEl) subtitleEl.textContent = "Retire sua senha";
      nameWrap.classList.remove("d-none");
      nameWrap.classList.add("d-flex");
    }
  } catch {
    // Ignore branding failures
  }
}

// Estado do fluxo: lista completa de serviços carregada da API
let allServices = [];

function createServiceCard(svc) {
  const isPriority = svc.priority_mode === "preferential";
  const icon = getServiceIcon(svc.name, isPriority);
  const subtitle = getServiceSubtitle(svc.name, isPriority);
  const cardClass = isPriority ? "service-card-priority" : "service-card-normal";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `service-card ${cardClass}`;
  btn.innerHTML = `
    <div class="service-icon">
      <span class="material-icons">${escapeHtml(icon)}</span>
    </div>
    <div class="service-name">${escapeHtml(svc.name)}</div>
    <div class="service-subtitle">${escapeHtml(subtitle)}</div>
  `;

  btn.addEventListener("click", () => emitTicket(svc));
  return btn;
}

function showScreen(screenId) {
  const choiceScreen = document.getElementById("choiceScreen");
  const servicesScreen = document.getElementById("servicesScreen");
  const emptyState = document.getElementById("emptyState");

  if (choiceScreen) choiceScreen.classList.add("d-none");
  if (servicesScreen) servicesScreen.classList.add("d-none");
  if (emptyState) {
    emptyState.classList.add("d-none");
    emptyState.classList.remove("d-flex");
  }

  if (screenId === "choice" && choiceScreen) {
    choiceScreen.classList.remove("d-none");
    choiceScreen.classList.add("d-flex");
  } else if (screenId === "services" && servicesScreen) {
    servicesScreen.classList.remove("d-none");
    servicesScreen.classList.add("d-flex");
  } else if (screenId === "empty" && emptyState) {
    emptyState.classList.remove("d-none");
    emptyState.classList.add("d-flex");
  }
}

function renderChoiceScreen(services) {
  const list = Array.isArray(services) ? services : [];
  const normal = list.filter((s) => s && s.priority_mode !== "preferential");
  const preferential = list.filter((s) => s && s.priority_mode === "preferential");

  const btnNormal = document.getElementById("btnNormal");
  const btnPreferential = document.getElementById("btnPreferential");
  if (btnNormal) btnNormal.style.display = normal.length > 0 ? "" : "none";
  if (btnPreferential) btnPreferential.style.display = preferential.length > 0 ? "" : "none";

  showScreen("choice");
  setStatus("");
  const footerText = document.getElementById("footerText");
  if (footerText) footerText.textContent = "Escolha o tipo de atendimento.";
}

function renderServicesList(serviceList) {
  const listEl = document.getElementById("servicesList");
  if (!listEl) return;
  listEl.innerHTML = "";
  const list = Array.isArray(serviceList) ? serviceList : [];
  list.forEach((svc) => listEl.appendChild(createServiceCard(svc)));
  showScreen("services");
  const footerText = document.getElementById("footerText");
  if (footerText) footerText.textContent = "Toque no serviço desejado para emitir sua senha.";
  setStatus(`${list.length} serviço(s) disponível(is)`);
}

function goBackToChoice() {
  renderChoiceScreen(allServices);
}

function renderServices(services) {
  const loadingState = document.getElementById("loadingState");
  const emptyState = document.getElementById("emptyState");

  if (loadingState) loadingState.classList.add("d-none");
  allServices = Array.isArray(services) ? services : [];

  if (!allServices.length) {
    showScreen("empty");
    setStatus("Nenhum serviço ativo encontrado.");
    return;
  }

  renderChoiceScreen(allServices);
}

let _overlayTimer = null;

function openOverlay(data) {
  const overlay = document.getElementById("overlay");
  overlay.classList.remove("d-none");
  overlay.classList.add("d-flex");
  overlay.setAttribute("aria-hidden", "false");

  document.getElementById("overlayCode").textContent = data.ticket_code || "---";
  document.getElementById("overlayService").textContent = data.service_name || "-";
  document.getElementById("overlayPriority").textContent =
    data.priority === "preferential" ? "Preferencial" : "Normal";

  const foot = document.getElementById("overlayFootnote");
  foot.textContent = data.printed
    ? "Recibo impresso. Aguarde sua vez no painel."
    : "Impressora indisponível. Aguarde sua vez no painel.";

  // Auto-fecha e volta para tela inicial após 2 segundos
  if (_overlayTimer) clearTimeout(_overlayTimer);
  _overlayTimer = setTimeout(() => closeOverlay(), 2000);
}

function closeOverlay() {
  if (_overlayTimer) { clearTimeout(_overlayTimer); _overlayTimer = null; }
  const overlay = document.getElementById("overlay");
  overlay.classList.add("d-none");
  overlay.classList.remove("d-flex");
  overlay.setAttribute("aria-hidden", "true");
  goBackToChoice();
}

function downloadTxt(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

let emitting = false;
async function emitTicket(service) {
  if (emitting) return;
  emitting = true;
  setStatus("Emitindo senha...");

  try {
    const data = await api("/totem/emit", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ service_id: service.id }),
    });

    // Recibo deve sair na impressora térmica; não fazemos download de .txt
    openOverlay(data);
    setStatus("Senha emitida com sucesso!");
  } catch (e) {
    console.error("Erro ao emitir senha:", e);
    setStatus(`Erro: ${String(e)}`);
    alert(`Erro ao emitir senha: ${String(e)}`);
  } finally {
    emitting = false;
  }
}

// Theme toggle (Bootstrap 5.3 data-bs-theme)
function initTheme() {
  const html = document.documentElement;
  const themeIcon = document.getElementById("themeIcon");
  const btnTheme = document.getElementById("btnThemeToggle");

  // Check saved preference or system preference
  const saved = localStorage.getItem("totem-theme");
  if (saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    html.setAttribute("data-bs-theme", "dark");
    themeIcon.textContent = "light_mode";
  }

  btnTheme.addEventListener("click", () => {
    const isDark = html.getAttribute("data-bs-theme") === "dark";
    if (isDark) {
      html.setAttribute("data-bs-theme", "light");
      themeIcon.textContent = "dark_mode";
      localStorage.setItem("totem-theme", "light");
    } else {
      html.setAttribute("data-bs-theme", "dark");
      themeIcon.textContent = "light_mode";
      localStorage.setItem("totem-theme", "dark");
    }
  });
}

async function main() {
  // Ano do copyright
  const yearEl = document.getElementById("footerYear");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // Start clock
  updateClock();
  setInterval(updateClock, 1000);

  // Initialize theme toggle
  initTheme();

  // Load tenant branding
  await loadTenantBranding();

  // Load services
  try {
    const raw = await api("/totem/services", { headers: authHeaders() });
    const services = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.services) ? raw.services : []);
    renderServices(services);
  } catch (e) {
    console.error("Falha ao carregar serviços:", e);
    const loadingState = document.getElementById("loadingState");
    const emptyState = document.getElementById("emptyState");
    if (loadingState) loadingState.classList.add("d-none");
    if (emptyState) {
      emptyState.classList.remove("d-none");
      emptyState.classList.add("d-flex");
    }
    setStatus(`Falha ao carregar: ${String(e)}`);
  }

  // Tela 1: botões NORMAL e PREFERENCIAL
  const btnNormal = document.getElementById("btnNormal");
  const btnPreferential = document.getElementById("btnPreferential");
  if (btnNormal) btnNormal.addEventListener("click", () => {
    const normal = allServices.filter((s) => s && s.priority_mode !== "preferential");
    if (normal.length) renderServicesList(normal);
  });
  if (btnPreferential) btnPreferential.addEventListener("click", () => {
    const preferential = allServices.filter((s) => s && s.priority_mode === "preferential");
    if (preferential.length) renderServicesList(preferential);
  });

  // Tela 2: voltar para escolha do tipo
  const btnBack = document.getElementById("btnBack");
  if (btnBack) btnBack.addEventListener("click", goBackToChoice);

  // Overlay handlers
  document.getElementById("btnOk").addEventListener("click", closeOverlay);
  document.getElementById("overlayBackdrop").addEventListener("click", closeOverlay);

  // Close overlay on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeOverlay();
  });
}

main();
