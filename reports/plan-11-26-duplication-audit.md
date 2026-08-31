# Plan 11.26 Task 13 Duplication Audit

- Source commit: `b62462f11abe858f58af12fa2d2f159eae09d832`
- Inventory digest: `193cc3f963aee9515b2828fbac734a6fb3dda228af31845b3205f6a2084c1797`
- Algorithm: `plan1126-duplication-v1`
- Gate status: `ACCEPTED_OPEN`
- Historical 78 groups: prior high-recall upper bound only; not a defect count.

## Affirmative exclusions

| Exclusion | Owner | Matched files | Reason |
|---|---|---:|---|
| `tests` | `Plan 11.26 / production-risk boundary` | 281 | Duplicated test scaffolding does not carry the production latent-defect risk that motivated Task 13. |
| `evidence-collector` | `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR` | 19 | Evidence Collector is a separate product; cross-product similarity is deliberate product separation, not core-agent duplication debt. |
| `a2a-ledger` | `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` | 34 | A2A Ledger is a separate product; cross-product similarity is deliberate product separation, not core-agent duplication debt. |

## Raw candidate groups

Raw groups: **176**; confirmed partitions: **64**.

| Raw group | Kind | Members | Join basis |
|---|---|---:|---|
| `group-048d7f8e2810633908ec` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-055711dfd53ac37a4aba` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-07118eba6cb5defb3cbf` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-07c696ba2b8abfa82b66` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-09b7953360b416a212f7` | `CALLABLE_SHAPE` | 3 | `FEATURE_SIMILARITY` |
| `group-0a96d16abfc76f13e7fa` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-0bf8a8a4da9d6db376e1` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-0c9d95b9a54100c7b0af` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-0d8f4a3312f903a6c3f4` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-149be5bd12a4b5766c6f` | `CALLABLE_SHAPE` | 4 | `AST_SHAPE_EQUAL` |
| `group-19b650e5dbf6368f1458` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-1a5753389e3825aa4cba` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-1e1a14e9dc2dc9b3da6c` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-1f21f7273ef77af7fd92` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-20a2716adba20c901b0b` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-2397b1424ab2df61d00c` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-23ddb82a15871939344d` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-28d14cc414071015131c` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-2aeba8467b8c024dedc6` | `CALLABLE_SHAPE` | 4 | `FEATURE_SIMILARITY` |
| `group-2b052c33f035cbeb7856` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-2d6d1f53e693eba6c117` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-2ee1e535d49c61427409` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-30071942399150ada1de` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-304a8556136afc5b1c45` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-30e291e3c28dcc65447c` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-342ad0c1ee3ae44660da` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-363baa3b1a8a20758baf` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-36a6fa5fcfe22f3ef33f` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-376c0a0f91cf55034165` | `CALLABLE_SHAPE` | 8 | `FEATURE_SIMILARITY` |
| `group-3b59fdd1b49cfe3ab8a7` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-3db454028c617a9b6104` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-3dd67f351f773653b3bb` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-403cd10929ee1d70e6dc` | `CALLABLE_SHAPE` | 4 | `AST_SHAPE_EQUAL` |
| `group-41fe38719fc93d64e097` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-44129de492102986847b` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-46e6266a4abdcc36bcf2` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-47acb391d66316bca0b9` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-48a5a106a9e55b2e763a` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-4934031d0b395bc0da88` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-494ce4a96eed340f105d` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-4abc7d04edca7e33efaf` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-4d67c5a834fde7e8136c` | `CALLABLE_SHAPE` | 4 | `AST_SHAPE_EQUAL` |
| `group-4d774358c7ae3a6925db` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-4dc34331ee9e431d9f5e` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-4e620238fb849a418d09` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-5065ae1e04652155eab2` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-5286c9c03cd6b648c2f8` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-559353560ff9a3583efb` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-5691d4e7cb53c25a1b69` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-583206ad61a036726788` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-59af57f02d914a46a11f` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-5a4d6b1482ec0e35c7f7` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-5a6e0beb054be4e15638` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-5b959e5545233477f987` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-5cda7d2da439ace83128` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-5ce5585db8a4abef7d17` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-5e8238f80094ea5990a3` | `CALLABLE_SHAPE` | 3 | `FEATURE_SIMILARITY` |
| `group-5e8ffd809ddc7c5482eb` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-5f90646013f1df30c94b` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-5fdbc1cd33ee55cfc302` | `CALLABLE_SHAPE` | 3 | `FEATURE_SIMILARITY` |
| `group-5fe276536494d18658c2` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-60b8a811490f421ef175` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-60f834d232f009308762` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-61182a437f9212907341` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-6673a4236c00bb14c61e` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-68417088f3b908b70ac6` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-6a1ce9e3e0b337ad7847` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-6bca8426d5b4806fc8f9` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-6c7da599351fd2466f9b` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-6d09a041b5fcf713b375` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-71cda80310bdc4330a6d` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-7533c9fae2ef3a380372` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-7795514022efeb43b164` | `CALLABLE_SHAPE` | 3 | `FEATURE_SIMILARITY` |
| `group-797ac058afc8fe585f92` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-7c2658d6d18d2ff3c9cf` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-80b1299c473e88a7e78f` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-81f03bb2a4929001ce67` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-86359a9f8c790510203d` | `CALLABLE_SHAPE` | 6 | `AST_SHAPE_EQUAL` |
| `group-8a514cc9c648f769568d` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-8d52db208f6111cb8918` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-91655ba6c379dc998e01` | `CALLABLE_SHAPE` | 5 | `FEATURE_SIMILARITY` |
| `group-91849cd5716bcbf8a597` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-9297fd9c90595b599235` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-9abf926032feb5b69f4f` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-a6fd7cb96aa99c39920a` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-a79ad32a5b90505b9168` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-a8122bb7f4e85b433ff8` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-a99d47d385693de0910e` | `CALLABLE_SHAPE` | 5 | `AST_SHAPE_EQUAL` |
| `group-abe087e036446df4a118` | `CALLABLE_SHAPE` | 4 | `AST_SHAPE_EQUAL` |
| `group-b1c6b13419060dfccc0d` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-b3cf03a52409e49c708f` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-bc55eb153424cbcfd1dc` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-bcfc34c726c5bf479d4c` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-bd7366fb96a18840fadb` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-be669f624b8dd318089a` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-bf941db009a9a96e4e9e` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-c39b2f5fb4f16c7a8818` | `CALLABLE_SHAPE` | 4 | `AST_SHAPE_EQUAL` |
| `group-c6235ab40519cf1b7fe7` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-c9220adcb88c17e7b66a` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-ca7fdbc9ed7060937fb0` | `CALLABLE_SHAPE` | 5 | `AST_SHAPE_EQUAL` |
| `group-cb1d3b6bd6832022fa18` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-ced68e66be42b0732760` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-d02215214a87b5874e39` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-d0338174687cf5e77d57` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-d310e0046d4ab01264af` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-d62c8e5fcf5e4c941b8b` | `CALLABLE_SHAPE` | 13 | `FEATURE_SIMILARITY` |
| `group-d6937bb0fa978f605699` | `CALLABLE_SHAPE` | 4 | `AST_SHAPE_EQUAL` |
| `group-d8947b0ce9e28a4b31e1` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-d8b599b78011294ecbab` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-da0ee4533b741287a7ae` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-da8abee200d4360ac010` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-da949dd9e689bdf95b73` | `CALLABLE_SHAPE` | 4 | `FEATURE_SIMILARITY` |
| `group-db55cedfa6793e39e03a` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-dc53ca202d24535993b2` | `CALLABLE_SHAPE` | 2 | `FEATURE_SIMILARITY` |
| `group-ddbd4e20e7f7cc557bd2` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-e124ef8114ba155d4192` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-e360fde503120101366d` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-e5ce00ea9462ab43dda7` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-e696c2d563f7b4ebf8a4` | `CALLABLE_SHAPE` | 3 | `AST_SHAPE_EQUAL` |
| `group-eab3b5f0e062f7b174cd` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-f06b1e7c667cf717f291` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-f53276b5c21c632da47d` | `CALLABLE_SHAPE` | 4 | `FEATURE_SIMILARITY` |
| `group-fc5b2c47231fb520c239` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-fd09f63389e0d8098b12` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-fd30b58cce21ad802a59` | `CALLABLE_SHAPE` | 4 | `FEATURE_SIMILARITY` |
| `group-fe8e6d70aec34148a07b` | `CALLABLE_SHAPE` | 2 | `AST_SHAPE_EQUAL` |
| `group-14d47f088487a59028d9` | `CONSTANT_NAME` | 4 | `REPEATED_NAME` |
| `group-193f3a45533c316c201d` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-28d73e042b7ea4548762` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-5e60a9554d522954981f` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-689ba2ed546dfd45903b` | `CONSTANT_NAME` | 4 | `REPEATED_NAME` |
| `group-7d85a456ae9b9cefa85c` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-879f3c0c20235383e069` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-8824882b829029b8204b` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-918ac8402dbb7ae32055` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-97c320001b7f8c808bc9` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-9ba4f8bd61435b53cbf1` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-aa3dc5cfafebe63027c2` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-b1fd65445f10653a6fca` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-b557920e67f80a673ee4` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-c257581722871ed6d290` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-cd9f24f421a2c5207d2d` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-cdb25f07ed31d02bb557` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-cf0c025889299adb1b29` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-e15a5579645e3f106c8b` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-e9233eedf865674d90fe` | `CONSTANT_NAME` | 5 | `REPEATED_NAME` |
| `group-e9da8a61d951eaf52ecd` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-ec09fe86230c2b6540b3` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-f1cb5f0a868cd68d620a` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-fce2751a1dd8b272f17e` | `CONSTANT_NAME` | 2 | `REPEATED_NAME` |
| `group-20238afe83fee9874878` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-24db7b6fedca4a53bece` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-3fbbb7fa42e4ace0edf7` | `CONSTANT_VALUE` | 5 | `NORMALIZED_VALUE_EQUAL` |
| `group-455fae9670dcd5ab70b7` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-4cb38acecb7b10de6fa5` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-60c65e69d45a2d2c8a8c` | `CONSTANT_VALUE` | 3 | `NORMALIZED_VALUE_EQUAL` |
| `group-647459e1d24cddbfa8a5` | `CONSTANT_VALUE` | 4 | `NORMALIZED_VALUE_EQUAL` |
| `group-71bc2dbd0aa5b5b90e45` | `CONSTANT_VALUE` | 4 | `NORMALIZED_VALUE_EQUAL` |
| `group-72f03431168aa208704b` | `CONSTANT_VALUE` | 4 | `NORMALIZED_VALUE_EQUAL` |
| `group-814f9c002279b38b1c89` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-93723fd3be0f5a67d725` | `CONSTANT_VALUE` | 7 | `NORMALIZED_VALUE_EQUAL` |
| `group-95658ac6cd0efcb04ded` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-a62c11f5ac01ac2b6faf` | `CONSTANT_VALUE` | 7 | `NORMALIZED_VALUE_EQUAL` |
| `group-ae82343020d47a40cc00` | `CONSTANT_VALUE` | 3 | `NORMALIZED_VALUE_EQUAL` |
| `group-b7daef731b77f155496e` | `CONSTANT_VALUE` | 3 | `NORMALIZED_VALUE_EQUAL` |
| `group-c0ee486a4589b003ff3a` | `CONSTANT_VALUE` | 3 | `NORMALIZED_VALUE_EQUAL` |
| `group-c305beaafd374949f4b1` | `CONSTANT_VALUE` | 11 | `NORMALIZED_VALUE_EQUAL` |
| `group-d9a9f576246af6348798` | `CONSTANT_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-e02a7f6a2833c2d71620` | `CONSTANT_VALUE` | 10 | `NORMALIZED_VALUE_EQUAL` |
| `group-0091be5c24928b7a326d` | `REGEX_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-24048c6b5dfca308e2a6` | `REGEX_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-b36571e1c4b6b8e3f2bc` | `REGEX_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-bc11a85e70ca25668571` | `REGEX_VALUE` | 3 | `NORMALIZED_VALUE_EQUAL` |
| `group-c390703861025a5a3593` | `REGEX_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-d45f7a69a7c2efb1f306` | `REGEX_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |
| `group-dacc264c255abf35e146` | `REGEX_VALUE` | 2 | `NORMALIZED_VALUE_EQUAL` |

