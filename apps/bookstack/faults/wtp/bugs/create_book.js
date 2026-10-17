// BEGIN isConditionMet
const isConditionMet = () => {
    return window.__BUG_INJECTOR_API__.transition("bookstack_create_book", {
        active: window.location.pathname === "/books",
        after: 2,
    });
};
// END isConditionMet

// BEGIN onConditionMet
const onConditionMet = () => {
  const cards = document.querySelectorAll('.grid-card');

  for (const card of cards) {
    const title = card.querySelector('.grid-card-content h2');
    if (!title) continue;

    if (title.textContent.trim() === 'New Book') {
      const desc = card.querySelector('.grid-card-content p.text-muted');
      if (desc) {
        desc.textContent = 'Bad Description';
        return true;
      }
    }
  }

  // 1. Find the "New Books" section
  const section = Array.from(document.querySelectorAll('h5'))
    .find(h => h.textContent.trim() === "New Books")
    ?.closest('#new');

  if (!section) return false;

  // 2. Find all book items inside this section
  const items = section.querySelectorAll('.entity-list-item');

  for (const item of items) {
    const title = item.querySelector('.entity-list-item-name');
    if (!title) continue;

    // 3. Match by visible title
    if (title.textContent.trim() === "New Book") {
      item.remove();
    }
  }
};
// END onConditionMet
