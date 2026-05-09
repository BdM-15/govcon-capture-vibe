window.createTheseusAppDelegates = function createTheseusAppDelegates() {
  return {
    navTitle() {
      return window.theseusNavTitle(this.active);
    },

    navIcon() {
      return window.theseusNavIcon(this.navGroups, this.active);
    },

    navSubtitle() {
      return window.theseusNavSubtitle(this.active, this.stats);
    },

    greeting() {
      return window.theseusGreeting();
    },

    metrics() {
      return window.theseusMetrics(this.stats);
    },

    ariadneMetrics() {
      return window.theseusAriadneMetrics(this);
    },

    ariadneMorningBrief() {
      return window.theseusAriadneMorningBrief(this);
    },

    ariadneWorkspaceRows() {
      return window.theseusAriadneWorkspaceRows(this);
    },

    ariadneQueueItems(bucket = "inbox", limit = 4) {
      return window.theseusAriadneQueueItems(this, bucket, limit);
    },

    ariadneActionQueue(limit = 12) {
      return window.theseusAriadneActionQueue(this, limit);
    },

    ariadnePromoteOptions() {
      return window.theseusAriadnePromoteOptions(this);
    },

    ariadneStage(row) {
      return window.theseusAriadneStage(row);
    },

    ariadneStageClass(row) {
      return window.theseusAriadneStageClass(row);
    },

    async loadAriadne() {
      return window.theseusLoadAriadne(this);
    },

    async submitAriadneCapture() {
      return window.theseusSubmitAriadneCapture(this);
    },

    async promoteAriadneNote(path) {
      return window.theseusPromoteAriadneNote(this, path);
    },

    async activateAriadneWorkspace(name) {
      return window.theseusActivateAriadneWorkspace(this, name);
    },

    async ariadneAsk(prompt) {
      return window.theseusAriadneAsk(this, prompt);
    },

    async init() {
      return window.theseusInit(this);
    },

    async refreshAll() {
      return window.theseusRefreshAll(this);
    },

    async api(path, opts = {}) {
      return window.theseusApi(path, opts);
    },

    toast(msg, kind = "ok") {
      return window.theseusToast(this, msg, kind);
    },

    async checkHealth() {
      return window.theseusCheckHealth(this);
    },

    async loadStats() {
      return window.theseusLoadStats(this);
    },

    openProcLog() {
      return window.theseusOpenProcLog(this);
    },

    closeProcLog() {
      return window.theseusCloseProcLog(this);
    },

    clearProcLog() {
      return window.theseusClearProcLog(this);
    },

    filteredProcLog() {
      return window.theseusFilteredProcLog(this);
    },

    _scrollProcLog() {
      return window.theseusScrollProcLog(this);
    },

    async loadDocuments() {
      return window.theseusLoadDocuments(this);
    },

    async uploadFiles(fileList) {
      return window.theseusUploadFiles(this, fileList);
    },

    async stageFiles(fileList) {
      return window.theseusStageFiles(this, fileList);
    },

    async scanRfp() {
      return window.theseusScanRfp(this);
    },

    async loadDocStats() {
      return window.theseusLoadDocStats(this);
    },

    startDocStatsPoll() {
      return window.theseusStartDocStatsPoll(this);
    },

    stopDocStatsPoll() {
      return window.theseusStopDocStatsPoll(this);
    },

    async cancelPipeline() {
      return window.theseusCancelPipeline(this);
    },

    async reprocessFailed() {
      return window.theseusReprocessFailed(this);
    },

    async deleteDocument(doc) {
      return window.theseusDeleteDocument(this, doc);
    },

    filteredDocuments() {
      return window.theseusFilteredDocuments(this);
    },

    async clearLlmCache() {
      return window.theseusClearLlmCache(this);
    },

    async clearAllDocuments() {
      return window.theseusClearAllDocuments(this);
    },

    settingsExpandAll() {
      return window.theseusSettingsExpandAll();
    },

    settingsCollapseAll() {
      return window.theseusSettingsCollapseAll();
    },

    askAbout(doc) {
      return window.theseusAskAboutDocument(this, doc);
    },

    async loadChats() {
      return window.theseusLoadChats(this);
    },

    async loadPromptLibrary() {
      return window.theseusLoadPromptLibrary(this);
    },

    async loadSkills(force = false) {
      return window.theseusLoadSkills(this, force);
    },

    async loadStudio() {
      return window.theseusLoadStudio(this);
    },

    async loadChains() {
      return window.theseusLoadChains(this);
    },

    async openChain(chainId) {
      return window.theseusOpenChain(this, chainId);
    },

    chainSteps(chain) {
      return window.theseusChainSteps(chain);
    },

    chainStatusClass(status) {
      return window.theseusChainStatusClass(status);
    },

    chainArtifactCount(chain) {
      return window.theseusChainArtifactCount(chain);
    },

    chainCanResume(chain) {
      return window.theseusChainCanResume(chain);
    },

    chainInputRequest(chain) {
      return window.theseusChainInputRequest(chain);
    },

    chainResumePlaceholder(chain) {
      return window.theseusChainResumePlaceholder(chain);
    },

    mountChainInputPanel(el) {
      return window.theseusMountChainInputPanel(this, el);
    },

    async rerunChain(chainId) {
      return window.theseusRerunChain(this, chainId);
    },

    async resumeChain(chainId) {
      return window.theseusResumeChain(this, chainId);
    },

    async openChainStepRun(step) {
      return window.theseusOpenChainStepRun(this, step);
    },

    primaryChain(deliverable) {
      return window.theseusPrimaryChain(deliverable);
    },

    studioHasChain(deliverable) {
      return window.theseusStudioHasChain(deliverable);
    },

    async openStudioChainTrace(deliverable) {
      return window.theseusOpenStudioChainTrace(this, deliverable);
    },

    closeStudioChainTrace() {
      return window.theseusCloseStudioChainTrace(this);
    },

    async rerunStudioChain(deliverable) {
      return window.theseusRerunStudioChain(this, deliverable);
    },

    async resumeStudioChain(deliverable) {
      return window.theseusResumeStudioChain(this, deliverable);
    },

    async planStudioChainGoal() {
      return window.theseusPlanStudioChainGoal(this);
    },

    async runStudioChainGoal() {
      return window.theseusRunStudioChainGoal(this);
    },

    studioChainPlanSteps() {
      return window.theseusStudioChainPlanSteps(this);
    },

    toggleStudioTrash() {
      return window.theseusToggleStudioTrash(this);
    },

    async emptyStudioTrash() {
      return window.theseusEmptyStudioTrash(this);
    },

    async restoreTrashedStudioArtifact(artifact) {
      return window.theseusRestoreTrashedStudioArtifact(this, artifact);
    },

    studioSkillOptions() {
      return window.theseusStudioSkillOptions(this);
    },

    studioFormatOptions() {
      return window.theseusStudioFormatOptions(this);
    },

    studioFiltered() {
      return window.theseusStudioFiltered(this);
    },

    studioGrouped() {
      return window.theseusStudioGrouped(this);
    },

    studioRenderableRows() {
      return window.theseusStudioRenderableRows(this);
    },

    studioSelectedCount() {
      return window.theseusStudioSelectedCount(this);
    },

    studioAllFilteredSelected() {
      return window.theseusStudioAllFilteredSelected(this);
    },

    toggleStudioSelection(deliverable) {
      return window.theseusToggleStudioSelection(this, deliverable);
    },

    toggleStudioSelectAllFiltered() {
      return window.theseusToggleStudioSelectAllFiltered(this);
    },

    clearStudioSelection() {
      return window.theseusClearStudioSelection(this);
    },

    pruneStudioSelectionToFiltered() {
      return window.theseusPruneStudioSelectionToFiltered(this);
    },

    async deleteSelectedStudioArtifacts() {
      return window.theseusDeleteSelectedStudioArtifacts(this);
    },

    async downloadSelectedStudioZip() {
      return window.theseusDownloadSelectedStudioZip(this);
    },

    studioDownloadHref(deliverable) {
      return window.theseusStudioDownloadHref(deliverable);
    },

    studioOpenRun(deliverable) {
      return window.theseusStudioOpenRun(this, deliverable);
    },

    studioKey(deliverable) {
      return window.theseusStudioKey(deliverable);
    },

    isStudioPinned(deliverable) {
      return window.theseusIsStudioPinned(this, deliverable);
    },

    toggleStudioPin(deliverable) {
      return window.theseusToggleStudioPin(this, deliverable);
    },

    _loadStudioPinned() {
      return window.theseusLoadStudioPinned(this);
    },

    _ensureScript(url) {
      return window.theseusEnsureScript(this, url);
    },

    _studioFormatFor(deliverable) {
      return window.theseusStudioFormatFor(deliverable);
    },

    async openStudioPreview(deliverable) {
      return window.theseusOpenStudioPreview(this, deliverable);
    },

    closeStudioPreview() {
      return window.theseusCloseStudioPreview(this);
    },

    studioSetSheet(index) {
      return window.theseusStudioSetSheet(this, index);
    },

    studioPreviewArtifacts() {
      return window.theseusStudioPreviewArtifacts(this);
    },

    studioPreviewHistory() {
      return window.theseusStudioPreviewHistory(this);
    },

    studioPreviewCanCompare() {
      return window.theseusStudioPreviewCanCompare(this);
    },

    async studioPreviewCompareVersion(deliverable) {
      return window.theseusStudioPreviewCompareVersion(this, deliverable);
    },

    studioPreviewClearCompare() {
      return window.theseusStudioPreviewClearCompare(this);
    },

    _extractJsonChunkIds(text) {
      return window.theseusExtractJsonChunkIds(text);
    },

    async openReasoning(deliverable) {
      return window.theseusOpenReasoning(this, deliverable);
    },

    closeReasoning() {
      return window.theseusCloseReasoning(this);
    },

    toggleReasoningStep(index) {
      return window.theseusToggleReasoningStep(this, index);
    },

    reasoningArtifacts() {
      return window.theseusReasoningArtifacts(this);
    },

    reasoningArtifactDownloadHref(artifact) {
      return window.theseusReasoningArtifactDownloadHref(this, artifact);
    },

    async openReasoningArtifactPreview(artifact) {
      return window.theseusOpenReasoningArtifactPreview(this, artifact);
    },

    async promoteReasoningArtifact(artifact) {
      return window.theseusPromoteReasoningArtifact(this, artifact);
    },

    reasoningStepIcon(kind) {
      return window.theseusReasoningStepIcon(kind);
    },

    reasoningPrettyJson(value) {
      return window.theseusPrettyJson(value);
    },

    copyToClipboard(text) {
      return window.theseusCopyToClipboard(this, text);
    },

    async fetchChunk(chunkId) {
      return window.theseusFetchChunk(this, chunkId);
    },

    async openChunkPreview(chunkId) {
      return window.theseusOpenChunkPreview(this, chunkId);
    },

    closeChunkPreview() {
      return window.theseusCloseChunkPreview(this);
    },

    skillPersonaConfig() {
      return window.createTheseusSkillPersonaConfig();
    },

    skillPersonaFilterConfig() {
      return window.createTheseusSkillPersonaFilterConfig();
    },

    skillPhaseConfig() {
      return window.createTheseusSkillPhaseConfig();
    },

    skillCapabilityConfig() {
      return window.createTheseusSkillCapabilityConfig();
    },

    isMetaSkill(skill) {
      return window.theseusIsMetaSkill(skill);
    },

    skillMatchesFilters(skill) {
      return window.theseusSkillMatchesFilters(this, skill);
    },

    skillsFiltered() {
      return window.theseusSkillsFiltered(this);
    },

    skillsCountForPersona(id) {
      return window.theseusSkillsCountForPersona(this, id);
    },

    skillsCountForPhase(id) {
      return window.theseusSkillsCountForPhase(this, id);
    },

    skillsCountForCapability(id) {
      return window.theseusSkillsCountForCapability(this, id);
    },

    toggleSkillPersona(id) {
      return window.theseusToggleSkillPersona(this, id);
    },

    toggleSkillPhase(id) {
      return window.theseusToggleSkillPhase(this, id);
    },

    toggleSkillCapability(id) {
      return window.theseusToggleSkillCapability(this, id);
    },

    clearSkillFilters() {
      return window.theseusClearSkillFilters(this);
    },

    personaLabel(id) {
      return window.theseusPersonaLabel(this, id);
    },

    async openSkill(name) {
      return window.theseusOpenSkill(this, name);
    },

    async invokeSkill() {
      return window.theseusInvokeSkill(this);
    },

    async loadSkillRuns(name) {
      return window.theseusLoadSkillRuns(this, name);
    },

    async loadSkillRunTrash(name) {
      return window.theseusLoadSkillRunTrash(this, name);
    },

    formatBytes(value) {
      return window.theseusFormatBytes(value);
    },

    artifactIcon(mime, name) {
      return window.theseusArtifactIcon(mime, name);
    },

    async loadSkillRun(name, runId) {
      return window.theseusLoadSkillRun(this, name, runId);
    },

    skillRunInputRequest(run) {
      return window.theseusSkillRunInputRequest(run);
    },

    skillRunCanResume(run) {
      return window.theseusSkillRunCanResume(run);
    },

    skillRunResumePlaceholder(run) {
      return window.theseusSkillRunResumePlaceholder(run);
    },

    mountSkillRunInputPanel(el) {
      return window.theseusMountSkillRunInputPanel(this, el);
    },

    async resumeSkillRun(name, runId) {
      return window.theseusResumeSkillRun(this, name, runId);
    },

    async deleteSkillRun(name, runId) {
      return window.theseusDeleteSkillRun(this, name, runId);
    },

    async emptySkillRunTrash(name) {
      return window.theseusEmptySkillRunTrash(this, name);
    },

    toggleSkillRunTrash() {
      return window.theseusToggleSkillRunTrash(this);
    },

    async restoreSkillRun(name, trashId) {
      return window.theseusRestoreSkillRun(this, name, trashId);
    },

    async installSkill() {
      return window.theseusInstallSkill(this);
    },

    async uninstallSkill() {
      return window.theseusUninstallSkill(this);
    },

    filteredPrompts() {
      return window.theseusFilteredPrompts(this);
    },

    promptPhases() {
      return window.theseusPromptPhases(this);
    },

    _phaseMeta() {
      return window.theseusPromptPhaseMeta();
    },

    phaseLabel(id) {
      return window.theseusPhaseLabel(id);
    },

    phasePillClass(id) {
      return window.theseusPhasePillClass(id);
    },

    usePrompt(prompt) {
      return window.theseusUsePrompt(this, prompt);
    },

    async copyPrompt(prompt) {
      return window.theseusCopyPrompt(this, prompt);
    },

    openPromptPicker() {
      return window.theseusOpenPromptPicker(this);
    },

    usePromptFromPicker(prompt) {
      return window.theseusUsePromptFromPicker(this, prompt);
    },

    pickerPhases() {
      return window.theseusPickerPhases(this);
    },

    async newChat(rfpContext = null) {
      return window.theseusNewChat(this, rfpContext);
    },

    async openChat(id) {
      return window.theseusOpenChat(this, id);
    },

    async deleteChat(id) {
      return window.theseusDeleteChat(this, id);
    },

    async renameChat() {
      return window.theseusRenameChat(this);
    },

    async updateMode() {
      return window.theseusUpdateChatMode(this);
    },

    async copyMessage(message) {
      return window.theseusCopyMessage(this, message);
    },

    editMessage(message) {
      return window.theseusEditMessage(this, message);
    },

    async regenerateMessage(index) {
      return window.theseusRegenerateMessage(this, index);
    },

    exportMessage(message, index) {
      return window.theseusExportMessage(this, message, index);
    },

    async sendMessage() {
      return window.theseusSendMessage(this);
    },

    stopMessage() {
      return window.theseusStopMessage(this);
    },

    renderMd(text, msgIdx) {
      return window.theseusRenderMd(text, msgIdx);
    },

    enhanceCitations(html, msgIdx) {
      return window.theseusEnhanceCitations(html, msgIdx);
    },

    handleCiteClick(event) {
      return window.theseusHandleCiteClick(this, event);
    },

    _scrollToRefList(index, refNumber) {
      return window.theseusScrollToRefList(this, index, refNumber);
    },

    toggleSources(index, forceOpen) {
      return window.theseusToggleSources(this, index, forceOpen);
    },

    basename(path) {
      return window.theseusBasename(path);
    },

    memoryLabel() {
      return window.theseusMemoryLabel(this.stats, this.currentChat);
    },

    formatSource(source) {
      return window.theseusFormatSource(source);
    },

    scrollMsgs() {
      return window.theseusScrollMessages(this);
    },

    entityColor(type) {
      return window.theseusEntityColor(type);
    },

    async searchLabels() {
      return window.theseusSearchLabels(this);
    },

    async loadGraph() {
      return window.theseusLoadGraph(this);
    },

    loadGraphFromNode(id) {
      return window.theseusLoadGraphFromNode(this, id);
    },

    renderGraph(nodes, edges) {
      return window.theseusRenderGraph(this, nodes, edges);
    },

    layoutOptions() {
      return window.theseusGraphLayoutOptions(this);
    },

    relayout() {
      return window.theseusRelayoutGraph(this);
    },

    fitGraph() {
      return window.theseusFitGraph(this);
    },

    exportPng() {
      return window.theseusExportGraphPng(this);
    },

    toggleTypeFilter(type) {
      return window.theseusToggleGraphTypeFilter(this, type);
    },

    applyFilters() {
      return window.theseusApplyGraphFilters(this);
    },

    async selectNode(node) {
      return window.theseusSelectGraphNode(this, node);
    },

    askAboutEntity(entity) {
      return window.theseusAskAboutEntity(this, entity);
    },

    async loadWorkspaceList(silent = true) {
      return window.theseusLoadWorkspaceList(this, silent);
    },

    async openWorkspaceModal() {
      return window.theseusOpenWorkspaceModal(this);
    },

    async switchWorkspace(name, create = false) {
      return window.theseusSwitchWorkspace(this, name, create);
    },

    async restartServer() {
      return window.theseusRestartServer(this);
    },

    async loadWorkspaceInventory() {
      return window.theseusLoadWorkspaceInventory(this);
    },

    openDeleteModal(workspace) {
      return window.theseusOpenDeleteModal(this, workspace);
    },

    closeDeleteModal() {
      return window.theseusCloseDeleteModal(this);
    },

    deleteModalSelectAll() {
      return window.theseusDeleteModalSelectAll(this);
    },

    deleteModalClearAll() {
      return window.theseusDeleteModalClearAll(this);
    },

    canSubmitDelete() {
      return window.theseusCanSubmitDelete(this);
    },

    async submitWorkspaceDelete() {
      return window.theseusSubmitWorkspaceDelete(this);
    },

    openWipeAllModal() {
      return window.theseusOpenWipeAllModal(this);
    },

    closeWipeAllModal() {
      return window.theseusCloseWipeAllModal(this);
    },

    canSubmitWipeAll() {
      return window.theseusCanSubmitWipeAll(this);
    },

    async submitWipeAll() {
      return window.theseusSubmitWipeAll(this);
    },

    async loadQuerySettings() {
      return window.theseusLoadQuerySettings(this);
    },

    async saveQuerySettings() {
      return window.theseusSaveQuerySettings(this);
    },

    async resetQuerySettings() {
      return window.theseusResetQuerySettings(this);
    },

    async loadSkillSettings() {
      return window.theseusLoadSkillSettings(this);
    },

    async loadSkillRuntimeSettings() {
      return window.theseusLoadSkillRuntimeSettings(this);
    },

    async saveSkillSettings() {
      return window.theseusSaveSkillSettings(this);
    },

    async saveSkillRuntimeSettings() {
      return window.theseusSaveSkillRuntimeSettings(this);
    },

    async resetSkillSettings() {
      return window.theseusResetSkillSettings(this);
    },

    async resetSkillRuntimeSettings() {
      return window.theseusResetSkillRuntimeSettings(this);
    },

    async loadMcps() {
      return window.theseusLoadMcps(this);
    },

    async saveMcpKeys(name) {
      return window.theseusSaveMcpKeys(this, name);
    },

    async testMcp(name) {
      return window.theseusTestMcp(this, name);
    },

    pollRestart() {
      return window.theseusPollRestart(this);
    },

    openPalette() {
      return window.theseusOpenPalette(this);
    },

    paletteResults() {
      return window.theseusPaletteResults(this);
    },

    runPaletteAction(item) {
      return window.theseusRunPaletteAction(this, item);
    },

    async loadIntel() {
      return window.theseusLoadIntel(this);
    },

    filteredLmRows() {
      return window.theseusFilteredLmRows(this);
    },

    orphanFactors() {
      return window.theseusOrphanFactors(this);
    },

    filteredTrace() {
      return window.theseusFilteredTrace(this);
    },

    coverageBadgeClass(score) {
      return window.theseusCoverageBadgeClass(score);
    },

    gapBuckets() {
      return window.theseusGapBuckets(this);
    },

    askIntel(prompt) {
      return window.theseusAskIntel(this, prompt);
    },
  };
};
