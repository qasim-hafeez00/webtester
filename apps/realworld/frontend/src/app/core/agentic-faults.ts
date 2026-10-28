// [agentic] Frontend side of the seeded-fault switchboard (see backend
// src/agentic/faults.ts). The enabled set is written into
// assets/runtime-config.js from the container's FAULTS variable.
export const fault = (id: string): boolean =>
  ((window as any).__FAULTS__ || []).includes(id.toUpperCase());

// Exposure marker (see backend fired()): the harness reads this console line as
// "the fault fired" and never reports it as a finding. Logging only.
export const fired = (id: string): void => {
  console.log(`[wt-fault] ${id.toUpperCase()}`);
};
