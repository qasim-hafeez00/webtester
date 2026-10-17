// BEGIN isConditionMet
const isConditionMet = () => {
  const condition = document.querySelector('h1.list-heading')?.textContent.trim() === 'Books';
  return window.__BUG_INJECTOR_API__.transition("bookstack_delete_book", {
    active: condition,
    after: 2,
  });
};
// END isConditionMet

// BEGIN onConditionMet
const onConditionMet = () => {
  // 1. Select the container holding the grid cards
  const container = document.querySelector('div.grid.third');

  // 2. Select the card you want to duplicate (e.g., the first one)
  const cardToDuplicate = container.querySelector('a.grid-card');

  // 3. Clone the card
  const clonedCard = cardToDuplicate.cloneNode(true); // true = deep clone including children

  // 4. Optionally modify the clone (e.g., change title or ID)
  clonedCard.querySelector('h2').textContent = 'Book';
  clonedCard.dataset.entityId = '999'; // example new ID
  clonedCard.href = '/books/book-duplicate';

  // 5. Insert the cloned card back into the container
  container.appendChild(clonedCard); // adds at the end
  // OR container.insertBefore(clonedCard, container.firstChild); // adds at the beginning
};
// END onConditionMet
