// ============================================================================
// documents.js — RAG panel: upload PDFs, list/delete indexed docs, and ask
// questions grounded in them via /rag/chat/{session_id}.
// ============================================================================

(function () {
  const sessionId = window.SIGNAL.sessionId;

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("pdf-input");
  const progressEl = document.getElementById("upload-progress");
  const docList = document.getElementById("doc-list");
  const chatLog = document.getElementById("docs-chat-log");
  const chatForm = document.getElementById("docs-chat-form");
  const questionInput = document.getElementById("docs-question");

  async function refreshDocumentList() {
    try {
      const res = await fetch(`/rag/documents/${sessionId}`);
      const data = await res.json();
      renderDocuments(data.documents || []);
    } catch (err) {
      console.error("Failed to load documents:", err);
    }
  }

  function renderDocuments(documents) {
    docList.innerHTML = "";
    if (documents.length === 0) {
      docList.innerHTML = '<li class="doc-empty">No documents uploaded yet.</li>';
      return;
    }
    documents.forEach((doc) => {
      const li = document.createElement("li");
      li.className = "doc-item";
      li.innerHTML = `
        <div>
          <div class="doc-name">${escapeHtml(doc.filename)}</div>
          <div class="doc-meta">${doc.chunk_count} chunks indexed</div>
        </div>
        <button class="doc-delete-btn" title="Remove document">✕</button>
      `;
      li.querySelector(".doc-delete-btn").addEventListener("click", () => deleteDocument(doc.doc_id));
      docList.appendChild(li);
    });
  }

  async function deleteDocument(docId) {
    try {
      await fetch(`/rag/documents/${sessionId}/${docId}`, { method: "DELETE" });
      refreshDocumentList();
    } catch (err) {
      console.error("Failed to delete document:", err);
    }
  }

  async function uploadPdf(file) {
    if (!file || file.type !== "application/pdf") {
      alert("Please upload a PDF file.");
      return;
    }
    progressEl.style.display = "block";
    progressEl.textContent = `Indexing ${file.name}…`;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`/rag/upload/${sessionId}`, { method: "POST", body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }
      const data = await res.json();
      progressEl.textContent = `Indexed ${data.chunks_indexed} chunks from ${data.filename}`;
      setTimeout(() => { progressEl.style.display = "none"; }, 2000);
      refreshDocumentList();
    } catch (err) {
      progressEl.textContent = `Error: ${err.message}`;
      console.error("PDF upload failed:", err);
    }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function appendChatMessage(role, text, sources) {
    const empty = chatLog.querySelector(".docs-chat-empty");
    if (empty) empty.remove();

    const msg = document.createElement("div");
    msg.className = `chat-msg ${role}`;
    msg.textContent = text;

    if (sources && sources.length > 0) {
      const srcEl = document.createElement("div");
      srcEl.className = "chat-sources";
      srcEl.textContent = "Sources: " + sources.map((s) => `${s.filename} (p.${s.page})`).join(", ");
      msg.appendChild(srcEl);
    }

    chatLog.appendChild(msg);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = questionInput.value.trim();
    if (!question) return;

    appendChatMessage("user", question);
    questionInput.value = "";

    try {
      const res = await fetch(`/rag/chat/${sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      appendChatMessage("assistant", data.answer, data.sources);
    } catch (err) {
      appendChatMessage("assistant", "Something went wrong asking that question.");
      console.error("RAG chat failed:", err);
    }
  });

  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) uploadPdf(fileInput.files[0]);
  });

  ["dragover", "dragenter"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) uploadPdf(file);
  });

  window.SignalDocs = { refresh: refreshDocumentList };
  refreshDocumentList();
})();
