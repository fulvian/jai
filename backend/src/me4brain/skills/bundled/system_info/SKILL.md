---
name: System Info
description: Get system information including OS, CPU, memory, and disk usage. Use when user asks about system status, machine info, or resource usage.
version: 1.0.0
author: me4brain
tags:
  - system
  - utility
  - monitoring
metadata:
  requires: []
---

# System Information Skill

This skill provides access to system information and resource monitoring.

## Capabilities

- Get operating system details (name, version, architecture)
- Check CPU usage and load averages
- Monitor memory usage (RAM, swap)
- Check disk space on all mounted volumes
- Get uptime and boot time

## Usage

When user asks:
- "What's my system status?"
- "How much RAM do I have?"
- "Check disk space"
- "Show CPU usage"
- "System info"

Execute the appropriate system monitoring command and return formatted results.

## Examples

1. "Show system info" → Returns OS, CPU, RAM summary
2. "How much disk space is left?" → Returns disk usage per mount point
3. "Is my system under load?" → Returns CPU and memory usage
