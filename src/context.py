"""Context gathering for AI Agent - fetches all relevant data for a conversation."""

import json
from dataclasses import dataclass, field
from typing import Optional
import psycopg

from src.settings import settings
from src.logging_conf import logger


@dataclass
class EmailInfo:
    id: str
    subject: str
    from_name: str
    from_email: str
    delivered_at: str
    body: str  # Truncated to 2000 chars


@dataclass
class CommentInfo:
    author_name: str
    created_at: str
    body: str


@dataclass
class TaskInfo:
    id: int
    name: str
    status: str
    assigned_to: str
    updated_at: str
    tasklist: str


@dataclass
class FileInfo:
    name: str
    path: str
    updated_at: str


@dataclass
class CraftDocInfo:
    id: str
    title: str
    modified_at: str


@dataclass
class ConversationContext:
    """All context needed for AI to respond to a conversation."""
    # Trigger info
    trigger_author: str
    trigger_instruction: str
    
    # Conversation basics
    conversation_id: str
    conversation_subject: str
    conversation_url: str
    
    # Project (may be None)
    project_name: str
    project_id: Optional[int]
    
    # Emails
    emails: list[EmailInfo] = field(default_factory=list)
    emails_metadata: list[dict] = field(default_factory=list)  # All emails: id, subject, from, date
    emails_count: int = 0
    
    # Comments
    comments: list[CommentInfo] = field(default_factory=list)
    
    # Tasks (by type)
    tasks: list[TaskInfo] = field(default_factory=list)
    anforderungen: list[TaskInfo] = field(default_factory=list)
    hinweise: list[TaskInfo] = field(default_factory=list)
    
    # Files and Craft
    files: list[FileInfo] = field(default_factory=list)
    craft_docs: list[CraftDocInfo] = field(default_factory=list)


def get_connection():
    """Get a database connection."""
    return psycopg.connect(settings.database_url)


def fetch_context(conversation_id: str, comment_body: str, author_id: str) -> ConversationContext:
    """
    Fetch all context for a conversation.
    
    Args:
        conversation_id: Missive conversation UUID
        comment_body: The comment that triggered the AI (contains @ai)
        author_id: UUID of the comment author
    """
    with get_connection() as conn:
        # Get author name
        trigger_author = _get_author_name(conn, author_id)
        
        # Extract instruction (everything after @ai, case-insensitive)
        trigger_instruction = _extract_instruction(comment_body)
        
        # Get conversation basics
        conv_info = _get_conversation_info(conn, conversation_id)
        
        # Get project info
        project_name, project_id = _get_project_info(conn, conversation_id)
        
        # Get emails
        emails, emails_metadata, emails_count = _get_emails(conn, conversation_id)
        
        # Get comments
        comments = _get_comments(conn, conversation_id)
        
        # Get tasks (only if project exists)
        tasks, anforderungen, hinweise = [], [], []
        files, craft_docs = [], []
        
        if project_id:
            tasks = _get_items_by_type(conn, project_name, 'other')
            anforderungen = _get_items_by_type(conn, project_name, 'info')
            hinweise = _get_items_by_type(conn, project_name, 'todo')
            files = _get_files(conn, project_id)
            craft_docs = _get_craft_docs(conn, project_id)
        
        return ConversationContext(
            trigger_author=trigger_author,
            trigger_instruction=trigger_instruction,
            conversation_id=conversation_id,
            conversation_subject=conv_info.get('subject', '(No subject)'),
            conversation_url=conv_info.get('web_url', ''),
            project_name=project_name,
            project_id=project_id,
            emails=emails,
            emails_metadata=emails_metadata,
            emails_count=emails_count,
            comments=comments,
            tasks=tasks,
            anforderungen=anforderungen,
            hinweise=hinweise,
            files=files,
            craft_docs=craft_docs,
        )


def _extract_instruction(comment_body: str) -> str:
    """Extract everything after @ai from comment body."""
    import re
    # Find @ai (case-insensitive) and get everything after it
    match = re.search(r'@ai\b\s*(.*)', comment_body, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _get_author_name(conn, author_id: str) -> str:
    """Get the name of a Missive user by ID."""
    if not author_id:
        return "Unknown"
    
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name FROM missive.users WHERE id = %s",
            (author_id,)
        )
        row = cur.fetchone()
        return row[0] if row else "Unknown"


def _get_conversation_info(conn, conversation_id: str) -> dict:
    """Get basic conversation info."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT subject, latest_message_subject, web_url, messages_count
            FROM missive.conversations
            WHERE id = %s
        """, (conversation_id,))
        row = cur.fetchone()
        if row:
            return {
                'subject': row[0] or row[1] or '(No subject)',
                'web_url': row[2] or '',
                'messages_count': row[3] or 0
            }
        return {}


def _get_project_info(conn, conversation_id: str) -> tuple[str, Optional[int]]:
    """Get project info linked to conversation via labels."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.name
            FROM project_conversations pc
            JOIN teamwork.projects p ON pc.tw_project_id = p.id
            WHERE pc.m_conversation_id = %s
            LIMIT 1
        """, (conversation_id,))
        row = cur.fetchone()
        if row:
            return row[1], row[0]
        return "Not assigned", None


