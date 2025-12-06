"""AI-powered task ranking using OpenAI."""

import json
import logging
import structlog
from typing import List
from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .config import Settings
from .models import TodoistTask, TodoistProject, PriorityRankings, TaskPriority, InboxOrganizations, InboxOrganization

logger = structlog.get_logger()


class AIRanker:
    """AI-powered task ranking using OpenAI."""
    
    def __init__(self, settings: Settings):
        """Initialize AI ranker.
        
        Args:
            settings: Application settings containing OpenAI API key
        """
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.logger = structlog.get_logger()
    
    def _build_prompt(self, tasks: List[TodoistTask]) -> str:
        """Build prompt for AI ranking.
        
        Args:
            tasks: List of tasks to rank
            
        Returns:
            Formatted prompt string
        """
        task_descriptions = "\n\n".join([
            task.to_ai_format() for task in tasks
        ])
        
        prompt = f"""Rank the following tasks using the Eisenhower Matrix method.
        
For each task, determine its Urgency and Importance to place it in one of the 4 quadrants:
1. Do First (Urgent & Important) -> P1
2. Schedule (Not Urgent & Important) -> P2
3. Delegate (Urgent & Not Important) -> P3
4. Don't Do (Not Urgent & Not Important) -> P4

If a task lacks specific attributes (like due date or description), use your best judgment based on the task content to estimate its importance and urgency.

For each task, provide:
1. A priority score from 0-100 (100 = highest priority)
2. A priority level: P1, P2, P3, or P4 based on the matrix
3. A brief reasoning explaining which quadrant it falls into and why

Return the result as a JSON object with this exact structure:
{{
  "rankings": [
    {{
      "task_id": "task ID from the input",
      "priority_score": 85,
      "priority_level": "P1",
      "reasoning": "Urgent and Important: [Explanation]"
    }}
  ]
}}

Tasks:
{task_descriptions}
"""
        return prompt
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API with retry logic.
        
        Args:
            prompt: The prompt to send to OpenAI
            
        Returns:
            Response content as string
        """
        self.logger.info(
            "calling_openai",
            model=self.settings.ai_model,
            temperature=self.settings.ai_temperature
        )
        
        response = self.client.chat.completions.create(
            model=self.settings.ai_model,
            temperature=self.settings.ai_temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a productivity expert who helps prioritize tasks. "
                        "Always respond with valid JSON matching the requested schema."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        
        self.logger.info(
            "openai_response_received",
            tokens_used=response.usage.total_tokens if response.usage else None
        )
        
        return content
    
    def rank_tasks(self, tasks: List[TodoistTask], batch_size: int = 20) -> PriorityRankings:
        """Rank tasks using AI with batching.
        
        Args:
            tasks: List of tasks to rank
            batch_size: Number of tasks to process in one API call
            
        Returns:
            PriorityRankings object with AI-determined priorities
            
        Raises:
            ValueError: If ranking fails or response is invalid
        """
        if not tasks:
            self.logger.warning("no_tasks_to_rank")
            return PriorityRankings(rankings=[])
        
        try:
            all_rankings: List[TaskPriority] = []
            
            # Split tasks into batches
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                self.logger.info(
                    "processing_batch",
                    batch_index=i // batch_size + 1,
                    total_batches=(len(tasks) + batch_size - 1) // batch_size,
                    batch_size=len(batch)
                )
                
                try:
                    # Build prompt for this batch
                    prompt = self._build_prompt(batch)
                    
                    # Call OpenAI
                    response_content = self._call_openai(prompt)
                    
                    # Parse JSON response
                    try:
                        response_data = json.loads(response_content)
                    except json.JSONDecodeError as e:
                        self.logger.error(
                            "json_parse_failed", 
                            error=str(e), 
                            batch_index=i // batch_size + 1,
                            batch_task_ids=[t.id for t in batch]
                        )
                        continue  # Skip failed batch but try others
                    
                    # Validate with Pydantic
                    try:
                        batch_rankings = PriorityRankings(**response_data)
                        all_rankings.extend(batch_rankings.rankings)
                    except Exception as e:
                        self.logger.error(
                            "validation_failed", 
                            error=str(e), 
                            batch_index=i // batch_size + 1,
                            batch_task_ids=[t.id for t in batch],
                            data=response_data
                        )
                        continue
                        
                except Exception as e:
                    self.logger.error(
                        "batch_failed", 
                        error=str(e),
                        batch_index=i // batch_size + 1,
                        batch_task_ids=[t.id for t in batch]
                    )
                    continue
            
            # Create final combined rankings
            final_rankings = PriorityRankings(rankings=all_rankings)
            
            # Verify all tasks got rankings
            ranked_ids = {r.task_id for r in final_rankings.rankings}
            task_ids = {t.id for t in tasks}
            
            missing_task_ids = task_ids - ranked_ids
            extra_task_ids = ranked_ids - task_ids
            
            if ranked_ids != task_ids:
                self.logger.warning(
                    "ranking_mismatch",
                    missing_tasks=list(missing_task_ids),
                    extra_tasks=list(extra_task_ids),
                    ranked_count=len(ranked_ids),
                    total_count=len(task_ids)
                )
            
            self.logger.info(
                "ranking_completed",
                rankings_count=len(final_rankings.rankings)
            )
            
            return final_rankings
            
        except Exception as e:
            self.logger.error("ranking_failed", error=str(e))
            raise
    
    def rank_tasks_with_summary(
        self,
        tasks: List[TodoistTask]
    ) -> tuple[PriorityRankings, dict]:
        """Rank tasks and return summary statistics.
        
        Args:
            tasks: List of tasks to rank
            
        Returns:
            Tuple of (PriorityRankings, summary_dict)
        """
        rankings = self.rank_tasks(tasks)
        
        # Calculate summary statistics
        priority_counts = {'P1': 0, 'P2': 0, 'P3': 0, 'P4': 0}
        score_sum = 0
        
        for ranking in rankings.rankings:
            priority_counts[ranking.priority_level] += 1
            score_sum += ranking.priority_score
        
        summary = {
            'total_tasks': len(tasks),
            'ranked_tasks': len(rankings.rankings),
            'priority_distribution': priority_counts,
            'average_score': score_sum / len(rankings.rankings) if rankings.rankings else 0
        }
        
        self.logger.info("ranking_summary", **summary)
        
        return rankings, summary
    
    def _build_inbox_organization_prompt(
        self, 
        tasks: List[TodoistTask], 
        projects: List[TodoistProject]
    ) -> str:
        """Build prompt for inbox organization.
        
        Args:
            tasks: List of inbox tasks to organize
            projects: List of available projects
            
        Returns:
            Formatted prompt string
        """
        task_descriptions = "\n\n".join([
            task.to_ai_format() for task in tasks
        ])
        
        # Format projects list for AI
        projects_list = "\n".join([
            f"- {p.name} (ID: {p.id})" + (" [ARCHIVED]" if p.is_archived else "")
            for p in projects
            if not p.is_archived  # Exclude archived projects
        ])
        
        prompt = f"""You are organizing tasks from a Todoist inbox. For each task, you need to:

