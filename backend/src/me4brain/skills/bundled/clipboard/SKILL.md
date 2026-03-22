---
name: Clipboard
description: Manage clipboard history - copy, paste, search clipboard history. Use when user asks about clipboard, wants to access previous copies, or manage copied content.
version: 1.0.0
author: me4brain
tags:
  - clipboard
  - utility
  - productivity
metadata:
  requires:
    - cli: pbcopy
    - cli: pbpaste
---

# Clipboard Skill

Manage macOS clipboard with history tracking.

## Capabilities

- Get current clipboard contents
- Copy text to clipboard
- Track clipboard history (session-based)
- Search clipboard history
- Clear clipboard

## Configuration

Uses macOS built-in `pbcopy` and `pbpaste` commands.
History is tracked in memory during session.

## Usage

When user asks:
- "What's in my clipboard?"
- "Show clipboard history"
- "Copy this: [text]"
- "Paste my clipboard"
- "Find in clipboard history: [query]"

## Examples

1. "What did I copy?" → Shows current clipboard
2. "Copy 'Hello World'" → Copies text to clipboard
3. "Show last 5 copies" → Lists clipboard history
