# Publication branding, version 1.0.1

This application shares Dessi Georgieva's publication baseline: strong Arial/Helvetica headings, warm paper, black navigation and calm reading surfaces. The owner selected this direction in “Map the motion graphics studio”; the publication's design direction and the studio's brand guidelines/tokens supplied the reference. The owner subsequently selected the rounded-square mark from their commerce assistant project for reuse here. The historical creative preview retains the bundled Inter font; workspace typography uses system fonts.

## Portable foundations

`frontend/src/brand/tokens.css` owns the versioned palette and font roles. `application.css` applies them to the existing workspace. The underlying layout uses these same variables. No additional component framework is needed.

| Role | Value |
| --- | --- |
| Paper | #faf9f6 |
| Ink | #171717 |
| Muted text | #626262 |
| Rule | #deddd9 |
| Surface | #efeeeb |
| Panel | #ffffff |
| Navigation | #000000 |
| Navigation text | #f4f3ed |
| Muted navigation text | #b5b4b0 |
| Dark rule / surface | #272727 / #111111 |
| Sans | Arial, Helvetica, sans-serif |
| Code | ui-monospace, SFMono-Regular, Menlo, Consolas, monospace |

Headings use weight 700 and tight tracking. Dense application tables use smaller type than publication articles. Primary actions are black. Green, amber, red and muted purple retain explicit success, warning, error and experiment-control roles, paired with text labels or icons. Buttons and the signature link have a 44px minimum target. Horizontal table and progress scrolling stays local to its container.

## Shared static mark

`frontend/public/brand/nested-squares.svg` adapts the owner's selected `ScoutMark` geometry from the commerce assistant project's `web/components/workspace-ui/WorkspaceIcons.tsx`. The owner explicitly requested this reuse. It also supplies `frontend/public/mark.svg`, the favicon. The working product name remains Direct Acquisition, endorsed “By Dessi Georgieva”. This does not settle the shared family name or final logo system.

The 48 × 48 SVG contains four rounded squares. For ring r = 0, 1, 2, 3: x and y are 4 + 5r, width and height are 40 - 10r, corner radius is 9 - 2r, and rotation is 8r degrees around (24, 24). Strokes are 2.5 units in brand ink on brand paper. Source commit: `add1d4228ee1307d3bab1af8ecb420339f8a7e71` (commerce assistant repository). The source file was clean at inspection. Geometry is unchanged from ScoutMark; CSS-dependent colors are resolved into portable SVG colors and the paper base fills the viewport. There is no motion, raster generation or external model.

Asset SHA-256: `569cccffd1aaff1f43019162de16ea69977da795a45b1c91cee9a83d23779a5a`.

Display contract: preserve the square proportions, 44px on desktop and 34px inside a 44px mobile link. Keep the mark at navigation identity and favicon scale. Do not tile it behind forms, evidence, tables or copy. The navigation image is decorative with empty alt text; the link retains the product and author name.

The earlier original wave motif remains in `wave-crop.svg` as a retired design asset. It is no longer referenced by the interface or favicon.

## Scope and verification

This is a light workspace with a black navigation rail. It does not introduce a dark theme. iwoca remains the campaign's product-evidence context. Saved campaign copy, exports, approvals, audience data and backend rules are unchanged by this presentation pass.

Review includes rendered desktop (1440 × 1000) and mobile (390 × 844), campaign audience/copy, evidence, learning, activity and the campaign dialog. Browser regressions check document width at both breakpoints before and after local table scrolling. Build, formatting, Python tests and architecture checks run separately. Screenshots are local review artifacts, not public product data.

Historical preview styling is frozen separately in `frontend/src/historical-preview.css` from commit `829d961`, including the original Inter font, paper, colors and responsive rules. Workspace brand tokens do not apply inside these previews. A future creative redesign needs explicit presentation versioning and new artifact identities.
