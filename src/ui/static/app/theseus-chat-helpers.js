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

window.theseusScrollMessages = function theseusScrollMessages(app) {
  app.$nextTick(() => {
    const el = app.$refs.msgs;
    if (el) el.scrollTop = el.scrollHeight;
  });
};

window.theseusStopMessage = function theseusStopMessage(app) {
  if (!app.chatAbort) return;
  try {
    app.chatAbort.abort();
  } catch (_) {}
};

const theseusResetChatStreamState = function theseusResetChatStreamState(app) {
  app.chatStatus = { phase: null, label: "", retrieve_ms: null };
  app.streamLiveContent = "";
  app.thinkElapsed = 0;
  app.thinkStartedAt = null;
  if (app.thinkTimer) {
    clearInterval(app.thinkTimer);
    app.thinkTimer = null;
  }
};

const theseusBeginChatSend = function theseusBeginChatSend(app, content) {
  app.composer = "";
  app.sending = true;
  theseusResetChatStreamState(app);

  app.currentChat.messages.push({
    role: "user",
    content,
    ts: new Date().toISOString(),
  });
  app.currentChat.messages.push({
    role: "assistant",
    content: "",
    ts: new Date().toISOString(),
    streaming: true,
  });

  window.theseusScrollMessages(app);
  return app.currentChat.messages[app.currentChat.messages.length - 1];
};

const theseusReplaceLiveChatMessage = function theseusReplaceLiveChatMessage(
  app,
  live,
  patch,
) {
  const idx = app.currentChat.messages.length - 1;
  const updated = { ...live, ...patch };
  if (idx >= 0) app.currentChat.messages.splice(idx, 1, updated);
  return updated;
};

const theseusFinishChatSend = function theseusFinishChatSend(app) {
  app.sending = false;
  app.chatAbort = null;
  theseusResetChatStreamState(app);
  window.theseusScrollMessages(app);
};

const theseusPriorUserMessage = function theseusPriorUserMessage(messages, idx) {
  for (let userIdx = idx - 1; userIdx >= 0; userIdx--) {
    if (messages[userIdx].role === "user") {
      return { index: userIdx, message: messages[userIdx] };
    }
  }
  return null;
};

window.theseusSendMessage = async function theseusSendMessage(app) {
  if (!app.currentChat || !app.composer.trim() || app.sending) return;

  const content = app.composer.trim();
  const chatId = app.currentChat.id;
  let live = theseusBeginChatSend(app, content);

  const controller = new AbortController();
  app.chatAbort = controller;
  try {
    const resp = await fetch(`/api/ui/chats/${chatId}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
      signal: controller.signal,
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let scrollPending = false;
    const scheduleScroll = () => {
      if (scrollPending) return;
      scrollPending = true;
      requestAnimationFrame(() => {
        scrollPending = false;
        const el = app.$refs.msgs;
        if (el) el.scrollTop = el.scrollHeight;
      });
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;

        let parsed;
        try {
          parsed = JSON.parse(data);
        } catch {
          continue;
        }

        if (event === "status") {
          app.chatStatus = {
            phase: parsed.phase || null,
            label: parsed.label || "",
            retrieve_ms:
              parsed.retrieve_ms != null
                ? parsed.retrieve_ms
                : app.chatStatus.retrieve_ms,
          };
          if (parsed.phase === "generating" && !app.thinkTimer) {
            app.thinkStartedAt = Date.now();
            app.thinkTimer = setInterval(() => {
              app.thinkElapsed = Math.floor(
                (Date.now() - app.thinkStartedAt) / 1000,
              );
            }, 250);
          }
          continue;
        }

        if (event === "sources") {
          live = theseusReplaceLiveChatMessage(app, live, {
            sources: parsed,
            sourcesOpen: false,
          });
          continue;
        }

        if (event === "token" && parsed.text) {
          live = theseusReplaceLiveChatMessage(app, live, {
            content: (live.content || "") + parsed.text,
          });
          app.streamLiveContent = live.content;
          scheduleScroll();
          continue;
        }

        if (event === "error") {
          live = theseusReplaceLiveChatMessage(app, live, {
            content:
              (live.content || "") +
              `\n\n\u26A0\uFE0F ${parsed.message || "stream error"}`,
          });
          app.toast("Query failed", "error");
          continue;
        }

        if (event === "done") {
          const updated = {
            streaming: false,
          };
          if (parsed.assistant?.content) {
            updated.content = parsed.assistant.content;
            updated.mode = parsed.assistant.mode;
            updated.timing = parsed.assistant.timing || parsed.timing;
          }
          if (parsed.assistant?.sources) {
            updated.sources = parsed.assistant.sources;
          }
          live = theseusReplaceLiveChatMessage(app, live, updated);
        }
      }
    }
    await app.loadChats();
  } catch (error) {
    let failureContent = live.content || "";
    if (error?.name === "AbortError") {
      failureContent += "\n\n_(stopped)_";
    } else {
      failureContent =
        failureContent || `\u26A0\uFE0F ${error?.message || "stream failed"}`;
      app.toast("Query failed", "error");
    }
    live = theseusReplaceLiveChatMessage(app, live, {
      content: failureContent,
      streaming: false,
    });
  } finally {
    theseusFinishChatSend(app);
  }
};

window.theseusCopyMessage = async function theseusCopyMessage(app, message) {
  if (!message || !message.content) return;
  await window.theseusCopyText(app, message.content, {
    success: "Message copied to clipboard",
    error: "Copy failed",
    kind: "info",
  });
};

window.theseusEditMessage = function theseusEditMessage(app, message) {
  if (!message || message.role !== "user" || app.sending) return;
  window.theseusLoadComposerText(app, message.content, {
    focus: true,
    placeCaretEnd: true,
    toastMessage: "Loaded into composer — edit and send",
  });
};

window.theseusRegenerateMessage = async function theseusRegenerateMessage(
  app,
  idx,
) {
  if (app.sending || !app.currentChat) return;
  const messages = app.currentChat.messages;
  if (idx <= 0 || idx >= messages.length) return;

  const priorUser = theseusPriorUserMessage(messages, idx);
  if (!priorUser) {
    app.toast("No prior user message to regenerate from", "error");
    return;
  }

  const userContent = priorUser.message.content;
  messages.splice(priorUser.index);
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
    prompt =
      theseusPriorUserMessage(app.currentChat.messages, idx)?.message.content ||
      "";
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

window.theseusLoadChats = async function theseusLoadChats(app) {
  try {
    const response = await app.api("/api/ui/chats");
    app.chats = response.chats || [];
  } catch {
    app.chats = [];
  }
};
