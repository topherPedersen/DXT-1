const status = document.getElementById("status");
window.dxtSetup.onStatus(message => {
  status.textContent = message.toUpperCase();
});
