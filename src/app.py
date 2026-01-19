"""AI Email Agent - Main application with polling loop."""

import time
import signal
import sys
from datetime import datetime
from typing import Optional
import psycopg

from src.settings import settings
from src.logging_conf import setup_logging, logger
from src.context import fetch_context
from src.template import render_template, DEFAULT_SYSTEM_PROMPT
from src.claude import call_claude
from src.missive import missive


# Graceful shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_requested
    logger.info("Shutdown requested...")
    shutdown_requested = True


def get_system_prompt() -> str:
    """
    Fetch system prompt from app_settings, fallback to default.
    
    The prompt is stored in app_settings.body['ai_agent_system_prompt'].
    """
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


def claim_pending_trigger() -> Optional[dict]:
    """
    Atomically claim a pending trigger for processing.
    
    Returns:
        Trigger dict with id, conversation_id, comment_body, author_id
        or None if no pending triggers.
    """
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            # Atomic claim: SELECT + UPDATE in one statement
            cur.execute("""
                UPDATE ai_triggers
                SET status = 'processing', processed_at = NOW()
                WHERE id = (
                    SELECT id FROM ai_triggers
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, conversation_id, comment_body, author_id
            """)
            row = cur.fetchone()
            conn.commit()
            
            if row:
                return {
                    'id': str(row[0]),
                    'conversation_id': str(row[1]),
                    'comment_body': row[2] or '',
                    'author_id': str(row[3]) if row[3] else None
                }
            return None


def update_trigger_status(
    trigger_id: str,
    status: str,
    placeholder_post_id: str = None,
    result_post_id: str = None,
    result_markdown: str = None,
    error_message: str = None
):
    """Update trigger status and related fields."""
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ai_triggers
                SET status = %s,
                    placeholder_post_id = COALESCE(%s, placeholder_post_id),
                    result_post_id = COALESCE(%s, result_post_id),
                    result_markdown = COALESCE(%s, result_markdown),
                    error_message = COALESCE(%s, error_message),
                    processed_at = NOW()
                WHERE id = %s
            """, (status, placeholder_post_id, result_post_id, result_markdown, error_message, trigger_id))
            conn.commit()


def process_trigger(trigger: dict):
    """
    Process a single AI trigger:
    1. Post placeholder
    2. Fetch context
    3. Render prompt
    4. Call Claude
    5. Delete placeholder
    6. Post result
    7. Update trigger status
    """
    trigger_id = trigger['id']
    conversation_id = trigger['conversation_id']
    comment_body = trigger['comment_body']
    author_id = trigger['author_id']
    
    logger.info(f"Processing trigger {trigger_id[:8]}... for conversation {conversation_id[:8]}...")
    
    # 1. Post placeholder
    placeholder_id = missive.post_message(
        conversation_id=conversation_id,
        markdown="🤖 *Researching...*"
    )
    
    if placeholder_id:
        update_trigger_status(trigger_id, 'processing', placeholder_post_id=placeholder_id)
    
    try:
        # 2. Fetch context
        ctx = fetch_context(conversation_id, comment_body, author_id)
        
        # 3. Render prompt
        system_prompt = get_system_prompt()
        rendered_prompt = render_template(system_prompt, ctx)
        
        # 4. Call Claude with MCP
        response = call_claude(rendered_prompt)
        
        # 5. Delete placeholder
        if placeholder_id:
            missive.delete_post(placeholder_id)
        
        # 6. Post result
        result_post_id = missive.post_message(
            conversation_id=conversation_id,
            markdown=response
        )
        
        # 7. Update trigger as done
        update_trigger_status(
            trigger_id,
            status='done',
            result_post_id=result_post_id,
            result_markdown=response
        )
        
        logger.info(f"Trigger {trigger_id[:8]}... completed successfully")
        
    except Exception as e:
        logger.error(f"Error processing trigger {trigger_id}: {e}", exc_info=True)
        
        # Delete placeholder on error
        if placeholder_id:
            missive.delete_post(placeholder_id)
        
        # Post error message
        error_post_id = missive.post_message(
            conversation_id=conversation_id,
            markdown=f"❌ AI temporarily unavailable. Please try again later.\n\n*Error: {str(e)[:100]}*"
        )
        
        update_trigger_status(
            trigger_id,
            status='error',
            result_post_id=error_post_id,
            error_message=str(e)
        )


def main():
    """Main polling loop."""
    setup_logging()
    logger.info("AI Email Agent starting...")
    logger.info(f"Polling interval: {settings.poll_interval_seconds}s")
    logger.info(f"Claude model: {settings.claude_model}")
    logger.info(f"MCP server: {settings.mcp_server_url}")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    while not shutdown_requested:
        try:
            # Try to claim a pending trigger
            trigger = claim_pending_trigger()
            
            if trigger:
                process_trigger(trigger)
            else:
                # No pending triggers, wait
                time.sleep(settings.poll_interval_seconds)
                
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(5)  # Back off on error
    
    logger.info("AI Email Agent stopped")


if __name__ == "__main__":
    main()

