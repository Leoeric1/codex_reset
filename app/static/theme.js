(() => {
  let saved;
  try { saved = localStorage.getItem('leohub-theme'); } catch { /* Device storage is optional. */ }
  document.documentElement.dataset.theme = saved === 'light' ? 'light' : 'dark';
})();
