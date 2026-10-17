// [agentic] Deterministic seed. Replaces the upstream random (falso) seed so
// every run starts from identical data. Run once per fresh database; the
// result is then snapshotted (see db/agentic-reset.sql) and every experiment
// run is reset to that snapshot.
//
// Accounts:
//   worker01..worker16  one per parallel exploring worker (password below)
//   alice, bob, carol, dave  content authors
import prisma from '../prisma/prisma-client';
import { createUser } from '../app/routes/auth/auth.service';
import { addComment, createArticle, favoriteArticle } from '../app/routes/article/article.service';
import { followUser } from '../app/routes/profile/profile.service';

export const WORKER_PASSWORD = 'conduit-test-pw';
const AUTHOR_PASSWORD = 'conduit-author-pw';
const pad = (n: number) => String(n).padStart(2, '0');

const AUTHORS = [
  { username: 'alice', bio: 'Writes about distributed systems.' },
  { username: 'bob', bio: 'Frontend engineer. Opinions on CSS.' },
  { username: 'carol', bio: 'Testing, tooling and the occasional rant.' },
  { username: 'dave', bio: null },
];

const TOPICS = [
  ['Why your cache is lying to you', 'Cache invalidation, revisited', ['caching', 'backend']],
  ['A gentle introduction to property-based testing', 'Stop writing examples by hand', ['testing', 'tooling']],
  ['CSS grid in practice', 'Layouts without the hacks', ['css', 'frontend']],
  ['Flaky tests are a smell', 'And how to find the source', ['testing', 'ci']],
  ['Postgres indexes you forgot about', 'Partial, covering and expression indexes', ['postgres', 'backend']],
  ['State machines for UI', 'Fewer impossible states', ['frontend', 'architecture']],
  ['Reading a flame graph', 'Profiling for the impatient', ['performance', 'tooling']],
  ['The case against micro-services', 'For small teams at least', ['architecture', 'backend']],
] as const;

const snapshotExists = async (): Promise<boolean> => {
  const rows = await prisma.$queryRaw<{ n: bigint }[]>`
    SELECT count(*) AS n FROM information_schema.schemata WHERE schema_name = 'snap'`;
  return Number(rows[0].n) > 0;
};

const main = async () => {
  if (await snapshotExists()) {
    console.info('snapshot exists, skipping seed');
    return;
  }
  const workers = [];
  for (let i = 1; i <= 16; i += 1) {
    workers.push(
      await createUser({
        username: `worker${pad(i)}`,
        email: `worker${pad(i)}@conduit.test`,
        password: WORKER_PASSWORD,
        demo: true,
      }),
    );
  }

  const authors = [];
  for (const a of AUTHORS) {
    authors.push(
      await createUser({
        username: a.username,
        email: `${a.username}@conduit.test`,
        password: AUTHOR_PASSWORD,
        bio: a.bio ?? undefined,
        demo: true,
      }),
    );
  }

  // 3 articles per author, round-robin over topics (12 articles, 8 distinct tags).
  const articles = [];
  for (let k = 0; k < 12; k += 1) {
    const author = authors[k % authors.length];
    const [title, description, tags] = TOPICS[k % TOPICS.length];
    const suffix = k >= TOPICS.length ? ', part two' : '';
    articles.push(
      await createArticle(
        {
          title: `${title}${suffix}`,
          description,
          body: `# ${title}${suffix}\n\nThis is seeded article number ${k + 1}.\n\nIt has **markdown** content and a [link](https://example.com).`,
          tagList: [...tags],
        },
        author.id,
      ),
    );
  }

  // Comments: each article gets comments from the next two authors.
  for (let k = 0; k < articles.length; k += 1) {
    for (let j = 1; j <= 2; j += 1) {
      const commenter = authors[(k + j) % authors.length];
      await addComment(`Seeded comment ${j} on article ${k + 1}.`, articles[k].slug, commenter.id);
    }
  }

  // Social graph: alice follows bob and carol; bob follows alice.
  await followUser('bob', authors[0].id);
  await followUser('carol', authors[0].id);
  await followUser('alice', authors[1].id);

  // Favorites: carol and dave favorite the first three articles.
  for (const art of articles.slice(0, 3)) {
    await favoriteArticle(art.slug, authors[2].id);
    await favoriteArticle(art.slug, authors[3].id);
  }

  await prisma.$executeRaw`SELECT agentic_snapshot()`;
  console.info(`seeded ${workers.length} workers, ${authors.length} authors, ${articles.length} articles`);
};

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });
