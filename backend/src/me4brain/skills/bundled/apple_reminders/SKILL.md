---
name: Apple Reminders
description: Manage Apple Reminders - create, list, complete tasks. Use when user wants to set reminders, check todos, or manage tasks.
version: 1.0.0
author: me4brain
tags:
  - apple
  - reminders
  - tasks
  - productivity
metadata:
  requires:
    - cli: osascript
---

# Apple Reminders Skill

Integration with Apple Reminders app on macOS.

## Capabilities

- List reminders from all lists
- Create new reminders with due dates
- Mark reminders as complete
- Search reminders
- Get upcoming reminders

## Configuration

Requires macOS with Apple Reminders app installed.
Uses `osascript` (AppleScript) for integration.

## Usage

When user asks:
- "Add a reminder: [task]"
- "Remind me to [task] at [time]"
- "Show my reminders"
- "What tasks are due today?"
- "Mark [task] as done"
- "List reminders in [list name]"

## Privacy

- Only accesses Reminders app on local machine
- Does not sync or share reminder data externally

## Examples

1. "Remind me to call mom tomorrow at 3pm" → Creates timed reminder
2. "Show today's reminders" → Lists due items
3. "Complete the grocery shopping task" → Marks as done
