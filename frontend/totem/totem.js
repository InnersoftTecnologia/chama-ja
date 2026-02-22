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
    const name = (t.nome_fantasia || t.nome_razao_social || "CHAMADOR").toString();
    document.getElementById("tenantName").textContent = name.toUpperCase();

    if (t.nome_fantasia || t.nome_razao_social) {
      document.getElementById("tenantSubtitle").textContent = "Retire sua senha";
    }

    const logoEl = document.getElementById("tenantLogo");
    const logoWrap = document.getElementById("logoWrap");
    if (logoEl && logoWrap) {
      if (t.logo_base64 && typeof t.logo_base64 === "string") {
        const v = t.logo_base64.trim();
        logoEl.src = v.startsWith("data:") ? v : `data:image/svg+xml;base64,${v}`;
        logoWrap.classList.remove("d-none");
        logoWrap.classList.add("d-flex");
      }
    }
  } catch {
    // Ignore branding failures
  }
}

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

function renderServices(services) {
  const loadingState = document.getElementById("loadingState");
  const servicesContainer = document.getElementById("servicesContainer");
  const emptyState = document.getElementById("emptyState");
  const normalServices = document.getElementById("normalServices");
  const preferentialServices = document.getElementById("preferentialServices");

  // Hide loading
  loadingState.classList.add("d-none");

  if (!services || services.length === 0) {
    emptyState.classList.remove("d-none");
    emptyState.classList.add("d-flex");
    setStatus("Nenhum serviço ativo encontrado.");
    return;
  }

  // Clear containers
  normalServices.innerHTML = "";
  preferentialServices.innerHTML = "";

  // Separate services by priority
  const normal = services.filter((s) => s.priority_mode !== "preferential");
  const preferential = services.filter((s) => s.priority_mode === "preferential");

  // Render normal services
  normal.forEach((svc) => {
    normalServices.appendChild(createServiceCard(svc));
  });

  // Render preferential services
  preferential.forEach((svc) => {
    preferentialServices.appendChild(createServiceCard(svc));
  });

  // Show empty message if a column has no services
  if (normal.length === 0) {
    normalServices.innerHTML = `
      <div class="empty-column">
        <span class="material-icons">inbox</span>
        <span>Sem serviços normais</span>
      </div>
    `;
  }

  if (preferential.length === 0) {
    preferentialServices.innerHTML = `
      <div class="empty-column">
        <span class="material-icons">inbox</span>
        <span>Sem serviços preferenciais</span>
      </div>
    `;
  }

  // Show services container
  servicesContainer.classList.remove("d-none");
  setStatus(`${services.length} serviço(s) disponível(is)`);
}

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
  foot.textContent = data.saved_path ? `Arquivo: ${data.saved_path}` : "Aguarde sua vez no painel.";
}

function closeOverlay() {
  const overlay = document.getElementById("overlay");
  overlay.classList.add("d-none");
  overlay.classList.remove("d-flex");
  overlay.setAttribute("aria-hidden", "true");
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

    // Download ticket file
    const txt = data.print_text || "";
    const fname = `ticket_${(data.ticket_code || "senha").replaceAll("/", "-")}.txt`;
    if (txt) downloadTxt(fname, txt);

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
  // Start clock
  updateClock();
  setInterval(updateClock, 1000);

  // Initialize theme toggle
  initTheme();

  // Load tenant branding
  await loadTenantBranding();

  // Load services
  try {
    const services = await api("/totem/services", { headers: authHeaders() });
    renderServices(services);
  } catch (e) {
    console.error("Falha ao carregar serviços:", e);
    document.getElementById("loadingState").classList.add("d-none");
    document.getElementById("emptyState").classList.remove("d-none");
    document.getElementById("emptyState").classList.add("d-flex");
    setStatus(`Falha ao carregar: ${String(e)}`);
  }

  // Overlay handlers
  document.getElementById("btnOk").addEventListener("click", closeOverlay);
  document.getElementById("overlayBackdrop").addEventListener("click", closeOverlay);

  // Close overlay on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeOverlay();
  });
}

main();
