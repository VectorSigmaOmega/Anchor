# UI Agent Notes

Anchor's UI uses Next.js static export with selected Astryx components for the
chat composer and theme primitives. Keep future changes compatible with the
existing exported deployment shape.

## Practical Rules

- Preserve static export compatibility. Routes must build to files under `out/`
  and be reachable through nginx clean-route fallbacks.
- Use Astryx components where they reduce implementation complexity, especially
  for chat/composer primitives.
- Custom semantic markup and CSS are allowed for product layout, landing pages,
  and app-specific transcript presentation.
- Keep client-side history local to the browser. Do not introduce accounts,
  server-side chat storage, or client-side API keys.
- Run `npm run lint` and `npm run build` after frontend changes.
- Visually inspect `/` and `/chat` at mobile, tablet, desktop, and at least one
  intermediate width before calling UI work complete.

## Astryx Setup

The global stylesheet imports the required Astryx reset, core CSS, and neutral
theme. If `@astryxdesign/core` is upgraded, run the Astryx upgrade workflow and
re-check the rendered chat composer states.
