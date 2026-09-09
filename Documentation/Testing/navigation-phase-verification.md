# Phase 9 Navigation / Overall UX Verification

## Scope and revision convention

Phase 9 began from `853143dec6e4dd1e318e44cfe38a063e4b3d3653` (`Complete atomic DataRoot onboarding and recovery`). The final Phase 9 SHA is the commit containing this document. A commit cannot embed its own SHA; the exact immutable SHA is therefore recorded in the final handoff and in the exact-SHA `Build & Package Matrix` run.

Application schema remains 2 and Data Root format remains 1. This phase changes only frontend navigation ownership, cross-screen handoffs, bounded return context, and their browser verification. It does not alter the backend, kinship or Search semantics, Journals, backup transactions, Data Root lifecycle, Hermes, or production data, and it does not start Phase 10 or Phase 11.

## Architecture audited and defects found

The audit traced `App.tsx`/Shell, `PerspectiveProvider`, People/Profile, Relationships, Family, Search, Backups, Data Root and startup/recovery views, shared person search, canonical-ID callbacks, root-keyed remounting, and controlled reloads. Backend code was inspected only where root identity, canonical IDs, and perspective state cross the API boundary.

Before Phase 9, primary navigation did not expose a semantic active state; Search unmounted and lost valid query/results state; contextual transitions had no bounded return path; a primary People click could reopen a stale contextual profile; Relationships selection had competing local/Shell state and could be cleared during a perspective handoff; rapid asynchronous handoffs could resolve out of order; the global and Relationships headers duplicated the same perspective-return control; several supported Profile/Relationships/Search-to-Family paths were absent; and generalized Family state retained a production-specific fallback ID.

The implementation keeps Shell as the single cross-screen navigation authority. It uses no router, URL state, browser history, local storage, SQLite navigation state, new dependency, or timeout-based completion. A monotonic request ID plus a serialized promise chain makes asynchronous Relationships handoffs last-request-wins while still awaiting an explicitly requested perspective change. A single in-memory return context supports only the current source/destination pair and is cleared by primary navigation, successful return, or root remount.

The Graphify source map was used only as a discovery aid because its health report contained 43 dangling-endpoint edges and 32 collapsed same-endpoint pairs. Every affected path and state boundary was verified in source and by real UI tests.

## State ownership and reset policy

| State | Authority | Ordinary screen change | Primary navigation | Data Root change |
| --- | --- | --- | --- | --- |
| Active screen | Shell | Changes to destination; one item has `aria-current=page` | Clears contextual return; primary People also clears its contextual target | Shell remounts to the normal default screen |
| Global My Perspective | root-keyed `PerspectiveProvider` | Persists unless an explicit perspective action changes it | Persists | Re-read from the new root |
| People/Profile target | Shell canonical person ID | Retained only for a contextual return/reconstruction | Cleared by primary People | Cleared by Shell remount |
| Relationships target | Shell canonical person ID, mirrored by Relationships selection | Persists for legitimate leave/return; invalid IDs are cleared | Reopens the legitimate current target | Cleared by Shell remount |
| Relationships perspective | Global My Perspective | Persists; explicit A-to-B handoff awaits perspective A first | Persists | Re-read from the new root |
| Family focus | Shell, independent of global perspective | Persists | Persists | Cleared and initialized from the new root |
| Family selected person | Shell canonical person ID | Persists; an invalid person is deliberately cleared | Persists | Cleared by Shell remount |
| Search query/results/filter | Lazily mounted Search view | Persists during the same root session | Persists when returning to Search | Destroyed by root-keyed remount |
| Search selected result | No separate authority | The chosen canonical ID is handed to the destination | No stale selection is reopened | None can survive remount |
| Transient modals/drafts | Owning screen | Unmount on departure; dirty Profile Journal navigation is disabled/guarded | Reset | Reset |
| Undo state | Existing view-local notice plus backend root-bound history | View notice resets on unmount; backend behavior is unchanged | Unchanged Phase 4 behavior | Existing Phase 8 root change clears backend mutation history |
| Root identity | Backend Data Root manager plus root-keyed app boundary | Never changes through navigation | Never changes through navigation | Controlled activation/reload makes the new root authoritative everywhere |

## Contextual navigation contracts

- People/Profile to Relationships targets the same canonical person; an explicit source perspective is awaited before opening the destination.
- People/Profile, Relationships, and Search can open Family using the canonical person ID without changing global My Perspective or Family focus.
- Relationships to Profile and Family to Profile open the exact canonical person. Returning reconstructs the relevant prior target rather than retaining a hidden modal.
- Family to Relationships carries exact focus A and selected target B. Returning restores the same Family focus and selection.
- Search to Profile/Relationships/Family preserves the legitimate query/results/filter state for return within the same root session.
- Primary navigation is authoritative, clears bounded return context, and never performs data writes. Backups remains a normal primary destination; Change Location remains a contextual Data Root workflow.
- Missing People/Relationships/Family targets are cleared with an understandable error rather than guessed or replaced by a hard-coded identity.

