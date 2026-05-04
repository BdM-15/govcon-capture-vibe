window.theseusOpenPalette = function theseusOpenPalette(app) {
  app.palette.open = true;
  app.palette.query = "";
  app.palette.cursor = 0;
  app.loadWorkspaceList();
  app.$nextTick(() => {
    app.$refs.paletteInput?.focus();
    lucide.createIcons();
  });
};

window.theseusPaletteResults = function theseusPaletteResults(app) {
  const query = (app.palette.query || "").trim().toLowerCase();
  const items = [];

  app.navGroups
    .flatMap((group) => group.items)
    .forEach((navItem) =>
      items.push({
        key: "view:" + navItem.id,
        kind: "view",
        label: navItem.label,
        hint: "Open " + navItem.label,
        icon: navItem.icon,
        action: () => {
          app.active = navItem.id;
        },
      }),
    );

  const activeWorkspace = (app.stats && app.stats.workspace) || "";
  (app.wsModal.items || []).forEach((workspace) => {
    const isActive = workspace.name === activeWorkspace;
    items.push({
      key: "ws:" + workspace.name,
      kind: "workspace",
      label: isActive
        ? `${workspace.name}  (active)`
        : `Switch to: ${workspace.name}`,
      hint: isActive
        ? "Current workspace — already loaded"
        : `Restart server with workspace "${workspace.name}"`,
      icon: isActive ? "check-circle" : "layers",
      action: () => {
        if (isActive) return;
        app.switchWorkspace(workspace.name);
      },
    });
  });

  items.push({
    key: "ws:manage",
    kind: "workspace",
    label: "Manage workspaces…",
    hint: "Open workspace picker (create, switch, inspect)",
    icon: "settings-2",
    action: () => app.openWorkspaceModal(),
  });

  items.push({
    key: "act:newchat",
    kind: "action",
    label: "New capture chat",
    hint: "Start a fresh Shipley-mentor chat",
    icon: "message-square-plus",
    action: () => app.newChat(),
  });
  items.push({
    key: "act:upload",
    kind: "action",
    label: "Upload RFP",
    hint: "Open the documents view",
    icon: "upload-cloud",
    action: () => {
      app.active = "documents";
    },
  });
  items.push({
    key: "act:scan",
    kind: "action",
    label: "Scan inputs/<workspace>/",
    hint: "Trigger /scan-rfp",
    icon: "folder-search",
    action: () => app.scanRfp(),
  });
  items.push({
    key: "act:refresh",
    kind: "action",
    label: "Refresh all",
    hint: "Reload stats / docs / chats",
    icon: "refresh-cw",
    action: () => app.refreshAll(),
  });

  (app.chats || []).slice(0, 8).forEach((chat) =>
    items.push({
      key: "chat:" + chat.id,
      kind: "chat",
      label: chat.title || "(untitled)",
      hint: `${chat.message_count} msgs · ${chat.mode}`,
      icon: "message-square",
      action: () => {
        app.openChat(chat.id);
        app.active = "chat";
      },
    }),
  );

  (app.promptLibrary || []).forEach((prompt) =>
    items.push({
      key: "prompt:" + prompt.title,
      kind: "prompt",
      label: prompt.title,
      hint: `Phase ${prompt.phase} · ${prompt.prompt.slice(0, 60)}…`,
      icon: "wand-sparkles",
      action: () => {
        app.composer = prompt.prompt;
        app.newChat();
      },
    }),
  );

  if (!query) return items.slice(0, 12);
  return items
    .filter(
      (item) =>
        item.label.toLowerCase().includes(query) ||
        (item.hint || "").toLowerCase().includes(query),
    )
    .slice(0, 20);
};

window.theseusRunPaletteAction = function theseusRunPaletteAction(app, item) {
  if (!item) return;
  app.palette.open = false;
  try {
    item.action();
  } catch (error) {
    app.toast("Action failed: " + error.message, "error");
  }
};