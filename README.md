# AI Email Agent

AI-powered email assistant for IBHelm. Triggered by `@ai` mentions in Missive conversation comments.

## How It Works

1. User mentions `@ai` in a Missive conversation comment
2. DB trigger inserts record into `public.ai_triggers`
3. AI Agent polls for pending triggers every 1 second
4. Agent posts "🤖 Researching..." placeholder
5. Agent fetches context (emails, comments, project, tasks, files, craft docs)
6. Agent calls Claude API with MCP connector for additional research capability
7. Agent deletes placeholder and posts final response

## Features

- **Context-aware**: Automatically gathers project context including tasks, requirements (Anforderungen), notes (Hinweise), files, and Craft documents
- **MCP Integration**: Claude can query the IBHelm database for additional research
- **Configurable prompts**: System prompt stored in `app_settings` with template variables
- **CLI for testing**: Test without posting to Missive

## Setup

1. Copy `env.example` to `.env` and fill in values
2. Apply DB schema: `./apply_schema.sh` (includes `007_ai_agent.sql`)
3. Build and run:

```bash
docker compose up -d
```

## CLI Testing

```bash
# Test with most recent conversation
python -m src.cli --recent --dry-run

# Test with specific conversation
python -m src.cli --conversation-id abc123 --show-prompt

# Test without MCP (faster)
python -m src.cli --recent --no-mcp

# Save output to file
python -m src.cli --recent --output debug.md --show-prompt
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-5-20250514` | Claude model to use |
| `MCP_SERVER_URL` | No | `https://api.ibhelm.de/mcp` | MCP server URL |
| `MCP_BEARER_TOKEN` | Yes | - | Bearer token for MCP auth |
| `MISSIVE_API_TOKEN` | Yes | - | Missive API token |
| `MISSIVE_ORGANIZATION_ID` | No | - | Missive organization ID |
| `POLL_INTERVAL_SECONDS` | No | `1` | Polling interval |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `BETTERSTACK_SOURCE_TOKEN` | No | - | BetterStack logging token |

## System Prompt Configuration

The system prompt is stored in `app_settings.body['ai_agent_system_prompt']`. Edit via dashboard Admin Settings.

### Available Template Variables

| Variable | Content |
|----------|---------|
| `{trigger_author}` | Name of user who triggered @ai |
| `{trigger_instruction}` | Text after @ai |
| `{conversation_subject}` | Email subject |
| `{conversation_url}` | Missive URL |
| `{project_name}` | Project name or "Not assigned" |
| `{project_id}` | Teamwork project ID |
| `{emails_summary}` | Last 3 emails (with body, truncated) |
| `{emails_metadata}` | All email IDs/subjects/dates |
| `{emails_count}` | Total email count |
| `{comments}` | All conversation comments |
| `{tasks}` | Last 10 tasks |
| `{anforderungen}` | Last 10 Anforderungen |
| `{hinweise}` | Last 10 Hinweise |
| `{files}` | Last 10 files |
| `{craft_docs}` | Last 10 Craft documents |

## Database Schema

### Table: `public.ai_triggers`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `conversation_id` | UUID | Missive conversation |
| `comment_id` | UUID | Triggering comment |
| `comment_body` | TEXT | Comment content |
| `author_id` | UUID | Comment author |
| `status` | VARCHAR(20) | pending/processing/done/error |
| `placeholder_post_id` | TEXT | Missive placeholder post ID |
| `result_post_id` | TEXT | Final response post ID |
| `result_markdown` | TEXT | AI response (for debugging) |
| `error_message` | TEXT | Error details if failed |
| `created_at` | TIMESTAMPTZ | Trigger creation time |
| `processed_at` | TIMESTAMPTZ | Processing timestamp |

### Trigger: `check_ai_mention_on_comment`

Fires on `INSERT` to `missive.conversation_comments`. Detects `@ai` (case-insensitive) and creates trigger record.

