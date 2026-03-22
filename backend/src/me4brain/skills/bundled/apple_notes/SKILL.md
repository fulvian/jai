---
name: Apple Notes
description: Access and manage Apple Notes - read, create, search notes. Use when user asks about their notes, wants to save information, or search for past notes.
version: 1.0.0
author: me4brain
tags:
  - apple
  - notes
  - productivity
metadata:
  requires:
    - cli: osascript
---

# Apple Notes Skill

Integration with Apple Notes app on macOS.

## Capabilities

- List all notes and folders
- Read note contents
- Create new notes
- Search notes by title or content
- Get recent notes

## Configuration

Requires macOS with Apple Notes app installed.
Uses `osascript` (AppleScript) for integration.

## Usage

When user asks:
- "Show my notes"
- "What notes do I have about [topic]?"
- "Create a note: [content]"
- "Search notes for [query]"
- "Read my latest note"
- "Save this to notes: [content]"

## Privacy

- Only accesses Notes app on local machine
- Does not sync or share note contents
- Respects folder permissions

## Examples

1. "Show my recent notes" → Lists last 10 notes
2. "Create a note about today's meeting" → Creates new note
3. "Find notes about project X" → Searches note contents
