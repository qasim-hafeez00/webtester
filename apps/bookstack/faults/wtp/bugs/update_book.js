// BEGIN isConditionMet
const isConditionMet = () => {
  return window.__BUG_INJECTOR_API__.transition("bookstack_update_book", {
    active: window.location.pathname === "/books",
    after: 2,
  });
};
// END isConditionMet

// BEGIN onConditionMet
const onConditionMet = () => {
  // Select all cards
  const cards = document.querySelectorAll('a.grid-card');

  cards.forEach(card => {
    const title = card.querySelector('h2.text-limit-lines-2');
    if (title && title.textContent === 'Updated Book') {
        title.textContent = 'Book2';
    }
  });
};
// END onConditionMet
