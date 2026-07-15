const { contextBridge } = require("electron");
const { ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("mjolniros", {
  platform: process.platform,
  versions: {
    chrome: process.versions.chrome,
    electron: process.versions.electron,
    node: process.versions.node
  },
  updateDesktopSettings: (settings) => ipcRenderer.send("settings-updated", settings),
  saveNavigationState: (view) => ipcRenderer.send("navigation-state", view),
  reportAssistantState: (state) => ipcRenderer.send("assistant-state", state),
  onNavigate: (callback) => {
    const listener = (_event, view) => callback(view);
    ipcRenderer.on("navigate", listener);
    return () => ipcRenderer.removeListener("navigate", listener);
  }
});
