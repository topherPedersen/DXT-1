const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dxtSetup", {
  onStatus: callback => {
    ipcRenderer.on("setup-status", (_event, message) => callback(String(message)));
  }
});
