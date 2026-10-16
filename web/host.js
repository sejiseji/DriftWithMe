(() => {
  if (window === window.top) {
    const frame = document.createElement("iframe");
    frame.src = window.location.href;
    frame.title = "DriftWithMe";
    frame.style.cssText = "border:0;position:absolute;left:0;top:0;transform-origin:top left";
    const fitFrame = () => {
      const viewport = window.visualViewport;
      const width = viewport ? viewport.width : window.innerWidth;
      const height = viewport ? viewport.height : window.innerHeight;
      const logical = window.__driftWithMeLogicalSize;
      const scale = Math.min(1, width / logical.width, height / logical.height);
      frame.style.width = `${Math.ceil(width / scale)}px`;
      frame.style.height = `${Math.ceil(height / scale)}px`;
      frame.style.transform = `scale(${scale})`;
    };
    fitFrame();document.body.appendChild(frame);
    window.addEventListener("resize", fitFrame);
    window.visualViewport?.addEventListener("resize", fitFrame);
    return;
  }
  const root = document.documentElement;
  const body = document.body;
  const pointer = {
    down: false,
    pressed: false,
    released: false,
    x: 0,
    y: 0,
    inside: false,
    sequence: 0,
  };
  window.__driftWithMePointer = pointer;
  let activePointerId = null;

  const updateViewport = () => {
    const viewport = window.visualViewport;
    const width = viewport ? viewport.width : window.innerWidth;
    const height = viewport ? viewport.height : window.innerHeight;
    root.style.setProperty("--drift-visible-width", `${Math.floor(width)}px`);
    root.style.setProperty("--drift-visible-height", `${Math.floor(height)}px`);
    body.classList.toggle("drift-portrait", height > width);
  };

  const findCanvas = () => document.querySelector("canvas");

  const logicalSize = () => {
    const configured = window.__driftWithMeLogicalSize || {};
    const canvas = findCanvas();
    return {
      width: Number(configured.width) || (canvas ? canvas.width : 512),
      height: Number(configured.height) || (canvas ? canvas.height : 236),
    };
  };

  const eventToLogical = (event) => {
    const canvas = findCanvas();
    const size = logicalSize();
    if (!canvas) {
      return { x: pointer.x, y: pointer.y, inside: false };
    }
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return { x: pointer.x, y: pointer.y, inside: false };
    }
    // Pyxel preserves the game aspect ratio inside the canvas backing buffer.
    // Exclude that letterbox before converting CSS/client coordinates to game pixels.
    const bufferWidth = canvas.width;
    const bufferHeight = canvas.height;
    if (bufferWidth <= 0 || bufferHeight <= 0) {
      return { x: pointer.x, y: pointer.y, inside: false };
    }
    const scale = Math.min(bufferWidth / size.width, bufferHeight / size.height);
    const contentWidth = size.width * scale;
    const contentHeight = size.height * scale;
    const bufferX = ((event.clientX - rect.left) * bufferWidth) / rect.width;
    const bufferY = ((event.clientY - rect.top) * bufferHeight) / rect.height;
    const rawX = (bufferX - (bufferWidth - contentWidth) / 2) / scale;
    const rawY = (bufferY - (bufferHeight - contentHeight) / 2) / scale;
    const inside = rawX >= 0 && rawX <= size.width && rawY >= 0 && rawY <= size.height;
    return {
      x: Math.max(0, Math.min(size.width - 1, rawX)),
      y: Math.max(0, Math.min(size.height - 1, rawY)),
      inside,
    };
  };

  const preventCanvasGesture = (event) => {
    if (event.cancelable) {
      event.preventDefault();
    }
  };

  const capturePointer = (pointerId) => {
    const canvas = findCanvas();
    if (!canvas || !canvas.setPointerCapture) {
      return;
    }
    try {
      canvas.setPointerCapture(pointerId);
    } catch {
      // The browser may already have released capture during fast orientation changes.
    }
  };

  const releasePointer = (pointerId) => {
    const canvas = findCanvas();
    if (!canvas || !canvas.releasePointerCapture) {
      return;
    }
    try {
      canvas.releasePointerCapture(pointerId);
    } catch {
      // Ignore stale pointer ids.
    }
  };

  const onPointerDown = (event) => {
    const position = eventToLogical(event);
    if (!position.inside || activePointerId !== null) {
      return;
    }
    activePointerId = event.pointerId;
    capturePointer(event.pointerId);
    pointer.down = true;
    pointer.pressed = true;
    pointer.released = false;
    pointer.x = position.x;
    pointer.y = position.y;
    pointer.inside = true;
    pointer.sequence += 1;
    preventCanvasGesture(event);
  };

  const onPointerMove = (event) => {
    if (activePointerId !== event.pointerId) {
      return;
    }
    const position = eventToLogical(event);
    pointer.down = true;
    pointer.x = position.x;
    pointer.y = position.y;
    pointer.inside = position.inside;
    preventCanvasGesture(event);
  };

  const onPointerFinish = (event) => {
    if (activePointerId !== event.pointerId) {
      return;
    }
    const position = eventToLogical(event);
    pointer.down = false;
    pointer.released = true;
    pointer.x = position.x;
    pointer.y = position.y;
    pointer.inside = position.inside;
    activePointerId = null;
    releasePointer(event.pointerId);
    preventCanvasGesture(event);
  };

  const cancelPointer = () => {
    activePointerId = null;
    pointer.down = false;
    pointer.released = true;
    pointer.inside = false;
  };

  updateViewport();
  window.addEventListener("resize", updateViewport, { passive: true });
  window.addEventListener("orientationchange", () => {
    updateViewport();
    cancelPointer();
  }, { passive: true });
  window.addEventListener("blur", cancelPointer, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      cancelPointer();
    }
  }, { passive: true });
  document.addEventListener("contextmenu", (event) => event.preventDefault());
  document.addEventListener("pointerdown", onPointerDown, { passive: false });
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("pointerup", onPointerFinish, { passive: false });
  document.addEventListener("pointercancel", onPointerFinish, { passive: false });

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", updateViewport, { passive: true });
    window.visualViewport.addEventListener("scroll", updateViewport, { passive: true });
  }
})();