def _get_emails(conn, conversation_id: str) -> tuple[list[EmailInfo], list[dict], int]:
    """Get emails for conversation: last 3 full, all metadata, total count."""
    with conn.cursor() as cur:
        # Get total count
        cur.execute(
            "SELECT COUNT(*) FROM missive.messages WHERE conversation_id = %s",
            (conversation_id,)
        )
        total_count = cur.fetchone()[0]
        
        # Get all emails metadata (id, subject, from, date)
        cur.execute("""
            SELECT m.id, m.subject, c.name, c.email, m.delivered_at
            FROM missive.messages m
            LEFT JOIN missive.contacts c ON m.from_contact_id = c.id
            WHERE m.conversation_id = %s
            ORDER BY m.delivered_at DESC
        """, (conversation_id,))
        
        all_metadata = []
        for row in cur.fetchall():
            all_metadata.append({
                'id': str(row[0]),
                'subject': row[1] or '(No subject)',
                'from_name': row[2] or 'Unknown',
                'from_email': row[3] or '',
                'delivered_at': str(row[4]) if row[4] else ''
            })
        
        # Get last 3 emails with body (truncated)
        cur.execute("""
            SELECT m.id, m.subject, c.name, c.email, m.delivered_at,
                   CASE 
                       WHEN LENGTH(COALESCE(m.body_plain_text, m.body, '')) > 2000 
                       THEN LEFT(COALESCE(m.body_plain_text, m.body, ''), 2000) || '...'
                       ELSE COALESCE(m.body_plain_text, m.body, '')
                   END as body
            FROM missive.messages m
            LEFT JOIN missive.contacts c ON m.from_contact_id = c.id
            WHERE m.conversation_id = %s
            ORDER BY m.delivered_at DESC
            LIMIT 3
        """, (conversation_id,))
        
        emails = []
        for row in cur.fetchall():
            emails.append(EmailInfo(
                id=str(row[0]),
                subject=row[1] or '(No subject)',
                from_name=row[2] or 'Unknown',
                from_email=row[3] or '',
                delivered_at=str(row[4]) if row[4] else '',
                body=row[5] or ''
            ))
        
        return emails, all_metadata, total_count


def _get_comments(conn, conversation_id: str) -> list[CommentInfo]:
    """Get all comments for conversation."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT u.name, cc.created_at, cc.body
            FROM missive.conversation_comments cc
            LEFT JOIN missive.users u ON cc.author_id = u.id
            WHERE cc.conversation_id = %s
            ORDER BY cc.created_at ASC
        """, (conversation_id,))
        
        return [
            CommentInfo(
                author_name=row[0] or 'Unknown',
                created_at=str(row[1]) if row[1] else '',
                body=row[2] or ''
            )
            for row in cur.fetchall()
        ]


def _get_items_by_type(conn, project_name: str, task_type_slug: str) -> list[TaskInfo]:
    """Get tasks/anforderungen/hinweise for a project from unified_items_secure."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, status, assigned_to, updated_at, tasklist
            FROM unified_items_secure
            WHERE type = 'task'
              AND project = %s
              AND task_type_slug = %s
            ORDER BY updated_at DESC
            LIMIT 10
        """, (project_name, task_type_slug))
        
        results = []
        for row in cur.fetchall():
            # Parse assigned_to JSONB
            assigned_to = ''
            if row[3]:
                try:
                    assignees = row[3] if isinstance(row[3], list) else json.loads(row[3])
                    names = [f"{a.get('first_name', '')} {a.get('last_name', '')}".strip() 
                             for a in assignees]
                    assigned_to = ', '.join(filter(None, names))
                except (json.JSONDecodeError, TypeError):
                    assigned_to = str(row[3])
            
            results.append(TaskInfo(
                id=row[0],
                name=row[1] or '',
                status=row[2] or '',
                assigned_to=assigned_to or 'Unassigned',
                updated_at=str(row[4]) if row[4] else '',
                tasklist=row[5] or ''
            ))
        
        return results


def _get_files(conn, project_id: int) -> list[FileInfo]:
    """Get recent files for a project."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                SPLIT_PART(full_path, '/', -1) as filename,
                full_path,
                COALESCE(db_updated_at, fs_mtime, db_created_at) as updated
            FROM files
            WHERE project_id = %s AND deleted_at IS NULL
            ORDER BY COALESCE(db_updated_at, fs_mtime, db_created_at) DESC
            LIMIT 10
        """, (project_id,))
        
        return [
            FileInfo(
                name=row[0] or '',
                path=row[1] or '',
                updated_at=str(row[2]) if row[2] else ''
            )
            for row in cur.fetchall()
        ]


def _get_craft_docs(conn, project_id: int) -> list[CraftDocInfo]:
    """Get recent Craft documents for a project."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cd.id, cd.title, cd.craft_last_modified_at
            FROM craft_documents cd
            JOIN project_craft_documents pcd ON cd.id = pcd.craft_document_id
            WHERE pcd.tw_project_id = %s AND cd.is_deleted = FALSE
            ORDER BY cd.craft_last_modified_at DESC
            LIMIT 10
        """, (project_id,))
        
        return [
            CraftDocInfo(
                id=str(row[0]),
                title=row[1] or '',
                modified_at=str(row[2]) if row[2] else ''
            )
            for row in cur.fetchall()
        ]

