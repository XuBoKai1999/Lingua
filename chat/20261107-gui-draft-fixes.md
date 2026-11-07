# GUI draft and import fixes — 2026-11-07

Scope: follow-up to `c454e65`, implementing the three independently reproduced issues authorized by the user. No schema changes or new dependencies.

- Creation forms now confirm before discarding a draft on Back, Home, Cancel, or window close. Cancelling keeps the same form, text, source/stage selections and navigation history. A failed creation keeps this protection; successful creation proceeds without a discard prompt.
- Edit Course writes before accepting the dialog. A failed write shows the error while keeping the edited fields open for retry or cancellation. Workspace state updates only after a successful save.
- Loading non-UTF-8 import files shows an explicit Traditional Chinese UTF-8 error. Existing import text, validation state and stored curriculum remain intact.
- Updated `steps.md` to describe the implemented GUI and follow-up verification.

Verification: `29 passed` in the full pytest suite (Qt offscreen), all 7 Python source/test files parsed, and `git diff --check` passed. Added regression checks for all three leave routes (cancel/discard), source-only drafts, creation failure/success, edit write failure followed by retry/cancel, and invalid UTF-8 preservation. Existing storage and GUI smoke tests also passed. Native Windows font/DPI appearance was not checked in this round.

Correction to the previous review: the 900×600 / 200% button geometry was sampled before Qt layout settled; the independent retest found it recovers after further event processing. That finding is withdrawn and no layout change was made. Course display-name edits retaining the directory name are confirmed behavior, but directory renaming or unique display names were not required; that finding is also withdrawn. No directory-moving mechanism was added. The stale `steps.md` statement is fixed above.

The implementation stays in the existing UI module and tests. Drafts remain in memory until created or explicitly discarded; no draft persistence or other features were added.
