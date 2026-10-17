// BEGIN isConditionMet
const isConditionMet = () => {
    return window.__BUG_INJECTOR_API__.transition("bookstack_create_sort_rule", {
        active: window.location.pathname === "/settings/sorting",
        after: 2,
    });
};
// END isConditionMet

// BEGIN onConditionMet
const onConditionMet = () => {
  const rows = document.querySelectorAll('.item-list-row');

  for (const row of rows) {
    const titleLink = row.querySelector('a');
    if (!titleLink) continue;

    // Only target the "New Sort Rule" row
    if (titleLink.textContent.trim() === 'New Sort Rule') {
      const meta = row.querySelector('.text-muted');
      if (!meta) return;

      meta.textContent = meta.textContent.replace(/\(Asc\)/g, '(Desc)');
      return;
    }
  }
};
// END onConditionMet
