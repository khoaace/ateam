/* Trang docs ateam — dùng chung cho site/index.html (vi) và site/en/index.html (en).
   Chữ theo ngôn ngữ trang đọc từ data-* trên <html> và <script type="application/json" id="hero-script">. */
(function () {
  var root = document.documentElement;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
  }

  // ---------- sao chép lệnh ----------
  function fallback(text) {
    var t = document.createElement("textarea"); t.value = text; document.body.appendChild(t);
    t.select(); try { document.execCommand("copy"); } catch (e) {} document.body.removeChild(t);
  }
  document.querySelectorAll(".copy").forEach(function (btn) {
    var label = btn.textContent;
    btn.addEventListener("click", function () {
      var text = document.getElementById(btn.dataset.copy).innerText.trim();
      var done = function () {
        btn.textContent = root.dataset.copied || "✓"; btn.classList.add("done");
        setTimeout(function () { btn.textContent = label; btn.classList.remove("done"); }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
      else { fallback(text); done(); }
    });
  });

  // ---------- sáng / tối ----------
  var themeBtn = document.querySelector(".theme-btn");
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    store("ateam-theme", next);
  });

  // ---------- ngôn ngữ: nhớ lựa chọn; trang tiếng Việt gợi ý bản tiếng Anh cho trình duyệt không phải tiếng Việt ----------
  document.querySelectorAll(".lang a").forEach(function (a) {
    a.addEventListener("click", function () { store("ateam-lang", a.getAttribute("hreflang")); });
  });
  var hint = document.querySelector(".lang-hint");
  if (hint) {
    var first = ((navigator.languages && navigator.languages[0]) || navigator.language || "").toLowerCase();
    if (!store("ateam-lang") && first && first.indexOf("vi") !== 0) hint.classList.add("on");
    hint.querySelector("button").addEventListener("click", function () { hint.classList.remove("on"); store("ateam-lang", "vi"); });
    hint.querySelector("a").addEventListener("click", function () { store("ateam-lang", "en"); });
  }

  // ---------- tab (gallery: danh sách màn hình + nút terminal / web) ----------
  document.querySelectorAll('[role="tablist"]').forEach(function (list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll(':scope > [role="tab"]'));
    var vertical = list.getAttribute("aria-orientation") === "vertical";
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t, false); });
      t.addEventListener("keydown", function (e) {
        var next = vertical ? "ArrowDown" : "ArrowRight", prev = vertical ? "ArrowUp" : "ArrowLeft";
        var j = e.key === next ? i + 1 : e.key === prev ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
        if (j === null) return;
        e.preventDefault(); select(tabs[(j + tabs.length) % tabs.length], true);
      });
    });
  });

  // ---------- hiện dần khi cuộn ----------
  var els = document.querySelectorAll(".reveal, .board");
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in", "seen"); io.unobserve(en.target); }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
    els.forEach(function (el) { io.observe(el); });
  } else {
    els.forEach(function (el) { el.classList.add("in", "seen"); });
  }

  // ---------- terminal "đang chạy" ở hero: [loại, html tiền tố, chữ gõ | thời gian chờ ms] ----------
  var term = document.getElementById("term"), src = document.getElementById("hero-script");
  if (!term || !src) return;
  var SCRIPT = JSON.parse(src.textContent);
  function line(html) {
    var el = document.createElement("span"); el.className = "ln"; el.innerHTML = html; term.appendChild(el); return el;
  }
  if (reduce) {
    SCRIPT.forEach(function (s) { line(s[0] === "type" ? s[1] + s[2] : s[1]); });
    return;
  }
  var i = 0;
  function step() {
    if (i >= SCRIPT.length) { setTimeout(function () { term.innerHTML = ""; i = 0; step(); }, 2600); return; }
    var s = SCRIPT[i++];
    if (s[0] === "out") { line(s[1]); setTimeout(step, s[2]); return; }
    var el = line(s[1]);
    var txt = document.createElement("span"); el.appendChild(txt);
    var caret = document.createElement("span"); caret.className = "caret"; el.appendChild(caret);
    var k = 0;
    (function typeOne() {
      if (k <= s[2].length) { txt.textContent = s[2].slice(0, k++); setTimeout(typeOne, 28 + Math.random() * 40); }
      else { setTimeout(function () { caret.remove(); step(); }, 450); }
    })();
  }
  step();
})();
