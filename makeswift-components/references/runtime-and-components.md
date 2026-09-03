# Makeswift runtime, components, and API surface

Source: official Makeswift developer docs. Covers everything around `registerComponent`/controls: how the runtime bootstraps, how snapshots get rendered, and the client/API-handler surface.

## `ReactRuntime` (the registry)

```ts
// lib/makeswift/runtime.ts (or wherever this project's equivalent lives)
import { ReactRuntime } from '@makeswift/runtime/react';

export const runtime = new ReactRuntime({
  breakpoints: {                              // optional — custom responsive breakpoints for the builder
    mobile: { width: 575, viewport: 390, label: 'Mobile' },
    tablet: { width: 768, viewport: 765, label: 'Tablet' },
    laptop: { width: 1024, viewport: 1000, label: 'Laptop' },
    external: { width: 1280, label: 'External' },
  },
});
```

Every `runtime.registerComponent(...)` call anywhere in the codebase adds to this single shared `runtime` instance — the instance must be imported from one canonical module everywhere (`register.ts` files import `~/lib/makeswift/runtime` or equivalent), not re-instantiated.

## Rendering a page: `<Page>` + `ReactRuntimeProvider`

```tsx
// app/[[...path]]/page.tsx (App Router)
import { getSiteVersion } from '@makeswift/runtime/next/server';
import { notFound } from 'next/navigation';
import { Page as MakeswiftPage } from '@makeswift/runtime/next';
import { client } from '@/makeswift/client';

export async function generateStaticParams() {
  const pages = await client.getPages().toArray();
  return pages.map((page) => ({ path: page.path.split('/').filter(Boolean) }));
}

export default async function Page({ params }: { params: Promise<{ path?: string[] }> }) {
  const path = '/' + ((await params)?.path ?? []).join('/');
  const snapshot = await client.getPageSnapshot(path, { siteVersion: getSiteVersion() });
  if (snapshot == null) return notFound();
  return <MakeswiftPage snapshot={snapshot} />;
}
```

`<Page snapshot metadata?>` — `metadata` defaults to `true` (auto page `<head>` tags); pass `false` to disable entirely, or a `PageMetadataSettings` object for granular control (title/description/social image/canonical).

`<ReactRuntimeProvider runtime siteVersion locale? children>` wraps the app root (usually inside a small client component) and is what actually lets `<Page>`/`<MakeswiftComponent>` render — `siteVersion` controls draft vs published content (`null` = published), `locale` is required for multi-language sites.

`<RootStyleRegistry>` — wraps the provider tree to make Makeswift's own CSS-in-JS output SSR-safe. Has an `enableCssReset` prop (default `true`) — **set `enableCssReset={false}` if using Tailwind v4**, since Tailwind's `@layer`-based reset gets silently overridden by Makeswift's unlayered normalize.css reset otherwise (styles outside any `@layer` always win over layered ones). This is a real, documented gotcha — check for it if Tailwind utility classes appear to have no effect specifically inside Makeswift-rendered content.

## `<MakeswiftComponent>` — the pattern behind `hidden: true` app-shell slots

This is exactly the mechanism this codebase uses for the header/site-theme "private" components (`hidden: true`, label ending in "(private)"/"(Dev)"-style naming):

```tsx
runtime.registerComponent(Header, {
  type: 'makeswift-header',
  label: 'Site Header',
  props: { className: Style(), logo: Image(), links: List({ ... }) },
});

// somewhere in the server-rendered layout:
const headerSnapshot = await client.getComponentSnapshot('my-header-id', {
  siteVersion: await getSiteVersion(),
});

<MakeswiftComponent
  snapshot={headerSnapshot}
  label="Site Header"
  type="makeswift-header"   // must match registerComponent's `type`
/>
```

Use this pattern (register with `hidden: true` + fetch/render via `getComponentSnapshot`/`<MakeswiftComponent>`) for anything that's a single global editable region (header, footer, site theme) rather than a draggable, repeatable component in the picker.

## `MakeswiftClient` methods

- `client.getPages()` — returns an async-iterable/list of all pages (used for `generateStaticParams`).
- `client.getPageSnapshot(path, { siteVersion })` — fetches the snapshot for `<Page>`.
- `client.getComponentSnapshot(componentId, { siteVersion })` — fetches the snapshot for a single `<MakeswiftComponent>` (global slot pattern above).
- `client.getSiteVersion()` / `getSiteVersion()` (from `@makeswift/runtime/next/server`) — resolves draft vs published based on the current preview-mode/draft-mode state.

## `MakeswiftApiHandler`

The API route (`app/api/makeswift/[...makeswift]/route.ts` or `pages/api/[...makeswift].ts`) that the builder iframe talks to for live preview/editing. Also where **custom fonts** get registered so they show up as selectable in the builder's Font control, in addition to being loaded via `next/font`:

```ts
export default MakeswiftApiHandler(process.env.MAKESWIFT_SITE_API_KEY, {
  runtime,
  getFonts() {
    return [
      {
        family: 'Satoshi',
        variants: [
          { weight: '400', style: 'normal', src: '/fonts/Satoshi-Variable.woff2' },
          { weight: '700', style: 'normal', src: '/fonts/Satoshi-Variable.woff2' },
        ],
      },
    ];
  },
});
```

Adding a Google Font via `next/font/google` (as this project's `app/fonts.ts` does) generally doesn't need a `getFonts()` entry — that's mainly for **local/self-hosted** font files (`next/font/local`) so the builder's own font picker knows about them too. If a custom font is loaded via `next/font` but never shows in the builder's font list, check whether `getFonts()` needs an entry for it.

## Troubleshooting quick-reference

- **Tailwind classes seem to have no effect inside a Makeswift-rendered region** → check `RootStyleRegistry`'s `enableCssReset` — set to `false` under Tailwind v4 (see above).
- **Visible layout shift right after hydration**, specifically when it correlates with a context value that differs between server render and client (locale, feature flag, A/B variant, session-derived value) → wrap that value with `useDeferredValue` so React finishes hydrating before propagating the update, instead of interrupting hydration and re-rendering with a Suspense fallback flash. Also consider: ensure server/client render identically in the first pass, memoize the value, or use `startTransition`.
- **"You are not using the correct API key"** → wrong/missing Makeswift API key in the client or API handler config; check both plus env vars.
- **"There are no available elements to edit / page not integrated with Makeswift"** → the page isn't wired to Makeswift yet, or data fetching failed — recheck the quickstart/installation steps for that route.
- **"The host manifest is unreachable"** → the builder can't reach your running Next.js app: confirm it's running, the host URL in Makeswift's site settings is correct, the API key is set, and the API handler route exists and is reachable.
- **"Your page did not connect to the builder in time"** → for Makeswift ≥ v0.24, check `ReactRuntimeProvider`'s `siteVersion`/preview-mode wiring; for < v0.24, check that `DraftModeScript` (App Router) / `PreviewModeScript` (Pages Router) is present in the layout/document.
- **`next typegen`/prelint failing with "Client configuration must include a channelId"** in a local sandbox with no `.env.local` configured — unrelated to Makeswift component code itself; it's the GraphQL client trying to resolve store credentials. The `eslint` step still runs and matters even if this prelint step errors.
