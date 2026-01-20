"""Missive API client for posting and deleting posts."""

import httpx
from typing import Optional

from src.settings import settings
from src.logging_conf import logger


class MissiveClient:
    """Client for Missive Posts API."""
    
    BASE_URL = "https://public.missiveapp.com/v1"
    
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {settings.missive_api_token}",
            "Content-Type": "application/json"
        }
    
    def post_message(
        self,
        conversation_id: str,
        markdown: str,
        username: str = "IBHelm AI",
        username_icon: str = "https://api.ibhelm.de/ai-avatar.png",
    ) -> Optional[str]:
        """
        Create a post in a Missive conversation.
        
        Returns:
            Post ID if successful, None otherwise.
        """
        payload = {
            "posts": {
                "conversation": conversation_id,
                "markdown": markdown,
                "username": username,
                "username_icon": username_icon,
                "notification": {
                    "title": "IBHelm AI",
                    "body": markdown[:100] + ("..." if len(markdown) > 100 else "")
                }
            }
        }
        
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self.BASE_URL}/posts",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code in (200, 201):
                    data = response.json()
                    post_id = data.get("posts", {}).get("id")
                    logger.debug(f"Created post {post_id} in conversation {conversation_id}")
                    return post_id
                else:
                    logger.error(f"Failed to create post: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error creating post: {e}")
            return None
    
    def delete_post(self, post_id: str) -> bool:
        """
        Delete a post by ID.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            with httpx.Client(timeout=30) as client:
                response = client.delete(
                    f"{self.BASE_URL}/posts/{post_id}",
                    headers=self.headers
                )
                
                if response.status_code in (200, 204):
                    logger.debug(f"Deleted post {post_id}")
                    return True
                elif response.status_code == 404:
                    logger.warning(f"Post {post_id} not found (already deleted?)")
                    return True  # Consider success if already gone
                else:
                    logger.error(f"Failed to delete post {post_id}: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error deleting post {post_id}: {e}")
            return False


# Singleton instance
missive = MissiveClient()

