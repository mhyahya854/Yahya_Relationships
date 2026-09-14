# Phase 10 Motion Evidence

## Motion intent

Motion is limited to orientation, hierarchy, and immediate interaction feedback. It does not animate graph geometry continuously, delay data work, or compete with names and relationships.

| Surface | Implementation | Purpose |
| --- | --- | --- |
| Shared modal | Backdrop opacity plus short modal opacity/translate/scale entry | Preserve spatial context and clarify the active layer |
| Context inspector | Short opacity/translate entry | Connect a selected graph node with its detail panel |
| Target card | Short disclosure entry and rotating chevron | Make independent target/path state legible |
| Sidebar | Grid-column/padding transition and icon rotation | Preserve orientation while expanding or collapsing navigation |
| Controls | Fast transform/color/shadow feedback | Confirm hover, press, focus, and selected state |
| Search and docks | Width/opacity transitions | Reveal secondary controls without permanently covering the graph |

Durations use the shared `--duration-fast`, `--duration-standard`, and `--duration-slow` tokens with standard and emphasized curves. Transform and opacity are preferred for entry motion; layout animation is limited to the intentional sidebar/search width changes.

## Interruption and accessibility

- CSS transitions remain interruptible when a user reverses a control.
- `prefers-reduced-motion: reduce` collapses animation and transition duration to `0.001ms` and removes smooth scrolling.
- Reduced-transparency mode replaces glass surfaces with solid raised surfaces.
- Focus is moved into portal dialogs, trapped while open, restored to the invoking control on close, and kept visible.
- No animation dependency, scroll-trigger system, perpetual ambient loop, or novelty motion was added.

## Verification

- The 124/124 visual suite exercises dialogs, inspector states, target disclosures, sidebar expanded/collapsed states, responsive views, Light/Dark theme switching, and reduced-motion CSS presence.
- The final screenshot package contains before/after states for sidebar expansion, target selection/removal, search expansion, dialogs, legends, fullscreen, and responsive layouts.
- Static screenshots prove state and geometry; the implementation table above is the motion evidence. Human review remains required for perceived timing and feel.
