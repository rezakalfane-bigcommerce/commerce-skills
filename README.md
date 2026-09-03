# bigcommerce-skills

A collection of [Claude Code](https://claude.com/claude-code) skills for working with BigCommerce, Catalyst/Makeswift storefronts, and local dev-server QA.

| Skill | Description |
|---|---|
| [`bigcommerce-admin`](./bigcommerce-admin) | Perform BigCommerce store administration and merchandising tasks via the BigCommerce REST Management APIs — products, categories, inventory, promotions, orders, customers, B2B Edition, webhooks, and more. |
| [`makeswift-components`](./makeswift-components) | Create or update Makeswift page-builder components in a BigCommerce Catalyst (Next.js) storefront — registering components, adding/editing props/controls, wiring builder-editable content. |
| [`screen-capture`](./screen-capture) | Capture full-page screenshots or short interaction-video recordings of a locally-running web app using Playwright, with a synthetic visible cursor and a number of dev-server-specific fixes baked in. |

## Install

### All three skills

Clone once, then symlink each subdirectory into `~/.claude/skills/`:

```bash
git clone https://github.com/rezakalfane-bigcommerce/bigcommerce-skills.git ~/dev/bigcommerce-skills
ln -s ~/dev/bigcommerce-skills/bigcommerce-admin ~/.claude/skills/bigcommerce-admin
ln -s ~/dev/bigcommerce-skills/makeswift-components ~/.claude/skills/makeswift-components
ln -s ~/dev/bigcommerce-skills/screen-capture ~/.claude/skills/screen-capture
```

Symlinking back to the clone means `git pull` in `~/dev/bigcommerce-skills` updates all installed skills at once.

### Just one skill

No git history, no full clone, via [`degit`](https://github.com/Rich-Harris/degit) (needs `npx`, nothing to install):

```bash
npx degit rezakalfane-bigcommerce/bigcommerce-skills/screen-capture ~/.claude/skills/screen-capture
```

Swap the subdirectory name (`bigcommerce-admin`, `makeswift-components`, `screen-capture`) to install a different one. This copies the files only — no `.git` folder, so it won't auto-update; re-run the same command to refresh.

Git-native alternative, if `npx`/degit isn't available, using sparse checkout:

```bash
git clone --filter=blob:none --sparse https://github.com/rezakalfane-bigcommerce/bigcommerce-skills.git /tmp/bcs
cd /tmp/bcs && git sparse-checkout set screen-capture
cp -R screen-capture ~/.claude/skills/screen-capture
```

## Migrated from

These three skills previously lived in separate repos, now archived:

- [`bigcommerce-admin-skill`](https://github.com/rezakalfane-bigcommerce/bigcommerce-admin-skill) → [`bigcommerce-admin`](./bigcommerce-admin)
- [`bigcommerce-makeswift-components`](https://github.com/rezakalfane-bigcommerce/bigcommerce-makeswift-components) → [`makeswift-components`](./makeswift-components)
- [`screen-capture-skill`](https://github.com/rezakalfane-bigcommerce/screen-capture-skill) → [`screen-capture`](./screen-capture)

## License

MIT
