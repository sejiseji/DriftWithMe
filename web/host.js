(() => {
  const root = document.documentElement;
  const body = document.body;

  const updateViewport = () => {
    const viewport = window.visualViewport;
    const width = viewport ? viewport.width : window.innerWidth;
    const height = viewport ? viewport.height : window.innerHeight;
    root.style.setProperty("--drift-visible-width", `${Math.floor(width)}px`);
    root.style.setProperty("--drift-visible-height", `${Math.floor(height)}px`);
    body.classList.toggle("drift-portrait", height > width);
  };

  updateViewport();
  window.addEventListener("resize", updateViewport, { passive: true });
  window.addEventListener("orientationchange", updateViewport, { passive: true });
  document.addEventListener("contextmenu", (event) => event.preventDefault());

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", updateViewport, { passive: true });
    window.visualViewport.addEventListener("scroll", updateViewport, { passive: true });
  }
})();
