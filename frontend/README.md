# Frontend: European Emissions Explorer

React + TypeScript dashboard for the Climate Emissions Platform API.

```bash
npm install
cp .env.example .env.local   # points at http://localhost:8000 by default
npm run dev                  # http://localhost:5173
npm test                     # Vitest + Testing Library
npm run build                # type-check and build to dist/
```

- Data fetching and caching with TanStack Query; the API client surfaces the API's RFC 9457
  error details.
- Charts are plain SVG components (no chart library). Each has a hover/keyboard tooltip
  and a data-table view, and supports dark mode. The three source colours were checked
  for colour-vision deficiency in light and dark mode.
- The selected country is kept in the URL (`?country=FR`), so views can be shared.
