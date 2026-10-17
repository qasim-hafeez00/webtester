// BEGIN isConditionMet
const isConditionMet = () => {
  return window.__BUG_INJECTOR_API__.transition("bookstack_recently_viewed_shelf", {
    active: window.location.pathname === "/",
    after: 2,
  });
};
// END isConditionMet

// BEGIN onConditionMet
const onConditionMet = () => {
  const items = document.querySelectorAll(
    '#recently-viewed a.entity-list-item'
  );

  items.forEach(item => {
    const titleEl = item.querySelector('.entity-list-item-name');
    if (!titleEl) return;

    const title = titleEl.textContent.trim();
    if (title === "Chapter 2") {
      item.remove();
    }
  });
};
// END onConditionMet
