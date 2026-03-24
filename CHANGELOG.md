# [0.27.0](https://github.com/marco0560/repoindex/compare/v0.26.0...v0.27.0) (2026-03-24)


### Features

* **docstrings:** harden NumPy docstring audit engine ([b4e7b2d](https://github.com/marco0560/repoindex/commit/b4e7b2df077f702755c44aacb361c4106a73b668))

# [0.26.0](https://github.com/marco0560/repoindex/compare/v0.25.1...v0.26.0) (2026-03-24)


### Features

* **context:** improve deterministic context rendering quality ([6957b2d](https://github.com/marco0560/repoindex/commit/6957b2d62d5809f481e8669834508358babd0d7d))

## [0.25.1](https://github.com/marco0560/repoindex/compare/v0.25.0...v0.25.1) (2026-03-24)


### Bug Fixes

* **retrieval:** stabilize deterministic channel merge behavior ([7a24686](https://github.com/marco0560/repoindex/commit/7a24686a46648859d936fc3a2a73bba7b7abca86))

# [0.25.0](https://github.com/marco0560/repoindex/compare/v0.24.1...v0.25.0) (2026-03-24)


### Features

* **release:** stabilize tagging and guard commit scopes ([762c5f9](https://github.com/marco0560/repoindex/commit/762c5f955292f91bbd70eaf210bacb93c49afd14))

## [0.24.1](https://github.com/marco0560/repoindex/compare/v0.24.0...v0.24.1) (2026-03-24)


### Bug Fixes

* **release:** add package-lock for npm ci ([3f1c8f8](https://github.com/marco0560/repoindex/commit/3f1c8f8df1f670c45811d520ef6f8745771c6d47))
* **release:** lock semantic-release toolchain for CI ([4d38c4d](https://github.com/marco0560/repoindex/commit/4d38c4df70b2e20860fd581f93ded50c570bad75))


### Features

* **context,json-schema:** introduce schema v1.1 validation and fix explain contract ([4423ab5](https://github.com/marco0560/repoindex/commit/4423ab5668861c1710781b06c97421c888706ddd))

# [0.24.0](https://github.com/marco0560/repoindex/compare/v0.23.0...v0.24.0) (2026-03-24)


### Features

* **query:** introduce rank-based multi-channel retrieval with independent semantic channel ([282fc1e](https://github.com/marco0560/repoindex/commit/282fc1e102e5a6a0c24b6e28998e41d2a61ac5f3))

# [0.23.0](https://github.com/marco0560/repoindex/compare/v0.22.2...v0.23.0) (2026-03-24)


### Features

* **retrieval:** introduce semantic channel (deterministic token-overlap) ([3a49623](https://github.com/marco0560/repoindex/commit/3a49623eb684241fdf1ece7ba0d403ef298ede86))

## [0.22.2](https://github.com/marco0560/repoindex/compare/v0.22.1...v0.22.2) (2026-03-23)


### Bug Fixes

* **context:** complete JSON explain mode and stabilize explain output ([9d0fcc9](https://github.com/marco0560/repoindex/commit/9d0fcc911cd6c3adaf4d9cd671d6331c0b12a702))

## [0.22.1](https://github.com/marco0560/repoindex/compare/v0.22.0...v0.22.1) (2026-03-23)


### Bug Fixes

* **context:** propagate as_json and as_prompt flags to renderer ([e3eccd6](https://github.com/marco0560/repoindex/commit/e3eccd62559c439cfb711594533b990ae2f3dd97))

# [0.22.0](https://github.com/marco0560/repoindex/compare/v0.21.0...v0.22.0) (2026-03-23)


### Features

* **explain:** add merge provenance and winner attribution to explain mode ([538dd1e](https://github.com/marco0560/repoindex/commit/538dd1e71f2823f6015bfb9c732cbe6bdab94aa4))

# [0.21.0](https://github.com/marco0560/repoindex/compare/v0.20.0...v0.21.0) (2026-03-23)


### Features

* **cli,context:** introduce explain mode flag and plumbing ([49d8381](https://github.com/marco0560/repoindex/commit/49d8381fbca7150c99bbaadf2654a55594667adc))
* **explain:** add routing diagnostics and per-channel results to context output ([2a667cf](https://github.com/marco0560/repoindex/commit/2a667cf0915e63273295a0f0e1b432644ff338b4))

# [0.20.0](https://github.com/marco0560/repoindex/compare/v0.19.0...v0.20.0) (2026-03-22)


### Features

* **retrieval:** introduce intent-based channel routing and remove symbol scoring bias ([0590958](https://github.com/marco0560/repoindex/commit/05909588e905c8fee9ba7beb8801aa003afd60c7))

# [0.19.0](https://github.com/marco0560/repoindex/compare/v0.18.0...v0.19.0) (2026-03-22)


### Features

* **retrieval:** route channels by intent and remove symbol scoring bias ([9b3c987](https://github.com/marco0560/repoindex/commit/9b3c987616c139cc95dff4f88dfda2e409b7d3a1))

# [0.18.0](https://github.com/marco0560/repoindex/compare/v0.17.0...v0.18.0) (2026-03-22)


### Features

* **retrieval:** activate test and script channels in pipeline (phase 1 completion) ([474ee2b](https://github.com/marco0560/repoindex/commit/474ee2bf2b8fc000b42bccc4f7bcfd1a6dd87094))

# [0.17.0](https://github.com/marco0560/repoindex/compare/v0.16.0...v0.17.0) (2026-03-22)


### Features

* **retrieval:** introduce multi-channel retrieval (phase 1, symbol channel extraction) ([5785474](https://github.com/marco0560/repoindex/commit/578547499878fa88bf34561d1901718e6daa3705))

# [0.16.0](https://github.com/marco0560/repoindex/compare/v0.15.0...v0.16.0) (2026-03-22)


### Features

* **query:** add script-intent symmetry in classifier and scoring ([182563d](https://github.com/marco0560/repoindex/commit/182563d6601bd5349676c08044ccd59d2f30b5dc))

# [0.15.0](https://github.com/marco0560/repoindex/compare/v0.14.0...v0.15.0) (2026-03-22)


### Features

* **query:** introduce QueryIntent classification, integrate intent-aware scoring ([c9b7e59](https://github.com/marco0560/repoindex/commit/c9b7e593df529126333b558428849469c762630f))

# [0.14.0](https://github.com/marco0560/repoindex/compare/v0.13.0...v0.14.0) (2026-03-22)


### Features

* **repoindex:** extract agent prompt rendering into prompts module ([534f63e](https://github.com/marco0560/repoindex/commit/534f63e92280a0151873956b1e0f7eba7b7cadb2))

# [0.13.0](https://github.com/marco0560/repoindex/compare/v0.12.2...v0.13.0) (2026-03-22)


### Features

* **repoindex:** unify retrieval pipeline with single final ranking/pruning stage ([cdc81a5](https://github.com/marco0560/repoindex/commit/cdc81a5efe7b084cfbbaa9e63651e2ee203b4b7c))

## [0.12.2](https://github.com/marco0560/repoindex/compare/v0.12.1...v0.12.2) (2026-03-21)


### Bug Fixes

* **query:** add fallback retrieval when strong token filtering yields no results ([2d0ca92](https://github.com/marco0560/repoindex/commit/2d0ca92a382dce80a5cbe1c34173ed9e75bf0607))

## [0.12.1](https://github.com/marco0560/repoindex/compare/v0.12.0...v0.12.1) (2026-03-21)


### Bug Fixes

* **query:** prevent empty retrieval results with deterministic fallback ([16551ed](https://github.com/marco0560/repoindex/commit/16551ed38f0a32b2bb86be17da5d2b163f7da636))

# [0.12.0](https://github.com/marco0560/repoindex/compare/v0.11.1...v0.12.0) (2026-03-21)


### Features

* **context:** stabilize retrieval quality, packaging, and cleanup behavior ([bc4fee7](https://github.com/marco0560/repoindex/commit/bc4fee741acf1e7a872c91cfa9ae9795902ee649))

## [0.11.1](https://github.com/marco0560/repoindex/compare/v0.11.0...v0.11.1) (2026-03-21)


### Bug Fixes

* **clean:** preserve generated version file and reduce retrieval noise ([f335dba](https://github.com/marco0560/repoindex/commit/f335dbaa84d135877d5bcd05dedc24c901b424f4))

# [0.11.0](https://github.com/marco0560/repoindex/compare/v0.10.1...v0.11.0) (2026-03-21)


### Features

* **build:** added automatic git tags-based version number ([eb2ef18](https://github.com/marco0560/repoindex/commit/eb2ef18bd203b73f12bd2f3a724756cc167332bd))

## [0.10.1](https://github.com/marco0560/repoindex/compare/v0.10.0...v0.10.1) (2026-03-21)


### Bug Fixes

* **build:** enforced repoindex version coherent with git tags ([2e2b598](https://github.com/marco0560/repoindex/commit/2e2b59895004ef66d08bf728a6e9ff8255ed62a7))

# [0.10.0](https://github.com/marco0560/repoindex/compare/v0.9.0...v0.10.0) (2026-03-21)


### Features

* **context:** add token-based cap to JSON context rendering ([8c5e816](https://github.com/marco0560/repoindex/commit/8c5e816f94f64e57f27f93da42bb837ed68d4212))

# [0.9.0](https://github.com/marco0560/repoindex/compare/v0.8.0...v0.9.0) (2026-03-21)


### Features

* **context:** add confidence scores to top matches ([d19f77a](https://github.com/marco0560/repoindex/commit/d19f77a2d46f5e7a620f831b48a066d59b055bf4))

# [0.8.0](https://github.com/marco0560/repoindex/compare/v0.7.0...v0.8.0) (2026-03-21)


### Features

* **context:** deduplicate symbols and references for cleaner agent context ([a555d8b](https://github.com/marco0560/repoindex/commit/a555d8b9fad847888f7e17d294e694edd717044f))

# [0.7.0](https://github.com/marco0560/repoindex/compare/v0.6.0...v0.7.0) (2026-03-21)


### Features

* **context:** add test-aware reference prioritization ([9c43f97](https://github.com/marco0560/repoindex/commit/9c43f97a29ac609f959cde45d4acfec891566220))

# [0.6.0](https://github.com/marco0560/repoindex/compare/v0.5.0...v0.6.0) (2026-03-21)


### Features

* **query:** add issue-driven context enrichment ([2dcefad](https://github.com/marco0560/repoindex/commit/2dcefadb998764ca99bdf446ce612d706db35fe0))

# [0.5.0](https://github.com/marco0560/repoindex/compare/v0.4.0...v0.5.0) (2026-03-21)


### Features

* **index:** add lightweight unresolved call graph extraction ([a51a558](https://github.com/marco0560/repoindex/commit/a51a558be4737d0ee5b9491beaec2c8ccfee799e))

# [0.4.0](https://github.com/marco0560/repoindex/compare/v0.3.0...v0.4.0) (2026-03-21)


### Features

* **agent:** add Codex-ready prompt output for context-for ([e56083a](https://github.com/marco0560/repoindex/commit/e56083ad04b4c04340b2491a8537e332a15be694))

# [0.3.0](https://github.com/marco0560/repoindex/compare/v0.2.0...v0.3.0) (2026-03-21)


### Features

* **context:** add structured JSON output and improve context quality ([f5c784a](https://github.com/marco0560/repoindex/commit/f5c784ac17884a51424a076b8cda673971499e1c))

# [0.2.0](https://github.com/marco0560/repoindex/compare/v0.1.0...v0.2.0) (2026-03-21)


### Features

* **context:** JSON output, schema contract, CLI integration, context pipeline hardening ([eb89b16](https://github.com/marco0560/repoindex/commit/eb89b1697cb586f7886e5ef6201ca2b71020f5ee))
* **context:** stabilize context_for pipeline and align query with indexing ([382200b](https://github.com/marco0560/repoindex/commit/382200b61f39577f5a87b3f5563b4e96bc9eacc7))
* enable semantic release pipeline ([435ba80](https://github.com/marco0560/repoindex/commit/435ba80729bf66c48a3b041320b224a8c4da6efd))
* **shcema:** added schema for json output ([a0b7176](https://github.com/marco0560/repoindex/commit/a0b717607658688c23149674f65d18d0f9768269))
* test release pipeline ([e7fea68](https://github.com/marco0560/repoindex/commit/e7fea686be35400ba08233226f6ece53e9c91db1))

# Changelog

All notable changes to this project will be documented in this file.
