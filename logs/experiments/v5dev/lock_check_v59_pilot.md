# v5.0 lock check: v59 against v5

## Run level, all rules

| app | recall (score, median) vs ref | ok | precision | ok | clean FA/run | ok | lock |
|---|---|---|---|---|---|---|---|
| bookstack | 8/13, 0.4615 vs 8/13, 0.4615 | yes | 71/125 = 0.568 (0 unlabelled) | **no** | 10.8 (54 in 5; 0 unlabelled) | **no** | **no** |
| realworld | 7/8, 0.75 vs 7/8, 0.75 | yes | 71/133 = 0.5338 (0 unlabelled) | **no** | 6.0 (30 in 5; 0 unlabelled) | **no** | **no** |

## Run level without R01x, R02h, R02m, R09, R09d, R12c, R20, R21b, R23, R30, R43, R50m, R65, R68, R68t, R49

| app | recall (score, median) vs ref | ok | precision | ok | clean FA/run | ok | lock |
|---|---|---|---|---|---|---|---|
| bookstack | 8/13, 0.4615 vs 8/13, 0.4615 | yes | 66/68 = 0.9706 (0 unlabelled) | yes | 0.4 (2 in 5; 0 unlabelled) | yes | yes |
| realworld | 7/8, 0.75 vs 7/8, 0.75 | yes | 70/71 = 0.9859 (0 unlabelled) | yes | 0.2 (1 in 5; 0 unlabelled) | yes | yes |

## Rule level (section 12.2)

83 of 143 rules meet (1), (2), (4), (5). Rules with findings or false alarms:

| rule | test | armed | seeded family | findings | precision | tier | clean FA | faults | enters |
|---|---|---|---|---|---|---|---|---|---|
| I-delete | yes | 44 | yes | 15 | 1.0 | T1 | 1 | F06 | yes |
| I-filter | yes | 69 | yes | 14 | 1.0 | T1 | 0 | F10 | yes |
| I-submit | yes | 17 | yes | 10 | 0.9 | T1 | 0 | F01, F02 | yes |
| R01x | yes | 1578 | **no** | 8 | 0.375 | T2 | 5 |  | yes |
| R02 | yes | 261 | yes | 1 | 1.0 | T2 | 0 | BS04 | yes |
| R02h | yes | 1578 | **no** | 5 | 0.0 | T2 | 0 |  | yes |
| R02m | yes | 1453 | **no** | 22 | 0.0 | T2 | 0 |  | yes |
| R03 | yes | 908 | yes | 19 | 1.0 | T1 | 0 | BS05, BS06, BS07, BS08 | yes |
| R04 | yes | 126 | yes | 14 | 1.0 | T1 | 0 | BS05, BS06, BS08 | yes |
| R07c | yes | 9 | yes | 6 | 1.0 | T1 | 0 | F08 | yes |
| R08 | yes | 285 | yes | 23 | 0.913 | T1 | 2 | BS09, BS10, BS11 | yes |
| R09 | yes | 420 | yes | 6 | 0.1667 | T2 | 1 | BS04 | yes |
| R09d | yes | 38 | **no** | 3 | 0.0 | T2 | 2 |  | yes |
| R11 | yes | 15 | yes | 5 | 1.0 | T1 | 0 | F09 | yes |
| R12c | yes | 5 | **no** | 3 | 0.0 | T2 | 3 |  | yes |
| R13 | yes | 66 | yes | 1 | 1.0 | T2 | 0 | F07 | yes |
| R16 | yes | 46 | yes | 5 | 1.0 | T1 | 0 | F01 | yes |
| R17 | yes | 46 | yes | 9 | 1.0 | T1 | 0 |  | yes |
| R20 | yes | 168 | yes | 6 | 0.0 | T2 | 6 |  | yes |
| R21b | yes | 9 | yes | 1 | 0.0 | T2 | 1 |  | yes |
| R23 | yes | 28 | yes | 10 | 0.1 | T2 | 9 | BS08 | yes |
| R23m | yes | 20 | **no** | 10 | 1.0 | T1 | 0 |  | yes |
| R30 | yes | 40 | **no** | 15 | 0.0 | T2 | 15 |  | yes |
| R43 | yes | 696 | **no** | 19 | 0.0 | T2 | 19 |  | yes |
| R48c | yes | 20 | **no** | 5 | 1.0 | T1 | 0 |  | yes |
| R49 | yes | 4 | **no** | 0 | None | - | 2 |  | yes |
| R50m | yes | 9 | **no** | 4 | 0.0 | T2 | 5 |  | yes |
| R63 | yes | 78 | **no** | 2 | 1.0 | T2 | 0 |  | yes |
| R65 | yes | 1578 | **no** | 9 | 0.0 | T2 | 5 |  | yes |
| R68 | yes | 28 | **no** | 7 | 0.1429 | T2 | 6 |  | yes |
| R68t | yes | 76 | **no** | 1 | 0.0 | T2 | 2 |  | yes |

**no fixture test** (0): -

**never armed** (60): G1, G3, R02d, R02s, R04b, R06, R09r, R10x, R15, R16i, R20d, R20f, R20u, R21a, R21s, R22, R22g, R22v, R26, R26p, R29k, R31, R33, R34, R34c, R35, R36b, R36p, R37, R37i, R38, R38c, R39, R40m, R42, R44, R45, R46c, R47, R47m, R47r, R48, R48s, R48u, R49a, R50, R52f, R55, R57e, R59, R66, R67f, R69, R70, R71, R72c, R74, http_5xx, page_error, request_failed

Armed and silent (no finding on either pass): G2, I-create, I-edit, I-error, I-logout, I-toggle, R01, R05, R06c, R06s, R07, R07b, R10, R12, R12b, R16u, R18, R19, R20t, R24, R24b, R25, R27, R28, R29, R32, R32d, R33g, R36, R36r, R40, R40c, R41, R46, R46w, R51, R51c, R52, R53, R54, R56, R57, R58, R60, R61, R62, R64, R67, R72, R73, R75, R77
