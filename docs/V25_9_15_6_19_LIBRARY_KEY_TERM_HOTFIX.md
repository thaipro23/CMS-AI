# v25.9.15.6.19 - Library Key includes Subject Term/Offering

## Problem

Bank Release for a subject version such as `WEB107_FA26 / Bài 2.1` was published to an Open edX Library key without the term:

```text
lib:FPT:web107-b-i-2-1-v1-0
```

FPT naming rule requires the term/version in the Library key:

```text
lib:FPT:web107-FA26-b-i-2-1-v1-0
```

## Fix

`QuestionBankService.release_library_key()` now includes the `SubjectOffering` term in the Open edX Library key.

Resolution order:

1. Use `SubjectOffering.term` when available.
2. Else parse the term from `SubjectOffering.code` by removing the subject code prefix.
   - `WEB107_FA26` -> `FA26`
   - `WEB107-SU25` -> `SU25`
3. If the bank version has no offering, keep the old fallback format.

## Existing old release keys

When publishing a release, if the stored `openedx_library_key` is missing the term, the backend upgrades it to the new expected key before calling the Open edX connector.

If the old release already had component IDs from the old library key, the publish flow forces re-import into the new key so the release points to the correct Library.

No database migration is required.
