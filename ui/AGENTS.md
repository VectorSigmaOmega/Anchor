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
- Keep chat history scoped to the anonymous `anchor_session` cookie through the
  `/chat-api/conversations` endpoints. Do not introduce accounts, login flows,
  cross-device identity, or client-side API keys.
- Run `npm run lint` and `npm run build` after frontend changes.
- Visually inspect `/` and `/chat` at mobile, tablet, desktop, and at least one
  intermediate width before calling UI work complete.

## Astryx Setup

The global stylesheet imports the required Astryx reset, core CSS, and neutral
theme, and `<html data-astryx-theme="neutral">` maps Astryx's tokens onto
Anchor's in `globals.css`. If `@astryxdesign/core` is upgraded, run the Astryx
upgrade workflow and re-check the rendered chat composer states.

Do not wrap the console in Astryx's `<Theme>` component. Its wrapper element
declares `--color-border`, `--color-accent` and `--color-success` itself, which
shadowed Anchor's values and turned every citation neutral grey; it also stamps
`color-scheme` from a React prop, which overrode the root's dark mode for the
whole console. `ChatComposer` renders correctly without it. `.workspace`
re-asserts those three tokens from `--brand-*` aliases as a guard.

## Appearance

`app/theme.tsx` owns light/dark. A blocking script in `app/layout.tsx` sets
`color-scheme` and `data-theme` on `<html>` before first paint, from
`localStorage` or `prefers-color-scheme`. Neither attribute may be rendered from
JSX — React resets `data-theme` to the prerendered value during hydration.
Read the current mode from `style.colorScheme`, which React never manages.

## Icons

All icons are inline SVG in `app/icons.tsx` — stroke-based, `currentColor`,
round caps and joins. There is no icon library; do not add one.
