// [agentic] Seeded-fault switchboard.
//
// Faults are compiled in but dormant. A run enables a set of them with the
// FAULTS environment variable (comma-separated ids, e.g. FAULTS=F01,F04), so
// one image serves every experimental condition and the ground truth for a run
// is exactly its FAULTS value. The catalogue (trigger, oracle, class) lives in
// apps/realworld/faults/FAULTS.md.
const enabled = new Set(
  (process.env.FAULTS || '')
    .split(',')
    .map((f) => f.trim().toUpperCase())
    .filter(Boolean),
);

export const fault = (id: string): boolean => enabled.has(id.toUpperCase());

// Exposure marker: called inside a faulty branch when it actually takes effect. The harness
// reads these lines from the container log after exploration (ground truth for "the fault
// fired", never a finding). Logging only: behaviour is decided by fault() alone.
export const fired = (id: string): void => {
  console.log(`[wt-fault] ${id.toUpperCase()}`);
};

export const enabledFaults = (): string[] => [...enabled].sort();