## Root and startup isolation

The app remains keyed by active root identity, so switch/create/move/restore activation remounts all root-bound frontend state. The navigation E2E proves that Root A Search, Family, Relationships, People, owner, and return state do not appear after switching to the deliberately different Root B.

Startup states remain distinct: unreachable backend uses `StartupFailureView`; reachable `UNCONFIGURED` uses onboarding; `MISSING` uses location recovery; and successful creation/recovery enters a fresh normal Shell only after the backend operation completes. Existing `INVALID`, `HEALTHY`, `READ_ONLY`, `REPAIRABLE`, and `MAINTENANCE` handling is unchanged.

## Verification results

The starting baseline completed without backend failures and with the one pre-existing Windows symlink-capability skip. People 18/18, Relationships 37/37, Journals 48/48, Search 42/42, Backups 42/42, Data Root 50/50, and smoke 18/18 passed. The first sequential Family baseline attempt timed out after 54 checks; its immediate isolated rerun passed 65/65, and the final Phase 9 run also passed 65/65.

Final local gates:

- dedicated Phase 9 navigation E2E: 18/18;
- full backend: 494 collected, 493 passed and one existing Windows symlink-capability skip;
- focused Search: 57/57; focused Data Root: 60/60;
- focused Backups: 57 passed and the same one Windows capability skip;
- People 18/18; Relationships 37/37; Family 65/65; Journals 48/48; Search 42/42; Backups 42/42; Data Root 50/50; smoke 18/18;
- legacy audit: 35 people, 44 parent-child facts, 12 marriages, 10 sibling groups, 21 focus-person cousin paths, and arbitrary-perspective PASS;
- frontend TypeScript typecheck and production Vite build: PASS;
- Tauri `cargo check`: PASS;
- package privacy tests: 7/7; staged bundle path audit: 4 items inspected, zero private-data violations.

The dedicated E2E uses temporary bootstraps and two synthetic roots containing Alice/Amina/Farah Root A and Bob/Bilal/Zoya Root B. It verifies all six primary destinations, canonical targeting and return, exact perspective/target ordering, Family independence, Search preservation, rapid handoff determinism, Backups read purity, cross-root invalidation, onboarding, missing-root recovery, backend failure, and zero browser dialogs or unexpected page/console errors.

## Visual evidence

Only four Phase 9 screenshots were retained, all captured from the isolated synthetic root and visually inspected for active-state clarity, correct person/perspective context, return wording, clipping, stale content, duplicate controls, and accidental redesign:

- `Documentation/UI-Screenshots/primary-navigation-people.png`
- `Documentation/UI-Screenshots/navigation-search-to-profile.png`
- `Documentation/UI-Screenshots/navigation-family-to-relationships.png`
- `Documentation/UI-Screenshots/navigation-backups.png`

## Production integrity

Before Phase 9, `Database/Main/family.db` was 192,512 bytes with SHA-256 `3258C738F9D65B23B15970D0E1E7389E8584A35BA8E26030249061BAF74E096E`; all 35 Journal relative paths, sizes, and SHA-256 values and all 176 Backup file records were captured; and the actual OS bootstrap was 115 bytes with SHA-256 `108506C8E37F9EB38A1ECC8726A2D355C246F3675A3F6774E5BE75AFF8137FDD`.

After all local gates, the database size/hash, complete Journal manifest, complete Backup manifest, and bootstrap bytes/hash were exactly unchanged. `Database/` and `Backups/` have no Git changes; no WAL, SHM, temporary, staging, test-root, browser-profile, or listening test service remains. Navigation read-purity was also checked inside the synthetic root before and after opening all six destinations.

## Deliberate limitations

Return context is intentionally one level and in memory; it is not a browser-history clone and never crosses a Data Root. Search preservation lasts only for the active root session. No global visual redesign, motion system, typography/color revision, or broad component restyling was attempted; those remain Phase 10 concerns. Comprehensive focus choreography, landmark/announcement review, contrast work, and other accessibility quality-of-life expansion remain Phase 11 concerns. Hermes functionality remains parked.

After push, the exact final SHA's `Build & Package Matrix` is the required live proof for backend, legacy, frontend, native sidecar, Cargo, packaging, privacy audit, upload, and the four named Windows x64, macOS ARM64, macOS Intel x64, and Linux x64 artifacts.
