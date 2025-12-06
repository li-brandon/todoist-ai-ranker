"""Data models for Todoist tasks and AI rankings."""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class TodoistDueDate(BaseModel):
    """Todoist task due date information."""
    
    date: str
    is_recurring: bool = False
    datetime: Optional[str] = None
    string: Optional[str] = None
    timezone: Optional[str] = None


class TodoistProject(BaseModel):
    """Todoist project model."""
    
    id: str
    name: str
    color: Optional[str] = None
    parent_id: Optional[str] = None
    order: int = 0
    is_archived: bool = False
    is_favorite: bool = False
    view_style: Optional[str] = None
    url: str


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
    
    @property
    def is_recurring(self) -> bool:
        """Check if task is a recurring task."""
        return self.due is not None and self.due.is_recurring
    
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


class InboxOrganization(BaseModel):
    """AI-determined organization for a single inbox task."""
    
    task_id: str
    priority_score: int = Field(ge=0, le=100, description="Priority score from 0-100")
    priority_level: str = Field(description="Priority level: P1, P2, P3, or P4")
    project_id: Optional[str] = Field(None, description="Suggested project ID to move task to")
    project_name: Optional[str] = Field(None, description="Suggested project name (for display)")
    due_date: Optional[str] = Field(None, description="Suggested due date (e.g., 'today', 'tomorrow', 'next week', or specific date)")
    reasoning: str = Field(default="", description="Explanation for the organization decisions")
    
    @field_validator('priority_level')
    @classmethod
    def validate_priority_level(cls, v: str) -> str:
        """Ensure priority level is valid."""
        if not v:
            return "P4"  # Default to lowest priority if empty
        valid_levels = ['P1', 'P2', 'P3', 'P4']
        v_upper = v.upper().strip()
        if v_upper not in valid_levels:
            # Try to extract priority from string if it contains it
            for level in valid_levels:
                if level in v_upper:
                    return level
            # Default to P4 if invalid
            return "P4"
        return v_upper
    
    @field_validator('priority_score', mode='before')
    @classmethod
    def validate_priority_score(cls, v) -> int:
        """Ensure priority score is within valid range."""
        try:
            score = int(v) if v is not None else 50
            return max(0, min(100, score))  # Clamp to 0-100
        except (ValueError, TypeError):
            return 50  # Default score
    
    @field_validator('project_id', mode='before')
    @classmethod
    def validate_project_id(cls, v) -> Optional[str]:
        """Handle null values, string 'null', and integers."""
        if v is None or v == "null" or v == "":
            return None
        # Convert integers to strings (AI sometimes returns project_id as int)
        if isinstance(v, int):
            return str(v)
        return str(v) if v else None
    
    @field_validator('project_name', mode='before')
    @classmethod
    def validate_project_name(cls, v) -> Optional[str]:
        """Handle null values and string 'null'."""
        if v is None or v == "null" or v == "":
            return None
        return str(v) if v else None
    
    @field_validator('due_date', mode='before')
    @classmethod
    def validate_due_date(cls, v) -> Optional[str]:
        """Handle null values and string 'null'."""
        if v is None or v == "null" or v == "":
            return None
        return str(v) if v else None
    
    @field_validator('reasoning', mode='before')
    @classmethod
    def validate_reasoning(cls, v) -> str:
        """Ensure reasoning is always a string."""
        if v is None or v == "null":
            return "No reasoning provided"
        return str(v) if v else "No reasoning provided"
    
    @property
    def todoist_priority(self) -> int:
        """Convert priority level to Todoist API value (P1=4, P2=3, P3=2, P4=1)."""
        priority_map = {
            'P1': 4,  # Urgent
            'P2': 3,  # High
            'P3': 2,  # Medium
            'P4': 1   # Normal
        }
        return priority_map.get(self.priority_level, 1)  # Default to P4 if invalid


class InboxOrganizations(BaseModel):
    """Collection of AI-determined organizations for all inbox tasks."""
    
    organizations: List[InboxOrganization]
    _task_map: Optional[dict] = None

    def _get_task_map(self) -> dict:
        """Build and cache a map from task_id to InboxOrganization for O(1) lookup."""
        if self._task_map is None:
            self._task_map = {org.task_id: org for org in self.organizations}
        return self._task_map

    def get_organization_for_task(self, task_id: str) -> Optional[InboxOrganization]:
        """Get organization for a specific task using O(1) lookup."""
        return self._get_task_map().get(task_id)
