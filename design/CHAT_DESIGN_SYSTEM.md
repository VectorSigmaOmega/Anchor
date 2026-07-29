# Chat Interface Design System

Rules for building chat UI. Read this before writing markup. When this document
and your instinct disagree, follow this document.

Influences: Linear (restraint, neutral surfaces, hairline borders), ChatGPT
(transcript and composer behaviour), Astryx `Chat*` components (token naming,
composer slot architecture).

---

## 0. Hard rules

Violating any of these makes the output wrong regardless of how it looks.

| # | Rule |
|---|------|
| 1 | **Two font families total.** One UI sans, one mono. Mono appears only inside code. |
| 2 | **Five type sizes total.** 12 / 13 / 15 / 17 / 20 px. Nothing larger ships in-product. |
| 3 | **Three font weights total.** 400, 500, 600. Never 300, never 700+, never italic for emphasis. |
| 4 | **One accent colour.** Used for focus, primary action, links, selection. Nothing else. |
| 5 | **Spacing comes from the scale.** 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48. No arbitrary values. |
| 6 | **Never put a label and a heading at wildly different sizes side by side.** If two pieces of text sit on the same line, they are within one step of each other. |
| 7 | **No decorative metadata.** No version badges, no "FIG 2.1", no section numbers, no fake status pills. If it isn't actionable or true, delete it. |
| 8 | **The transcript is capped at 720px.** Never full-bleed. |
| 9 | **Stop is always reachable while streaming**, by pointer and by keyboard. |
| 10 | **Never disable the composer input.** Not while streaming, not while awaiting a confirmation. |
| 11 | **The app frame never scrolls.** Only the transcript and the sidebar list scroll. Header, composer and account row are always visible at any viewport size or zoom level. |
| 12 | **`Enter` sends, `Shift+Enter` inserts a newline.** List markers continue automatically. |
| 13 | **Every user-initiated action shows feedback within 100ms**, even when the underlying work is instant. |

---

## 1. Tokens

Copy this block verbatim. Names follow the Astryx contract so a project already
on Astryx can swap the theme file and keep its components.

```css
:root {
  color-scheme: light dark;

  /* Surface */
  --color-bg-app:        light-dark(#FFFFFF, #1A1A1C);
  --color-bg-sunken:     light-dark(#F7F7F8, #131314);  /* sidebar */
  --color-bg-raised:     light-dark(#FFFFFF, #232325);  /* menus, cards */
  --color-bg-hover:      light-dark(#00000008, #FFFFFF0D);
  --color-bg-active:     light-dark(#00000012, #FFFFFF14);
  --color-bg-selected:   light-dark(#00000010, #FFFFFF12);

  /* Text */
  --color-text:           light-dark(#1A1A1A, #ECECEE);
  --color-text-secondary: light-dark(#6B6B70, #A0A0A6);
  --color-text-tertiary:  light-dark(#8B8B92, #74747A);
  --color-text-inverted:  light-dark(#FFFFFF, #1A1A1C);

  /* Line */
  --color-border:        light-dark(#E5E5E7, #2E2E31);
  --color-border-strong: light-dark(#D1D1D4, #3D3D41);

  /* Accent — focus, primary action, links, selection. Nothing else. */
  --color-accent:        light-dark(#2E6BE6, #5B8DEF);
  --color-accent-fg:     light-dark(#FFFFFF, #101014);
  --color-accent-subtle: light-dark(#2E6BE614, #5B8DEF1F);

  /* Status */
  --color-danger:  light-dark(#C5221F, #F28B82);
  --color-success: light-dark(#1E8E3E, #81C995);
  --color-warning: light-dark(#B06000, #FDD663);

  /* Chat roles */
  --color-bubble-user:  light-dark(#F0F0F1, #2A2A2D);
  --color-code-bg:      light-dark(#F7F7F8, #131314);

  /* Syntax — code content, not UI. Five roles is enough for a chat
     code block; anything finer belongs in a real editor. */
  --color-syntax-keyword:  light-dark(#8250DF, #C297FF);
  --color-syntax-string:   light-dark(#0A6B3D, #92D9A9);
  --color-syntax-function: light-dark(#1F4FCC, #8AB4F8);
  --color-syntax-number:   light-dark(#9A4600, #F0B37E);
  --color-syntax-comment:  var(--color-text-tertiary);

  /* Type */
  --font-ui:   'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;

  --text-xs:   12px;   /* timestamps, badge counts */
  --text-sm:   13px;   /* metadata, control labels, sidebar */
  --text-base: 15px;   /* message body, composer input */
  --text-lg:   17px;   /* conversation title */
  --text-xl:   20px;   /* empty-state heading — largest in product */

  --weight-normal:   400;
  --weight-medium:   500;
  --weight-semibold: 600;

  --leading-body: 1.6;   /* message text only */
  --leading-ui:   1.45;
  --leading-tight: 1.3;  /* 17px and 20px */

  /* Space */
  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
  --space-5: 20px;  --space-6: 24px;  --space-8: 32px;  --space-12: 48px;

  /* Shape */
  --radius-sm:   6px;    /* chips, icon buttons */
  --radius-md:   10px;   /* code blocks, cards, menus */
  --radius-lg:   16px;   /* user bubble */
  --radius-xl:   24px;   /* composer shell */
  --radius-full: 9999px; /* pills, avatars, send button */

  /* Elevation */
  --shadow-sm: 0 1px 2px light-dark(#0000000F, #00000052);
  --shadow-md: 0 4px 12px light-dark(#00000014, #00000052);
  --shadow-lg: 0 8px 28px light-dark(#0000001F, #00000066);

  /* Motion */
  --duration-fast: 120ms;  /* hover, press */
  --duration-base: 200ms;  /* enter, exit */
  --duration-slow: 320ms;  /* drawer, panel */
  --ease: cubic-bezier(0.2, 0, 0.2, 1);

  /* Layout */
  --width-transcript: 720px;
  --width-sidebar:    260px;
}
```

