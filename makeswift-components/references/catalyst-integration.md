# How Makeswift is actually wired into Catalyst

This documents the **real, concrete wiring** in a BigCommerce Catalyst storefront (`@bigcommerce/catalyst-makeswift` variant), as opposed to the generic Makeswift+Next.js setup in `references/setup-and-installation.md`. Read that file first for the conceptual pieces (runtime, client, provider, catch-all page, API handler) — this file maps each of those onto Catalyst's actual file paths and explains where/why Catalyst diverges from the generic pattern.

**Key framing:** in this monorepo, `@bigcommerce/catalyst-makeswift` is not a library added on top of a generic Catalyst app — the whole `core` package *is* that variant: a full Catalyst Next.js storefront pre-wired with Makeswift end-to-end. There's a parallel `@bigcommerce/catalyst-core` (BigCommerce-only, no Makeswift) and `@bigcommerce/catalyst-b2b-makeswift` variant published from sibling `integrations/*` branches.

## File map (generic concept → Catalyst reality)

| Generic concept | Catalyst file |
|---|---|
| `src/makeswift/runtime.ts` | `lib/makeswift/runtime.ts` |
| `src/makeswift/client.ts` | `lib/makeswift/client.ts` |
| `src/makeswift/components.tsx` (barrel) | `lib/makeswift/components.ts` |
| `src/makeswift/provider.tsx` | `lib/makeswift/provider.tsx` |
| `src/app/[[...path]]/page.tsx` | `app/[locale]/(default)/[...rest]/page.tsx` (+ `lib/makeswift/page.tsx`) |
| `src/app/api/makeswift/[...makeswift]/route.ts` | `app/api/makeswift/[...makeswift]/route.ts` |
| Individual component registration | `lib/makeswift/components/<name>/register.ts` |

## `lib/makeswift/runtime.ts` — uses `ReactRuntimeCore`, not `ReactRuntime`

```ts
import { fetch } from '@makeswift/runtime/next';
import { registerBoxComponent } from '@makeswift/runtime/react/builtins/box';
import { registerDividerComponent } from '@makeswift/runtime/react/builtins/divider';
import { registerEmbedComponent } from '@makeswift/runtime/react/builtins/embed';
import { registerImageComponent } from '@makeswift/runtime/react/builtins/image';
import { registerRootComponent } from '@makeswift/runtime/react/builtins/root';
import { registerSlotComponent } from '@makeswift/runtime/react/builtins/slot';
import { registerSocialLinksComponent } from '@makeswift/runtime/react/builtins/social-links';
import { registerTextComponent } from '@makeswift/runtime/react/builtins/text';
import { registerVideoComponent } from '@makeswift/runtime/react/builtins/video';
import { ReactRuntimeCore } from '@makeswift/runtime/react/core';

const runtime = new ReactRuntimeCore({
  apiOrigin: process.env.NEXT_PUBLIC_MAKESWIFT_API_ORIGIN,
  appOrigin: process.env.NEXT_PUBLIC_MAKESWIFT_APP_ORIGIN,
  breakpoints: {
    small: { width: 640, viewport: 390, label: 'Small' },
    medium: { width: 768, viewport: 765, label: 'Medium' },
    large: { width: 1024, viewport: 1000, label: 'Large' },
    screen: { width: 1280, label: 'XL' },
  },
  fetch,
});

// Only register necessary built-in components. Omitted: Navigation, Button, Form, Carousel, Countdown
registerRootComponent(runtime);
registerSlotComponent(runtime);
registerBoxComponent(runtime);
registerTextComponent(runtime);
registerImageComponent(runtime);
registerDividerComponent(runtime);
registerEmbedComponent(runtime);
registerSocialLinksComponent(runtime);
registerVideoComponent(runtime);

export { runtime };
```

**Why this matters:** Makeswift ships built-in Navigation/Button/Form/Carousel/Countdown components, but Catalyst deliberately does **not** call their `register*Component` functions — it has its own custom equivalents instead (`button-link`, `carousel`, `card-carousel`, `products-carousel`, the site-wide `Navigation` primitive wired via `site-header`). If you're ever tempted to reach for a Makeswift built-in in this codebase, check `lib/makeswift/components/` first — there's almost certainly a Catalyst-native replacement that matches the storefront's design system, and using the raw built-in would bypass it. Also note custom breakpoint labels differ from the generic docs example (`small`/`medium`/`large`/`screen`, not `mobile`/`tablet`/`laptop`/`external`) — match whatever this project already uses, don't invent new breakpoint keys.

