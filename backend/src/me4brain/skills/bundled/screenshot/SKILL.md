---
name: Screenshot
description: Capture screenshots and screen recordings. Use when user wants to take a screenshot, record screen, or capture a specific window.
version: 1.0.0
author: me4brain
tags:
  - screen
  - capture
  - utility
metadata:
  requires:
    - cli: screencapture
---

# Screenshot Skill

Capture screenshots and screen recordings on macOS.

## Capabilities

- Take full screen screenshots
- Capture specific windows
- Take selection screenshots
- Record screen (with audio option)
- Capture with timer delay

## Configuration

Uses macOS built-in `screencapture` command.
No additional configuration required.

## Usage

When user asks:
- "Take a screenshot"
- "Capture this window"
- "Screenshot my screen"
- "Record my screen for [duration]"
- "Capture selection"

## Output

Screenshots are saved to Desktop by default.
Returns the file path of captured image/video.

## Examples

1. "Take a screenshot" → Captures full screen, saves to Desktop
2. "Screenshot in 5 seconds" → Delayed capture
3. "Capture this window" → Prompts user to select window
