// Offer the page in the browser's language once; never redirect.
(function () {
  const here = document.documentElement.lang;
  const want = (navigator.languages || [navigator.language]).map((l) => (l || "").slice(0, 2))
    .find((l) => l in window.TRIKI_HINTS);
  if (!want || want === here || localStorage.getItem("triki-hint-closed")) return;
  const box = document.getElementById("hint");
  const a = document.createElement("a");
  a.href = window.TRIKI_PAGES[want]; a.hreflang = want; a.lang = want; a.textContent = window.TRIKI_HINTS[want];
  const x = document.createElement("button");
  x.type = "button"; x.setAttribute("aria-label", "Close"); x.textContent = "×";
  x.onclick = () => { box.hidden = true; localStorage.setItem("triki-hint-closed", "1"); };
  box.append(a, x); box.hidden = false;
})();