## `lib/makeswift/client.ts` — subclassed for ISR + locale normalization

Beyond the generic `new Makeswift(apiKey, { runtime })`, Catalyst:
- Subclasses `Makeswift` (as `CatalystMakeswift`) overriding `fetchOptions()` to inject `next.revalidate` on published-content fetches — `0` in dev (no ISR against local dev), `3600` in prod, overridable via `MAKESWIFT_REVALIDATE_TARGET`. Draft-mode requests skip this (draft mode already forces `cache: 'no-store'`).
- Exposes wrapped helpers — `getPageSnapshot`, `getComponentSnapshot`, `getMakeswiftPageMetadata` — that thread through `siteVersion` (from `getSiteVersion()`) and a `locale` normalized via a `normalizeLocale()` helper (maps the *default* locale to `undefined` so Makeswift treats it as the canonical/unprefixed locale) sourced from `~/i18n/locale-config`.
- Enforces `MAKESWIFT_SITE_API_KEY` via `assert.strict` at module load — same as the generic pattern, just also present here.

**Takeaway:** don't call the raw `client.getPageSnapshot(path, { siteVersion })` signature from generic docs directly in Catalyst code — use the wrapped helpers so locale + revalidation stay consistent with the rest of the app.

## `lib/makeswift/components.ts` — hand-written barrel, imported twice

```ts
import './components/accordion/register';
import './components/button-link/register';
import './components/card/register';
import './components/card-carousel/register';
import './components/carousel/register';
import './components/customer-group-slot/register';
import './components/product-card/register';
import './components/product-detail/register';
import './components/products-carousel/register';
import './components/products-list/register';
import './components/section/register';
import './components/site-footer/register';
import './components/site-header/register';
import './components/site-theme/register';
import './components/slideshow/register';
import './components/sticky-sidebar/register';
```

This is **not auto-discovered** — a new component's `register.ts` must be added here manually or it silently never registers (see the diagnostic checklist in `setup-and-installation.md`; this is the #1 cause of "my new component doesn't show up"). It's imported for side effects from two separate places that both need every component registered independently:
- `lib/makeswift/provider.tsx` (client-side, for the builder canvas)
- `app/api/makeswift/[...makeswift]/route.ts` (server-side, for the API handler's introspection of component data)

If you add a new component and it's missing from *one* of these render contexts (e.g. shows in the canvas but the builder panel can't introspect its props, or vice versa), the barrel import is still the first thing to check — confirm it's actually reached from both entry points, not just one.

## `lib/makeswift/provider.tsx` — `enableCssReset={false}`, locale-aware

```tsx
'use client';

import { ReactRuntimeProvider, RootStyleRegistry, type SiteVersion } from '@makeswift/runtime/next';
import { runtime } from '~/lib/makeswift/runtime';
import '~/lib/makeswift/components';

export function MakeswiftProvider({
  children,
  locale,
  siteVersion,
}: {
  children: React.ReactNode;
  locale?: string;
  siteVersion: SiteVersion | null;
}) {
  return (
    <ReactRuntimeProvider locale={locale} runtime={runtime} siteVersion={siteVersion}>
      <RootStyleRegistry enableCssReset={false}>{children}</RootStyleRegistry>
    </ReactRuntimeProvider>
  );
}
```

Confirms the Tailwind-reset gotcha from `references/runtime-and-components.md` is already handled here (`enableCssReset={false}`) — Catalyst uses **Tailwind v3** (not v4; `package.json` pins `tailwindcss: ^3.4.17` with a standard `tailwind.config.ts`, plus `tailwindcss-radix`, `tailwindcss-animate`, `@tailwindcss/container-queries`, `@tailwindcss/typography`), and this flag is set regardless, to avoid Makeswift's reset fighting the storefront's own base styles. Consumed by `app/[locale]/layout.tsx` and `app/not-found.tsx`.

## Catch-all page route — layered under locale + route-group, not a bare top-level catch-all

Path: `app/[locale]/(default)/[...rest]/page.tsx`, delegating to `lib/makeswift/page.tsx`:

```tsx
// app/[locale]/(default)/[...rest]/page.tsx
export async function generateMetadata({ params }: { params: Promise<PageParams> }) {
  const { rest, locale } = await params;
  const metadata = await getMakeswiftPageMetadata({ path: `/${rest.join('/')}`, locale });
  return metadata ?? {};
}

// Intentionally no generateStaticParams — locale list and page paths resolve at request time.

export default async function CatchAllPage({ params }: { params: Promise<PageParams> }) {
  const { rest, locale } = await params;
  return <Page locale={locale} path={`/${rest.join('/')}`} />;
}
```

