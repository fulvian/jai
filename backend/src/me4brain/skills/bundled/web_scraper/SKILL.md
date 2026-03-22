---
name: Web Scraper
description: Extract content from web pages - fetch articles, parse HTML, extract structured data. Use when user wants to read a webpage, extract article text, or get information from URLs.
version: 1.0.0
author: me4brain
tags:
  - web
  - scraping
  - extraction
metadata:
  requires: []
---

# Web Scraper Skill

Extracts content from web pages using Python libraries (no paid APIs required).

## Backend Stack

Uses free, open-source libraries:
- **requests** + **BeautifulSoup4**: Core HTML fetching and parsing
- **trafilatura**: Article text extraction with boilerplate removal
- **newspaper3k**: News article parsing (title, text, images)
- **httpx**: Async HTTP for concurrent fetches

## Capabilities

- Fetch and parse static HTML pages
- Extract article text and metadata (title, author, date)
- Parse structured data (tables, lists)
- Handle multiple URLs concurrently
- Respect robots.txt and rate limiting

## Usage

When user asks:
- "Read this article: [URL]"
- "Extract content from [URL]"
- "What does [website] say about [topic]?"
- "Get the main text from [URL]"
- "Scrape [URL]"

## Limitations

- Static HTML only (no JavaScript rendering)
- Respects rate limits to avoid bans
- May not work on heavily protected sites

## Examples

1. "Read https://example.com/article" → Extracts and returns article text
2. "Get the headlines from [news URL]" → Parses news article
3. "What's the main content of [blog URL]?" → Returns parsed article

