/* For an editable page at port 8766:
 * <script src="http://127.0.0.1:8767/bridge.js"></script>
 * const bridge = new BeatBridge();
 * bridge.connectVideo(document.querySelector('video'));
 * bridge.start();
 * Other renderers can listen to the 'bpmbeat' CustomEvent or read bridge.state.
 */
(function (root) {
  "use strict";
  class BeatBridge {
    constructor({url = "http://127.0.0.1:8767", pollMs = 100} = {}) {
      this.url = url.replace(/\/$/, "");
      this.pollMs = pollMs;
      this.state = null;
      this.targets = [];
      this.running = false;
      this.clockOffset = 0;
    }
    connectVideo(video, {phaseOffset = 0, baseBpm = 120} = {}) {
      video.muted = true;
      video.loop = true;
      this.targets.push({kind: "video", element: video, phaseOffset, baseBpm});
      return this;
    }
    connectAnimation(animation, {phaseOffset = 0, baseBpm = 120} = {}) {
      this.targets.push({kind: "animation", element: animation, phaseOffset, baseBpm});
      return this;
    }
    active() {
      const s = this.state;
      return !!(s && s.audio_active && s.confidence >= 0.28 &&
        Number.isFinite(s.bpm) && s.bpm > 0 && Number.isFinite(s.beat_at) &&
        (Date.now()/1000 + this.clockOffset - s.updated_at) < 3);
    }
    async poll() {
      while (this.running) {
        const before = Date.now()/1000;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 1500);
        try {
          const response = await fetch(this.url + "/state", {cache: "no-store", signal: controller.signal});
          if (!response.ok) throw new Error("Bridge HTTP " + response.status);
          const s = await response.json();
          if (!this.running) break;
          this.clockOffset = s.server_time - (before + Date.now()/1000)/2;
          this.state = s;
          root.dispatchEvent(new CustomEvent("bpmbeat", {detail: s}));
        } catch (_) {
          this.state = null;
        } finally {
          clearTimeout(timeout);
        }
        if (this.running) await new Promise(resolve => setTimeout(resolve, this.pollMs));
      }
    }
    render() {
      if (!this.running) return;
      const active = this.active();
      const now = Date.now()/1000 + this.clockOffset;
      for (const target of this.targets) {
        const el = target.element;
        if (!active) { el.pause(); continue; }
        const rate = this.state.bpm / target.baseBpm;
        const position = (now - this.state.beat_at) * rate + target.phaseOffset;
        if (target.kind === "video") {
          if (!Number.isFinite(el.duration) || el.duration <= 0 || el.readyState < 2) continue;
          const desired = ((position % el.duration) + el.duration) % el.duration;
          let error = desired - el.currentTime;
          if (error > el.duration/2) error -= el.duration;
          if (error < -el.duration/2) error += el.duration;
          // Large offsets need a seek; small drift is corrected by a gentle rate adjustment.
          if (Math.abs(error) > 0.12 && !el.seeking) el.currentTime = desired;
          el.playbackRate = Math.min(4, Math.max(0.25, rate * (1 + Math.max(-0.05, Math.min(0.05, error*0.4)))));
          if (el.paused) el.play().catch(() => {});
        } else {
          // Set timeline directly: no accumulated drift, no new bounce layered over the original.
          el.pause();
          el.currentTime = position * 1000;
        }
      }
      this.frame = requestAnimationFrame(() => this.render());
    }
    start() {
      if (this.running) return this;
      this.running = true;
      this.poll();
      this.render();
      return this;
    }
    stop() {
      this.running = false;
      cancelAnimationFrame(this.frame);
      for (const target of this.targets) target.element.pause();
    }
  }
  root.BeatBridge = BeatBridge;
})(window);
