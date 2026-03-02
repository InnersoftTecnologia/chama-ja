(function () {
  const host = window.location.hostname;
  const protocol = window.location.protocol;
  const EDGE_PORT = 7071;
  const TOTEM_PORT = 7076;
  const EDGE_BASE = `${protocol}//${host}:${EDGE_PORT}`;
  const EDGE_TOKEN = "dev-edge-token";

  // ── Monitor modal ──────────────────────────────────────────────
  let monitorInterval = null;

  function openMonitor() {
    const modal = document.getElementById("monitorModal");
    if (!modal) return;
    modal.hidden = false;
    fetchMonitor();
    monitorInterval = setInterval(fetchMonitor, 1000);
  }

  function closeMonitor() {
    const modal = document.getElementById("monitorModal");
    if (!modal) return;
    modal.hidden = true;
    if (monitorInterval) { clearInterval(monitorInterval); monitorInterval = null; }
  }

  async function fetchMonitor() {
    try {
      const res = await fetch(`${EDGE_BASE}/tv/state`, {
        headers: { Authorization: `Bearer ${EDGE_TOKEN}` }
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderMonitor(data);
    } catch (e) {
      const body = document.getElementById("monitorBody");
      if (body) body.innerHTML = `<p class="monitor-empty">Erro ao buscar dados: ${escapeHtml(String(e))}</p>`;
    }
  }

  function renderMonitor(data) {
    const body = document.getElementById("monitorBody");
    const updatedEl = document.getElementById("monitorUpdatedAt");
    if (!body) return;

    const currentCalls = data.current_calls || [];
    const waiting = data.waiting_queue || [];
    const waitingPref = waiting.filter(t => t.priority === "preferential").length;
    const waitingNorm = waiting.filter(t => t.priority !== "preferential").length;

    // Operadores ativos: deduplica por operator_name com base nos tickets chamados/em atendimento
    const opMap = new Map();
    for (const call of currentCalls) {
      const name = call.operator_name || "—";
      const key = name;
      if (!opMap.has(key)) {
        opMap.set(key, { name, counter: call.counter_name || "—", ticket: call.ticket_code, status: call.status });
      }
    }

    const statusLabel = { called: "Chamado", in_service: "Em atendimento" };

    body.innerHTML = `
      <div>
        <p class="monitor-section-title">Fila de espera</p>
        <div class="monitor-stats">
          <div class="monitor-stat">
            <div class="monitor-stat-value">${waitingPref}</div>
            <div class="monitor-stat-label">Preferencial</div>
          </div>
          <div class="monitor-stat">
            <div class="monitor-stat-value">${waitingNorm}</div>
            <div class="monitor-stat-label">Normal</div>
          </div>
          <div class="monitor-stat">
            <div class="monitor-stat-value">${waiting.length}</div>
            <div class="monitor-stat-label">Total aguardando</div>
          </div>
          <div class="monitor-stat">
            <div class="monitor-stat-value">${currentCalls.length}</div>
            <div class="monitor-stat-label">Em atendimento</div>
          </div>
        </div>
      </div>
      <div>
        <p class="monitor-section-title">Operadores atendendo agora</p>
        <div class="monitor-ops">
          ${opMap.size === 0
            ? `<p class="monitor-empty">Nenhum operador em atendimento no momento.</p>`
            : [...opMap.values()].map(op => `
              <div class="monitor-op-row">
                <div class="monitor-op-dot"></div>
                <div class="monitor-op-name">${escapeHtml(op.name)}</div>
                <div class="monitor-op-detail">${escapeHtml(op.counter)}</div>
                <div class="monitor-op-badge">${escapeHtml(op.ticket)} · ${escapeHtml(statusLabel[op.status] || op.status)}</div>
              </div>
            `).join("")
          }
        </div>
      </div>
    `;

    if (updatedEl) {
      updatedEl.textContent = `Atualizado: ${new Date().toLocaleTimeString("pt-BR")}`;
    }
  }
  // ───────────────────────────────────────────────────────────────

  const apps = [
    {
      id: "tv",
      icon: "📺",
      title: "TV / Painel",
      desc: "Monitor de chamadas — exibe senhas, histórico e mídia.",
      port: 7073,
    },
    {
      id: "operador",
      icon: "👤",
      title: "Operador",
      desc: "Interface do atendente — chamar senhas, guichê, fila.",
      port: 7074,
    },
    {
      id: "admin",
      icon: "⚙️",
      title: "Admin Tenant",
      desc: "Configurações — operadores, guichês, serviços, TV, playlist.",
      port: 7075,
    },
    {
      id: "totem",
      icon: "🖥️",
      title: "Totem",
      desc: "Emissão de senhas — tela touch para o cliente.",
      port: 7076,
    },
    {
      id: "test",
      icon: "🧪",
      title: "Test UI",
      desc: "Interface de teste (legado).",
      port: 7072,
    },
    {
      id: "edge",
      icon: "🔌",
      title: "Edge API",
      desc: "Backend — health e documentação.",
      port: 7071,
      path: "/health",
    },
  ];

  function getTheme() {
    return localStorage.getItem("chamaja-dashboard-theme") || "dark";
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("chamaja-dashboard-theme", theme);
  }

  function toggleTheme() {
    const next = getTheme() === "dark" ? "light" : "dark";
    setTheme(next);
  }

  function buildUrl(app, useHost) {
    const h = useHost != null ? useHost : host;
    const path = app.path || "/";
    return `${protocol}//${h}:${app.port}${path}`;
  }

  function totemQrImageSrc(totemUrl) {
    return `https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=${encodeURIComponent(totemUrl)}`;
  }

  function renderCards(totemHost) {
    const container = document.getElementById("cards");
    if (!container) return;
    const hostForTotem = totemHost || host;
    container.innerHTML = apps
      .map((app) => {
        const url = buildUrl(app, app.id === "totem" ? hostForTotem : null);
        const isTotem = app.id === "totem";
        const qrUrl = isTotem ? totemQrImageSrc(url) : "";
        return `
      <a class="card ${isTotem ? "card-with-qr" : ""}" href="${url}" target="_blank" rel="noopener noreferrer" data-app="${app.id}">
        <div class="card-icon">${app.icon}</div>
        <h2 class="card-title">${escapeHtml(app.title)}</h2>
        <p class="card-desc">${escapeHtml(app.desc)}</p>
        <span class="card-badge">:${app.port}</span>
        ${isTotem ? `
        <div class="card-qr">
          <p class="card-qr-label">Acesse pelo celular ou tablet</p>
          <img id="totem-qr-img" class="card-qr-img" src="${qrUrl}" alt="QR Code para ${escapeHtml(app.title)}" width="140" height="140" />
        </div>
        ` : ""}
      </a>
    `;
      })
      .join("");

    // Card especial de acompanhamento (não é link, abre modal)
    const monitorCard = document.createElement("div");
    monitorCard.className = "card card-monitor";
    monitorCard.setAttribute("role", "button");
    monitorCard.setAttribute("tabindex", "0");
    monitorCard.innerHTML = `
      <div class="card-icon">📊</div>
      <h2 class="card-title">Acompanhamento</h2>
      <p class="card-desc">Fila em tempo real — operadores atendendo, senhas aguardando.</p>
      <span class="card-badge">ao vivo</span>
    `;
    monitorCard.addEventListener("click", openMonitor);
    monitorCard.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") openMonitor(); });
    container.appendChild(monitorCard);
  }

  function updateTotemQrFromApi() {
    const edgeUrl = `${protocol}//${host}:${EDGE_PORT}`;
    fetch(`${edgeUrl}/api/host`)
      .then((r) => r.json())
      .then((data) => {
        const apiHost = (data && data.host && data.host.trim()) || null;
        if (apiHost && apiHost !== host) {
          const totemUrl = `${protocol}//${apiHost}:${TOTEM_PORT}/`;
          const img = document.getElementById("totem-qr-img");
          if (img) img.src = totemQrImageSrc(totemUrl);
        }
      })
      .catch(() => {});
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  document.getElementById("themeToggle")?.addEventListener("click", toggleTheme);
  document.getElementById("monitorClose")?.addEventListener("click", closeMonitor);
  document.getElementById("monitorModal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeMonitor();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMonitor(); });

  setTheme(getTheme());
  renderCards();
  updateTotemQrFromApi();
})();
