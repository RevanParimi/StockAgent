# Architecture map — interface checklist

Our own wording of the points that apply to a map of this kind, taken from Vercel's
**Web Interface Guidelines** (`vercel-labs/web-interface-guidelines`, MIT licence) at commit
`434b7f91364665f2f733b310ec54809bf8f37937`, read once on 27 Nov 2026 and kept here so the map and
its check stay offline and repeatable. Nothing fetches it at build or test time. A newer version is
adopted only by editing this file.

Each map story passes the list for what it adds; its receipt marks every item **passed** or
**not applicable**, with a reason. MAP-005 passed the whole list over the whole map: the 3D view,
the flat map and the phone layout.

## Keyboard and focus

| # | Check |
|---|---|
| K1 | Every action works from the keyboard alone, in the order the screen reads. |
| K2 | Focus is always visible (`:focus-visible`), never covered by a fixed bar or dialog. No `outline: none` without a replacement. |
| K3 | Opening a dialog moves focus into it and keeps it there; closing returns it to where it came from. |
| K4 | `Esc` closes the topmost thing (dialog, then panel). Single-key shortcuts do nothing while typing in a field or with Ctrl, Alt or Meta held. |
| K5 | A long list or panel can be skipped (a skip link) and each part has a heading. |

## Pointer and targets

| # | Check |
|---|---|
| P1 | Targets are at least 24 px; a small visual has a larger hit area. |
| P2 | Anything that looks clickable is clickable; no dead zone inside a control. |
| P3 | Every drag or 3D gesture (orbit, click a block) has a button or key that does the same. |
| P4 | Hover is a bonus: nothing is shown only on hover. |
| P5 | Zoom is never disabled; `touch-action: manipulation` on controls. |
| P6 | Buttons and links show hover, active and focus states, each stronger than rest. |

## Navigation and state

| # | Check |
|---|---|
| N1 | What is open is in the address (`#m=<id>`, audience), so it can be shared and reloaded; Back and Forward move through it. |
| N2 | The page title says what is open. |
| N3 | Real buttons for actions, real links for places (`<a href>`), never a clickable `div`. |
| N4 | No dead end: an unknown link, an empty section or a missing 3D view still offers a next step. |

## Motion

| # | Check |
|---|---|
| M1 | With "reduce motion" set, motion stops or becomes a jump. |
| M2 | Motion longer than five seconds can be paused by a visible control. |
| M3 | Animations can be interrupted by the user's input. |
| M4 | Only `transform`, `opacity` and colour are transitioned in CSS; never `transition: all`. |

## Text and content

| # | Check |
|---|---|
| T1 | `…` for more-to-come and loading; curly quotes in prose; sentence case. |
| T2 | Long content wraps or scrolls; nothing is cut off without a way to see it. Flex children can shrink. |
| T3 | Empty and sparse states say so in words (a module without stores, a part without jobs). |
| T4 | Numbers that are compared use tabular figures; dates are written unambiguously. |
| T5 | Code names, paths and keys carry `translate="no"`. |
| T6 | Headings are in order (`h1`, `h2`, `h3`); labels are clear and specific. |

## Accessibility semantics

| # | Check |
|---|---|
| A1 | Native elements first (`button`, `a`, `dialog`, `input`, `table`), ARIA only where needed. |
| A2 | Every control has an accessible name; icon-only buttons have `aria-label`; decoration is `aria-hidden`. |
| A3 | Status changes that matter (a layout being computed, a search result count) are announced politely. |
| A4 | The 3D view has a text equivalent: the legend, the panel and an outline of each flowchart. |
| A5 | Colour is never the only cue: shape, words or position say it too. |

## Dark theme and contrast

| # | Check |
|---|---|
| C1 | `color-scheme: dark` and a matching `theme-color`. |
| C2 | Text 4.5:1, meaningful lines and focus 3:1 (see DESIGN.md §8). |
| C3 | Native inputs set their own background and text colours. |

## Layout and loading

| # | Check |
|---|---|
| L1 | No unwanted scrollbars; flex and grid do the layout, not script measurements. |
| L2 | Safe-area insets respected where the page meets a screen edge. |
| L3 | A loading state is shown for anything that can take a noticeable moment, and the page never jumps when it ends. |
| L4 | Modals and drawers keep their own scrolling (`overscroll-behavior: contain`). |
| L5 | Checked at laptop, wide-desktop and phone widths. |

## Forms (search)

| # | Check |
|---|---|
| F1 | The search field has a label, is not autofilled (`autocomplete="off"`, `spellcheck="false"`), and paste works. |
| F2 | `Enter` opens the highlighted result; arrows move; the number of results is announced. |
| F3 | The placeholder ends with `…` and shows an example. |

## Performance and offline

| # | Check |
|---|---|
| O1 | The page makes no network request: fonts, scripts, data and images are inside the file. |
| O2 | No console error on load or while using it. |
| O3 | Work that can wait is done when first needed (a flowchart is laid out when opened), and moving parts stop when paused. |