## Reviewed partitions

| Partition | Raw group | Disposition | Members | Rationale |
|---|---|---|---:|---|
| `partition-001` | `group-048d7f8e2810633908ec` | `CONFIRMED_DUPLICATION` | 2 | Redaction cleanup, containment, hashing, and count aggregation is repeated across 2 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-002` | `group-055711dfd53ac37a4aba` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-003` | `group-07118eba6cb5defb3cbf` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-004` | `group-07c696ba2b8abfa82b66` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-005` | `group-09b7953360b416a212f7` | `CONFIRMED_DUPLICATION` | 3 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 3 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-006` | `group-0a96d16abfc76f13e7fa` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-007` | `group-0bf8a8a4da9d6db376e1` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-008` | `group-0c9d95b9a54100c7b0af` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-009` | `group-0d8f4a3312f903a6c3f4` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-010` | `group-149be5bd12a4b5766c6f` | `INTENTIONAL_REPETITION` | 4 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-011` | `group-19b650e5dbf6368f1458` | `CONFIRMED_DUPLICATION` | 3 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 3 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-012` | `group-1a5753389e3825aa4cba` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-013` | `group-1e1a14e9dc2dc9b3da6c` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-014` | `group-1f21f7273ef77af7fd92` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-015` | `group-20a2716adba20c901b0b` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-016` | `group-2397b1424ab2df61d00c` | `STRUCTURAL_SIMILARITY_ONLY` | 2 | AST_SHAPE_EQUAL joins append, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-017` | `group-23ddb82a15871939344d` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-018` | `group-28d14cc414071015131c` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-019` | `group-2aeba8467b8c024dedc6` | `INTENTIONAL_REPETITION` | 4 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-020` | `group-2b052c33f035cbeb7856` | `CONFIRMED_DUPLICATION` | 3 | Redaction cleanup, containment, hashing, and count aggregation is repeated across 3 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-021` | `group-2d6d1f53e693eba6c117` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-022` | `group-2ee1e535d49c61427409` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-023` | `group-30071942399150ada1de` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-024` | `group-304a8556136afc5b1c45` | `CONFIRMED_DUPLICATION` | 2 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 2 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-025` | `group-30e291e3c28dcc65447c` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-026` | `group-342ad0c1ee3ae44660da` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-027` | `group-363baa3b1a8a20758baf` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-028` | `group-36a6fa5fcfe22f3ef33f` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-029` | `group-376c0a0f91cf55034165` | `INTENTIONAL_REPETITION` | 8 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-030` | `group-3b59fdd1b49cfe3ab8a7` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-031` | `group-3db454028c617a9b6104` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-032` | `group-3dd67f351f773653b3bb` | `CONFIRMED_DUPLICATION` | 2 | Security text sanitization and validation primitives is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-033` | `group-403cd10929ee1d70e6dc` | `CONFIRMED_DUPLICATION` | 4 | Domain and HTTPS normalization and matching policy is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-034` | `group-41fe38719fc93d64e097` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-035` | `group-44129de492102986847b` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-036` | `group-46e6266a4abdcc36bcf2` | `CONFIRMED_DUPLICATION` | 2 | Redis health-check exception normalization is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-037` | `group-47acb391d66316bca0b9` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-038` | `group-48a5a106a9e55b2e763a` | `CONFIRMED_DUPLICATION` | 2 | Evidence and provider-usage ledger settlement logic is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-039` | `group-4934031d0b395bc0da88` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-040` | `group-494ce4a96eed340f105d` | `CONFIRMED_DUPLICATION` | 2 | Evidence and provider-usage ledger settlement logic is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-041` | `group-4abc7d04edca7e33efaf` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-042` | `group-4d67c5a834fde7e8136c` | `CONFIRMED_DUPLICATION` | 4 | Evidence-runner helpers and pinned contract values is repeated across 3 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-043` | `group-4d774358c7ae3a6925db` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-044` | `group-4dc34331ee9e431d9f5e` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-045` | `group-4e620238fb849a418d09` | `CONFIRMED_DUPLICATION` | 2 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 2 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-046` | `group-5065ae1e04652155eab2` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-047` | `group-5286c9c03cd6b648c2f8` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-048` | `group-559353560ff9a3583efb` | `CONFIRMED_DUPLICATION` | 2 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-049` | `group-5691d4e7cb53c25a1b69` | `CONFIRMED_DUPLICATION` | 2 | Evidence and provider-usage ledger settlement logic is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-050` | `group-583206ad61a036726788` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-051` | `group-59af57f02d914a46a11f` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-052` | `group-5a4d6b1482ec0e35c7f7` | `CONFIRMED_DUPLICATION` | 2 | Evidence and provider-usage ledger settlement logic is independently implemented by the selected symbols across 2 modules; one contract can drift. |
| `partition-053` | `group-5a4d6b1482ec0e35c7f7` | `STRUCTURAL_SIMILARITY_ONLY` | 1 | The remaining symbols share a broad hashing shape but normalize different data contracts, so they do not have one owner. |
| `partition-054` | `group-5a6e0beb054be4e15638` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-055` | `group-5b959e5545233477f987` | `CONFIRMED_DUPLICATION` | 3 | Redaction cleanup, containment, hashing, and count aggregation is repeated across 3 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-056` | `group-5cda7d2da439ace83128` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-057` | `group-5ce5585db8a4abef7d17` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-058` | `group-5e8238f80094ea5990a3` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-059` | `group-5e8ffd809ddc7c5482eb` | `CONFIRMED_DUPLICATION` | 2 | Security text sanitization and validation primitives is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-060` | `group-5f90646013f1df30c94b` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-061` | `group-5fdbc1cd33ee55cfc302` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-062` | `group-5fe276536494d18658c2` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-063` | `group-60b8a811490f421ef175` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-064` | `group-60f834d232f009308762` | `CONFIRMED_DUPLICATION` | 2 | Security text sanitization and validation primitives is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-065` | `group-61182a437f9212907341` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-066` | `group-6673a4236c00bb14c61e` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-067` | `group-68417088f3b908b70ac6` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-068` | `group-6a1ce9e3e0b337ad7847` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-069` | `group-6bca8426d5b4806fc8f9` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-070` | `group-6c7da599351fd2466f9b` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-071` | `group-6d09a041b5fcf713b375` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-072` | `group-71cda80310bdc4330a6d` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-073` | `group-7533c9fae2ef3a380372` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-074` | `group-7795514022efeb43b164` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-075` | `group-797ac058afc8fe585f92` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-076` | `group-7c2658d6d18d2ff3c9cf` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-077` | `group-80b1299c473e88a7e78f` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-078` | `group-81f03bb2a4929001ce67` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-079` | `group-86359a9f8c790510203d` | `INTENTIONAL_REPETITION` | 6 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-080` | `group-8a514cc9c648f769568d` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-081` | `group-8d52db208f6111cb8918` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-082` | `group-91655ba6c379dc998e01` | `CONFIRMED_DUPLICATION` | 3 | Audit-tool canonicalization, symbol, citation, and visitor helpers is independently implemented by the selected symbols across 3 modules; one contract can drift. |
| `partition-083` | `group-91655ba6c379dc998e01` | `STRUCTURAL_SIMILARITY_ONLY` | 2 | The remaining symbols share a broad hashing shape but normalize different data contracts, so they do not have one owner. |
| `partition-084` | `group-91849cd5716bcbf8a597` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-085` | `group-9297fd9c90595b599235` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-086` | `group-9abf926032feb5b69f4f` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-087` | `group-a6fd7cb96aa99c39920a` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-088` | `group-a79ad32a5b90505b9168` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-089` | `group-a8122bb7f4e85b433ff8` | `CONFIRMED_DUPLICATION` | 2 | Domain and HTTPS normalization and matching policy is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-090` | `group-a99d47d385693de0910e` | `INTENTIONAL_REPETITION` | 5 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-091` | `group-abe087e036446df4a118` | `CONFIRMED_DUPLICATION` | 4 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 4 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-092` | `group-b1c6b13419060dfccc0d` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-093` | `group-b3cf03a52409e49c708f` | `CONFIRMED_DUPLICATION` | 2 | Credential fingerprints and launch-security constants is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-094` | `group-bc55eb153424cbcfd1dc` | `CONFIRMED_DUPLICATION` | 2 | Redaction cleanup, containment, hashing, and count aggregation is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-095` | `group-bcfc34c726c5bf479d4c` | `CONFIRMED_DUPLICATION` | 2 | Evidence acquisition and package-advisory recording helpers is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-096` | `group-bd7366fb96a18840fadb` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-097` | `group-be669f624b8dd318089a` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-098` | `group-bf941db009a9a96e4e9e` | `STRUCTURAL_SIMILARITY_ONLY` | 3 | AST_SHAPE_EQUAL joins _path_digest, _secret_digest, _digest, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-099` | `group-c39b2f5fb4f16c7a8818` | `INTENTIONAL_REPETITION` | 4 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-100` | `group-c6235ab40519cf1b7fe7` | `CONFIRMED_DUPLICATION` | 2 | Credential fingerprints and launch-security constants is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-101` | `group-c9220adcb88c17e7b66a` | `CONFIRMED_DUPLICATION` | 2 | Evidence acquisition and package-advisory recording helpers is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-102` | `group-ca7fdbc9ed7060937fb0` | `INTENTIONAL_REPETITION` | 5 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-103` | `group-cb1d3b6bd6832022fa18` | `CONFIRMED_DUPLICATION` | 2 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 1 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-104` | `group-ced68e66be42b0732760` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-105` | `group-d02215214a87b5874e39` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-106` | `group-d0338174687cf5e77d57` | `CONFIRMED_DUPLICATION` | 2 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 1 independently maintained module paths; FEATURE_SIMILARITY evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-107` | `group-d310e0046d4ab01264af` | `CONFIRMED_DUPLICATION` | 2 | Evidence acquisition and package-advisory recording helpers is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-108` | `group-d62c8e5fcf5e4c941b8b` | `INTENTIONAL_REPETITION` | 13 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-109` | `group-d6937bb0fa978f605699` | `CONFIRMED_DUPLICATION` | 4 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-110` | `group-d8947b0ce9e28a4b31e1` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-111` | `group-d8b599b78011294ecbab` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-112` | `group-da0ee4533b741287a7ae` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-113` | `group-da8abee200d4360ac010` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-114` | `group-da949dd9e689bdf95b73` | `INTENTIONAL_REPETITION` | 4 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-115` | `group-db55cedfa6793e39e03a` | `CONFIRMED_DUPLICATION` | 2 | Domain and HTTPS normalization and matching policy is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-116` | `group-dc53ca202d24535993b2` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-117` | `group-ddbd4e20e7f7cc557bd2` | `CONFIRMED_DUPLICATION` | 2 | Evidence and provider-usage ledger settlement logic is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-118` | `group-e124ef8114ba155d4192` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-119` | `group-e360fde503120101366d` | `CONFIRMED_DUPLICATION` | 2 | Retry delay conversion is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-120` | `group-e5ce00ea9462ab43dda7` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-121` | `group-e696c2d563f7b4ebf8a4` | `INTENTIONAL_REPETITION` | 3 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-122` | `group-eab3b5f0e062f7b174cd` | `CONFIRMED_DUPLICATION` | 2 | Domain and HTTPS normalization and matching policy is repeated across 2 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-123` | `group-f06b1e7c667cf717f291` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-124` | `group-f53276b5c21c632da47d` | `INTENTIONAL_REPETITION` | 4 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-125` | `group-fc5b2c47231fb520c239` | `CONFIRMED_DUPLICATION` | 2 | Audit-tool canonicalization, symbol, citation, and visitor helpers is repeated across 1 independently maintained module paths; AST_SHAPE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-126` | `group-fd09f63389e0d8098b12` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-127` | `group-fd30b58cce21ad802a59` | `STRUCTURAL_SIMILARITY_ONLY` | 4 | FEATURE_SIMILARITY joins __repr__, _ownership_citation, _serialize_planning_read_evidence, _serialize_planning_observation, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-128` | `group-fe8e6d70aec34148a07b` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-129` | `group-14d47f088487a59028d9` | `CONFIRMED_DUPLICATION` | 4 | Credential fingerprints and launch-security constants is repeated across 4 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-130` | `group-193f3a45533c316c201d` | `CONFIRMED_DUPLICATION` | 2 | Credential fingerprints and launch-security constants is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-131` | `group-28d73e042b7ea4548762` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-132` | `group-5e60a9554d522954981f` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-133` | `group-689ba2ed546dfd45903b` | `INTENTIONAL_REPETITION` | 4 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-134` | `group-7d85a456ae9b9cefa85c` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-135` | `group-879f3c0c20235383e069` | `CONFIRMED_DUPLICATION` | 2 | Credential fingerprints and launch-security constants is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-136` | `group-8824882b829029b8204b` | `CONFIRMED_DUPLICATION` | 2 | Planner directive grammar is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-137` | `group-918ac8402dbb7ae32055` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-138` | `group-97c320001b7f8c808bc9` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-139` | `group-9ba4f8bd61435b53cbf1` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-140` | `group-aa3dc5cfafebe63027c2` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-141` | `group-b1fd65445f10653a6fca` | `CONFIRMED_DUPLICATION` | 2 | Domain and HTTPS normalization and matching policy is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-142` | `group-b557920e67f80a673ee4` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-143` | `group-c257581722871ed6d290` | `CONFIRMED_DUPLICATION` | 2 | Security text sanitization and validation primitives is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-144` | `group-cd9f24f421a2c5207d2d` | `CONFIRMED_DUPLICATION` | 2 | Credential fingerprints and launch-security constants is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-145` | `group-cdb25f07ed31d02bb557` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-146` | `group-cf0c025889299adb1b29` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-147` | `group-e15a5579645e3f106c8b` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-148` | `group-e9233eedf865674d90fe` | `CONFIRMED_DUPLICATION` | 5 | Evidence-runner helpers and pinned contract values is repeated across 5 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-149` | `group-e9da8a61d951eaf52ecd` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-150` | `group-ec09fe86230c2b6540b3` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-151` | `group-f1cb5f0a868cd68d620a` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-152` | `group-fce2751a1dd8b272f17e` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; REPEATED_NAME evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-153` | `group-20238afe83fee9874878` | `STRUCTURAL_SIMILARITY_ONLY` | 2 | NORMALIZED_VALUE_EQUAL joins LANE_PROMPT_VERSION, MULTI_TURN_PLANNER_PROMPT_VERSION, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-154` | `group-24db7b6fedca4a53bece` | `CONFIRMED_DUPLICATION` | 2 | Evidence-runner helpers and pinned contract values is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-155` | `group-3fbbb7fa42e4ace0edf7` | `STRUCTURAL_SIMILARITY_ONLY` | 5 | NORMALIZED_VALUE_EQUAL joins _NO_MULTIPLE_TRUSTEE, _TRUSTEE_IS_SID, _NO_INHERITANCE, _ACCESS_ALLOWED_ACE_TYPE, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-156` | `group-455fae9670dcd5ab70b7` | `STRUCTURAL_SIMILARITY_ONLY` | 2 | NORMALIZED_VALUE_EQUAL joins MAX_TOKENS, _PREFIX_SUFFIX_MIN, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-157` | `group-4cb38acecb7b10de6fa5` | `STRUCTURAL_SIMILARITY_ONLY` | 2 | NORMALIZED_VALUE_EQUAL joins _ADVANCED_SEARCH_RESULT_CAP, _DEFAULT_MAX_CALLS_PER_TOOL, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-158` | `group-60c65e69d45a2d2c8a8c` | `STRUCTURAL_SIMILARITY_ONLY` | 3 | NORMALIZED_VALUE_EQUAL joins DEFAULT_MAX_PLANNING_TURNS, _TOKEN_QUERY, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-159` | `group-647459e1d24cddbfa8a5` | `STRUCTURAL_SIMILARITY_ONLY` | 4 | NORMALIZED_VALUE_EQUAL joins MAX_CATALOG_ELAPSED_SECONDS, _CAPTURE_WAIT_TIMEOUT_SECONDS, _PHOENIX_READY_TIMEOUT_SECONDS, DEFAULT_GATEWAY_TIMEOUT_SECONDS, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-160` | `group-71bc2dbd0aa5b5b90e45` | `STRUCTURAL_SIMILARITY_ONLY` | 4 | NORMALIZED_VALUE_EQUAL joins _DACL_SECURITY_INFORMATION, _MAX_UPSTREAM_ATTEMPTS, _ET_CORE, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-161` | `group-72f03431168aa208704b` | `STRUCTURAL_SIMILARITY_ONLY` | 4 | NORMALIZED_VALUE_EQUAL joins _ACP_TIMEOUT_SECONDS, _DRIVE_SESSION_WAIT_TIMEOUT_SECONDS, ACP_TIMEOUT_SECONDS, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-162` | `group-814f9c002279b38b1c89` | `STRUCTURAL_SIMILARITY_ONLY` | 2 | NORMALIZED_VALUE_EQUAL joins MANIFEST_MAX_AGE_SECONDS, TIMEOUT_SECONDS, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-163` | `group-93723fd3be0f5a67d725` | `STRUCTURAL_SIMILARITY_ONLY` | 7 | NORMALIZED_VALUE_EQUAL joins _ACL_SIZE_INFORMATION_CLASS, _OBJECT_INHERIT_ACE, _TRUSTEE_IS_GROUP, APPROVAL_SCHEMA_VERSION, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-164` | `group-95658ac6cd0efcb04ded` | `CONFIRMED_DUPLICATION` | 2 | Shared model defaults and MCP name grammar is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-165` | `group-a62c11f5ac01ac2b6faf` | `STRUCTURAL_SIMILARITY_ONLY` | 7 | NORMALIZED_VALUE_EQUAL joins _OWNER, _H3_OWNER, _H4_COVERAGE_OWNER, _COVERAGE_OWNER, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-166` | `group-ae82343020d47a40cc00` | `STRUCTURAL_SIMILARITY_ONLY` | 3 | NORMALIZED_VALUE_EQUAL joins _DEFAULT_PROVENANCE_TTL_SECONDS, DEFAULT_PLAN_TTL_SECONDS, _DEFAULT_CALL_CAP_TTL_SECONDS, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-167` | `group-b7daef731b77f155496e` | `CONFIRMED_DUPLICATION` | 3 | Credential fingerprints and launch-security constants is repeated across 3 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-168` | `group-c0ee486a4589b003ff3a` | `STRUCTURAL_SIMILARITY_ONLY` | 3 | NORMALIZED_VALUE_EQUAL joins _KEYRING_SERVICE, _CONFIG_DIR_NAME, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-169` | `group-c305beaafd374949f4b1` | `STRUCTURAL_SIMILARITY_ONLY` | 11 | NORMALIZED_VALUE_EQUAL joins MANIFEST_SCHEMA_VERSION, LEGACY_APPROVAL_SCHEMA_VERSION, CLIENT_MCP_SCHEMA_VERSION, _SE_FILE_OBJECT, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-170` | `group-d9a9f576246af6348798` | `INTENTIONAL_REPETITION` | 2 | These symbols are parallel variants, adapters, protocol methods, or fixed platform bindings in local APIs; repetition is deliberate and preserves separate boundary ownership. |
| `partition-171` | `group-e02a7f6a2833c2d71620` | `STRUCTURAL_SIMILARITY_ONLY` | 10 | NORMALIZED_VALUE_EQUAL joins MAX_COMPLETED_ATTEMPTS, MAX_CORRELATION_ORDINAL_UNDER_AMENDMENT, _MODEL_MAX_UPSTREAM_ATTEMPTS, WORKSPACE_IDENTITY_FORMAT_VERSION, but qualified paths and responsibilities are semantically distinct; shape, name, or value equality alone does not prove shared ownership. |
| `partition-172` | `group-0091be5c24928b7a326d` | `CONFIRMED_DUPLICATION` | 2 | Security text sanitization and validation primitives is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-173` | `group-24048c6b5dfca308e2a6` | `CONFIRMED_DUPLICATION` | 2 | Planner directive grammar is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-174` | `group-b36571e1c4b6b8e3f2bc` | `CONFIRMED_DUPLICATION` | 2 | Security text sanitization and validation primitives is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-175` | `group-bc11a85e70ca25668571` | `CONFIRMED_DUPLICATION` | 3 | Security text sanitization and validation primitives is repeated across 3 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-176` | `group-c390703861025a5a3593` | `CONFIRMED_DUPLICATION` | 2 | Planner directive grammar is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-177` | `group-d45f7a69a7c2efb1f306` | `CONFIRMED_DUPLICATION` | 2 | Shared model defaults and MCP name grammar is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |
| `partition-178` | `group-dacc264c255abf35e146` | `CONFIRMED_DUPLICATION` | 2 | Planner directive grammar is repeated across 2 independently maintained module paths; NORMALIZED_VALUE_EQUAL evidence and qualified responsibilities establish one drift-prone contract. |

