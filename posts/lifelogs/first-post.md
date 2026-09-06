---
title: "Back to plain old HTML"
slug: "back-to-plain-html"
date: 2026-09-05
author: "Italia Troller"
tags:
  - web
  - html
  - cms
description: "After three months of SSGs and CMSes, it's time to go back to basics."
---

# Back to plain old HTML

It's now rewritten in HTML! After using and reviewing SSGs and CMSes
for 3 months and a week, good ol' HTML still can't be beaten.

## Why?

Most web frameworks solve problems that a personal site doesn't have.
A small, filesystem-based static site is:

- simple to understand
- trivial to deploy
- easy to debug
- totally under your control

```python
def hello():
    return "Hello, static world!"
```

### The stack

It's just **HTML + CSS + Python**:

1. Write content in Markdown
2. Render it at build time with a tiny script
3. Ship the static files to Cloudflare Pages

> Less code is more maintainable.

## Verdict

If you don't need a database, don't bring one. Use good ol' HTML.