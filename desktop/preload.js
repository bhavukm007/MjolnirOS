const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("mjolniros", {
  platform: process.platform,
  versions: {
    chrome: process.versions.chrome,
    electron: process.versions.electron,
    node: process.versions.node
  },
  desktop: {
    getSettings: () => ipcRenderer.invoke("desktop:get-settings"),
    setLaunchOnStartup: (enabled) => ipcRenderer.invoke("desktop:set-launch-on-startup", enabled),
    getSystemStatus: () => ipcRenderer.invoke("desktop:get-system-status"),
    openSettings: () => ipcRenderer.invoke("desktop:open-settings"),
    openMainWindow: () => ipcRenderer.invoke("desktop:open-main-window")
  }
});
