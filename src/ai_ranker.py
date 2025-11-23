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
from .models import TodoistTask, PriorityRankings, TaskPriority

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
        
        prompt = f"""Rank the following tasks in priority order. Consider:
- Urgency: How time-sensitive is the task?
- Due date: Tasks due sooner should typically be higher priority
- Impact: How important is completing this task?
- Effort: Consider the effort required relative to the value

For each task, provide:
1. A priority score from 0-100 (100 = highest priority)
2. A priority level: P1 (Urgent), P2 (High), P3 (Medium), or P4 (Normal)
3. A brief reasoning for the priority assignment

Return the result as a JSON object with this exact structure:
{{
  "rankings": [
    {{
      "task_id": "task ID from the input",
      "priority_score": 85,
      "priority_level": "P1",
      "reasoning": "Brief explanation"
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
    
    def rank_tasks(self, tasks: List[TodoistTask]) -> PriorityRankings:
        """Rank tasks using AI.
        
        Args:
            tasks: List of tasks to rank
            
        Returns:
            PriorityRankings object with AI-determined priorities
            
        Raises:
            ValueError: If ranking fails or response is invalid
        """
        if not tasks:
            self.logger.warning("no_tasks_to_rank")
            return PriorityRankings(rankings=[])
        
        try:
            self.logger.info("ranking_tasks", task_count=len(tasks))
            
            # Build prompt
            prompt = self._build_prompt(tasks)
            
            # Call OpenAI
            response_content = self._call_openai(prompt)
            
            # Parse JSON response
            try:
                response_data = json.loads(response_content)
            except json.JSONDecodeError as e:
                self.logger.error("json_parse_failed", error=str(e), content=response_content)
                raise ValueError(f"Failed to parse AI response as JSON: {e}")
            
            # Validate with Pydantic
            try:
                rankings = PriorityRankings(**response_data)
            except Exception as e:
                self.logger.error("validation_failed", error=str(e), data=response_data)
                raise ValueError(f"AI response validation failed: {e}")
            
            # Verify all tasks got rankings
            ranked_ids = {r.task_id for r in rankings.rankings}
            task_ids = {t.id for t in tasks}
            
            if ranked_ids != task_ids:
                missing = task_ids - ranked_ids
                extra = ranked_ids - task_ids
                self.logger.warning(
                    "ranking_mismatch",
                    missing_tasks=list(missing),
                    extra_tasks=list(extra)
                )
            
            self.logger.info(
                "ranking_completed",
                rankings_count=len(rankings.rankings)
            )
            
            return rankings
            
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
