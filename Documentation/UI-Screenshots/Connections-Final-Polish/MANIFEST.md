# Connections Final Polish Screenshot Manifest

All captures were made with the isolated, deterministic Connections synthetic data root. The fixture contains only fictional records; it does not read or mutate the user’s production relationship data.

- Rebuild command: `npm run test:connections-redesign` from `Codebase`
- Synthetic people: 82
- Theme coverage: light and dark

| File | Screen | State | Theme | FROM | TO | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| connections-default-owner-immediate.png | Connections | default owner immediate view | light | Mira Rahim | — | Central FROM, readable direct family/general neighbours only |
| connections-maternal-paternal-compact-islands.png | Connections | compact contextual islands | light | Mira Rahim | — | Maternal and paternal islands fit their direct members |
| connections-compact-external-sector.png | Connections | lower external arc | light | Mira Rahim | — | Direct external relationships form a deliberate lower sector |
| connections-builder-compact.png | Connections | compact Relationship Builder | light | Mira Rahim | — | FROM, TO, and immediate rows remain scannable |
| connections-dark-default.png | Connections | default owner immediate view | dark | Mira Rahim | — | Direct context and compact islands remain readable |
| connections-alternate-from-few.png | Connections | alternate FROM with few direct connections | light | Mariam Rahal | — | Small direct world remains close to FROM |
| connections-alternate-from-many.png | Connections | alternate FROM with dense direct context | light | Darya Sol | — | Dense direct world expands without losing central readability |
| connections-info-overview.png | Connections | explicit info drawer overview | light | Mira Rahim | — | ⓘ only information entry point and real Overview fields |
| connections-info-relationships.png | Connections | explicit information drawer relationships | light | Mira Rahim | — | Implemented relationship facts are distinct from future boundaries |
| connections-info-relationship-paths.png | Connections | canonical paths information tab | light | Mira Rahim | — | Relationship Paths is a dedicated visible drawer tab |
| connections-info-memories.png | Connections | synthetic Memories drawer boundary | light | Mira Rahim | — | Clearly labelled synthetic future-domain preview |
| connections-info-events.png | Connections | synthetic Events drawer boundary | light | Mira Rahim | — | Clearly labelled synthetic future-domain preview |
| connections-info-photos-videos.png | Connections | synthetic Photos & Videos drawer boundary | light | Mira Rahim | — | No production media is fabricated |
| connections-info-conversations.png | Connections | synthetic Conversations drawer boundary | light | Mira Rahim | — | Conversations remains an honest synthetic-only boundary |
| connections-info-documents.png | Connections | synthetic Documents drawer boundary | light | Mira Rahim | — | Documents remains an honest synthetic-only boundary |
| connections-info-places-travel.png | Connections | synthetic Places / Travel drawer boundary | light | Mira Rahim | — | Places / Travel is a dedicated visible drawer tab |
| connections-info-groups.png | Connections | implemented Groups drawer tab | light | Mira Rahim | — | Real supported group content stays distinct from future domains |
| connections-info-journal-notes.png | Connections | implemented Journal / Notes drawer tab | light | Mira Rahim | — | Real synthetic journal is available through its dedicated tab |
| connections-search-popover.png | Connections | compact search result actions | light | Mira Rahim | — | Search remains a compact popover with Set as FROM and Add to TO |
| connections-one-direct-to.png | Connections | one direct friend target | light | Mira Rahim | Darya Sol | Direct TO remains strong while context stays mounted |
| connections-greyed-context.png | Connections | active direct route with context | light | Mira Rahim | Darya Sol | Unrelated nodes stay mounted and visibly greyed |
| connections-builder-compact-path-state.png | Connections | compact TO and path rows | light | Mira Rahim | Darya Sol | Builder path rows remain compact and scannable |
| connections-one-distant-to.png | Connections | one distant mixed route | light | Mira Rahim | Mila Rahal-Calder | Neutral intermediates appear without removing immediate context |
| connections-family-multipath.png | Connections | one family target with multiple paths | light | Mira Rahim | Maeve Rowan | Multiple canonical maternal and paternal routes remain independently visible |
| connections-one-selected-path.png | Connections | one selected route among valid multipath routes | light | Mira Rahim | Maeve Rowan | Selected route is strongest; alternate valid route remains lighter |
| connections-multi-target.png | Connections | three simultaneous targets | light | Mira Rahim | Maeve Rowan; Darya Sol; Mila Rahal-Calder | Per-target compact route rows and union highlighting |
| connections-dark-path-state.png | Connections | multiple targets dark mode | dark | Mira Rahim | Maeve Rowan; Darya Sol; Mila Rahal-Calder | Readable cards, dimming, selected routes, and compact path rows |
| connections-collapsed-navigation.png | Connections | collapsed navigation | dark | Mira Rahim | Maeve Rowan; Darya Sol; Mila Rahal-Calder | Builder and graph survive shell navigation collapse |

The synthetic drawer previews are explicitly labelled as fixture content and exercise future-domain UI boundaries only; they are not production data.
