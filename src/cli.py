"""CLI for testing AI Agent without Missive."""

import argparse
import sys
from datetime import datetime
from typing import Optional
import psycopg

from src.settings import settings
from src.logging_conf import setup_logging, logger
from src.context import fetch_context
from src.template import render_template, DEFAULT_SYSTEM_PROMPT
from src.claude import call_claude, call_claude_simple


def get_system_prompt() -> str:
    """Fetch system prompt from app_settings."""
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT body->>'ai_agent_system_prompt'
                    FROM app_settings
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row and row[0]:
                    return row[0]
    except Exception as e:
        logger.warning(f"Failed to fetch system prompt from DB: {e}")
    return DEFAULT_SYSTEM_PROMPT


def get_recent_conversation_with_comments() -> Optional[dict]:
    """Get the most recent conversation that has comments."""
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.subject, cc.body, cc.author_id, u.name
                FROM missive.conversations c
                JOIN missive.conversation_comments cc ON c.id = cc.conversation_id
                LEFT JOIN missive.users u ON cc.author_id = u.id
                ORDER BY cc.created_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    'conversation_id': str(row[0]),
                    'subject': row[1] or '(No subject)',
                    'comment_body': row[2] or '',
                    'author_id': str(row[3]) if row[3] else None,
                    'author_name': row[4] or 'Unknown'
                }
            return None


def get_conversation_by_id(conversation_id: str) -> Optional[dict]:
    """Get conversation info and most recent comment."""
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            # Get conversation
            cur.execute("""
                SELECT c.id, c.subject
                FROM missive.conversations c
                WHERE c.id = %s
            """, (conversation_id,))
            conv_row = cur.fetchone()
            if not conv_row:
                return None
            
            # Get most recent comment (or simulate one)
            cur.execute("""
                SELECT cc.body, cc.author_id, u.name
                FROM missive.conversation_comments cc
                LEFT JOIN missive.users u ON cc.author_id = u.id
                WHERE cc.conversation_id = %s
                ORDER BY cc.created_at DESC
                LIMIT 1
            """, (conversation_id,))
            comment_row = cur.fetchone()
            
            return {
                'conversation_id': str(conv_row[0]),
                'subject': conv_row[1] or '(No subject)',
                'comment_body': comment_row[0] if comment_row else '@ai',
                'author_id': str(comment_row[1]) if comment_row and comment_row[1] else None,
                'author_name': comment_row[2] if comment_row else 'Test User'
            }


def output_result(result: str, output_path: Optional[str], rendered_prompt: Optional[str], show_prompt: bool):
    """Output result to console or file."""
    separator = "=" * 80
    
    output = []
    output.append(separator)
    output.append("AI AGENT TEST OUTPUT")
    output.append(f"Generated at: {datetime.now().isoformat()}")
    output.append(separator)
    
    if show_prompt and rendered_prompt:
        output.append("\n## RENDERED SYSTEM PROMPT\n")
        output.append(rendered_prompt)
        output.append("\n" + separator)
    
    output.append("\n## AI RESPONSE\n")
    output.append(result)
    output.append("\n" + separator)
    
    final_output = "\n".join(output)
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(final_output)
        print(f"Output written to: {output_path}", flush=True)
    else:
        print(final_output, flush=True)


def main():
    parser = argparse.ArgumentParser(description='Test AI Agent without Missive')
    parser.add_argument(
        '--conversation-id', '-c',
        help='Specific conversation ID to process'
    )
    parser.add_argument(
        '--recent', '-r',
        action='store_true',
        help='Use most recent conversation with comments'
    )
    parser.add_argument(
        '--instruction', '-i',
        default='',
        help='Override instruction (simulates @ai <instruction>)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: console)'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Show rendered prompt without calling Claude'
    )
    parser.add_argument(
        '--no-mcp',
        action='store_true',
        help='Call Claude without MCP connector'
    )
    parser.add_argument(
        '--show-prompt', '-p',
        action='store_true',
        help='Include rendered prompt in output'
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    # Get conversation
    if args.conversation_id:
        conv = get_conversation_by_id(args.conversation_id)
        if not conv:
            print(f"Error: Conversation {args.conversation_id} not found")
            sys.exit(1)
    elif args.recent:
        conv = get_recent_conversation_with_comments()
        if not conv:
            print("Error: No conversations with comments found")
            sys.exit(1)
    else:
        print("Error: Specify --conversation-id or --recent")
        parser.print_help()
        sys.exit(1)
    
    # Override instruction if provided
    if args.instruction:
        conv['comment_body'] = f"@ai {args.instruction}"
    
    print(f"Processing conversation: {conv['conversation_id'][:8]}...", flush=True)
    print(f"Subject: {conv['subject']}", flush=True)
    print(f"Triggered by: {conv['author_name']}", flush=True)
    print(f"Comment: {conv['comment_body'][:100]}...", flush=True)
    print(flush=True)
    
    # Fetch context
    logger.info("Fetching context...")
    ctx = fetch_context(
        conv['conversation_id'],
        conv['comment_body'],
        conv['author_id']
    )
    
    print(f"Project: {ctx.project_name}", flush=True)
    print(f"Emails: {ctx.emails_count}", flush=True)
    print(f"Comments: {len(ctx.comments)}", flush=True)
    print(f"Tasks: {len(ctx.tasks)}", flush=True)
    print(f"Anforderungen: {len(ctx.anforderungen)}", flush=True)
    print(f"Hinweise: {len(ctx.hinweise)}", flush=True)
    print(f"Files: {len(ctx.files)}", flush=True)
    print(f"Craft docs: {len(ctx.craft_docs)}", flush=True)
    print(flush=True)
    
    # Render prompt
    logger.info("Rendering prompt...")
    system_prompt = get_system_prompt()
    rendered_prompt = render_template(system_prompt, ctx)
    
    if args.dry_run:
        output_result(
            "(Dry run - Claude not called)",
            args.output,
            rendered_prompt,
            show_prompt=True  # Always show prompt in dry run
        )
        return
    
    # Call Claude
    logger.info("Calling Claude...")
    if args.no_mcp:
        result = call_claude_simple(rendered_prompt)
    else:
        result = call_claude(rendered_prompt)
    
    # Output
    output_result(
        result,
        args.output,
        rendered_prompt if args.show_prompt else None,
        args.show_prompt
    )


if __name__ == "__main__":
    main()

