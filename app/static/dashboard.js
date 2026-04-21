const state = {
  token: null,
};

async function fetchJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(url, { ...options, headers });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }
  return data;
}

function setPreview(id, payload) {
  const element = document.getElementById(id);
  element.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

async function loadHealth() {
  try {
    setPreview("health-preview", await fetchJson("/health/ready"));
  } catch (error) {
    setPreview("health-preview", `Failed to load health:\n${error.message}`);
  }
}

async function loadUsers() {
  try {
    setPreview("users-preview", await fetchJson("/demo/users"));
  } catch (error) {
    setPreview("users-preview", `Failed to load users:\n${error.message}`);
  }
}

async function loadTickets() {
  if (!state.token) {
    setPreview("tickets-preview", "Login to load tickets.");
    return;
  }
  try {
    setPreview("tickets-preview", await fetchJson("/tickets"));
  } catch (error) {
    setPreview("tickets-preview", `Failed to load tickets:\n${error.message}`);
  }
}

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const payload = await fetchJson("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    state.token = payload.access_token;
    setPreview("token-preview", `${payload.token_type} ${payload.access_token}`);
    await loadTickets();
  } catch (error) {
    setPreview("token-preview", `Login failed:\n${error.message}`);
  }
});

document.getElementById("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const raw = Object.fromEntries(new FormData(event.currentTarget).entries());
  const payload = {
    title: raw.title,
    description: raw.description,
    priority: raw.priority,
    visibility: raw.visibility,
    tags: raw.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
  };

  try {
    const ticket = await fetchJson("/tickets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadTickets();
    setPreview("tickets-preview", ticket);
  } catch (error) {
    setPreview("tickets-preview", `Create failed:\n${error.message}`);
  }
});

document.getElementById("status-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const raw = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const ticket = await fetchJson(`/tickets/${raw.ticket_id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: raw.status, message: raw.message }),
    });
    setPreview("tickets-preview", ticket);
  } catch (error) {
    setPreview("tickets-preview", `Status update failed:\n${error.message}`);
  }
});

loadHealth();
loadUsers();
