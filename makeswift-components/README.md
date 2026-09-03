# bigcommerce-makeswift-components

A [Claude Code](https://claude.com/claude-code) skill for creating and updating [Makeswift](https://www.makeswift.com/) page-builder components inside a [BigCommerce Catalyst](https://www.catalyst.dev/) storefront (Next.js).

It captures both:
- **The official Makeswift component-authoring API** — every control type (`TextInput`, `Number`, `Select`, `Image`, `Style`, `Slot`, `List`, `Group`, `Font`, etc.), the `registerComponent`/`ReactRuntime`/`<Page>`/`<MakeswiftComponent>` surface, and the builder's own troubleshooting messages — pulled from Makeswift's developer docs.
- **Catalyst-specific conventions and gotchas** learned by building real components against this stack: the `vibes/soul/` (presentational) vs `lib/makeswift/components/` (builder adapter) split, the REST-route + SWR + Zod bridge Makeswift components use to reach BigCommerce data (since they render client-side in the builder canvas), the Site Theme font-token system, and a real Tailwind `content`-glob bug this skill helped catch.

## Why

Claude Code loads a skill's `SKILL.md` automatically when a task matches its description, and can pull in the files under `references/` on demand. This turns "how do I add a prop to a Makeswift component" or "why isn't this Tailwind class working inside my Makeswift wrapper" from a fresh investigation every time into a one-shot lookup grounded in both the current docs and this codebase's actual patterns.

## Contents

- **`SKILL.md`** — the entry point: workflow for adding/updating a component, and the project-specific gotchas.
- **`references/controls.md`** — full API reference for every Makeswift control (options + resolved prop type), plus a canonical end-to-end new-component example.
- **`references/runtime-and-components.md`** — `ReactRuntime` setup, `<Page>` / `<ReactRuntimeProvider>` / `<RootStyleRegistry>` / `<MakeswiftComponent>`, `MakeswiftClient` methods, `MakeswiftApiHandler` + custom fonts, and a troubleshooting quick-reference.
- **`references/setup-and-installation.md`** — the generic Makeswift + Next.js App Router install (quickstart CLI and full manual step-by-step), plus a diagnostic checklist for "component doesn't show up"/"won't connect" issues.
- **`references/catalyst-integration.md`** — how that generic setup maps onto **actual Catalyst file paths** (`lib/makeswift/runtime.ts`, `client.ts`, the `components.ts` barrel, `provider.tsx`, the locale-aware catch-all route, the API handler's `getFonts()`), where and why Catalyst diverges from the generic pattern, and the current full inventory of registered components.

## Installing

Drop this directory under `~/.claude/skills/` (personal, all projects) or `<project>/.claude/skills/` (project-scoped):

```bash
git clone https://github.com/rezakalfane-bigcommerce/bigcommerce-makeswift-components.git ~/.claude/skills/makeswift-components
```

Claude Code picks up any `SKILL.md` under a skills directory automatically — no further registration needed.

## Scope

This skill assumes a Catalyst-shaped repo (`vibes/soul/`, `lib/makeswift/components/`, `app/api/...` route handlers, gql.tada-typed GraphQL). The control/runtime reference is generic Makeswift and applies to any Makeswift + Next.js project; the workflow and gotchas sections are Catalyst-specific.

## Contributing

This started as notes from a real build session. If you hit a new Makeswift + Catalyst gotcha, add it to `SKILL.md` or the relevant reference file — keep entries concrete (what broke, why, the fix) rather than generic advice.
