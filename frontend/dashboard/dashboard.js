(function () {
  const host = window.location.hostname;
  const protocol = window.location.protocol;
  const EDGE_PORT = 7071;
  const TOTEM_PORT = 7076;

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
  setTheme(getTheme());
  renderCards();
  updateTotemQrFromApi();
})();
