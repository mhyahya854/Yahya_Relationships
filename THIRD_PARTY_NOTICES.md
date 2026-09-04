# Third-party notices

People Relationships builds on open-source packages. No GEDCOM Navigator
source code was copied into this project; only general navigation concepts
(bounded path exploration, expand/collapse, relationship-to-path
explanation) were adapted to this codebase's own architecture.

## JavaScript / frontend

### @xyflow/react (React Flow) — MIT

- Used for: the diagram-first Relationships graph (nodes, edges, zoom/pan,
  fit-to-view, selection, path highlighting).
- License: MIT — see https://github.com/xyflow/xyflow

### @dagrejs/dagre — MIT

- Used for: deterministic hierarchical graph layout.
- License: MIT — see https://github.com/dagrejs/dagre

### mermaid — MIT

- Used for: the existing Family (Mermaid) genealogy renderer.
- License: MIT — see https://github.com/mermaid-js/mermaid

### react / react-dom — MIT

### vite, @vitejs/plugin-react, typescript — MIT

## Python / backend

### fastapi, uvicorn, pydantic, httpx, pytest — MIT/BSD

Refer to each package's own license for exact terms. MIT license text for the
frontend packages above is available in the respective package folders under
`app/frontend/node_modules/<package>/LICENSE`.
