---
name: File Manager
description: Manage files and directories - list, search, read, and organize files. Use when user asks about files, folders, or wants to find/read specific files.
version: 1.0.0
author: me4brain
tags:
  - files
  - utility
  - productivity
metadata:
  requires: []
---

# File Manager Skill

Provides file system operations for the Me4BrAIn agent.

## Capabilities

- List files and directories with details (size, date, permissions)
- Search for files by name, extension, or content
- Read file contents (text files only)
- Get file/directory information
- Find recently modified files

## Usage

When user asks:
- "List files in [directory]"
- "Find files named [pattern]"
- "What's in the Downloads folder?"
- "Search for .py files"
- "Show me recent files"
- "Read file [path]"

## Safety

- Only reads files, never modifies or deletes
- Respects file permissions
- Limits output size for large files

## Examples

1. "Show files in my Documents" → Lists Documents folder contents
2. "Find all Python files" → Searches for *.py recursively
3. "Read config.yaml" → Shows file contents
