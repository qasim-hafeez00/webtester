# v5.0 lock check: v62 against v5

## Run level, all rules

| app | recall (score, median) vs ref | ok | precision | ok | clean FA/run | ok | lock |
|---|---|---|---|---|---|---|---|
| bookstack | 8/13, 0.4615 vs 8/13, 0.4615 | yes | 91/95 = 0.9579 (0 unlabelled) | yes | 0.8 (4 in 5; 0 unlabelled) | **no** | **no** |
| realworld | 7/8, 0.75 vs 7/8, 0.75 | yes | 65/100 = 0.65 (0 unlabelled) | **no** | 5.2 (26 in 5; 0 unlabelled) | **no** | **no** |

## Run level without R02h, R02m, R09, R09d, R12c, R21b, R30, R50m, R65, R68t

| app | recall (score, median) vs ref | ok | precision | ok | clean FA/run | ok | lock |
|---|---|---|---|---|---|---|---|
| bookstack | 8/13, 0.4615 vs 8/13, 0.4615 | yes | 90/92 = 0.9783 (0 unlabelled) | yes | 0.4 (2 in 5; 0 unlabelled) | yes | yes |
| realworld | 7/8, 0.75 vs 7/8, 0.75 | yes | 65/67 = 0.9701 (0 unlabelled) | yes | 0.2 (1 in 5; 0 unlabelled) | yes | yes |

## Rule level (section 12.2)

85 of 143 rules meet (1), (2), (4), (5). Rules with findings or false alarms:

| rule | test | armed | seeded family | findings | precision | tier | clean FA | faults | enters |
|---|---|---|---|---|---|---|---|---|---|
| I-delete | yes | 41 | yes | 13 | 1.0 | T1 | 1 | F06 | yes |
| I-filter | yes | 70 | yes | 14 | 1.0 | T1 | 0 | F10 | yes |
| I-submit | yes | 16 | yes | 10 | 0.8 | T2 | 0 | F01, F02 | yes |
| R01x | yes | 1578 | **no** | 3 | 1.0 | T2 | 0 |  | yes |
| R02 | yes | 258 | yes | 1 | 1.0 | T2 | 0 | BS04 | yes |
| R02h | yes | 1578 | **no** | 3 | 0.0 | T2 | 0 |  | yes |
| R02m | yes | 1463 | **no** | 1 | 0.0 | T2 | 0 |  | yes |
| R03 | yes | 915 | yes | 20 | 1.0 | T1 | 0 | BS05, BS06, BS07, BS08 | yes |
| R04 | yes | 126 | yes | 15 | 1.0 | T1 | 0 | BS05, BS06, BS08 | yes |
| R07c | yes | 9 | yes | 5 | 1.0 | T1 | 0 | F08 | yes |
| R08 | yes | 286 | yes | 23 | 0.913 | T1 | 2 | BS09, BS10, BS11 | yes |
| R09 | yes | 434 | yes | 3 | 0.3333 | T2 | 1 | BS04 | yes |
| R09d | yes | 35 | **no** | 2 | 0.0 | T2 | 2 |  | yes |
| R11 | yes | 16 | yes | 5 | 1.0 | T1 | 0 | F09 | yes |
| R12c | yes | 2 | **no** | 1 | 0.0 | T2 | 1 |  | yes |
| R13 | yes | 65 | yes | 1 | 1.0 | T2 | 0 | F07 | yes |
| R16 | yes | 45 | yes | 4 | 1.0 | T2 | 0 | F01 | yes |
| R17 | yes | 45 | yes | 8 | 1.0 | T1 | 0 |  | yes |
| R21b | yes | 10 | yes | 1 | 0.0 | T2 | 1 |  | yes |
| R23m | yes | 20 | **no** | 10 | 1.0 | T1 | 0 |  | yes |
| R30 | yes | 43 | **no** | 17 | 0.0 | T2 | 15 |  | yes |
| R43 | yes | 696 | **no** | 19 | 1.0 | T1 | 0 |  | yes |
| R48c | yes | 20 | **no** | 5 | 1.0 | T1 | 0 |  | yes |
| R50m | yes | 8 | **no** | 3 | 0.0 | T2 | 5 |  | yes |
| R63 | yes | 78 | **no** | 2 | 1.0 | T2 | 0 |  | yes |
| R65 | yes | 1578 | **no** | 4 | 0.0 | T2 | 0 |  | yes |
| R68 | yes | 4 | **no** | 1 | 1.0 | T2 | 0 |  | yes |
| R68t | yes | 75 | **no** | 1 | 0.0 | T2 | 2 |  | yes |

**no fixture test** (0): -

**never armed** (58): G1, G3, R02d, R02s, R04b, R06, R09r, R10x, R15, R16i, R20d, R20f, R20u, R21a, R21s, R22, R22g, R22v, R26, R26p, R29k, R31, R33, R34, R34c, R35, R36b, R36p, R37, R37i, R38, R38c, R39, R40c, R40m, R42, R44, R45, R46c, R47, R47m, R47r, R48, R48s, R48u, R49a, R50, R52f, R55, R57e, R59, R66, R67f, R69, R70, R71, R72c, R74

Armed and silent (no finding on either pass): G2, I-create, I-edit, I-error, I-logout, I-toggle, R01, R05, R06c, R06s, R07, R07b, R10, R12, R12b, R16u, R18, R19, R20, R20t, R23, R24, R24b, R25, R27, R28, R29, R32, R32d, R33g, R36, R36r, R40, R41, R46, R46w, R49, R51, R51c, R52, R53, R54, R56, R57, R58, R60, R61, R62, R64, R67, R72, R73, R75, R77, http_5xx, page_error, request_failed
