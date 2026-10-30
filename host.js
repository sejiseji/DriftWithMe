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
    if (window.__driftWithMeLifecycle?.active === false) return;
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
    pointer.pressed = false;
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
    pointer.pressed = false;
    pointer.released = true;
    pointer.inside = false;
  };

  const invalidatePointerGeometry = () => {
    updateViewport();
    cancelPointer();
    // Python must also discard the old logical anchor and wait for release.
    const lifecycle = window.__driftWithMeLifecycle;
    if (lifecycle) lifecycle.inputEpoch += 1;
  };
  updateViewport();
  window.addEventListener("resize", invalidatePointerGeometry, { passive: true });
  window.addEventListener("orientationchange", invalidatePointerGeometry, { passive: true });
  // This hook belongs only to the game iframe, before launchPyxel starts it.
  if (!window.__driftWithMeLifecycle) {
    let pageHidden = false;
    let frozen = false;
    const keys = new Map();
    const contexts = new Map();
    const frames = new Map();
    let nextFrame = 1;
    const nativeRequest = window.requestAnimationFrame?.bind(window);
    const nativeCancel = window.cancelAnimationFrame?.bind(window);
    const lifecycle = {
      active: !document.hidden,
      generation: 0,
      inputEpoch: 0,
      ready: !document.hidden,
      acknowledge(generation) {
        if (generation !== this.generation || !this.active) return;
        this.ready = true;
        syncAudio();
      },
    };
    window.__driftWithMeLifecycle = lifecycle;

    const schedule = (id) => {
      const frame = frames.get(id);
      if (!frame || frame.nativeId !== null || !lifecycle.active) return;
      const ticket = ++frame.ticket;
      frame.nativeId = nativeRequest((timestamp) => {
        if (frames.get(id) !== frame || frame.ticket !== ticket) return;
        frame.nativeId = null;
        if (!lifecycle.active) return;
        frames.delete(id);
        frame.callback(timestamp);
      });
    };
    if (nativeRequest && nativeCancel) {
      window.requestAnimationFrame = (callback) => {
        const id = nextFrame++;
        frames.set(id, { callback, nativeId: null, ticket: 0 });
        schedule(id);
        return id;
      };
      window.cancelAnimationFrame = (id) => {
        const frame = frames.get(id);
        if (!frame) return;
        if (frame.nativeId !== null) nativeCancel(frame.nativeId);
        frames.delete(id);
      };
    }

    const syncAudio = () => {
      for (const [context, state] of contexts) {
        if (context.state === "closed") { contexts.delete(context); continue; }
        if (!lifecycle.active && context.state === "running") state.wasRunning = true;
        state.pending = state.pending.then(async () => {
          if (!lifecycle.active && context.state === "running") {
            await context.suspend();
          } else if (lifecycle.active && lifecycle.ready && state.wasRunning &&
                     context.state === "suspended") {
            await context.resume();
            state.wasRunning = false;
          }
        }).catch(() => {}); // A denied resume is retried only on a later user gesture.
      }
    };
    const retryAudio = () => {
      if (!lifecycle.active || !lifecycle.ready) return;
      for (const [context, state] of contexts) {
        if (state.wasRunning && context.state === "suspended") {
          context.resume().then(() => { state.wasRunning = false; }).catch(() => {});
        }
      }
    };
    for (const name of ["AudioContext", "webkitAudioContext"]) {
      const Original = window[name];
      if (!Original) continue;
      window[name] = new Proxy(Original, {
        construct(target, args) {
          const context = Reflect.construct(target, args);
          contexts.set(context, { wasRunning: false, pending: Promise.resolve() });
          syncAudio();
          return context;
        },
      });
    }
    const releaseInputs = () => {
      cancelPointer();
      lifecycle.inputEpoch += 1;
      for (const key of keys.values()) {
        if (typeof window.KeyboardEvent !== "function") continue;
        const target = findCanvas() || document;
        target.dispatchEvent(new window.KeyboardEvent("keyup", { ...key, bubbles: true }));
      }
      keys.clear();
    };
    const refresh = () => {
      const active = !document.hidden && !pageHidden && !frozen;
      if (active === lifecycle.active) return;
      lifecycle.active = active;
      lifecycle.generation += 1;
      lifecycle.ready = false;
      releaseInputs();
      if (active) {
        for (const id of frames.keys()) schedule(id);
      } else {
        for (const frame of frames.values()) {
          if (frame.nativeId !== null) nativeCancel(frame.nativeId);
          frame.nativeId = null;
          frame.ticket += 1;
        }
      }
      syncAudio();
    };
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("pagehide", () => { pageHidden = true; refresh(); });
    window.addEventListener("pageshow", () => { pageHidden = false; refresh(); });
    document.addEventListener("freeze", () => { frozen = true; refresh(); });
    document.addEventListener("resume", () => { frozen = false; refresh(); });
    // Toolbars, dialogs and iframe focus changes are not reliable visibility signals.
    window.addEventListener("blur", releaseInputs, { passive: true });
    window.addEventListener("keydown", (event) => {
      if (!lifecycle.active) { event.stopImmediatePropagation?.(); return; }
      keys.set(event.code || event.key, {
        code: event.code, key: event.key, keyCode: event.keyCode,
        which: event.which, location: event.location,
      });
      retryAudio();
    }, true);
    window.addEventListener("keyup", (event) => { keys.delete(event.code || event.key); }, true);
    window.addEventListener("pointerdown", retryAudio, true);
  }

  document.addEventListener("contextmenu", (event) => event.preventDefault());
  document.addEventListener("pointerdown", onPointerDown, { passive: false });
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("pointerup", onPointerFinish, { passive: false });
  document.addEventListener("pointercancel", onPointerFinish, { passive: false });

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", invalidatePointerGeometry, { passive: true });
    window.visualViewport.addEventListener("scroll", invalidatePointerGeometry, { passive: true });
  }
})();