**Never** hardcode a hex, px size, or duration that exists as a token above. If
you need a colour with no token, add a token — don't inline the value.

Syntax colours are the **only** exception to the one-accent rule. They colour
*content*, not chrome, and they never appear outside a code block.

---

## 2. Typography

One family for the interface, one for code. The UI font is invisible by design —
in a chat product the only interesting text is the content, and a display face
competes with it.

| Role | Size | Weight | Line height | Where |
|------|------|--------|-------------|-------|
| Message body | 15 | 400 | 1.6 | Every message, user and assistant |
| Input | 15 | 400 | 1.5 | Composer textarea |
| Conversation title | 17 | 600 | 1.3 | Header, sidebar active item |
| Empty state | 20 | 600 | 1.3 | First-run heading only |
| Control label | 13 | 500 | 1.45 | Buttons, menu items, tabs |
| Metadata | 13 | 400 | 1.45 | Model name, "Edited", sidebar rows |
| Timestamp / count | 12 | 400 | 1.4 | Badges, relative times |
| Code | 13 | 400 | 1.55 | Code blocks, inline code, IDs |

### Never

- **Never introduce a third family.** No display face, no second mono, no
  "characteristic" serif. If a heading needs presence it gets weight 600, not a
  new typeface.
- **Never use a size outside the five.** Not 14, not 18, not 28.
- **Never set body copy above 15px or below 13px.**
- **Never pair a 12px label with a 20px heading on the same line.** Maximum one
  step of contrast between adjacent text.
- **Never use letter-spacing below −0.01em.** Tight tracking on a UI font is a
  display-type mannerism and it hurts scanning.
- **Never use uppercase + wide tracking for section labels.** It reads as
  decoration and forces a 5th size to stay legible.
- **Never use mono for UI chrome** — not for labels, timestamps, badges, or
  headings. Mono means "the machine wrote this literally."

---

## 3. Layout

```
┌──────────┬────────────────────────────────────────┐
│ sidebar  │  header (title, actions)               │
│ 260px    ├────────────────────────────────────────┤
│          │                                        │
│ new chat │      transcript · max 720px · centred  │
│ history  │                                        │
│          ├────────────────────────────────────────┤
│ account  │      composer · max 720px · centred    │
└──────────┴────────────────────────────────────────┘
```

