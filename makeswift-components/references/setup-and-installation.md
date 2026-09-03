# Makeswift setup & installation (Next.js App Router)

Source: official Makeswift developer docs (`get-started/quickstart`, `get-started/installation/app-router`).

**Note on Catalyst repos:** a BigCommerce Catalyst storefront (this skill's primary target) already has all of this scaffolding wired up out of the box via `@bigcommerce/catalyst-makeswift`. You will not normally redo this setup in a Catalyst project — this reference exists so that when something in the chain is missing/misconfigured (e.g. a fresh non-Catalyst Next.js app, or diagnosing "why doesn't my page connect to the builder"), you know exactly which piece to check rather than guessing.

## Quickstart (automatic, new project only)

```bash
npx makeswift@latest init
```

This scaffolds a new Next.js app, opens a browser to link it to a Makeswift site (existing or new, optionally from a template), and writes `MAKESWIFT_SITE_API_KEY` into `.env.local` for you. Only applicable when starting a brand-new project — not how you'd add Makeswift to an existing app.

**Requirements:** Node.js ≥ 20.19, Next.js ≥ 13.4 with App Router.

## Manual installation (add Makeswift to an existing Next.js app)

### 1. Install

```bash
npm install @makeswift/runtime
```

### 2. Env var

```sh
# .env.local
MAKESWIFT_SITE_API_KEY=paste-your-api-key-here
```

Get the key from the Makeswift builder: **Settings → Host**.

### 3. Runtime — `src/makeswift/runtime.ts`

```ts
import { ReactRuntime } from '@makeswift/runtime/react';

export const runtime = new ReactRuntime();
```

This is the single shared registry every `register.ts`/`components.tsx` file imports and calls `runtime.registerComponent(...)` on (see `SKILL.md`/`references/controls.md` for that side).

### 4. Client — `src/makeswift/client.ts`

```ts
import { Makeswift } from '@makeswift/runtime/next';
import { strict } from 'assert';
import { runtime } from './runtime';

strict(process.env.MAKESWIFT_SITE_API_KEY, 'MAKESWIFT_SITE_API_KEY is required');

export const client = new Makeswift(process.env.MAKESWIFT_SITE_API_KEY, { runtime });
```

This is the `client` used elsewhere for `client.getPages()`, `client.getPageSnapshot(...)`, `client.getComponentSnapshot(...)` (see `references/runtime-and-components.md`).

### 5. Next.js plugin — `next.config.ts`

```ts
import createWithMakeswift from '@makeswift/runtime/next/plugin';

const withMakeswift = createWithMakeswift();

const nextConfig = {
  // your existing next config
};

export default withMakeswift(nextConfig);
```

### 6. Component registration entry point — `src/makeswift/components.tsx`

This is the **central barrel** that must import every component's registration file so `runtime.registerComponent(...)` actually runs for all of them (this is "wherever the runtime bootstrap already imports all components from" referenced in `SKILL.md` step 2 — in a Catalyst repo, find this file rather than assuming its name/path).

```tsx
import { runtime } from '@/makeswift/runtime';
import { Style } from '@makeswift/runtime/controls';

function HelloWorld({ className }: { className: string }) {
  return <p className={className}>Hello, world!</p>;
}

runtime.registerComponent(HelloWorld, {
  type: 'hello-world',
  label: 'Hello, world!',
  props: { className: Style() },
});
```

In practice this file usually just re-exports/imports one line per component folder (`import './components/card/register'; import './components/carousel/register'; ...`) rather than defining components inline like the toy example above.

### 7. Provider — `src/makeswift/provider.tsx`

```tsx
'use client';

import { runtime } from '@/makeswift/runtime';
import { type SiteVersion } from '@makeswift/runtime/next';
import { ReactRuntimeProvider, RootStyleRegistry } from '@makeswift/runtime/next';
import '@/makeswift/components';

export function MakeswiftProvider({
  children,
  siteVersion,
}: {
  children: React.ReactNode;
  siteVersion: SiteVersion | null;
}) {
  return (
    <ReactRuntimeProvider siteVersion={siteVersion} runtime={runtime}>
      <RootStyleRegistry>{children}</RootStyleRegistry>
    </ReactRuntimeProvider>
  );
}
```

Note `RootStyleRegistry` wraps children *inside* the runtime provider here — if you're chasing the Tailwind-v4-reset-override gotcha (see `references/runtime-and-components.md`), this is the file where `enableCssReset={false}` would go: `<RootStyleRegistry enableCssReset={false}>`.

### 8. Root layout — `src/app/layout.tsx`

```tsx
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { getSiteVersion } from '@makeswift/runtime/next/server';
import { MakeswiftProvider } from '@/makeswift/provider';
import '@/makeswift/components';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = { title: 'Create Next App', description: '...' };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <MakeswiftProvider siteVersion={await getSiteVersion()}>{children}</MakeswiftProvider>
      </body>
    </html>
  );
}
```

### 9. Catch-all page route — `src/app/[[...path]]/page.tsx`

```tsx
import { getSiteVersion } from '@makeswift/runtime/next/server';
import { notFound } from 'next/navigation';
import { Page as MakeswiftPage } from '@makeswift/runtime/next';
import { client } from '@/makeswift/client';

export async function generateStaticParams() {
  const pages = await client.getPages().toArray();
  return pages.map((page) => ({ path: page.path.split('/').filter((s) => s !== '') }));
}

export default async function Page({ params }: { params: Promise<{ path?: string[] }> }) {
  const path = '/' + ((await params)?.path ?? []).join('/');
  const snapshot = await client.getPageSnapshot(path, { siteVersion: getSiteVersion() });
  if (snapshot == null) return notFound();
  return <MakeswiftPage snapshot={snapshot} />;
}
```

**Important:** remove any existing `src/app/page.tsx` so this catch-all owns the root route too — Makeswift is meant to manage every page under it. In a Catalyst repo, the equivalent route is more layered (locale segment, `(default)` route group, etc.) — find the actual catch-all rather than assuming this exact path.

### 10. API route handler — `src/app/api/makeswift/[...makeswift]/route.ts`

```ts
import { MakeswiftApiHandler } from '@makeswift/runtime/next/server';
import { strict } from 'assert';
import { runtime } from '@/makeswift/runtime';
import '@/makeswift/components'; // makes custom components' data available for introspection

strict(process.env.MAKESWIFT_SITE_API_KEY, 'MAKESWIFT_SITE_API_KEY is required');

const handler = MakeswiftApiHandler(process.env.MAKESWIFT_SITE_API_KEY, { runtime });

export { handler as GET, handler as POST, handler as OPTIONS };
```

This is also where `getFonts()` goes for self-hosted/local custom fonts (see `references/runtime-and-components.md`).

### 11. Run + connect

```bash
npm run dev
```

Then in the Makeswift builder: **Settings → Host** → set the app URL (`http://localhost:3000` in development). This is the connection the "host manifest is unreachable" / "page did not connect to the builder in time" troubleshooting entries are about.

## Quick diagnostic checklist

If a component "doesn't show up" or "won't connect", check these in order — each corresponds to a step above:

1. Is `MAKESWIFT_SITE_API_KEY` set (both where `client.ts` reads it and where the API route handler reads it)?
2. Does the component's `register.ts`/registration file actually get imported by the central components barrel (step 6)? A component whose file exists but is never imported never calls `registerComponent` and simply won't appear — this is the single most common "why isn't my new component showing up" cause.
3. Is `RootStyleRegistry`/`ReactRuntimeProvider` actually wrapping the tree that renders `<Page>`/`<MakeswiftComponent>`?
4. Is the Makeswift builder's **Settings → Host** URL pointing at the actually-running dev server (or deployed preview) address?
