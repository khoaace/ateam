/* Nhạc lofi khi vibe code: nút tròn góc dưới phải, bấm mới hiện popup điều khiển phía trên nút; phát radio online — YouTube live (iframe, điều khiển bằng
   postMessage của enablejsapi, không nạp script ngoài) hoặc link stream mp3/aac (<audio>). Đài, âm lượng, link
   riêng lưu theo trình duyệt (localStorage "ateam-lofi"). Trang đặt Referrer-Policy: no-referrer nên iframe tự
   khai referrerpolicy — YouTube từ chối embed không có referrer (lỗi 153). */
"use strict";

window.Lofi = (() => {
  const STATIONS = [  // chỉ đài cho nhúng (nhiều live của Lofi Girl chặn nhúng: lỗi 150)
    { key: "lofi", name: "Chillhop · lofi hip hop", yt: "7NOSDKb0HlU" },
    { key: "jazzy", name: "Chillhop · jazzy", yt: "5yx6BWlEVcY" },
    { key: "synth", name: "Lofi Girl · synthwave", yt: "4xDzrJKXOOY" },
    { key: "ambient", name: "Lofi Girl · dark ambient", yt: "S_MOd40zlYU" },
  ];
  const L = Object.assign({ station: "lofi", vol: 50, url: "" }, (() => {
    try { return JSON.parse(localStorage.getItem("ateam-lofi") || "{}"); } catch (e) { return {}; }
  })());
  let playing = false, popOpen = false;
  const save = () => { try { localStorage.setItem("ateam-lofi", JSON.stringify(L)); } catch (e) { /* chặn lưu */ } };
  const box = () => $("#lofi");

  /* link YouTube (watch?v= / youtu.be / live / embed) → id; link http(s) khác coi là stream âm thanh */
  function parse(url) {
    const m = /(?:youtu\.be\/|[?&]v=|\/(?:live|embed|shorts)\/)([\w-]{11})/.exec(url || "");
    if (m) return { yt: m[1] };
    return /^https?:\/\/\S+$/.test(url || "") ? { audio: url } : null;
  }
  function current() {
    if (L.station === "custom") {
      const p = parse(L.url);
      return p && Object.assign({ key: "custom", name: t("lofi_custom") }, p);
    }
    return STATIONS.find((s) => s.key === L.station) || STATIONS[0];
  }
  window.addEventListener("message", (e) => {  // video không phát được (chặn nhúng, đã xoá…) → báo thay vì khung đen
    if (!/^https:\/\/www\.youtube\.com$/.test(e.origin) || !box()) return;
    try { if (JSON.parse(e.data).event === "onError") toast(t("lofi_blocked"), "warn"); } catch (x) { /* message khác */ }
  });

  function yt(func, args) {
    const f = $("#lofi-media iframe");
    if (f && f.contentWindow) f.contentWindow.postMessage(JSON.stringify({ event: "command", func, args: args || [] }), "*");
  }
  function setVolume(v) {
    L.vol = v; save();
    const a = $("#lofi-media audio");
    if (a) a.volume = v / 100; else yt("setVolume", [v]);
  }
  function load() {
    const s = current(), media = $("#lofi-media");
    if (!s) { toast(t("lofi_bad_url"), "warn"); return; }
    if (s.yt) {
      media.innerHTML = `<iframe src="https://www.youtube.com/embed/${s.yt}?autoplay=1&enablejsapi=1&playsinline=1&rel=0"
        allow="autoplay; encrypted-media; picture-in-picture" referrerpolicy="strict-origin-when-cross-origin"
        title="${esc(s.name)}"></iframe>`;
      const f = $("iframe", media);
      f.addEventListener("load", () => {  // API của iframe sẵn sàng sau load: bắt tay rồi đặt âm lượng
        f.contentWindow.postMessage(JSON.stringify({ event: "listening" }), "*");
        setTimeout(() => setVolume(L.vol), 300); setTimeout(() => setVolume(L.vol), 1500);
      });
    } else {
      media.innerHTML = `<audio src="${esc(s.audio)}" autoplay preload="none"></audio>`;
      const a = $("audio", media);
      a.volume = L.vol / 100;
      a.addEventListener("error", () => toast(t("lofi_bad_url"), "warn"));
    }
    playing = true;
    render();
  }

  function render() {
    const nav = $("[data-action=lofi]"), b = box();
    if (nav) nav.classList.toggle("playing", playing);
    if (!b) return;
    const s = current() || { name: t("lofi_custom") };
    b.classList.toggle("pop", popOpen);
    b.classList.toggle("playing", playing);
    $(".lofi-name", b).textContent = s.name;
    $("[data-lf=play]", b).textContent = playing ? "❚❚" : "▶";
    $("[data-lf=play]", b).title = t(playing ? "lofi_pause" : "lofi_play");
    const fab = $(".lofi-fab", b);
    fab.title = t("lofi") + " · " + s.name;
    fab.setAttribute("aria-expanded", popOpen ? "true" : "false");
    $$(".lofi-st", b).forEach((x) => x.classList.toggle("on", x.dataset.st === L.station));
  }
  function setPop(on) { popOpen = on; render(); }

  function open() {
    const d = document.createElement("div");
    d.className = "lofi";
    d.id = "lofi";
    d.innerHTML = `
      <div class="lofi-pop" role="dialog" aria-label="${esc(t("lofi"))}">
        <div class="lofi-media" id="lofi-media"></div>
        <div class="lofi-bar">
          <span class="lofi-eq" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="lofi-name"></span>
          <button class="mini" data-lf="play"></button>
          <input type="range" min="0" max="100" step="5" value="${L.vol}" aria-label="${esc(t("sound_volume"))}">
          <button class="mini" data-lf="hide" title="${esc(t("lofi_hide"))}">▾</button>
          <button class="mini" data-lf="close" title="${esc(t("lofi_close"))}">✕</button>
        </div>
        <div class="lofi-more">
          <div class="lofi-sts">${STATIONS.map((s) => `<button class="lofi-st" data-st="${s.key}">${esc(s.name)}</button>`).join("")}</div>
          <input class="field one" id="lofi-url" placeholder="${esc(t("lofi_custom_ph"))}" value="${esc(L.url)}" spellcheck="false" autocomplete="off">
          <div class="muted small">${esc(t("lofi_hint"))}</div>
        </div>
      </div>
      <button class="lofi-fab" data-lf="fab" aria-label="${esc(t("lofi"))}">
        <svg viewBox="0 0 24 24"><path d="M9 17.5V5.5l11-2v12"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="15.5" r="2.5"/></svg>
        <span class="lofi-eq" aria-hidden="true"><i></i><i></i><i></i></span>
      </button>`;
    document.body.appendChild(d);
    $("input[type=range]", d).addEventListener("input", (e) => setVolume(+e.target.value));
    $("#lofi-url", d).addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const url = e.target.value.trim();
      if (!parse(url)) { toast(t("lofi_bad_url"), "warn"); return; }
      L.url = url; L.station = "custom"; save(); load();
    });
    d.addEventListener("click", (e) => {
      const st = e.target.closest("[data-st]"), b = e.target.closest("[data-lf]");
      if (st) { L.station = st.dataset.st; save(); load(); return; }
      if (!b) return;
      if (b.dataset.lf === "play") toggle();
      else if (b.dataset.lf === "fab") setPop(!popOpen);
      else if (b.dataset.lf === "hide") setPop(false);
      else if (b.dataset.lf === "close") close();
    });
    popOpen = true;
    load();
  }
  /* bấm ra ngoài → thu về nút tròn (nhạc vẫn phát); bỏ qua nút ở thanh bên vì nó tự bật/tắt popup */
  window.addEventListener("pointerdown", (e) => {
    if (!popOpen || !box() || box().contains(e.target) || e.target.closest("[data-action=lofi]")) return;
    setPop(false);
  });
  function toggle() {
    const a = $("#lofi-media audio");
    if (!$("#lofi-media").childElementCount) return load();
    playing = !playing;
    if (a) { if (playing) a.play().catch(() => {}); else a.pause(); }
    else yt(playing ? "playVideo" : "pauseVideo");
    render();
  }
  function close() {
    const b = box();
    if (b) b.remove();
    playing = false; popOpen = false;
    render();
  }

  /* nút ở thanh bên: chưa mở → hiện nút tròn, phát và mở popup; đã có → bật/tắt popup (tắt nhạc hẳn bằng ✕) */
  return {
    open: () => { if (!box()) open(); else setPop(!popOpen); },
    popOpen: () => popOpen && !!box(), hidePop: () => setPop(false), STATIONS, parse,
  };
})();
