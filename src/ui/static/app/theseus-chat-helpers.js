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
    window.theseusClearChatHistoryUi(app);
    app.currentChat = await app.api(`/api/ui/chats/${id}`);
    window.theseusRenderMdCache = {};
  } catch (error) {
    app.toast("Could not open chat", "error");
  }
};

window.theseusChatRelativeTime = function theseusChatRelativeTime(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
};

window.theseusFilteredChats = function theseusFilteredChats(app) {
  const query = (app.chatHistory?.filter || "").trim().toLowerCase();
  if (!query) return app.chats || [];
  return (app.chats || []).filter((chat) => {
    const title = (chat.title || "").toLowerCase();
    const mode = (chat.mode || "").toLowerCase();
    return title.includes(query) || mode.includes(query);
  });
};

window.theseusClearChatHistoryUi = function theseusClearChatHistoryUi(app) {
  if (!app.chatHistory) return;
  app.chatHistory.deletePendingId = null;
  app.chatHistory.editingId = null;
  app.chatHistory.editingTitle = "";
};

window.theseusRequestDeleteChat = function theseusRequestDeleteChat(app, id) {
  window.theseusClearChatHistoryUi(app);
  app.chatHistory.deletePendingId = id;
};

window.theseusCancelDeleteChat = function theseusCancelDeleteChat(app) {
  app.chatHistory.deletePendingId = null;
};

window.theseusConfirmDeleteChat = async function theseusConfirmDeleteChat(
  app,
  id,
) {
  try {
    await app.api(`/api/ui/chats/${id}`, { method: "DELETE" });
    if (app.currentChat?.id === id) app.currentChat = null;
    app.chatHistory.deletePendingId = null;
    await app.loadChats();
    await app.loadStats();
    app.toast("Chat deleted");
  } catch (error) {
    app.toast("Delete failed: " + error.message, "error");
  }
};

window.theseusDeleteChat = async function theseusDeleteChat(app, id) {
  window.theseusRequestDeleteChat(app, id);
};

window.theseusStartRenameChat = function theseusStartRenameChat(app, chat) {
  if (!chat) return;
  window.theseusClearChatHistoryUi(app);
  app.chatHistory.editingId = chat.id;
  app.chatHistory.editingTitle = chat.title || "";
  app.$nextTick(() => {
    const input = document.querySelector(
      `[data-chat-rename-input="${chat.id}"]`,
    );
    if (input) {
      input.focus();
      input.select();
    }
  });
};

window.theseusCancelRenameChat = function theseusCancelRenameChat(app) {
  app.chatHistory.editingId = null;
  app.chatHistory.editingTitle = "";
};

