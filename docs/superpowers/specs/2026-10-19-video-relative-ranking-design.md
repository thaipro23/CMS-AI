# Video relative ranking v2

Approved scope: user's seven deployment instructions of 16 October, resumed 19 October 2026. This supersedes v1 video ranking. Baseline: dbd0c62. Implement and merge after green CI without another approval. Execution: inline, one independent final review. No production connection or deployment has been established.

## Outcome and invariants

Video first. Display a relative rank, measured features, median and MAD explanations, never a verdict or violation probability. Keep official grades and existing rule results intact. Quiz ML defaults disabled separately; future enablement requires compatible telemetry from CMS-FPT PR #3 on plugin 0.4.18 or newer, deployed and verified (do not downgrade to the older 0.4.17 package).

## Measurement

Persist versioned video playback measurements in existing progress evidence, separately from legacy wall-time totals. Count plausible media advancement during observed playing intervals; exclude seek jumps and cap supported observed speed at 4x. Derive rate from media/wall advancement, not an assumption that every learner watches at 1x. Keep informational average rate outside ranking features. Carry playback state between incremental batches; replaying an event must not add time again. Legacy cumulative rows without a complete measurement history and intervals with missing positions cannot supply a reliable rank. No invented historical rates. Three distinct measured videos are required.

Normalize coverage and completion by video length. Rank on completion/coverage gap, coverage ratio, seeks per media minute and passive media ratio. Treat closed, measured zero-coverage intervals as zero, while missing observations remain missing. A long seek cannot create watched content. Supported fast viewers with the same observed content advancement get equivalent ranking features.

## Cohorts and bounded reads

At least 30 distinct canonical learners, 30–49 labelled LOW confidence / “Độ tin cậy thấp”, 50+ STANDARD. Configured minimum may be higher, never below 30. Reference cap 5,000, stable hash sampling; source and roster bounds remain. Explicit ANALYTICS_ML_VIDEO_REFERENCE_COURSE_IDS (maximum 20 including the requested course) pools active effective class/course rosters. An empty list uses the requested course. Combine valid video measurements per learner across that pool, qualify current-outline identities within each course, count each learner once. Group by exposure (3–5 / 6–10 / 11+) and median video duration regime (up to 5 / up to 20 / over 20 minutes). No course IDs, reference names or answers are exposed by the card.

## Statistics and comparison

Median/MAD baseline: per feature median, scale=max(1.4826*MAD, numerical floor). Gap has positive direction, coverage negative; seeks and passive are descriptive two-sided deviations. The baseline score is the maximum directed robust deviation. Zero MAD uses a documented floor (0.05 for ratios, 1 for seeks/media-minute), not division by zero. Peer percentile uses midranks; ties are not arbitrarily ordered.

Fit Isolation Forest for comparison only, 200 trees, seed 42 by default, one thread, max_samples<=256. Compare rankings using Spearman rank correlation >=0.8 AND tie-aware top-five overlap >=0.8. MAD is the primary visible method; when agreement is close show the simpler explanation, otherwise expose both relative percentiles and say the methods differ. No forced fraction, categorical outlier label or automated action. Explanations are the directed baseline contributions, not claimed IF causal attribution. Optional comparison failure leaves valid MAD scores available with an explicit comparison-unavailable state.

## Controls and presentation

Retain ANALYTICS_ML_MODE=off as global kill switch and explicit pilot classes. Add ANALYTICS_ML_VIDEO_ENABLED=true and ANALYTICS_ML_QUIZ_ENABLED=false. Gates checked before reads and writes; API immediately hides saved ranks when off. Default source config remains off, without fabricated pilot IDs. GET only reads persisted, versioned, scoped evidence; stale or malformed evidence cannot surface active scores. Public fields use relative score/rank, confidence, method, comparison and measured deviations; no outlier boolean.

## Acceptance

Tests: 29 cannot score; 30–49 low confidence; 50 standard; duplicates do not increase people. 1x/2x equivalent coverage, seek jumps excluded, missing measurements excluded, incremental partition/replay invariance. Synthetic high-completion/very-low-coverage people lead both ranked lists. Run seeds 0,1,7,42,99, compare every pair's top-five overlap >=80%; test row-order and ties. Constant data, zero MAD, missing/nonfinite data, comparison failure, source bounds, cancellation and off gates. Real cross-course roster test, no cross-scope persistence, API sanitization and UI copy tests. Benchmarks 1,000 and 5,000 rows in fresh processes, <10 seconds / <256 MiB incremental RSS as test budgets (not production SLO). Replay retained exports and report skipped groups/reasons without identifying learners. CI must exercise all new tests before merge.
