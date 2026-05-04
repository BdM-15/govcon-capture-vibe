window.theseusNewChat = async function theseusNewChat(app, rfpContext = null) {
  const chat = await app.api("/api/ui/chats", {
    method: "POST",
    body: JSON.stringify({
      title: "New chat",
      mode: "mix",
      rfp_context: rfpContext,
    }),
  });
  await app.loadChats();
  await app.openChat(chat.id);
  app.active = "chat";
};

window.theseusOpenChat = async function theseusOpenChat(app, id) {
  try {
    app.currentChat = await app.api(`/api/ui/chats/${id}`);
  } catch (error) {
    app.toast("Could not open chat", "error");
  }
};

window.theseusDeleteChat = async function theseusDeleteChat(app, id) {
  if (!confirm("Delete this chat?")) return;
  await app.api(`/api/ui/chats/${id}`, { method: "DELETE" });
  if (app.currentChat?.id === id) app.currentChat = null;
  await app.loadChats();
  await app.loadStats();
};

window.theseusRenameChat = async function theseusRenameChat(app) {
  if (!app.currentChat) return;
  await app.api(`/api/ui/chats/${app.currentChat.id}`, {
    method: "PATCH",
    body: JSON.stringify({ title: app.currentChat.title }),
  });
  await app.loadChats();
};

window.theseusUpdateChatMode = async function theseusUpdateChatMode(app) {
  if (!app.currentChat) return;
  await app.api(`/api/ui/chats/${app.currentChat.id}`, {
    method: "PATCH",
    body: JSON.stringify({ mode: app.currentChat.mode }),
  });
};

window.theseusCopyMessage = async function theseusCopyMessage(app, message) {
  if (!message || !message.content) return;
  try {
    await navigator.clipboard.writeText(message.content);
    app.toast("Message copied to clipboard", "info");
  } catch (error) {
    app.toast("Copy failed: " + error.message, "error");
  }
};

window.theseusEditMessage = function theseusEditMessage(app, message) {
  if (!message || message.role !== "user" || app.sending) return;
  app.composer = message.content;
  app.$nextTick(() => {
    const textarea = document.querySelector('textarea[x-model="composer"]');
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }
  });
  app.toast("Loaded into composer — edit and send", "info");
};

window.theseusRegenerateMessage = async function theseusRegenerateMessage(app, idx) {
  if (app.sending || !app.currentChat) return;
  const messages = app.currentChat.messages;
  if (idx <= 0 || idx >= messages.length) return;

  let userIdx = idx - 1;
  while (userIdx >= 0 && messages[userIdx].role !== "user") userIdx--;
  if (userIdx < 0) {
    app.toast("No prior user message to regenerate from", "error");
    return;
  }

  const userContent = messages[userIdx].content;
  messages.splice(userIdx);
  app.composer = userContent;
  await app.sendMessage();
};

window.theseusExportMessage = function theseusExportMessage(app, message, idx) {
  if (!message || !message.content) return;
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const chatTitle = (app.currentChat && app.currentChat.title) || "chat";
  const slug = chatTitle
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .slice(0, 40);

  let prompt = "";
  if (app.currentChat && idx != null) {
    for (let j = idx - 1; j >= 0; j--) {
      if (app.currentChat.messages[j].role === "user") {
        prompt = app.currentChat.messages[j].content;
        break;
      }
    }
  }

  const front =
    `---\n` +
    `chat: ${chatTitle}\n` +
    `workspace: ${(app.stats && app.stats.workspace) || ""}\n` +
    `mode: ${message.mode || (app.currentChat && app.currentChat.mode) || ""}\n` +
    `exported: ${new Date().toISOString()}\n` +
    (message.timing && message.timing.total_ms != null
      ? `total_ms: ${message.timing.total_ms}\n`
      : "") +
    `---\n\n`;
  const body =
    (prompt ? `## Question\n\n${prompt}\n\n## Answer\n\n` : "") +
    message.content +
    "\n";
  const blob = new Blob([front + body], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `theseus-${slug}-${ts}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
  app.toast("Exported as Markdown", "info");
};