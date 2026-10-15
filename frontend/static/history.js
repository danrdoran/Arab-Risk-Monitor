/* Browser-owned conversations and briefs. No network or API keys. */
(function (root) {
  "use strict";
  const STORAGE_KEY = "arm_history_v1";
  const MAX_CONVERSATIONS = 20;
  const MAX_MESSAGES = 100;
  const MAX_BRIEF_ITEMS = 200;
  const MAX_STORAGE_CHARS = 2_000_000;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const fresh = () => ({ version: 1, conversations: [], briefItems: [], activeId: null });
  const validId = (id) => typeof id === "string" && /^[a-zA-Z0-9_-]{1,64}$/.test(id);
  const uid = () => root.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2);
  const now = () => new Date().toISOString();

  function compactPayload(payload) {
    if (!payload || typeof payload !== "object") return null;
    const take = (name, n) => Array.isArray(payload[name]) ? payload[name].slice(0, n) : [];
    return clone({
      citations: take("citations", 60), paper_citations: take("paper_citations", 20),
      score_rows: take("score_rows", 40), chart_rows: take("chart_rows", 400),
      graph_context: {
        nodes: (payload.graph_context?.nodes || []).slice(0, 60),
        edges: (payload.graph_context?.edges || []).slice(0, 120),
      },
      trace: take("trace", 12), models: payload.models || {},
    });
  }

  class BrowserHistory {
    constructor(storage, notify = () => {}) {
      this.notify = notify;
      this.data = fresh();
      try {
        this.storage = storage === undefined ? root.localStorage : storage;
      } catch {
        this.storage = null;
      }
      if (!this.storage) this.notify("unavailable");
      this.reload();
    }

    reload() {
      if (!this.storage) return;
      try {
        const raw = this.storage.getItem(STORAGE_KEY);
        if (!raw) { this.data = fresh(); return; }
        const parsed = JSON.parse(raw);
        if (parsed.version !== 1 || !Array.isArray(parsed.conversations) || !Array.isArray(parsed.briefItems)) throw new Error("invalid history");
        const conversations = parsed.conversations.filter((c) =>
          c && validId(c.id) && Array.isArray(c.messages) && c.messages.every((m) =>
            m && ["user", "assistant"].includes(m.role) && typeof m.content === "string"
          )
        ).slice(0, MAX_CONVERSATIONS).map((c) => ({
          ...c, title: String(c.title || "").slice(0, 80),
          created_at: typeof c.created_at === "string" ? c.created_at : now(),
          updated_at: typeof c.updated_at === "string" ? c.updated_at : now(),
          messages: c.messages.slice(-MAX_MESSAGES),
          payload: compactPayload(c.payload),
        }));
        const ids = new Set(conversations.map((c) => c.id));
        this.data = {
          version: 1, conversations,
          briefItems: parsed.briefItems.filter((b) =>
            b && validId(b.id) && ids.has(b.conversation_id) && typeof b.kind === "string" &&
            b.ref && typeof b.ref === "object"
          ).slice(-MAX_BRIEF_ITEMS),
          activeId: ids.has(parsed.activeId) ? parsed.activeId : null,
        };
      } catch {
        // Preserve the page's in-memory work if browser storage is blocked.
        this.storage = null;
        this.notify("unavailable");
      }
    }

    _dropConversation(id) {
      this.data.conversations = this.data.conversations.filter((c) => c.id !== id);
      this.data.briefItems = this.data.briefItems.filter((b) => b.conversation_id !== id);
      if (this.data.activeId === id) this.data.activeId = null;
    }

    _persist() {
      this.data.conversations.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      while (this.data.conversations.length > MAX_CONVERSATIONS) this._dropConversation(this.data.conversations.at(-1).id);
      this.data.briefItems = this.data.briefItems.slice(-MAX_BRIEF_ITEMS);
      if (!this.storage) return;
      let trimmed = false;
      while (true) {
        const serialized = JSON.stringify(this.data);
        let quotaError = serialized.length > MAX_STORAGE_CHARS;
        if (!quotaError) {
          try {
            this.storage.setItem(STORAGE_KEY, serialized);
            if (trimmed) this.notify("trimmed");
            return;
          } catch (error) {
            quotaError = ["QuotaExceededError", "NS_ERROR_DOM_QUOTA_REACHED"].includes(error.name);
            if (!quotaError) { this.storage = null; this.notify("unavailable"); return; }
          }
        }
        const old = this.data.conversations.findLast((c) => c.id !== this.data.activeId);
        if (old) this._dropConversation(old.id);
        else {
          const active = this.data.conversations[0];
          if (active?.payload) active.payload = null;
          else if (active?.messages.length > 2) active.messages.splice(0, 2);
          else { this.storage = null; this.notify("unavailable"); return; }
        }
        trimmed = true;
      }
    }

    list() { return clone(this.data.conversations); }
    get(id) { return clone(this.data.conversations.find((c) => c.id === id) || null); }
    activeId() { return this.data.activeId; }
    setActive(id) { this.reload(); this.data.activeId = this.get(id) ? id : null; this._persist(); }

    saveConversation({ id, lang = "en", messages = [], payload = null }) {
      this.reload(); // Merge changes saved by another tab before writing.
      let conversation = this.data.conversations.find((c) => c.id === id);
      if (!conversation) {
        conversation = { id: uid(), created_at: now(), updated_at: now(), title: "", lang, messages: [], payload: null };
        this.data.conversations.unshift(conversation);
      }
      conversation.lang = lang;
      conversation.messages = clone(messages.slice(-MAX_MESSAGES));
      if (conversation.messages[0]?.role === "assistant") conversation.messages.shift();
      if (!conversation.title) conversation.title = (conversation.messages.find((m) => m.role === "user")?.content || "").split("\n")[0].slice(0, 80);
      conversation.payload = compactPayload(payload);
      conversation.updated_at = now();
      this.data.activeId = conversation.id;
      this._persist();
      return conversation.id;
    }

    deleteConversation(id) { this.reload(); this._dropConversation(id); this._persist(); }
    clear() {
      this.data = fresh();
      if (this.storage) {
        try { this.storage.removeItem(STORAGE_KEY); }
        catch { this.storage = null; this.notify("unavailable"); }
      }
    }

    listBrief(conversationId) {
      return clone(this.data.briefItems.filter((b) => b.conversation_id === conversationId));
    }
    addBrief(kind, ref, conversationId) {
      this.reload();
      const item = { id: uid(), kind, ref: clone(ref), conversation_id: conversationId, note: "", created_at: now() };
      this.data.briefItems.push(item);
      this._persist();
      return item.id;
    }
    updateBrief(id, note) {
      this.reload();
      const item = this.data.briefItems.find((b) => b.id === id);
      if (item) { item.note = note.slice(0, 2_000); this._persist(); }
    }
    deleteBrief(id) { this.reload(); this.data.briefItems = this.data.briefItems.filter((b) => b.id !== id); this._persist(); }

    exportConversations() {
      const lines = ["# Arab Risk Monitor conversations", ""];
      for (const c of this.list()) {
        lines.push("## " + (c.title || "Untitled"), "");
        for (const m of c.messages) lines.push("**" + (m.role === "user" ? "You" : "Advisor") + "**", "", m.content, "");
        if (this.listBrief(c.id).length) lines.push(this.exportBrief(c.id), "");
      }
      return lines.join("\n");
    }

    exportBrief(conversationId) {
      const conversation = this.get(conversationId);
      const lines = ["# Brief — " + (conversation?.title || "Conflict prevention"), "", "_Arab Risk Monitor · " + now().slice(0, 10) + "_", ""];
      const groups = { passage: "Policy evidence", data: "Data points", score: "Composite scores", graph_node: "Knowledge-graph context" };
      const items = this.listBrief(conversationId);
      for (const [kind, heading] of Object.entries(groups)) {
        const group = items.filter((b) => b.kind === kind);
        if (!group.length) continue;
        lines.push("## " + heading, "");
        for (const item of group) {
          const r = item.ref;
          if (kind === "passage") lines.push("- **" + (r.citation || "") + "** — " + (r.section || ""), r.snippet ? "  > " + r.snippet : "", r.url ? "  <" + r.url + ">" : "");
          else if (kind === "data") lines.push("- **" + (r.indicator_label || "") + "** — " + (r.country_name || "") + " " + (r.year || "") + ": " + (r.value ?? "") + " " + (r.unit || "") + " (" + (r.source_name || "") + ", retrieved " + String(r.retrieved_at || "").slice(0, 10) + ")");
          else if (kind === "score") lines.push("- **" + (r.country_name || "") + " — " + (r.pathway || "") + "** (" + (r.year || "") + "): risk " + (r.risk ?? "") + ", vulnerability " + (r.vulnerability ?? "") + ", resilience " + (r.resilience ?? ""));
          else lines.push("- **" + (r.label || "") + "** — " + (r.summary || ""));
          if (item.note) lines.push("  Note: " + item.note);
        }
        lines.push("");
      }
      return lines.join("\n");
    }
  }

  const api = { BrowserHistory, STORAGE_KEY, MAX_CONVERSATIONS, MAX_MESSAGES };
  root.ARMHistory = api;
  if (typeof module !== "undefined") module.exports = api;
})(globalThis);
