---
title: "Migrating from VitePress back to static HTML"
slug: "migrating-vitepress-html"
date: 2026-09-04
author: "Italia Troller"
tags:
  - web
  - static-site
  - migration
description: "A practical walkthrough of dropping the Vue-based toolchain for plain HTML."
---

# Migrating from VitePress back to static HTML

VitePress is great for docs, but for a tiny personal website it was
overkill. Here's what the migration looked like.

## What had to go

- Node modules (68,000 files!)
- Vue components
- Build step complexity
- 1MB of tooling for three pages

## What came in

```bash
# Build the site
python3 build.py

# Create a new post
python3 new_post.py

# Deploy
cp -r dist/* /wherever/your/host/lives
```

## Lessons

| Old way | New way |
|---------|---------|
| dependency tree | nothing |
| dev server | open the file |
| 200MB node_modules | 5 KB of scripts |

Sometimes simpler really is better.