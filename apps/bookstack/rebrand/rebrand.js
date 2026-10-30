// E6 (D60): rebranded BookStack, a contamination control. The LLM may know BookStack from its training data;
// this init script renames the product and its nouns in every text node (also those added later) and shifts
// the colours, so the same app with the same faults reads as an unfamiliar one. Fault scripts still match
// their own text, because they run first (fault_script is added before init_scripts) and the rename keeps
// the item names they look for (only the product and the kind nouns change).
(() => {
  const MAP = [
    [/\bBookStack\b/g, 'Ledgerly'], [/\bShelves\b/g, 'Cabinets'], [/\bShelf\b/g, 'Cabinet'],
    [/\bshelves\b/g, 'cabinets'], [/\bshelf\b/g, 'cabinet'], [/\bChapters\b/g, 'Sections'],
    [/\bChapter\b/g, 'Section'], [/\bchapters\b/g, 'sections'], [/\bchapter\b/g, 'section'],
  ];
  const fix = (node) => {
    if (node.nodeType === 3) {
      let t = node.nodeValue, u = t;
      for (const [rx, to] of MAP) u = u.replace(rx, to);
      if (u !== t) node.nodeValue = u;
      return;
    }
    if (node.nodeType !== 1 || /^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(node.tagName)) return;
    for (const c of node.childNodes) fix(c);
  };
  const run = () => {
    if (!document.body) return;
    fix(document.body);
    if (document.title) for (const [rx, to] of MAP) document.title = document.title.replace(rx, to);
    new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach(fix))).observe(document.body, {childList: true, subtree: true});
    const st = document.createElement('style');
    st.textContent = 'html { filter: hue-rotate(140deg); } img, video, canvas { filter: hue-rotate(-140deg); }';
    document.head.appendChild(st);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
