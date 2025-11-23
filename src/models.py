"""Data models for Todoist tasks and AI rankings."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class TodoistDueDate(BaseModel):
    """Todoist task due date information."""
    
    date: str
    is_recurring: bool = False
    datetime: Optional[str] = None
    string: Optional[str] = None
    timezone: Optional[str] = None


class TodoistTask(BaseModel):
    """Todoist task model."""
    
    id: str
    content: str
    description: str = ""
    project_id: str
    priority: int = Field(ge=1, le=4)
    due: Optional[TodoistDueDate] = None
    labels: List[str] = Field(default_factory=list)
    created_at: str
    url: str
    
    @property
    def priority_label(self) -> str:
        """Convert numeric priority to human-readable label."""
        priority_map = {
            4: "P1 (Urgent)",
            3: "P2 (High)",
            2: "P3 (Medium)",
            1: "P4 (Normal)"
        }
        return priority_map.get(self.priority, "Unknown")
    
    def to_ai_format(self) -> str:
        """Format task for AI prompt."""
        parts = [f"- {self.content}"]
        
        if self.description:
            parts.append(f"  Description: {self.description}")
        
        if self.due:
            due_str = self.due.string or self.due.date
            parts.append(f"  Due: {due_str}")
        
        if self.labels:
            parts.append(f"  Labels: {', '.join(self.labels)}")
        
        parts.append(f"  Current Priority: {self.priority_label}")
        parts.append(f"  Task ID: {self.id}")
        
        return "\n".join(parts)


class TaskPriority(BaseModel):
    """AI-determined priority for a single task."""
    
    task_id: str
    priority_score: int = Field(ge=0, le=100, description="Priority score from 0-100")
    priority_level: str = Field(description="Priority level: P1, P2, P3, or P4")
    reasoning: str = Field(description="Explanation for the priority assignment")
    
    @field_validator('priority_level')
    @classmethod
    def validate_priority_level(cls, v: str) -> str:
        """Ensure priority level is valid."""
        valid_levels = ['P1', 'P2', 'P3', 'P4']
        if v.upper() not in valid_levels:
            raise ValueError(f"Priority level must be one of {valid_levels}")
        return v.upper()
    
    @property
    def todoist_priority(self) -> int:
        """Convert priority level to Todoist API value (P1=4, P2=3, P3=2, P4=1)."""
        priority_map = {
            'P1': 4,  # Urgent
            'P2': 3,  # High
            'P3': 2,  # Medium
            'P4': 1   # Normal
        }
        return priority_map[self.priority_level]


class PriorityRankings(BaseModel):
    """Collection of AI-determined priorities for all tasks."""
    
    rankings: List[TaskPriority]
    
    def get_ranking_for_task(self, task_id: str) -> Optional[TaskPriority]:
        """Get ranking for a specific task."""
        for ranking in self.rankings:
            if ranking.task_id == task_id:
                return ranking
        return None
