function theseus() {
  return {
    ...window.createTheseusInitialState(),
    ...window.createTheseusAppDelegates(),
  };
}