| Element | Rule |
|---------|------|
| Transcript width | `max-width: 720px`, horizontally centred, `padding-inline: 24px` |
| Composer width | Identical to transcript. They must share an edge. |
| Gap between turns | 24px |
| Gap within a turn | 8px (metadata → body) |
| Sidebar | 260px fixed, `--color-bg-sunken`, collapses below 768px |
| Header | 52px, hairline bottom border, sticky |

**Never** let the transcript and composer have different widths — misaligned
left edges are the most visible possible error in this layout.

### Application frame

The window is a fixed frame with two scroll regions inside it. Nothing else
scrolls, ever. This must hold at 50% zoom, at 200% zoom, at 320px wide, and on a
short landscape phone.

```css
html, body { height: 100%; overflow: hidden; overscroll-behavior: none; }

.app {
  display: grid;
  grid-template-columns: var(--width-sidebar) minmax(0, 1fr);
  height: 100vh;          /* fallback */
  height: 100dvh;         /* excludes mobile browser chrome */
  overflow: hidden;
}

/* Sidebar: fixed top, scrolling middle, fixed bottom */
.sidebar        { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.sidebar__top   { flex: none; }
.sidebar__list  { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
.sidebar__foot  { flex: none; }

/* Main: fixed header, scrolling transcript, fixed composer */
.main      { display: grid; grid-template-rows: auto minmax(0, 1fr) auto;
             min-height: 0; min-width: 0; overflow: hidden; }
.header    { min-height: 52px; }
.scroller  { min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
.dock      { flex: none; }
```

| Requirement | Why |
|-------------|-----|
| `min-height: 0` on every scroll container | A grid or flex child defaults to `min-height: auto` and **refuses to shrink**. This is the single most common cause of a composer that scrolls off-screen. |
| `100dvh`, not `100vh`, for the frame | `vh` ignores mobile browser chrome, so the composer sits under the URL bar. |
| `auto` header row, not a fixed `52px` | At 200% zoom a fixed row clips its own contents. Use `min-height`. |
| Composer input `max-height: min(200px, 32dvh)` | A fixed 200px cap eats a short viewport whole. |
| Drawer body `max-height: 22dvh; overflow-y: auto` | Eight attachments must not push the input off-screen. |
| `overscroll-behavior: contain` on scrollers | Stops scroll chaining from bouncing the whole frame. |

**Never** use `position: fixed` for the composer or header. Fixed positioning
breaks inside transformed ancestors, ignores the sidebar column, and needs
manual padding compensation on the transcript. The grid frame above needs none.

**Never** set a fixed pixel height on the header, footer, or composer. They size
to their content; only the transcript flexes.

---

## 4. Message list

The two roles are rendered **asymmetrically** and this is deliberate.

### User turn

- Right-aligned bubble, `--color-bubble-user`, `--radius-lg`
- `max-width: 75%`, padding `12px 16px`
- No avatar, no name, no model label
- Timestamp only on hover, or not at all

### Assistant turn

- **No bubble.** Full 720px measure, transparent background.
- Metadata line above the message: name · model. 13px, secondary.
- Action row below (copy, retry, feedback): visible on hover and on
  `:focus-within`; **always visible on touch devices**.
- Renders markdown: headings map to 17px/600, lists at 15px, code to the code
  block rules below.

### Never

- **Never give the assistant a bubble.** It costs ~20% of reading width and
  distinguishes nothing that alignment hasn't already distinguished.
- **Never give either party an avatar in a two-party chat.** There are two
  voices; position already tells you which is which.
- **Never hide the copy action behind hover on touch.** Copy is the most-used
  action in the product.
- **Never animate message entry** beyond a 120ms opacity fade. Sliding or
  scaling messages makes the transcript feel unstable while streaming.
- **Never right-align assistant text**, in any locale logic. Only the user
  bubble is aligned to the inline end.

---

## 5. Composer

Five named slots, after Astryx `ChatComposer`: `drawer`, `header`, `input`,
`footer`, `send`. A minimal product fills `input` and `send`; an agent console
fills all five. The shell never changes.