window.theseusSaveChatTitle = async function theseusSaveChatTitle(
  app,
  chatId,
  title,
) {
  const nextTitle = (title || "").trim();
  if (!nextTitle) {
    app.toast("Title cannot be empty", "error");
    return false;
  }
  const existing = (app.chats || []).find((chat) => chat.id === chatId);
  if (existing && (existing.title || "").trim() === nextTitle) {
    app.chatHistory.editingId = null;
    app.chatHistory.editingTitle = "";
    if (app.currentChat?.id === chatId) {
      app.currentChat.title = nextTitle;
    }
    return true;
  }
  try {
    await app.api(`/api/ui/chats/${chatId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: nextTitle }),
    });
    if (app.currentChat?.id === chatId) {
      app.currentChat.title = nextTitle;
    }
    app.chatHistory.editingId = null;
    app.chatHistory.editingTitle = "";
    await app.loadChats();
    return true;
  } catch (error) {
    app.toast("Rename failed: " + error.message, "error");
    return false;
  }
};

window.theseusSaveSidebarRename = async function theseusSaveSidebarRename(
  app,
  chatId,
) {
  if (app.chatHistory.editingId !== chatId) return false;
  return window.theseusSaveChatTitle(
    app,
    chatId,
    app.chatHistory.editingTitle,
  );
};

window.theseusRenameChat = async function theseusRenameChat(app) {
  if (!app.currentChat) return;
  await window.theseusSaveChatTitle(
    app,
    app.currentChat.id,
    app.currentChat.title,
  );
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
  app.chatStatus = {
    phase: null,
    label: "",
    retrieve_ms: null,
    source_counts: null,
  };
  app.streamLiveContent = "";
  app.streamLiveHtml = "";
  app.thinkElapsed = 0;
  app.thinkStartedAt = null;
  if (app.thinkTimer) {
    clearInterval(app.thinkTimer);
    app.thinkTimer = null;
  }
};

const theseusResolveSendMode = function theseusResolveSendMode(app) {
  const chatMode = app.currentChat?.mode || "mix";
  if (app.composerBypassOnce) {
    return { mode: "bypass", modeOverride: chatMode !== "bypass" };
  }
  return { mode: chatMode, modeOverride: false };
};

const theseusBeginChatSend = function theseusBeginChatSend(
  app,
  content,
  sendMeta = {},
) {
  const { mode = app.currentChat?.mode || "mix", modeOverride = false } =
    sendMeta;
  app.composer = "";
  app.composerBypassOnce = false;
  app.sending = true;
  theseusResetChatStreamState(app);

  const userMsg = {
    role: "user",
    content,
    ts: new Date().toISOString(),
    mode,
  };
  if (modeOverride) userMsg.mode_override = true;
  app.currentChat.messages.push(userMsg);
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
  const sendMeta = theseusResolveSendMode(app);
  let live = theseusBeginChatSend(app, content, sendMeta);

  const payload = { content };
  if (sendMeta.modeOverride) {
    payload.mode = sendMeta.mode;
  }

  const controller = new AbortController();
  app.chatAbort = controller;
  try {
    const resp = await fetch(`/api/ui/chats/${chatId}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let scrollPending = false;
    let pendingTokenText = "";
    let tokenFlushRaf = null;
    let streamContent = "";
    let streamMdTimer = null;
    const liveMsgIdx = () =>
      app.currentChat?.messages ? app.currentChat.messages.length - 1 : 0;
    const finalizeRenderedHtml = (text, msgIdx) => {
      if (!text) return "";
      if (window.theseusRenderMdCache) {
        Object.keys(window.theseusRenderMdCache).forEach((key) => {
          if (key.startsWith(`${msgIdx}:`)) delete window.theseusRenderMdCache[key];
        });
      }
      return window.theseusRenderMd(text, msgIdx);
    };
    const scheduleStreamMarkdown = () => {
      if (streamMdTimer != null) return;
      streamMdTimer = setTimeout(() => {
        streamMdTimer = null;
        if (!streamContent) {
          app.streamLiveHtml = "";
          return;
        }
        app.streamLiveHtml = window.theseusRenderMd(streamContent, null, {
          light: true,
        });
      }, 400);
    };
    const scheduleScroll = () => {
      if (scrollPending) return;
      scrollPending = true;
      requestAnimationFrame(() => {
        scrollPending = false;
        const el = app.$refs.msgs;
        if (el) el.scrollTop = el.scrollHeight;
      });
    };
    const flushPendingTokens = () => {
      tokenFlushRaf = null;
      if (!pendingTokenText) return;
      streamContent += pendingTokenText;
      pendingTokenText = "";
      app.streamLiveContent = streamContent;
      scheduleStreamMarkdown();
      scheduleScroll();
    };
    const queueTokenText = (text) => {
      pendingTokenText += text;
      if (tokenFlushRaf != null) return;
      tokenFlushRaf = requestAnimationFrame(flushPendingTokens);
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
            source_counts: parsed.source_counts || app.chatStatus.source_counts,
          };
          if (
            (parsed.phase === "generating" || parsed.phase === "reasoning") &&
            !app.thinkTimer
          ) {
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
          continue;
        }

        if (event === "token" && parsed.text) {
          queueTokenText(parsed.text);
          continue;
        }

        if (event === "error") {
          flushPendingTokens();
          const errorBody =
            streamContent +
            `\n\n\u26A0\uFE0F ${parsed.message || "stream error"}`;
          live = theseusReplaceLiveChatMessage(app, live, {
            content: errorBody,
            streaming: false,
            renderedHtml: finalizeRenderedHtml(errorBody, liveMsgIdx()),
          });
          app.toast("Query failed", "error");
          continue;
        }

        if (event === "done") {
          if (tokenFlushRaf != null) {
            cancelAnimationFrame(tokenFlushRaf);
            tokenFlushRaf = null;
          }
          if (streamMdTimer != null) {
            clearTimeout(streamMdTimer);
            streamMdTimer = null;
          }
          flushPendingTokens();
          const finalContent = parsed.assistant?.content || "";
          const streamedContent = streamContent || "";
          let body = streamedContent;
          if (
            finalContent &&
            (!streamedContent ||
              streamedContent.length < finalContent.length * 0.95)
          ) {
            body = finalContent;
          }
          const msgIdx = liveMsgIdx();
          const updated = {
            streaming: false,
            streamHtml: null,
            content: body,
            renderedHtml: finalizeRenderedHtml(body, msgIdx),
          };
          if (parsed.assistant?.mode) updated.mode = parsed.assistant.mode;
          if (parsed.assistant?.timing || parsed.timing) {
            updated.timing = parsed.assistant?.timing || parsed.timing;
          }
          if (parsed.assistant?.sources) {
            updated.sources = parsed.assistant.sources;
            updated.renderedHtml = finalizeRenderedHtml(body, msgIdx);
          }
          live = theseusReplaceLiveChatMessage(app, live, updated);
        }
      }
    }
    flushPendingTokens();
    if (live.streaming !== false && streamContent) {
      const msgIdx = liveMsgIdx();
      live = theseusReplaceLiveChatMessage(app, live, {
        streaming: false,
        content: streamContent,
        renderedHtml: finalizeRenderedHtml(streamContent, msgIdx),
      });
    }
    await app.loadChats();
  } catch (error) {
    let failureContent = streamContent || live.content || "";
    if (error?.name === "AbortError") {
      failureContent += "\n\n_(stopped)_";
    } else {
      failureContent =
        failureContent || `\u26A0\uFE0F ${error?.message || "stream failed"}`;
      app.toast("Query failed", "error");
    }
    const msgIdx = liveMsgIdx();
    live = theseusReplaceLiveChatMessage(app, live, {
      content: failureContent,
      streaming: false,
      renderedHtml: finalizeRenderedHtml(failureContent, msgIdx),
    });
  } finally {
    if (streamMdTimer != null) {
      clearTimeout(streamMdTimer);
      streamMdTimer = null;
    }
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