1. Determine priority using the Eisenhower Matrix:
   - P1: Urgent & Important (Do First)
   - P2: Not Urgent & Important (Schedule)
   - P3: Urgent & Not Important (Delegate)
   - P4: Not Urgent & Not Important (Don't Do)

2. Suggest the BEST project for this task based on:
   - Task name and description
   - Project names and their likely purpose
   - If no project fits well, suggest keeping it in Inbox (use project_id: null)

3. Suggest an appropriate due date based on:
   - Task urgency and importance
   - Task content and context
   - Use natural language: "today", "tomorrow", "next week", "next month", or specific dates like "YYYY-MM-DD"
   - If no due date is needed, use null

Available projects:
{projects_list}

For each task, provide:
1. Priority score (0-100, where 100 = highest priority)
2. Priority level (P1, P2, P3, or P4)
3. Best project ID (from the list above, or null to keep in Inbox)
4. Project name (for display purposes)
5. Suggested due date (natural language string or null)
6. Reasoning explaining all decisions

Return the result as a JSON object with this exact structure:
{{
  "organizations": [
    {{
      "task_id": "task ID from the input",
      "priority_score": 85,
      "priority_level": "P1",
      "project_id": "project_id_from_list" or null,
      "project_name": "Project Name" or null,
      "due_date": "today" or "tomorrow" or "next week" or null,
      "reasoning": "Priority: [explanation]. Project: [explanation]. Due date: [explanation]."
    }}
  ]
}}

IMPORTANT:
- Use JSON null (not the string "null") for optional fields when no value is needed
- priority_score must be an integer between 0 and 100
- priority_level must be exactly one of: "P1", "P2", "P3", or "P4"
- project_id must be a valid project ID from the list above, or JSON null to keep in Inbox
- project_name should match the project name from the list, or null if keeping in Inbox
- due_date should be a natural language string like "today", "tomorrow", "next week", or null
- reasoning is required and should explain your decisions

Tasks to organize:
{task_descriptions}
"""
        return prompt
    
    def organize_inbox_tasks(
        self, 
        tasks: List[TodoistTask], 
        projects: List[TodoistProject],
        batch_size: int = 15
    ) -> InboxOrganizations:
        """Organize inbox tasks with AI suggestions for project, due date, and priority.
        
        Args:
            tasks: List of inbox tasks to organize
            projects: List of available projects
            batch_size: Number of tasks to process in one API call (smaller due to more complex prompt)
            
        Returns:
            InboxOrganizations object with AI suggestions
            
        Raises:
            ValueError: If organization fails or response is invalid
        """
        if not tasks:
            self.logger.warning("no_tasks_to_organize")
            return InboxOrganizations(organizations=[])
        
        try:
            all_organizations: List[InboxOrganization] = []
            
            # Split tasks into batches
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                self.logger.info(
                    "processing_organization_batch",
                    batch_index=i // batch_size + 1,
                    total_batches=(len(tasks) + batch_size - 1) // batch_size,
                    batch_size=len(batch)
                )
                
                try:
                    # Build prompt for this batch
                    prompt = self._build_inbox_organization_prompt(batch, projects)
                    
                    # Call OpenAI
                    response_content = self._call_openai(prompt)
                    
                    # Parse JSON response
                    try:
                        response_data = json.loads(response_content)
                    except json.JSONDecodeError as e:
                        self.logger.error(
                            "json_parse_failed", 
                            error=str(e), 
                            batch_index=i // batch_size + 1,
                            batch_task_ids=[t.id for t in batch]
                        )
                        continue  # Skip failed batch but try others
                    
                    # Validate with Pydantic
                    try:
                        batch_organizations = InboxOrganizations(**response_data)
                        all_organizations.extend(batch_organizations.organizations)
                    except Exception as e:
                        # Try to validate individual organizations to see which ones fail
                        if "organizations" in response_data:
                            valid_orgs = []
                            for org_data in response_data.get("organizations", []):
                                try:
                                    org = InboxOrganization(**org_data)
                                    valid_orgs.append(org)
                                except Exception as org_error:
                                    self.logger.warning(
                                        "individual_org_validation_failed",
                                        task_id=org_data.get("task_id", "unknown"),
                                        error=str(org_error),
                                        org_data=org_data
                                    )
                            if valid_orgs:
                                # Add the valid ones
                                all_organizations.extend(valid_orgs)
                                self.logger.warning(
                                    "partial_batch_validation",
                                    batch_index=i // batch_size + 1,
                                    valid_count=len(valid_orgs),
                                    total_count=len(response_data.get("organizations", []))
                                )
                            else:
                                self.logger.error(
                                    "validation_failed", 
                                    error=str(e), 
                                    batch_index=i // batch_size + 1,
                                    batch_task_ids=[t.id for t in batch],
                                    data=response_data
                                )
                        else:
                            self.logger.error(
                                "validation_failed_no_organizations", 
                                error=str(e), 
                                batch_index=i // batch_size + 1,
                                batch_task_ids=[t.id for t in batch],
                                data=response_data
                            )
                        continue
                        
                except Exception as e:
                    self.logger.error(
                        "batch_failed", 
                        error=str(e),
                        batch_index=i // batch_size + 1,
                        batch_task_ids=[t.id for t in batch]
                    )
                    continue
            
            # Create final combined organizations
            final_organizations = InboxOrganizations(organizations=all_organizations)
            
            # Verify all tasks got organizations
            organized_ids = {o.task_id for o in final_organizations.organizations}
            task_ids = {t.id for t in tasks}
            
            missing_task_ids = task_ids - organized_ids
            extra_task_ids = organized_ids - task_ids
            
            if organized_ids != task_ids:
                self.logger.warning(
                    "organization_mismatch",
                    missing_tasks=list(missing_task_ids),
                    extra_tasks=list(extra_task_ids),
                    organized_count=len(organized_ids),
                    total_count=len(task_ids)
                )
            
            self.logger.info(
                "organization_completed",
                organizations_count=len(final_organizations.organizations)
            )
            
            return final_organizations
            
        except Exception as e:
            self.logger.error("organization_failed", error=str(e))
            raise