```
┌─────────────────────────────────────────┐
│ ┌─ drawer ─────────────────────────────┐│  attachments, context, confirmations
│ ├─ header ─────────────────────────────┤│  reply-to, context meter (rare)
│ │  input                               ││  auto-growing textarea
│ │  footer                    [ send ]  ││  attach, dictate, tools
│ └──────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| Shell radius | `--radius-xl` (24px) |
| Shell padding | `--space-2` (8px) |
| **Child radius** | `24 − 8 = 16px` — concentric. See rule below. |
| Border | 1px `--color-border-strong` |
| Rest | No shadow |
| Focus-within | `--shadow-md` + border → `--color-accent` |
| Input min height | 44px |
| Input max height | 200px, then scrolls |
| Send button | 32px circle, `--radius-full` |

**Concentric radius rule:** a rounded child inside a rounded parent uses
`parent_radius − padding`. A 24px composer with 8px padding gives its drawer a
16px radius. Using the same radius on both makes the corners visibly diverge and
is the clearest tell of a hand-built composer.

### Send button

One button, one position, three states. Send and stop share the same 32px so the
pointer never moves — the moment you most want to stop a response is immediately
after sending it.

| State | Appearance | Enabled when |
|-------|-----------|--------------|
| Empty | Filled, 35% opacity | Never — disabled |
| Ready | Filled `--color-text`, inverted glyph | Trimmed input non-empty **or** an attachment exists |
| Streaming | Square stop glyph, same fill | Always |

### Drawer

Sits above the input. Holds attachments, context chips, and confirmations.

- Pass a **count** to enable the collapse toggle. Collapsed shows a count badge
  and a label only.
- **Threshold is 4.** Below that, stay expanded — a toggle that hides two chips
  wastes a tap.
- Files with previews go in a horizontally scrolling thumbnail row; files
  without go in removable chips below.
- Confirmations render as keyed options (A / B / C) so they can be answered from
  the keyboard.

### Input behaviour

The composer is a plain `<textarea>` with editor conveniences layered on. People
arrive already knowing these bindings from every other chat product; deviating
from them is never a feature.

| Key | Behaviour |
|-----|-----------|
| `Enter` | Send. On touch devices, inserts a newline instead — send is tap-only. |
| `Shift + Enter` | Newline. **Continues a list marker** if the current line has one. |
| `Cmd/Ctrl + Enter` | Send, always, from anywhere in the field. |
| `Backspace` at end of a bare marker | Deletes the whole marker, leaving the indent. Pressing again removes one indent level. |
| `Tab` / `Shift + Tab` **inside a list line** | Indent / outdent by two spaces. |
| `Tab` anywhere else | Moves focus. **Never trap Tab in the textarea.** |
| `Esc` | Stops an in-flight response. |

**List continuation.** On `Shift + Enter`, if the current line matches
`-`, `*`, `+`, `1.`, `1)`, or a `- [ ]` checkbox, insert the next marker on the
new line at the same indent. Ordered markers increment. An empty marker means
the person is done: clear the line instead of adding another.

**Undo must survive.** Every programmatic edit goes through
`document.execCommand('insertText' | 'delete')` rather than assigning to
`.value`. Writing to `.value` silently destroys the browser's native undo stack,
and `Cmd+Z` losing a paragraph is unforgivable in a text field.

**Auto-grow** by setting `height: auto` then `height: scrollHeight` on every
input event — never with a CSS transition, which visibly lags behind typing.

### Never

- **Never disable the input to force a confirmation.** A person who has changed
  their mind needs somewhere to say so. Confirmation adds an option; it never
  removes one.
- **Never put the send button anywhere but the inline end of the footer.**
- **Never let Enter send when a modifier is held.** `Enter` sends,
  `Shift+Enter` inserts a newline. On touch, `Enter` inserts a newline and send
  is tap-only.
- **Never animate the composer's height with a transition.** Set the height
  directly from `scrollHeight`; a transition lags behind typing.

---

## 6. Microinteractions

Motion here has one job: confirm that the thing you did happened. An action with
no visible response reads as broken, and the person taps it again.

### The rule

Every interactive element moves through **rest → hover → press → result**. Press
and result are not optional. A button that only changes on hover is unfinished,
and hover doesn't exist on touch at all.

| Phase | Treatment | Duration |
|-------|-----------|----------|
| Hover | `--color-bg-hover`, text → `--color-text` | `--duration-fast` (120ms) |
| Press | `transform: scale(0.92)` | `--duration-fast`, no easing out |
| Result | State change + one icon pop | 320ms pop, state holds 1.6s |
| Return | Back to rest | `--duration-base` (200ms) |

```css
@keyframes pop { 0% { transform: scale(1) } 40% { transform: scale(1.18) } 100% { transform: scale(1) } }
```

### Per-action specification

| Action | Feedback | Reverts |
|--------|----------|---------|
| Copy message / copy code | Icon swaps to a check, colour → `--color-success`, icon pops | After 1.6s |
| Thumbs up / down | Icon fills, colour → `--color-accent`, icon pops. The pair is mutually exclusive; clicking the active one clears it. | Persists — it's a stored opinion |
| Retry | Icon rotates 360° once over 400ms | On completion |
| Remove attachment | Chip scales to 0.9 and fades over 160ms, **then** unmounts | N/A |
| Send | Press scale, button swaps to stop in the same position | On stream end |
| Expand tool call / drawer | Chevron rotates 180°, body fades and rises 4px | On collapse |
| Select conversation | Background settles to `--color-bg-selected` | On next selection |
| Jump to latest | Slides up 8px and fades in | On dismiss |

### Never

- **Never animate on page load.** Entrance animations on first paint make a
  product feel slow, and they replay on every navigation.
- **Never overshoot past 1.18 scale**, and never bounce more than once. A
  spring that wobbles reads as a toy.
- **Never use a toast to confirm a copy.** The icon already said it, and a
  toast covers the message you just copied.
- **Never animate anything the user didn't trigger**, except the streaming
  caret and an active spinner.
- **Never gate the state change on the animation.** Under
  `prefers-reduced-motion` the check icon and the filled thumb still appear —
  only the movement is dropped. The feedback is the information; the motion is
  the delivery.

---

## 7. Streaming and agent surfaces

Work the assistant does before answering is content, not a loading state.

| Surface | Rule |
|---------|------|
| Caret | 2px block or thin bar at the end of streaming text. Blinks at ~1s on a step function — no easing. |
| Stopped | Partial text **stays**. Show "Stopped" in the metadata line. Never delete generated text. |
| Tool call | Collapsed card, `--radius-md`. Header shows tool name + result summary + duration. Expandable. |
| Thinking | Single line, secondary text, left rule. Collapsed by default. |
| Scroll | Auto-pin to bottom while streaming; **release the moment the user scrolls up** and show a "jump to latest" affordance. |

### Never

- **Never show a spinner for the message itself.** The message is already on
  screen; a spinner contradicts it. Spinners belong to tool calls only.
- **Never label a tool card "Using tool…".** Show what it did:
  `search_docs · 4 results · 240ms`. That tells a reader whether to trust the
  answer; "Using tool" tells them nothing and costs the same space.
- **Never re-pin scroll after the user has scrolled away.** Yanking the viewport
  is the single most complained-about behaviour in chat UI.
- **Never announce streaming tokens to screen readers.** The container is
  `aria-live="polite"` and announces **once, on completion**.

---

## 8. States and copy

Interface copy sits inches from the assistant's copy and is constantly compared
to it. It labels and reports; it never performs personality.

| State | Copy | Treatment |
|-------|------|-----------|
| Sending | — | Send becomes stop. No spinner. |
| Streaming | — | Caret trails text. |
| Stopped | `Stopped` | Partial text stays. Retry available. |
| Send failed | `Message didn't send. Try again.` | Draft preserved, composer border → danger, retry inline |
| Rate limited | `You're at your limit until 3:40pm.` | Name the time. |
| Offline | `No connection. Your draft is saved.` | Second sentence is the one that matters. |
| Context full | `Older messages will be trimmed to fit.` | Warn **before** trimming. Warning colour, not danger. |
| Declined | Plain message | **No error styling.** A considered refusal is an answer, not a malfunction. |
| Empty chat | `What are we working on?` + 3 specific starters | No illustration, no greeting. Composer autofocused. |

