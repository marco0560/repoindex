# [1.8.0](https://github.com/marco0560/repoindex/compare/v1.7.1...v1.8.0) (2026-04-03)


### Features

* **cli:** enrich docstring audit results ([684915e](https://github.com/marco0560/repoindex/commit/684915e6e2eefaf2078d7abbe065c9fa213edf41))

## [1.7.1](https://github.com/marco0560/repoindex/compare/v1.7.0...v1.7.1) (2026-04-03)


### Bug Fixes

* **docstrings:** skip shell audit issues ([48329f4](https://github.com/marco0560/repoindex/commit/48329f45f4a94c5a271ac3c319ef73f94ec845f7))

# [1.7.0](https://github.com/marco0560/repoindex/compare/v1.6.1...v1.7.0) (2026-04-03)


### Features

* **cli:** add JSON output for index command ([a77f10d](https://github.com/marco0560/repoindex/commit/a77f10da7c4c966ba3e6181371bcb12b60cc8307))

## [1.6.1](https://github.com/marco0560/repoindex/compare/v1.6.0...v1.6.1) (2026-04-03)


### Bug Fixes

* **docstrings:** make audit-docstrings language-aware for current analyzers ([a40e90b](https://github.com/marco0560/repoindex/commit/a40e90bf255ded6e56b39b70a1b6c1dc7cc522bf))

# [1.6.0](https://github.com/marco0560/repoindex/compare/v1.5.0...v1.6.0) (2026-04-03)


### Features

* **embeddings:** batch index-time embedding generation ([c9d339e](https://github.com/marco0560/repoindex/commit/c9d339eddf09e859f89184c7f183dbb0f1b6b544))

# [1.5.0](https://github.com/marco0560/repoindex/compare/v1.4.0...v1.5.0) (2026-04-03)


### Features

* **packaging:** deprecate stale extras and label plugin origin ([a3d7a49](https://github.com/marco0560/repoindex/commit/a3d7a49bc0af4f31907bb03b4166a7618784e8b2))
* **packaging:** extract official analyzer packages ([c4197f8](https://github.com/marco0560/repoindex/commit/c4197f87b88ef515bfa24b76814249d720a5a254))

# [1.4.0](https://github.com/marco0560/repoindex/compare/v1.3.0...v1.4.0) (2026-04-02)


### Features

* **core:** add capability-driven retrieval signal layer ([d78b6bb](https://github.com/marco0560/repoindex/commit/d78b6bb8070e6dcea67994541951cfcd79b4274c)), closes [#9](https://github.com/marco0560/repoindex/issues/9)

# [1.3.0](https://github.com/marco0560/repoindex/compare/v1.2.1...v1.3.0) (2026-04-02)


### Bug Fixes

* **bash:** deduplicate redefined shell functions before indexing ([878dcb1](https://github.com/marco0560/repoindex/commit/878dcb1904c3ab74c1f86f38ad098a52fea147da))
* **index:** deduplicate C declarations and collapse index tracebacks ([55cafe1](https://github.com/marco0560/repoindex/commit/55cafe19a1ba284dbd29d33c95b947d3546aa2c0))
* **index:** disambiguate duplicate C function stable IDs with a deterministic suffix ([d6661a7](https://github.com/marco0560/repoindex/commit/d6661a7d0ee6ccc2532f168a1031a069f6269772))
* **index:** preserve stable ids across C and Python edge cases ([3d66264](https://github.com/marco0560/repoindex/commit/3d6626421efca2b0b566003eaf02b8d1deb46a9a))


### Features

* **analyzer:** add call site extraction to bash analyzer ([d38d1cf](https://github.com/marco0560/repoindex/commit/d38d1cf9412e05c9e47b5c950ba95b9dd680d4eb))
* **analyzers:** add BashAnalyzer for shell function extraction ([fb76aea](https://github.com/marco0560/repoindex/commit/fb76aeaa9ed362c3a1c56798e4036e56f5b505d3))

## [1.2.1](https://github.com/marco0560/repoindex/compare/v1.2.0...v1.2.1) (2026-03-30)


### Bug Fixes

* **parser:** ignore nested helper control flow in docstring metadata ([5511edc](https://github.com/marco0560/repoindex/commit/5511edc62bea935943bc173753ef45c697a44cc6))

# [1.2.0](https://github.com/marco0560/repoindex/compare/v1.1.1...v1.2.0) (2026-03-30)


### Bug Fixes

* **index:** preserve freshness metadata across queries ([3d314ea](https://github.com/marco0560/repoindex/commit/3d314eab7c94ac62ae2ea9c4af059c948b7b8db0))


### Features

* **index:** serialize rebuilds across processes ([0875b3f](https://github.com/marco0560/repoindex/commit/0875b3fc6018580b92a17c41daa33621c3d71c19))

## [1.1.1](https://github.com/marco0560/repoindex/compare/v1.1.0...v1.1.1) (2026-03-29)


### Bug Fixes

* **semantic:** streamline first-party embedding setup ([331e730](https://github.com/marco0560/repoindex/commit/331e730f5bab9bd6ed0a21ad6ed47ccb7746ebba))

# [1.1.0](https://github.com/marco0560/repoindex/compare/v1.0.3...v1.1.0) (2026-03-29)


### Features

* **semantic:** introduce real persisted embeddings with durable symbol identity ([cdc56b7](https://github.com/marco0560/repoindex/commit/cdc56b701dda5376ae0baeeaf57e421f8dc0bd7f)), closes [#1](https://github.com/marco0560/repoindex/issues/1)

## [1.0.3](https://github.com/marco0560/repoindex/compare/v1.0.2...v1.0.3) (2026-03-29)


### Bug Fixes

* **mypy:** tolerate optional tree-sitter imports ([42e94a1](https://github.com/marco0560/repoindex/commit/42e94a1dd77e33e0138f7424e5d6350802b03340))

## [1.0.2](https://github.com/marco0560/repoindex/compare/v1.0.1...v1.0.2) (2026-03-29)


### Bug Fixes

* **indexer:** keep indexing through parser warnings and failures ([8b6a021](https://github.com/marco0560/repoindex/commit/8b6a0211bd1c7b20a270c7eb50bf612016721d7f)), closes [#3](https://github.com/marco0560/repoindex/issues/3)

## [1.0.1](https://github.com/marco0560/repoindex/compare/v1.0.0...v1.0.1) (2026-03-29)


### Bug Fixes

* **c-analyzer:** skip malformed macro pseudo-functions ([57c3cc2](https://github.com/marco0560/repoindex/commit/57c3cc20015082cb28aa864eaf2f666c1c534a2b))

# [1.0.0](https://github.com/marco0560/repoindex/compare/v0.34.0...v1.0.0) (2026-03-29)


### Features

* **release:** promote stable major versioning ([c64aac1](https://github.com/marco0560/repoindex/commit/c64aac139970a1ef725413940f91b207ba3e6ce7))


### BREAKING CHANGES

* **release:** semantic-release now promotes breaking changes on the pre-1.0 line to major releases, so the next breaking publish from main enters the 1.x series instead of remaining on 0.x.

# [0.34.0](https://github.com/marco0560/repoindex/compare/v0.33.1...v0.34.0) (2026-03-29)


### Features

* **adr-004:** complete multi-language plugin architecture ([57526cc](https://github.com/marco0560/repoindex/commit/57526ccfee03fa8416472fc7dde4c917a878416a)), closes [#2](https://github.com/marco0560/repoindex/issues/2)


### BREAKING CHANGES

* **adr-004:** repoindex now assumes the ADR-004 plugin architecture. Third-party analyzers must register through the repoindex.analyzers entry-point group, provide deterministic discovery_globs metadata, and participate in plugin-aware coverage and rebuild semantics. Optional C-family support is no longer part of the core install and must be installed via the dedicated analyzer dependency path.

## [0.33.1](https://github.com/marco0560/repoindex/compare/v0.33.0...v0.33.1) (2026-03-28)


### Bug Fixes

* **release:** publish github releases ([208ce21](https://github.com/marco0560/repoindex/commit/208ce212f39f028cdd0316809e400d9256873288))

# [0.33.0](https://github.com/marco0560/repoindex/compare/v0.32.0...v0.33.0) (2026-03-28)


### Features

* **query:** add json output for exact query subcommands ([f3dd5e5](https://github.com/marco0560/repoindex/commit/f3dd5e5b190748aab125e28437303b4cf1b7f529))

# [0.32.0](https://github.com/marco0560/repoindex/compare/v0.31.4...v0.32.0) (2026-03-27)


### Features

* **prefix:** add repo-root scoped query filtering ([3a64334](https://github.com/marco0560/repoindex/commit/3a64334212b190e7d6d1f67376a67b6592b77251))

## [0.31.4](https://github.com/marco0560/repoindex/compare/v0.31.3...v0.31.4) (2026-03-27)


### Bug Fixes

* **docstring:** enforce python result-section semantics ([16f0f81](https://github.com/marco0560/repoindex/commit/16f0f8132fb916f4e225b5a92765cf62dd567da8))

## [0.31.3](https://github.com/marco0560/repoindex/compare/v0.31.2...v0.31.3) (2026-03-27)


### Bug Fixes

* **docstring:** require Yields for generator audits ([3a87e66](https://github.com/marco0560/repoindex/commit/3a87e6693617dc82183e58c7dce936e50588cca3))

## [0.31.2](https://github.com/marco0560/repoindex/compare/v0.31.1...v0.31.2) (2026-03-26)


### Bug Fixes

* **parser:** preserve chained attribute call sites ([bb9383a](https://github.com/marco0560/repoindex/commit/bb9383aed1a1a756ad74a890a1a99253ab888944))

## [0.31.1](https://github.com/marco0560/repoindex/compare/v0.31.0...v0.31.1) (2026-03-26)


### Bug Fixes

* **build:** introduced development dependencies in pyproject.toml ([ec86e71](https://github.com/marco0560/repoindex/commit/ec86e716e0acf92af0c3ca552937c4aa0f9c9397))
* normalize windows path handling ([69c5259](https://github.com/marco0560/repoindex/commit/69c5259d148b58b3a90b30f209b1b0cb033a7aee))

# [0.31.0](https://github.com/marco0560/repoindex/compare/v0.30.0...v0.31.0) (2026-03-25)


### Features

* add incremental indexing ([acea3a9](https://github.com/marco0560/repoindex/commit/acea3a9874a1ea6d0134f021fbf8b5ac3d2902e6))

# [0.30.0](https://github.com/marco0560/repoindex/compare/v0.29.1...v0.30.0) (2026-03-25)


### Features

* add embedding backend metadata ([7c418e8](https://github.com/marco0560/repoindex/commit/7c418e8c24cea4feb0ea8a37f4677d774d84af9f))
* expand context with graph relations ([3aa0d85](https://github.com/marco0560/repoindex/commit/3aa0d85301d37c17c735f4cb25d4125eaff7cb84))

## [0.29.1](https://github.com/marco0560/repoindex/compare/v0.29.0...v0.29.1) (2026-03-25)


### Bug Fixes

* reject mixed context output modes ([1856d6f](https://github.com/marco0560/repoindex/commit/1856d6f626d16ddfa3d351aef8d39be5f8cd898e))

# [0.29.0](https://github.com/marco0560/repoindex/compare/v0.28.0...v0.29.0) (2026-03-25)


### Features

* add deterministic embedding retrieval ([18257a7](https://github.com/marco0560/repoindex/commit/18257a7893e2ccc2e3076df0122e08b1153866c0))

# [0.28.0](https://github.com/marco0560/repoindex/compare/v0.27.4...v0.28.0) (2026-03-25)


### Bug Fixes

* improve cli help output ([0be499f](https://github.com/marco0560/repoindex/commit/0be499f9023d17422df8dcd4579aab78bce9eb29))


### Features

* add static call graph indexing ([d83fe90](https://github.com/marco0560/repoindex/commit/d83fe904f1646d2b08cfe56e7e5806e4c172f827))
* index callable references ([ecf9c1a](https://github.com/marco0560/repoindex/commit/ecf9c1a289397828e9764ab6f10ce7b2df898c8f))

## [0.27.4](https://github.com/marco0560/repoindex/compare/v0.27.3...v0.27.4) (2026-03-25)


### Bug Fixes

* clarify ri-fix help ([380eac3](https://github.com/marco0560/repoindex/commit/380eac353042388a2e8ac82931046c398e1f119c))

## [0.27.3](https://github.com/marco0560/repoindex/compare/v0.27.2...v0.27.3) (2026-03-25)


### Bug Fixes

* describe context-for help ([76dd9fe](https://github.com/marco0560/repoindex/commit/76dd9fe671be43def184df88d7cea3c29519e358))

## [0.27.2](https://github.com/marco0560/repoindex/compare/v0.27.1...v0.27.2) (2026-03-24)


### Bug Fixes

* **prompt:** added prompts for roadmap enhancements ([51721e1](https://github.com/marco0560/repoindex/commit/51721e1dfa5b3982427231c9aba0484b8a5d4f70))

## [0.27.1](https://github.com/marco0560/repoindex/compare/v0.27.0...v0.27.1) (2026-03-24)


### Bug Fixes

* **prompt:** enhanced criteria ([9d76f6d](https://github.com/marco0560/repoindex/commit/9d76f6db0fe45566e0f22dc593238225512f6ff3))

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
