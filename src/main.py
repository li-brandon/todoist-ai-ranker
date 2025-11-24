"""Main script to rank Todoist tasks using AI."""

import sys
import logging
import structlog
from typing import Optional
from pathlib import Path

from .config import get_settings
from .todoist_client import TodoistClient
from .ai_ranker import AIRanker
from .models import TodoistTask, PriorityRankings


# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()


def print_banner():
    """Print application banner."""
    print("\n" + "=" * 60)
    print("  Todoist AI Task Ranker")
    print("  Automatically prioritize your tasks using AI")
    print("=" * 60 + "\n")


def print_task_changes(
    tasks: list[TodoistTask],
    rankings: PriorityRankings,
    dry_run: bool = False
) -> None:
    """Print summary of priority changes.
    
    Args:
        tasks: Original tasks
        rankings: AI-determined rankings
        dry_run: Whether this is a dry run
    """
    print("\n" + "-" * 60)
    print("  Priority Changes" + (" (DRY RUN)" if dry_run else ""))
    print("-" * 60 + "\n")
    
    changes = 0
    no_changes = 0
    
    for task in tasks:
        ranking = rankings.get_ranking_for_task(task.id)
        if not ranking:
            continue
        
        old_priority = task.priority
        new_priority = ranking.todoist_priority
        
        if old_priority != new_priority:
            changes += 1
            # Convert priorities to labels
            priority_labels = {4: "P1", 3: "P2", 2: "P3", 1: "P4"}
            old_label = priority_labels[old_priority]
            new_label = ranking.priority_level
            
            print(f"📝 {task.content[:50]}...")
            print(f"   {old_label} → {new_label} (score: {ranking.priority_score})")
            print(f"   Reasoning: {ranking.reasoning}")
            print()
        else:
            no_changes += 1
    
    print("-" * 60)
    print(f"Tasks to update: {changes}")
    print(f"Tasks unchanged: {no_changes}")
    print("-" * 60 + "\n")


def main(
    dry_run: bool = False,
    project_id: Optional[str] = None,
    label: Optional[str] = None,
    filter_query: Optional[str] = None,
    verbose: bool = False
) -> int:
    """Main application logic.
    
    Args:
        dry_run: If True, don't actually update tasks
        project_id: Optional project ID to filter tasks
        label: Optional label to filter tasks
        filter_query: Optional Todoist filter query
        verbose: If True, show detailed output
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        print_banner()
        
        # Load configuration
        logger.info("loading_configuration")
        settings = get_settings()
        
        # Initialize clients
        logger.info("initializing_clients")
        todoist_client = TodoistClient(settings)
        ai_ranker = AIRanker(settings)
        
        # Fetch tasks
        logger.info("fetching_tasks")
        print("📥 Fetching tasks from Todoist...")
        tasks = todoist_client.get_tasks(
            project_id=project_id,
            label=label,
            filter_query=filter_query
        )
        
        if not tasks:
            print("✅ No tasks found to rank!")
            return 0
        
        print(f"   Found {len(tasks)} task(s)\n")
        
        # Rank tasks with AI
        logger.info("ranking_tasks")
        print("🤖 Ranking tasks with AI...")
        rankings, summary = ai_ranker.rank_tasks_with_summary(tasks)
        
        print(f"   Ranked {summary['ranked_tasks']} task(s)")
        print(f"   Priority distribution:")
        for level in ['P1', 'P2', 'P3', 'P4']:
            count = summary['priority_distribution'][level]
            if count > 0:
                print(f"     {level}: {count} task(s)")
        print()
        
        if verbose:
            print("-" * 60)
            print("  Ranked Tasks")
            print("-" * 60 + "\n")
            
            # Sort by priority and score for display
            display_list = []
            for ranking in rankings.rankings:
                task = next((t for t in tasks if t.id == ranking.task_id), None)
                if task:
                    display_list.append((task, ranking))
            
            display_list.sort(key=lambda x: (x[1].todoist_priority, x[1].priority_score), reverse=True)
            
            for task, ranking in display_list:
                print(f"• {task.content[:60]}")
                print(f"  {ranking.priority_level} (Score: {ranking.priority_score}) - {ranking.reasoning}")
                print()
            print("-" * 60 + "\n")
        
        # Show changes
        print_task_changes(tasks, rankings, dry_run)
        
        if dry_run:
            print("ℹ️  This was a dry run. No tasks were updated.")
            print("   Remove --dry-run to apply changes.\n")
            return 0
        
        # Confirm before updating
        print("Do you want to update these priorities in Todoist? (y/N): ", end="")
        confirmation = input().strip().lower()
        
        if confirmation != 'y':
            print("\n❌ Update cancelled.\n")
            return 0
        
        # Update tasks
        logger.info("updating_tasks")
        print("\n📤 Updating task priorities...")
        
        updates = []
        for task in tasks:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking and task.priority != ranking.todoist_priority:
                updates.append((task.id, ranking.todoist_priority))
        
        if updates:
            results = todoist_client.batch_update_priorities(updates)
            print(f"   ✅ Successfully updated: {results['successful']} task(s)")
            if results['failed'] > 0:
                print(f"   ❌ Failed to update: {results['failed']} task(s)")
        else:
            print("   ℹ️  No priority updates needed.")
            
        # Reorder tasks
        print("\n🔄 Reordering tasks...")
        
        # Sort tasks by new priority (P1 first -> P4 last) and then by score (descending)
        # We need to map tasks to their new rankings
        task_map = {t.id: t for t in tasks}
        ranked_tasks_list = []
        
        for ranking in rankings.rankings:
            if ranking.task_id in task_map:
                task = task_map[ranking.task_id]
                ranked_tasks_list.append({
                    'task': task,
                    'priority': ranking.todoist_priority,
                    'score': ranking.priority_score
                })
        
        # Sort: Priority (descending: 4=P1, 1=P4), then Score (descending)
        ranked_tasks_list.sort(key=lambda x: (x['priority'], x['score']), reverse=True)
        
        ordered_tasks = [item['task'] for item in ranked_tasks_list]
        
        if todoist_client.reorder_tasks(ordered_tasks):
            print("   ✅ Tasks reordered successfully")
        else:
            print("   ❌ Failed to reorder tasks")
        
        print("\n✨ Done!\n")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user.\n")
        return 1
    except Exception as e:
        logger.error("application_error", error=str(e), exc_info=True)
        print(f"\n❌ Error: {e}\n")
        return 1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Rank Todoist tasks using AI"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating tasks"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Filter by project ID"
    )
    parser.add_argument(
        "--label",
        type=str,
        help="Filter by label"
    )
    parser.add_argument(
        "--filter",
        type=str,
        help="Todoist filter query (e.g., 'today | overdue')"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output including all ranked tasks"
    )
    
    args = parser.parse_args()
    
    sys.exit(main(
        dry_run=args.dry_run,
        project_id=args.project,
        label=args.label,
        filter_query=args.filter,
        verbose=args.verbose
    ))