### Never

- **Never apologise in an error.** `Oops! Something went wrong 😅` names
  nothing, offers nothing, and costs trust.
- **Never write "Try again later."** Name the time or the condition.
- **Never change an action's name between the button and the result.** "Attach
  file" → "Attached", not "Submit" → "Upload successful".
- **Never style a refusal as an error.**

---

## 9. Accessibility floor

Non-negotiable. Ship none of this later.

| Requirement | Spec |
|-------------|------|
| Focus ring | 2px `--color-accent`, 2px offset, on every interactive element |
| Contrast | Body and metadata ≥ 4.5:1. `--color-text-tertiary` is for non-essential text only. |
| Touch targets | 32px visual minimum, 44px hit area via padding |
| Stop | Keyboard-reachable the instant streaming starts; `Esc` stops |
| Live region | Message container `aria-live="polite"`, announced once on completion |
| Reduced motion | Caret stops blinking and stays solid. **Text still streams** — it's content, not decoration. |
| Sidebar | Collapsible, and never the only path to a conversation |

---

## 10. Anti-patterns

These are the specific failure modes to check your output against. Each one is
common, each one looks plausible while you're building it.

| Anti-pattern | Why it fails |
|--------------|--------------|
| A display typeface for headings | Chat has no headings large enough to need one. It adds a family and competes with content. |
| Mono for labels, timestamps, or eyebrows | Mono means "literal machine output". Using it decoratively destroys that signal. |
| Small-caps eyebrow labels above headings | Forces an extra type size, adds no information, reads as template furniture. |
| `v0.1 · draft` / `FIG 2.1` / section numbers | Decoration disguised as metadata. Delete unless a reader will actually cite it. |
| A 12px number next to a 24px title | Mismatched scale on one line. Keep adjacent text within one step. |
| Gradient text or gradient accents | Reads as decoration in a product whose job is reading. |
| Assistant messages in bubbles | Costs reading width, distinguishes nothing. |
| Avatars in a two-party chat | 32px of nothing. Alignment already answers "who". |
| Coloured category chips everywhere | Dilutes the single accent until focus state stops reading as focus. |
| Animated message entry | Makes the transcript feel unstable during streaming. |
| Emoji in interface copy | Interface copy labels; it doesn't emote. |
| Full-bleed transcript | Line lengths past ~90ch measurably slow reading. |
| `position: fixed` composer | Breaks in transformed ancestors, ignores the sidebar column, needs manual transcript padding. Use the grid frame. |
| Fixed pixel height on the header | Clips its own contents at 200% zoom. |
| Writing to `textarea.value` | Destroys native undo. Use `execCommand`. |
| Buttons with hover states but no press state | Reads as broken on touch, where hover never fires. |
| A toast confirming every action | The control that was clicked is where the person is already looking. |

---

## 11. Pre-ship checklist

- [ ] Exactly two font families in the stylesheet
- [ ] Exactly five font sizes, three weights
- [ ] No hex, px, or ms value that isn't a token
- [ ] Transcript and composer share the same width and left edge
- [ ] Assistant messages have no bubble and no avatar
- [ ] Send and stop occupy the same position
- [ ] Composer child radius = shell radius − shell padding
- [ ] Copy action reachable without hover
- [ ] `Esc` stops a stream; stop is tab-reachable
- [ ] Scroll releases when the user scrolls up
- [ ] Every error names what happened and what to do
- [ ] Focus visible on every interactive element
- [ ] Header, composer and account row stay visible at 50%, 100% and 200% zoom
- [ ] `min-height: 0` on every scroll container
- [ ] Frame uses `100dvh`; nothing uses `position: fixed`
- [ ] `Enter` sends, `Shift+Enter` newlines, list markers continue
- [ ] `Cmd+Z` restores text after a list marker was auto-inserted
- [ ] `Tab` moves focus outside a list line
- [ ] Copy, thumbs and retry each have a press state and a result state
- [ ] Works at 320px wide
- [ ] `prefers-reduced-motion` respected; text still streams, states still change
