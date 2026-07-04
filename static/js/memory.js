// ============================================================================
// memory.js — memory panel: shows facts extracted from past voice sessions
// and lets the user delete anything they don't want remembered.
// ============================================================================

(function () {
  const userId = window.SIGNAL.userId;
  const memoryList = document.getElementById("memory-list");
  const refreshBtn = document.getElementById("refresh-memory-btn");

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  async function refreshMemory() {
    try {
      const res = await fetch(`/memory/${userId}`);
      const data = await res.json();
      renderMemory(data.facts || []);
    } catch (err) {
      console.error("Failed to load memory:", err);
    }
  }

  function renderMemory(facts) {
    memoryList.innerHTML = "";
    if (facts.length === 0) {
      memoryList.innerHTML =
        '<li class="memory-empty">No memories yet — they\'re captured automatically after a voice session ends.</li>';
      return;
    }
    facts.forEach((f) => {
      const li = document.createElement("li");
      li.className = "memory-item";
      li.innerHTML = `
        <div>
          <div class="memory-fact">${escapeHtml(f.fact)}</div>
          <span class="memory-date">${escapeHtml(f.created_at)}</span>
        </div>
        <button class="memory-delete-btn" title="Forget this">✕</button>
      `;
      li.querySelector(".memory-delete-btn").addEventListener("click", () => deleteFact(f.id));
      memoryList.appendChild(li);
    });
  }

  async function deleteFact(factId) {
    try {
      await fetch(`/memory/${userId}/${factId}`, { method: "DELETE" });
      refreshMemory();
    } catch (err) {
      console.error("Failed to delete memory fact:", err);
    }
  }

  refreshBtn.addEventListener("click", refreshMemory);
  window.SignalMemory = { refresh: refreshMemory };
  refreshMemory();
})();
