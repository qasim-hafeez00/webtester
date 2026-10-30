# Real historical faults (v5 plan E5 a, D60): protocol

Ground truth that the rule authors did not write: bugs that were reported and fixed upstream, run on the
version before the fix. Target 8-15 across BookStack and the RealWorld implementations.

Selection, fixed before any rule is checked against them:

1. Source: the project's closed issues and release notes ("Fixed ..." lines), versions 23.x-25.x for BookStack.
2. Keep a bug when (a) it shows in the browser without special data or configuration, (b) a fix commit is
   linked, (c) the version before the fix builds from its tag with our compose setup.
3. Drop security issues (out of scope, D1), performance issues, and bugs needing mail, LDAP, SAML or uploads
   of a specific file type.
4. Record per bug: issue URL, fix commit, last affected tag, the user-visible symptom, its fault family
   (fault_families.md), and `reachable` (can exploration trigger it with the seeded data).
5. The person who selects the bugs does not look at the rules' code or findings while doing it; the family is
   assigned from the symptom only.

`candidates.toml` holds the entries (empty: selection needs a web search of the issue trackers, I58). A run on
a historical version uses its own compose file (`docker-compose.<tag>.yml`) and its own config.
