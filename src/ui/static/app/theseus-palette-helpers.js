window.theseusOpenPalette = function theseusOpenPalette(app) {
  app.palette.open = true;
  app.palette.query = "";
  app.palette.cursor = 0;
  app.loadWorkspaceList();
  window.theseusAfterRender(app, () => {
    app.$refs.paletteInput?.focus();
  });
};

const theseusPaletteItem = function theseusPaletteItem(options) {
  return {
    key: options.key,
    kind: options.kind,
    label: options.label,
    hint: options.hint,
    icon: options.icon,
    action: options.action,
  };
};

const theseusPaletteActionDescriptors = function theseusPaletteActionDescriptors(
  app,
) {
  return [
    {
      key: "ws:manage",
      kind: "workspace",
      label: "Manage workspaces…",
      hint: "Open workspace picker (create, switch, inspect)",
      icon: "settings-2",
      action: () => app.openWorkspaceModal(),
    },
    {
      key: "act:newchat",
      kind: "action",
      label: "New capture chat",
      hint: "Start a fresh Shipley-mentor chat",
      icon: "message-square-plus",
      action: () => app.newChat(),
    },
    {
      key: "act:upload",
      kind: "action",
      label: "Upload RFP",
      hint: "Open the documents view",
      icon: "upload-cloud",
      action: () => {
        app.active = "documents";
      },
    },
    {
      key: "act:scan",
      kind: "action",
      label: "Scan inputs/<workspace>/",
      hint: "Trigger /scan-rfp",
      icon: "folder-search",
      action: () => app.scanRfp(),
    },
    {
      key: "act:refresh",
      kind: "action",
      label: "Refresh all",
      hint: "Reload stats / docs / chats",
      icon: "refresh-cw",
      action: () => app.refreshAll(),
    },
  ];
};

const theseusPaletteMatchesQuery = function theseusPaletteMatchesQuery(
  item,
  query,
) {
  return (
    item.label.toLowerCase().includes(query) ||
    (item.hint || "").toLowerCase().includes(query)
  );
};

window.theseusPaletteResults = function theseusPaletteResults(app) {
  const query = (app.palette.query || "").trim().toLowerCase();
  const items = [];

  app.navGroups
    .flatMap((group) => group.items)
    .forEach((navItem) =>
      items.push(
        theseusPaletteItem({
          key: "view:" + navItem.id,
          kind: "view",
          label: navItem.label,
          hint: "Open " + navItem.label,
          icon: navItem.icon,
          action: () => {
            app.active = navItem.id;
          },
        }),
      ),
    );

  const activeWorkspace = (app.stats && app.stats.workspace) || "";
  (app.wsModal.items || []).forEach((workspace) => {
    const isActive = workspace.name === activeWorkspace;
    items.push(
      theseusPaletteItem({
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
      }),
    );
  });

  theseusPaletteActionDescriptors(app).forEach((item) => items.push(item));

  (app.chats || []).slice(0, 8).forEach((chat) =>
    items.push(
      theseusPaletteItem({
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
    ),
  );

  (app.promptLibrary || []).forEach((prompt) =>
    items.push(
      theseusPaletteItem({
        key: "prompt:" + prompt.title,
        kind: "prompt",
        label: prompt.title,
        hint: `Phase ${prompt.phase} · ${prompt.prompt.slice(0, 60)}…`,
        icon: "wand-sparkles",
        action: () => {
          window.theseusStartChatWithComposer(app, prompt.prompt);
        },
      }),
    ),
  );

  if (!query) return items.slice(0, 12);
  return items.filter((item) => theseusPaletteMatchesQuery(item, query)).slice(0, 20);
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
