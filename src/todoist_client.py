"""Todoist API client with rate limiting and error handling."""

import time
import logging
import structlog
import requests
from collections import deque
from typing import List, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from requests.exceptions import RequestException, HTTPError

from .config import Settings
from .models import TodoistTask

logger = structlog.get_logger()


class RateLimiter:
    """Token bucket rate limiter for API calls."""
    
    def __init__(self, max_calls: int, period_seconds: int):
        """Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls allowed in the time period
            period_seconds: Time period in seconds
        """
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls = deque()
    
    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = time.time()
        
        # Remove old calls outside the window
        while self.calls and self.calls[0] < now - self.period:
            self.calls.popleft()
        
        # If at limit, wait
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0]) + 0.1  # Small buffer
            if sleep_time > 0:
                logger.warning(
                    "rate_limit_reached",
                    sleep_time=sleep_time,
                    calls_made=len(self.calls)
                )
                time.sleep(sleep_time)
                self.wait_if_needed()  # Recursive check
                return
        
        self.calls.append(now)


class TodoistClient:
    """Wrapper for Todoist API with rate limiting and error handling."""
    
    BASE_URL = "https://api.todoist.com/rest/v2"
    
    def __init__(self, settings: Settings):
        """Initialize Todoist client.
        
        Args:
            settings: Application settings containing API token
        """
        self.settings = settings
        self.api_token = settings.todoist_api_token
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        self.rate_limiter = RateLimiter(
            max_calls=settings.todoist_rate_limit,
            period_seconds=settings.todoist_rate_period
        )
        self.logger = structlog.get_logger()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RequestException, HTTPError)),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    def _api_call_with_retry(self, func, *args, **kwargs):
        """Execute API call with retry logic.
        
        Args:
            func: API function to call
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the API call
        """
        self.rate_limiter.wait_if_needed()
        return func(*args, **kwargs)
    
    def get_tasks(
        self,
        project_id: Optional[str] = None,
        label: Optional[str] = None,
        filter_query: Optional[str] = None
    ) -> List[TodoistTask]:
        """Fetch tasks from Todoist.
        
        Args:
            project_id: Optional project ID to filter by
            label: Optional label to filter by
            filter_query: Optional Todoist filter query
            
        Returns:
            List of TodoistTask objects
        """
        try:
            self.logger.info(
                "fetching_tasks",
                project_id=project_id,
                label=label,
                filter_query=filter_query
            )
            
            # Build query parameters
            params = {}
            if project_id:
                params['project_id'] = project_id
            if label:
                params['label'] = label
            if filter_query:
                params['filter'] = filter_query
            
            # Fetch tasks with retry - returns raw JSON
            response = self._api_call_with_retry(
                lambda: requests.get(
                    f"{self.BASE_URL}/tasks",
                    headers=self.headers,
                    params=params,
                    timeout=self.settings.api_timeout
                )
            )
            response.raise_for_status()
            tasks_data = response.json()
            
            # Convert to our model
            todoist_tasks = []
            for task_dict in tasks_data:
                try:
                    # Parse task data
                    parsed_task = {
                        'id': task_dict['id'],
                        'content': task_dict['content'],
                        'description': task_dict.get('description', ''),
                        'project_id': task_dict['project_id'],
                        'priority': task_dict['priority'],
                        'labels': task_dict.get('labels', []),
                        'created_at': task_dict['created_at'],
                        'url': task_dict['url'],
                    }
                    
                    # Add due date if present
                    if task_dict.get('due'):
                        parsed_task['due'] = {
                            'date': task_dict['due']['date'],
                            'is_recurring': task_dict['due'].get('is_recurring', False),
                            'datetime': task_dict['due'].get('datetime'),
                            'string': task_dict['due'].get('string'),
                            'timezone': task_dict['due'].get('timezone'),
                        }
                    
                    todoist_tasks.append(TodoistTask(**parsed_task))
                except Exception as e:
                    self.logger.error(
                        "task_conversion_failed",
                        task_id=task_dict.get('id', 'unknown'),
                        error=str(e)
                    )
                    continue
            
            self.logger.info("tasks_fetched", count=len(todoist_tasks))
            return todoist_tasks
            
        except Exception as e:
            self.logger.error("fetch_tasks_failed", error=str(e))
            raise
    
    def update_task_priority(
        self,
        task_id: str,
        priority: int,
        dry_run: bool = False
    ) -> bool:
        """Update task priority in Todoist.
        
        Args:
            task_id: ID of the task to update
            priority: New priority (1-4, where 4 is urgent)
            dry_run: If True, don't actually update the task
            
        Returns:
            True if successful, False otherwise
        """
        if not 1 <= priority <= 4:
            self.logger.error("invalid_priority", priority=priority)
            return False
        
        if dry_run:
            self.logger.info(
                "dry_run_update",
                task_id=task_id,
                priority=priority
            )
            return True
        
        try:
            self.logger.info(
                "updating_task_priority",
                task_id=task_id,
                priority=priority
            )
            
            response = self._api_call_with_retry(
                lambda: requests.post(
                    f"{self.BASE_URL}/tasks/{task_id}",
                    headers=self.headers,
                    json={"priority": priority},
                    timeout=self.settings.api_timeout
                )
            )
            response.raise_for_status()
            
            self.logger.info("task_updated", task_id=task_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "update_task_failed",
                task_id=task_id,
                error=str(e)
            )
            return False
    
    def batch_update_priorities(
        self,
        updates: List[tuple[str, int]],
        dry_run: bool = False
    ) -> dict:
        """Update multiple task priorities.
        
        Args:
            updates: List of (task_id, priority) tuples
            dry_run: If True, don't actually update tasks
            
        Returns:
            Dict with 'successful' and 'failed' counts
        """
        results = {'successful': 0, 'failed': 0}
        
        self.logger.info(
            "batch_update_started",
            total_tasks=len(updates),
            dry_run=dry_run
        )
        
        for task_id, priority in updates:
            if self.update_task_priority(task_id, priority, dry_run):
                results['successful'] += 1
            else:
                results['failed'] += 1
            
            # Small delay between updates to be respectful
            if not dry_run:
                time.sleep(0.1)
        
        self.logger.info(
            "batch_update_completed",
            successful=results['successful'],
            failed=results['failed']
        )
        
        return results

    def get_today_tasks(self) -> List[TodoistTask]:
        """Fetch tasks that are due today.
        
        Returns:
            List of TodoistTask objects due today
        """
        return self.get_tasks(filter_query="today")
    
    def update_task_due_date(
        self,
        task_id: str,
        due_string: Optional[str] = None,
        dry_run: bool = False
    ) -> bool:
        """Update task due date in Todoist.
        
        Args:
            task_id: ID of the task to update
            due_string: Due date string (e.g., "today", "tomorrow", None to remove)
            dry_run: If True, don't actually update the task
            
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            self.logger.info(
                "dry_run_due_date_update",
                task_id=task_id,
                due_string=due_string
            )
            return True
        
        try:
            self.logger.info(
                "updating_task_due_date",
                task_id=task_id,
                due_string=due_string
            )
            
            # Build the update payload
            payload = {}
            if due_string:
                payload["due_string"] = due_string
            else:
                # To remove due date, we need to set due_date to None
                payload["due_string"] = "no date"
            
            response = self._api_call_with_retry(
                lambda: requests.post(
                    f"{self.BASE_URL}/tasks/{task_id}",
                    headers=self.headers,
                    json=payload,
                    timeout=self.settings.api_timeout
                )
            )
            response.raise_for_status()
            
            self.logger.info("task_due_date_updated", task_id=task_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "update_task_due_date_failed",
                task_id=task_id,
                error=str(e)
            )
            return False
    
    def batch_update_due_dates(
        self,
        updates: List[tuple[str, Optional[str]]],
        dry_run: bool = False
    ) -> dict:
        """Update multiple task due dates.
        
        Args:
            updates: List of (task_id, due_string) tuples
            dry_run: If True, don't actually update tasks
            
        Returns:
            Dict with 'successful' and 'failed' counts
        """
        results = {'successful': 0, 'failed': 0}
        
        self.logger.info(
            "batch_due_date_update_started",
            total_tasks=len(updates),
            dry_run=dry_run
        )
        
        for task_id, due_string in updates:
            if self.update_task_due_date(task_id, due_string, dry_run):
                results['successful'] += 1
            else:
                results['failed'] += 1
            
            # Small delay between updates to be respectful
            if not dry_run:
                time.sleep(0.1)
        
        self.logger.info(
            "batch_due_date_update_completed",
            successful=results['successful'],
            failed=results['failed']
        )
        
        return results

    def reorder_tasks(
        self,
        ordered_tasks: List[TodoistTask],
        dry_run: bool = False
    ) -> bool:
        """Reorder tasks in Todoist using the Sync API.
        
        Args:
            ordered_tasks: List of tasks in the desired order
            dry_run: If True, don't actually reorder tasks
            
        Returns:
            True if successful, False otherwise
        """
        if not ordered_tasks:
            return True
            
        if dry_run:
            self.logger.info(
                "dry_run_reorder",
                task_count=len(ordered_tasks),
                first_task=ordered_tasks[0].content,
                last_task=ordered_tasks[-1].content
            )
            return True
            
        try:
            self.logger.info(
                "reordering_tasks",
                task_count=len(ordered_tasks)
            )
            
            # The Sync API expects a list of task IDs in the desired order
            # We need to construct a command for item_reorder
            cmd = {
                "type": "item_reorder",
                "uuid": str(time.time()),  # Simple UUID generation
                "args": {
                    "items": [
                        {"id": task.id, "child_order": idx}
                        for idx, task in enumerate(ordered_tasks)
                    ]
                }
            }
            
            response = self._api_call_with_retry(
                lambda: requests.post(
                    f"https://api.todoist.com/sync/v9/sync",
                    headers=self.headers,
                    json={"commands": [cmd]},
                    timeout=self.settings.api_timeout
                )
            )
            response.raise_for_status()
            
            result = response.json()
            if result.get("sync_status", {}).get(cmd["uuid"]) == "ok":
                self.logger.info("reorder_completed")
                return True
            else:
                self.logger.error("reorder_failed_sync_status", result=result)
                return False
                
        except Exception as e:
            self.logger.error("reorder_failed", error=str(e))
            return False
