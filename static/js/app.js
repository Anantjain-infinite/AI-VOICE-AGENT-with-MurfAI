// ============================================================================
// app.js — shared app shell logic: session/user identity, tabs, keys drawer.
//
// Two distinct ids are tracked on purpose:
//   - sessionId: resets per browser tab/session (query param, like before).
//     Chat history and uploaded RAG documents are scoped to this.
//   - userId: persisted in localStorage, survives across sessions/restarts.
//     Long-term memory facts are scoped to this, which is what makes
//     "remembering across sessions" actually mean something.
// ============================================================================

function getOrCreateSessionId() {
  const url = new URL(window.location.href);
  let sid = url.searchParams.get("session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    url.searchParams.set("session_id", sid);
    window.history.replaceState({}, "", url.toString());
  }
  return sid;
}

function getOrCreateUserId() {
  let uid = localStorage.getItem("signal_user_id");
  if (!uid) {
    uid = crypto.randomUUID();
    localStorage.setItem("signal_user_id", uid);
  }
  return uid;
}

window.SIGNAL = {
  sessionId: getOrCreateSessionId(),
  userId: getOrCreateUserId(),
  apiKeysConfigured: false,
};

// ---- Tabs ----
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");

    if (btn.dataset.tab === "documents" && window.SignalDocs) {
      window.SignalDocs.refresh();
    }
    if (btn.dataset.tab === "memory" && window.SignalMemory) {
      window.SignalMemory.refresh();
    }
  });
});

// ---- Keys drawer ----
const drawer = document.getElementById("keys-drawer");
const overlay = document.getElementById("drawer-overlay");

function openDrawer() {
  drawer.classList.add("active");
  overlay.classList.add("active");
}
function closeDrawer() {
  drawer.classList.remove("active");
  overlay.classList.remove("active");
}

document.getElementById("toggle-keys-btn").addEventListener("click", openDrawer);
document.getElementById("close-drawer-btn").addEventListener("click", closeDrawer);
overlay.addEventListener("click", closeDrawer);

function areApiKeysFilled() {
  return [1, 2, 3, 4, 5, 6].every(
    (n) => document.getElementById(`input${n}`).value.trim().length > 0
  );
}

document.getElementById("apiform").addEventListener("submit", function (e) {
  e.preventDefault();

  const payload = {
    api_key_1: document.getElementById("input1").value,
    api_key_2: document.getElementById("input2").value,
    api_key_3: document.getElementById("input3").value,
    api_key_4: document.getElementById("input4").value,
    api_key_5: document.getElementById("input5").value,
    api_key_6: document.getElementById("input6").value,
  };

  fetch("/get-api-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((res) => res.json())
    .then(() => {
      document.getElementById("api-success-message").style.display = "block";
      if (areApiKeysFilled()) {
        window.SIGNAL.apiKeysConfigured = true;
        document.getElementById("keys-dot").classList.add("ok");
      }
      setTimeout(closeDrawer, 900);
    })
    .catch((err) => console.error("Error configuring keys:", err));
});
