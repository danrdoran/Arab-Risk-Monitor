const test = require("node:test");
const assert = require("node:assert/strict");
const { BrowserHistory, STORAGE_KEY, MAX_CONVERSATIONS } = require("../frontend/static/history.js");

function storage() {
  const entries = new Map();
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key),
  };
}
function conversation(store, text = "Question") {
  return store.saveConversation({
    messages: [{ role: "user", content: text }, { role: "assistant", content: "Cited answer" }],
    payload: { paper_citations: [{ citation: "Source p. 1", section: "Evidence" }] },
  });
}

test("reload restores messages, active chat, citations, pinned notes and exports", () => {
  const backing = storage();
  const first = new BrowserHistory(backing);
  const id = conversation(first);
  const briefId = first.addBrief("passage", { citation: "Source p. 1", section: "Evidence", snippet: "A passage", url: "https://example.org/paper" }, id);
  first.updateBrief(briefId, "My note");
  const restored = new BrowserHistory(backing);
  assert.equal(restored.activeId(), id);
  assert.equal(restored.get(id).messages[1].content, "Cited answer");
  assert.equal(restored.get(id).payload.paper_citations[0].citation, "Source p. 1");
  assert.equal(restored.listBrief(id)[0].note, "My note");
  assert.match(restored.exportBrief(id), /My note/);
  assert.match(restored.exportConversations(), /Cited answer/);
});

test("different browser profiles do not share conversations", () => {
  const alice = new BrowserHistory(storage());
  conversation(alice, "Alice's question");
  const bob = new BrowserHistory(storage());
  assert.equal(bob.list().length, 0);
  assert.equal(bob.activeId(), null);
});

test("two tabs preserve each other's distinct conversations and notes", () => {
  const backing = storage();
  const firstTab = new BrowserHistory(backing);
  const secondTab = new BrowserHistory(backing);
  const alice = conversation(firstTab, "First tab");
  const bob = conversation(secondTab, "Second tab");
  firstTab.addBrief("graph_node", { label: "Inclusion" }, alice);
  secondTab.addBrief("data", { value: 0 }, bob);
  const restored = new BrowserHistory(backing);
  assert.equal(restored.list().length, 2);
  assert.equal(restored.listBrief(alice).length, 1);
  assert.equal(restored.listBrief(bob).length, 1);
});

test("deleting a conversation also deletes its brief", () => {
  const store = new BrowserHistory(storage());
  const id = conversation(store);
  store.addBrief("graph_node", { id: "factor", label: "A factor" }, id);
  store.deleteConversation(id);
  assert.equal(store.get(id), null);
  assert.deepEqual(store.listBrief(id), []);
});

test("bounded history evicts the oldest conversation and its pins", () => {
  const store = new BrowserHistory(storage());
  const old = conversation(store, "Old");
  store.addBrief("data", { value: 0 }, old);
  for (let i = 0; i < MAX_CONVERSATIONS; i++) conversation(store, "Question " + i);
  assert.equal(store.list().length, MAX_CONVERSATIONS);
  assert.equal(store.get(old), null);
  assert.deepEqual(store.listBrief(old), []);
});

test("clear removes only this app's history, preserving language preference", () => {
  const backing = storage();
  backing.setItem("arm_lang", "fr");
  const store = new BrowserHistory(backing);
  conversation(store);
  store.clear();
  assert.equal(backing.getItem(STORAGE_KEY), null);
  assert.equal(backing.getItem("arm_lang"), "fr");
  assert.equal(new BrowserHistory(backing).list().length, 0);
});

test("blocked or corrupt browser storage falls back to page memory", () => {
  for (const backing of [
    { getItem() { throw new Error("blocked"); } },
    { getItem() { return "{broken"; } },
    { getItem() { return null; }, setItem() { throw new Error("blocked"); } },
  ]) {
    const notices = [];
    const store = new BrowserHistory(backing, (reason) => notices.push(reason));
    const id = conversation(store);
    assert.equal(store.get(id).messages.length, 2);
    assert.ok(notices.includes("unavailable"));
  }
});

test("quota failures preserve current chat in memory and display a notice", () => {
  const backing = storage();
  backing.setItem = () => { const error = new Error("full"); error.name = "QuotaExceededError"; throw error; };
  const notices = [];
  const store = new BrowserHistory(backing, (reason) => notices.push(reason));
  const id = conversation(store);
  assert.equal(store.get(id).messages[0].content, "Question");
  assert.ok(notices.includes("unavailable"));
});

test("brief export preserves zero-valued observations and source provenance", () => {
  const store = new BrowserHistory(storage());
  const id = conversation(store);
  store.addBrief("data", { indicator_label: "Deaths", country_name: "Lebanon", year: 2024, value: 0, source_name: "UCDP", retrieved_at: "2026-09-01T00:00:00Z" }, id);
  assert.match(store.exportBrief(id), /2024: 0/);
  assert.match(store.exportBrief(id), /UCDP, retrieved 2026-09-01/);
});