## Confirmed findings

| Finding | Severity | Subject |
|---|---|---|
| `T13-FIND-001` | `HIGH` | Redaction cleanup, containment, hashing, and count aggregation |
| `T13-FIND-002` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-003` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-004` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-005` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-006` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-007` | `HIGH` | Redaction cleanup, containment, hashing, and count aggregation |
| `T13-FIND-008` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-009` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-010` | `HIGH` | Domain and HTTPS normalization and matching policy |
| `T13-FIND-011` | `HIGH` | Redis health-check exception normalization |
| `T13-FIND-012` | `HIGH` | Evidence and provider-usage ledger settlement logic |
| `T13-FIND-013` | `HIGH` | Evidence and provider-usage ledger settlement logic |
| `T13-FIND-014` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-015` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-016` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-017` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-018` | `HIGH` | Evidence and provider-usage ledger settlement logic |
| `T13-FIND-019` | `HIGH` | Evidence and provider-usage ledger settlement logic |
| `T13-FIND-020` | `HIGH` | Redaction cleanup, containment, hashing, and count aggregation |
| `T13-FIND-021` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-022` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-023` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-024` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-025` | `HIGH` | Domain and HTTPS normalization and matching policy |
| `T13-FIND-026` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-027` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-028` | `HIGH` | Redaction cleanup, containment, hashing, and count aggregation |
| `T13-FIND-029` | `MEDIUM` | Evidence acquisition and package-advisory recording helpers |
| `T13-FIND-030` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-031` | `MEDIUM` | Evidence acquisition and package-advisory recording helpers |
| `T13-FIND-032` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-033` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-034` | `MEDIUM` | Evidence acquisition and package-advisory recording helpers |
| `T13-FIND-035` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-036` | `HIGH` | Domain and HTTPS normalization and matching policy |
| `T13-FIND-037` | `HIGH` | Evidence and provider-usage ledger settlement logic |
| `T13-FIND-038` | `MEDIUM` | Retry delay conversion |
| `T13-FIND-039` | `HIGH` | Domain and HTTPS normalization and matching policy |
| `T13-FIND-040` | `MEDIUM` | Audit-tool canonicalization, symbol, citation, and visitor helpers |
| `T13-FIND-041` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-042` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-043` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-044` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-045` | `HIGH` | Planner directive grammar |
| `T13-FIND-046` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-047` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-048` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-049` | `HIGH` | Domain and HTTPS normalization and matching policy |
| `T13-FIND-050` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-051` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-052` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-053` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-054` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-055` | `MEDIUM` | Evidence-runner helpers and pinned contract values |
| `T13-FIND-056` | `MEDIUM` | Shared model defaults and MCP name grammar |
| `T13-FIND-057` | `HIGH` | Credential fingerprints and launch-security constants |
| `T13-FIND-058` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-059` | `HIGH` | Planner directive grammar |
| `T13-FIND-060` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-061` | `HIGH` | Security text sanitization and validation primitives |
| `T13-FIND-062` | `HIGH` | Planner directive grammar |
| `T13-FIND-063` | `MEDIUM` | Shared model defaults and MCP name grammar |
| `T13-FIND-064` | `HIGH` | Planner directive grammar |

## Ranked remediation custody

| Rank | Candidate | Shape | Surface | Severity | Owner-to-be |
|---:|---|---|---:|---|---|
| 1 | `T13-CAND-RUNNER-CONTRACTS` | `consolidation` | 37 | `MEDIUM` | P11-REMEDIATION-RUNNER-CONTRACTS |
| 2 | `T13-CAND-AUDIT-PRIMITIVES` | `consolidation` | 25 | `MEDIUM` | P11-REMEDIATION-AUDIT-PRIMITIVES |
| 3 | `T13-CAND-CREDENTIAL-CONTRACTS` | `consolidation` | 15 | `HIGH` | P11-REMEDIATION-CREDENTIAL-CONTRACTS |
| 4 | `T13-CAND-SECURITY-TEXT` | `consolidation` | 13 | `HIGH` | P11-REMEDIATION-SECURITY-TEXT-POLICY |
| 5 | `T13-CAND-DOMAIN-HTTPS` | `consolidation` | 12 | `HIGH` | P11-REMEDIATION-DOMAIN-POLICY |
| 6 | `T13-CAND-LEDGER-ACCOUNTING` | `consolidation` | 10 | `HIGH` | P11-REMEDIATION-LEDGER-ACCOUNTING |
| 7 | `T13-CAND-REDACTION-LIFETIME` | `consolidation` | 10 | `HIGH` | P11-REMEDIATION-REDACTION-LIFETIME |
| 8 | `T13-CAND-DIRECTIVE-GRAMMAR` | `consolidation` | 6 | `HIGH` | P11-REMEDIATION-DIRECTIVE-GRAMMAR |
| 9 | `T13-CAND-EVIDENCE-SERVICE` | `consolidation` | 6 | `MEDIUM` | P11-REMEDIATION-EVIDENCE-SERVICES |
| 10 | `T13-CAND-SHARED-DEFAULTS` | `consolidation` | 4 | `MEDIUM` | P11-REMEDIATION-SHARED-CONFIG |
| 11 | `T13-CAND-REDIS-HEALTH` | `consolidation` | 2 | `HIGH` | P11-REMEDIATION-REDIS-RUNTIME |
| 12 | `T13-CAND-RETRY-TIMING` | `consolidation` | 2 | `MEDIUM` | P11-REMEDIATION-RETRY-POLICY |
