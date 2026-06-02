# RSS Sources Management

Script to manage RSS feed sources for the VeilleIA system.

## Usage

```bash
./scripts/rss-sources.sh [command]
```

## Commands

| Command | Description |
|---------|-------------|
| `status` | Show active sources with categories and priorities (default) |
| `validate` | Validate JSON syntax of `rss_sources.json` |
| `list` | List all sources (active and inactive) |
| `reload` | Restart n8n container to reload sources |

## Examples

```bash
# Check current active sources
./scripts/rss-sources.sh status

# Validate after editing rss_sources.json
./scripts/rss-sources.sh validate

# See all sources including disabled ones
./scripts/rss-sources.sh list

# Reload after making changes
./scripts/rss-sources.sh reload
```

## Adding/Removing Sources

Edit `rss_sources.json` in the project root:

```json
{
  "name": "New Source Name",
  "url": "https://example.com/feed.xml",
  "category": "Tech News",
  "active": true,
  "priority": "high"
}
```

**Priority levels:** `high`, `medium`, `low`

Changes are picked up automatically on the next workflow execution (no restart needed).
