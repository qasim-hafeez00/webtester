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

export const enabledFaults = (): string[] => [...enabled].sort();
