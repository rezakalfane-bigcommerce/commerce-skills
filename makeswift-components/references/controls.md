# Makeswift control reference

All controls are imported from `@makeswift/runtime/controls` and passed as values in `registerComponent`'s `props: {}` map. Source: official Makeswift developer docs (`docs.makeswift.com/developer/docs/reference/controls/*`), current as of this writing.

## Core concept: Props vs Controls

- **Props** are how data gets into a React component (first argument of the render function) — same as any React component, nothing Makeswift-specific.
- **Controls** are the builder-side UI that produces those prop values. Two categories:
  - **Basic controls** (can't contain other controls): `Checkbox`, `Color`, `Combobox`, `Image`, `Link`, `Number`, `Select`, `Slider`, `TextArea`, `TextInput`, `Code`, `IconRadioGroup`. Plus three special ones: `RichText` (inline editable text overlay), `Slot` (a drop zone for visually adding child components), `Style` (CSS property panel/overlay, the only responsive control).
  - **Composable controls** (produce arrays or objects out of other controls): `List` (array), `Group` (object; supersedes the deprecated `Shape`).
- Multiple different controls can produce the same underlying prop type with different builder UX (e.g. `Select` vs `IconRadioGroup` both produce a `string` union) — pick based on how you want the *editor* to interact with it, not just the resulting type.

## `registerComponent(component, options)`

```ts
runtime.registerComponent(Component, {
  type: 'unique-string',        // required, permanent — don't change once used in a live page
  label: 'Display Name',        // required, shown in the component picker
  props: { ... },               // required, prop name -> control
  description: 'markdown text', // optional, shown in the builder panel
  icon: 'icon-name',            // optional, from Makeswift's icon set
  hidden: true,                 // optional, hides from the component picker (used for app-shell slots, not normal components — see MakeswiftComponent below)
  builtinSuspense: true,        // optional, default true — wraps registered component in a <Suspense> boundary automatically
});
```

## Text & primitive value controls

| Control | Resolved prop type | Key options |
|---|---|---|
| `TextInput({ label, description, defaultValue })` | `string \| undefined` | single-line text |
| `TextArea({ label, description, defaultValue })` | `string \| undefined` | multi-line text |
| `Number({ label, description, labelOrientation, defaultValue, min, max, step, suffix })` | `number \| undefined` | numeric stepper input; `suffix` appends decorative text (e.g. `"px"`) |
| `Slider({ label, description, defaultValue, min, max, step, showInput })` | `number \| undefined` | drag slider; `showInput: true` also shows a numeric field next to it |
| `Checkbox({ label, description, defaultValue })` | `boolean \| undefined` | toggle |
| `Select({ label, description, labelOrientation, options: [{ value, label }], defaultValue })` | the option's `value` type (a string union), or `undefined` | dropdown |
| `IconRadioGroup({ label, options: [{ value, label, icon }], defaultValue })` | the option's `value` type, or `undefined` | icon-button radio group instead of a dropdown — better UX for a small fixed set of visual choices (alignment, layout direction, etc). `icon` is a kebab-case string or `IconRadioGroup.Icon.X` accessor. |
| `Color({ label, description, labelOrientation, defaultValue, hideAlpha })` | `string` (CSS rgba) — narrows away `undefined` if `defaultValue` given | color picker; `defaultValue` can be a plain CSS string or `{ color, opacity }` (v0.28.6+) for opacity support |
| `Code({ label, description, defaultValue })` | `{ value: string } \| undefined` | Monaco-based code editor with automatic language detection; note the resolved shape is an object, not a bare string |

## `Link({ label, description })`

Resolves to `{ href?: string; target?: '_blank' | '_self' } | undefined`. Use for any click-through destination (buttons, cards, banners).

## `Image({ label, description, format })`

Two formats:
- `Image.Format.URL` (default) → resolves to `string | undefined` (the image URL).
- `Image.Format.WithDimensions` → resolves to `{ url: string; dimensions: { width: number; height: number } } | undefined`. Use whenever the component needs to size a container from the image's real aspect ratio before the browser loads it (avoids a load-then-reflow jump). Falls back to `undefined` if the underlying asset has no recorded dimensions (e.g. some external URLs).

## `Style({ properties })`

The **only responsive control** — its value can differ per breakpoint without any other control needing to. Resolves to a `className` string.

- `Style.Default` (used if `properties` omitted) → Width + Margin only.
- `Style.All` → Width, Margin, Padding, Border, Border Radius, Text Style.
- Or pass a custom array of specific properties to expose only some of those.

```ts
className: Style({ properties: Style.All }),
```

## `RichText({ mode })`

Visual inline-editable text. Resolves to `ReactNode` — render it directly in JSX, don't try to treat it as a string.

- `RichText.Mode.Block` (default) — full-line block content (`display: block`), for headlines/paragraphs.
- `RichText.Mode.Inline` — for content that must render `display: inline` (buttons, links) — required to avoid hydration mismatches; needs Makeswift ≥ v0.10.0.

```ts
headline: RichText(),                              // block
children: RichText({ mode: RichText.Mode.Inline }), // inline
```

## `Font({ label, description, variant, defaultValue })`

- `variant` (boolean, default `true`) — whether `fontStyle`/`fontWeight` are included in the resolved value at all. Set `false` when the token should be a fixed weight/style, only the family is user-editable (this is how this project's Site Theme heading/body/accent tokens are configured).
- `defaultValue: { fontFamily: string; fontStyle?: 'normal' | 'italic'; fontWeight?: number }`.
- Resolves to `{ fontFamily: string; fontStyle: string; fontWeight: number }` (or just `{ fontFamily }` if `variant: false`).
- `fontFamily` values are typically CSS variable references (`'var(--font-family-heading)'`) that resolve through `next/font`-generated variables applied on `<html>`, not raw font names.

## `Combobox({ label, description, getOptions })`

For async/searchable single-select against external data (e.g. "pick a product").

```ts
type getComboboxOptions<T> = (query: string) => ComboboxOption<T>[] | Promise<ComboboxOption<T>[]>;
type ComboboxOption<T> = { id: string; label: string; value: T };
```

Resolves to the selected option's `value` (type `T`) or `undefined`. `getOptions` is called with the current search query on every keystroke — filter/fetch inside it (debounce/cache on your side if the underlying fetch is expensive).

```ts
product: Combobox({
  label: 'Product',
  async getOptions(query) {
    const products = await searchProducts(query);
    return products.map((p) => ({ id: p.entityId.toString(), label: p.name, value: p }));
  },
}),
```

## `Slot()`

Lets the builder user visually drop arbitrary content (any other Makeswift component) into a designated area of your component — like `children`, but explicit and named, and multiple slots can coexist on one component.

```ts
props: { media: Slot() }
```

```tsx
interface Props { media: ReactNode }
export function FeatureCard({ media }: Props) {
  return <div>{media}</div>;
}
```

No config options; always resolves to `ReactNode`. **Gotcha (from the official Accordion tutorial):** if a `Slot` lives inside content that's conditionally rendered by interactive state (e.g. an accordion panel that's collapsed by default), the builder user must switch to **Interact mode**, expand/open it, switch back to **Build mode**, and only then can they drag components into that slot — it's not reachable while collapsed.

## `Group({ label, description, preferredLayout, props })`

Bundles multiple related controls into a single nested object — for a cohesive "settings group" (e.g. a banner's text + background color together), not a repeatable list. Supersedes the deprecated `Shape` control (treat `Shape` as equivalent if you encounter it in old code, but always use `Group` for anything new).

- `preferredLayout`: `Group.Layout.Inline` (renders inline in the parent panel, default) or `Group.Layout.Popover` (renders in its own popover — better for a large bundle of sub-controls; this project's font-tokens `Group` uses `Popover`).
- Resolves to an object keyed by the nested `props` names.

```ts
banner: Group({
  label: 'Banner properties',
  preferredLayout: Group.Layout.Popover,
  props: {
    text: TextInput({ defaultValue: 'Banner text' }),
    background: Color({ label: 'Background', defaultValue: 'black' }),
  },
}),
```

## `List({ label, description, type, getItemLabel })`

Repeatable array of items, each shaped by `type` (any other control, commonly a `Group`). `getItemLabel(item)` customizes each row's label in the builder's list UI.

Resolves to `T[]` where `T` is whatever `type`'s control resolves to.

```ts
slides: List({
  label: 'Items',
  type: Group({
    label: 'Item',
    props: {
      name: TextInput({ label: 'Name', defaultValue: '' }),
      children: Slot(),
    },
  }),
  getItemLabel(slide) {
    return slide?.name || 'Item';
  },
}),
```

## Deprecated

- `Shape` — superseded by `Group`. Don't use in new components.

## Building a new component end-to-end (canonical shape)

```
lib/makeswift/components/<name>/
  register.ts   # runtime.registerComponent(...) + control definitions
  client.tsx    # 'use client' wrapper mapping Makeswift props -> real component props
```

```tsx
// register.ts
import { Style, TextInput, TextArea, Link, Image } from '@makeswift/runtime/controls';
import { runtime } from '~/lib/makeswift/runtime';
import { MSCard } from './client';

runtime.registerComponent(MSCard, {
  type: 'catalog-card',           // permanent identifier
  label: 'Catalog / Card',
  icon: 'image',
  props: {
    className: Style(),
    image: Image({ format: Image.Format.WithDimensions }),
    alt: TextInput({ label: 'Image alt text', defaultValue: '' }),
    heading: TextInput({ label: 'Heading', defaultValue: 'My Heading' }),
    description: TextArea({ label: 'Description', defaultValue: '' }),
    link: Link({ label: 'Link' }),
  },
});
```

```tsx
// client.tsx
'use client';
import { Card } from '@/vibes/soul/primitives/card';

export function MSCard({ image, alt, heading, description, link, className }: Props) {
  return (
    <Card
      className={className}
      image={image ? { src: image.url, alt } : undefined}
      heading={heading}
      description={description}
      href={link?.href ?? '#'}
    />
  );
}
```

Then register the import in wherever the project's central Makeswift component barrel lives (grep an existing sibling to find it) so it's actually loaded at runtime.
