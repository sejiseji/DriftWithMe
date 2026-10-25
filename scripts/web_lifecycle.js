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