```tsx
// lib/makeswift/page.tsx
export async function Page({ path, locale }: { path: string; locale: string }) {
  const snapshot = await getPageSnapshot({ path, locale });
  if (snapshot == null) {
    await connection();   // Next.js dynamic-rendering signal
    return notFound();
  }
  return <MakeswiftPageShim metadata={false} snapshot={snapshot} />;
}
```

Two real divergences from the generic single-file catch-all:
1. **It's the last-resort route inside a route group that also holds BigCommerce's own page-type routes** (`product/[slug]`, `(faceted)/category/[slug]`, `(faceted)/brand/[slug]`, `(faceted)/search`, `blog`, `cart`, `gift-certificates`, etc). Any URL Next.js can't match to one of those more specific routes falls through to `[...rest]` and is resolved as Makeswift-authored content. So a "page not found" in Makeswift can also mean a BigCommerce route match failed upstream — check both layers when a URL 404s unexpectedly.
2. **`await connection()` before `notFound()`** — a Catalyst-specific fix ensuring unpublished/draft Makeswift pages stay dynamically rendered (not statically optimized away) so they remain editable/previewable in the builder, rather than getting cached as a 404.

## API route handler — passes `getFonts()` for the storefront's actual font tokens

```ts
// app/api/makeswift/[...makeswift]/route.ts
const defaultVariants: Font['variants'] = [
  { weight: '300', style: 'normal' },
  { weight: '400', style: 'normal' },
  { weight: '500', style: 'normal' },
];

const handler = MakeswiftApiHandler(process.env.MAKESWIFT_SITE_API_KEY, {
  runtime,
  getFonts() {
    return [
      { family: 'var(--font-family-inter)', label: 'Inter', variants: defaultVariants },
      { family: 'var(--font-family-dm-serif-text)', label: 'DM Serif Text', variants: [{ weight: '400', style: 'normal' }] },
      { family: 'var(--font-family-roboto-mono)', label: 'Roboto Mono', variants: defaultVariants },
    ];
  },
});
```

**If you add a new font in `app/fonts.ts`** (see `SKILL.md`'s font-tokens gotcha), it will apply correctly via CSS the moment it's in the `fonts` array — but it **won't appear by name in the builder's Font-control picker** until you also add a matching entry here with the right `family` (the CSS variable, e.g. `'var(--font-family-mulish)'`), `label`, and `variants`. This is a second place, distinct from `app/fonts.ts` and `lib/makeswift/controls/font-tokens.ts`, that a new font touches.

## Full component inventory (`lib/makeswift/components/`)

```
accordion            card-carousel         product-detail        site-footer
button-link          carousel              products-carousel     site-header
card                 customer-group-slot   products-list         site-theme
                                            section               slideshow
                                                                   sticky-sidebar
```

`site-header`, `site-theme`, and (likely) `site-footer`/`customer-group-slot` are registered with `hidden: true` and rendered via the `<MakeswiftComponent>` global-slot pattern (see `references/runtime-and-components.md`) rather than being draggable in the picker — check each one's `register.ts` for `hidden: true` before assuming a component is meant to be end-user-placeable.

## Practical checklist specific to this repo

When adding or debugging a Makeswift component in Catalyst:

1. New component → is its `register.ts` import added to `lib/makeswift/components.ts`? (Not auto-discovered.)
2. Needs a Makeswift built-in (Navigation/Button/Form/Carousel/Countdown)? → check `lib/makeswift/components/` for Catalyst's own registered replacement first; the raw built-ins aren't even registered in `runtime.ts`.
3. Needs page/component snapshot data? → use `lib/makeswift/client.ts`'s wrapped `getPageSnapshot`/`getComponentSnapshot`/`getMakeswiftPageMetadata`, not a raw `Makeswift` client call, so locale normalization + ISR revalidation stay consistent.
4. New/changed font? → three places, not one: `app/fonts.ts` (loads it via `next/font`), `lib/makeswift/controls/font-tokens.ts` (site-theme default tokens, if it should be a heading/body/accent option), and `app/api/makeswift/[...makeswift]/route.ts`'s `getFonts()` (so it's named/selectable in the builder's Font control).
5. A URL 404s unexpectedly on a page you expect Makeswift to serve → remember `[...rest]` is the *last* route matched inside `(default)`; confirm no BigCommerce route (product/category/brand/search/etc.) is shadowing or mis-matching it first.
