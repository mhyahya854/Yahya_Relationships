# Connections Redesign Screenshot Manifest

All captures were made with the isolated, deterministic Connections synthetic data root. The fixture contains only fictional records; it does not read or mutate the user’s production relationship data.

- Rebuild command: `npm run test:connections-redesign` from `Codebase`
- Synthetic people: 82
- Theme coverage: light and dark

| File | Screen | State | Theme | FROM | TO | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| connections-default-owner-immediate.png | Connections | default owner immediate view | light | Mira Rahim | — | Central FROM, direct family/general neighbours only, builder visible |
| connections-maternal-paternal-spacing.png | Connections | default spatial regions | light | Mira Rahim | — | Separate pale maternal and paternal contextual regions |
| connections-dark-default-immediate.png | Connections | default owner immediate view | dark | Mira Rahim | — | Direct context remains readable in dark mode |
| connections-info-overview.png | Connections | explicit info drawer overview | light | Mira Rahim | — | ⓘ only information entry point and real Overview fields |
| connections-info-relationships.png | Connections | explicit information drawer relationships | light | Mira Rahim | — | Implemented relationship facts are distinct from future boundaries |
| connections-info-memories.png | Connections | synthetic Memories drawer boundary | light | Mira Rahim | — | Clearly labelled synthetic future-domain preview |
| connections-info-events.png | Connections | synthetic Events drawer boundary | light | Mira Rahim | — | Clearly labelled synthetic future-domain preview |
| connections-info-media.png | Connections | synthetic media drawer boundary | light | Mira Rahim | — | No production media is fabricated |
| connections-search-expanded.png | Connections | search result actions | light | Mira Rahim | — | Search result supports reveal, Set as FROM, and Add to TO |
| connections-direct-friend-target.png | Connections | one direct friend target | light | Mira Rahim | Darya Sol | All canonical direct paths selected and context dimmed, not removed |
| connections-one-selected-route.png | Connections | one selected direct route | light | Mira Rahim | Darya Sol | A single selected route emphasizes only its direct edge |
| connections-greyed-context.png | Connections | active direct route with context | light | Mira Rahim | Darya Sol | Unrelated nodes stay mounted and visibly greyed |
| connections-family-multipath.png | Connections | family target with multiple paths | light | Mira Rahim | Darya Sol; Maeve Rowan | Multiple canonical maternal/paternal routes listed independently |
| connections-distant-mixed-route.png | Connections | distant mixed family and external route | light | Mira Rahim | Darya Sol; Maeve Rowan; Mila Rahal-Calder | Missing intermediates appear without removing surrounding immediate context |
| connections-multi-target-path-list.png | Connections | three simultaneous targets | light | Mira Rahim | Darya Sol; Maeve Rowan; Mila Rahal-Calder | Per-target all-route groups and union highlighting |
| connections-another-from.png | Connections | replacement FROM | light | Mariam Rahal | Darya Sol; Maeve Rowan; Mila Rahal-Calder | Exactly one FROM replaces the origin and re-queries route meaning |
| connections-return-owner.png | Connections | owner FROM restored | light | Mira Rahim | Darya Sol; Maeve Rowan; Mila Rahal-Calder | Return to My Perspective restores configured owner |
| connections-dark-theme.png | Connections | multiple targets dark mode | dark | Mira Rahim | Darya Sol; Maeve Rowan; Mila Rahal-Calder | Readable cards, dimming, regions, and route list in dark theme |
| connections-collapsed-navigation.png | Connections | collapsed navigation | dark | Mira Rahim | Darya Sol; Maeve Rowan; Mila Rahal-Calder | Builder and graph survive shell navigation collapse |
| people-directory.png | People | synthetic directory | light | Mira Rahim | — | 82 fictional people and overlapping groups |
| family-tree.png | Family Tree | Mermaid family screen | light | Mira Rahim | — | Family Tree remains a separate Mermaid experience |
| global-search.png | Search | synthetic root | light | Mira Rahim | — | Primary search surface remains available |
| hermes.png | Hermes | synthetic root | light | Mira Rahim | — | Existing deferred tooling remains separate from Connections |
| backups.png | Backups | synthetic root | light | Mira Rahim | — | Synthetic root backup surface remains available |

The synthetic drawer previews are explicitly labelled as fixture content and exercise future-domain UI boundaries only; they are not production data.
