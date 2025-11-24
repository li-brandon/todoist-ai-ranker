"""Main script to rank Todoist tasks using AI."""

import sys
import logging
import structlog
from typing import Optional

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


def print_today_organization_summary(
    all_tasks: list[TodoistTask],
    selected_tasks: list[TodoistTask],
    excluded_tasks: list[TodoistTask],
    rankings: PriorityRankings,
    limit: int,
    dry_run: bool = False
) -> None:
    """Print summary of Today view organization.
    
    Args:
        all_tasks: All tasks in Today view
        selected_tasks: Tasks selected for organization
        excluded_tasks: Tasks excluded from organization
        rankings: AI-determined rankings
        limit: Maximum number of tasks in organized view
        dry_run: Whether this is a dry run
    """
    print("\n" + "=" * 60)
    print("  Today View Organization" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60 + "\n")
    
    print(f"📊 Summary:")
    print(f"   Total tasks in Today view: {len(all_tasks)}")
    print(f"   Tasks selected for organization: {len(selected_tasks)} (limit: {limit})")
    print(f"   Tasks excluded: {len(excluded_tasks)}")
    print()
    
    # Calculate priority distribution of selected tasks
    priority_counts = {'P1': 0, 'P2': 0, 'P3': 0, 'P4': 0}
    for task in selected_tasks:
        ranking = rankings.get_ranking_for_task(task.id)
        if ranking:
            priority_counts[ranking.priority_level] += 1
    
    print("📈 Priority Distribution (Selected Tasks):")
    for level in ['P1', 'P2', 'P3', 'P4']:
        count = priority_counts[level]
        if count > 0:
            percentage = (count / len(selected_tasks)) * 100 if selected_tasks else 0
            print(f"   {level}: {count} task(s) ({percentage:.1f}%)")
    print()
    
    # Show selected tasks
    if selected_tasks:
        print("-" * 60)
        print("  Selected Tasks (Will be organized)")
        print("-" * 60 + "\n")
        
        # Sort selected tasks by priority and score
        selected_with_rankings = []
        for task in selected_tasks:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking:
                selected_with_rankings.append((task, ranking))
        
        selected_with_rankings.sort(
            key=lambda x: (x[1].todoist_priority, x[1].priority_score),
            reverse=True
        )
        
        for task, ranking in selected_with_rankings:
            priority_labels = {4: "P1", 3: "P2", 2: "P3", 1: "P4"}
            old_label = priority_labels.get(task.priority, "?")
            new_label = ranking.priority_level
            
            if task.priority != ranking.todoist_priority:
                print(f"✅ {task.content[:50]}...")
                print(f"   {old_label} → {new_label} (score: {ranking.priority_score})")
            else:
                print(f"✅ {task.content[:50]}...")
                print(f"   {new_label} (score: {ranking.priority_score}) - No change needed")
            print()
    
    # Show excluded tasks
    if excluded_tasks:
        print("-" * 60)
        print("  Excluded Tasks (Remain in Today view but not organized)")
        print("-" * 60 + "\n")
        
        for task in excluded_tasks[:10]:  # Show first 10 excluded tasks
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking:
                print(f"⏭️  {task.content[:50]}... ({ranking.priority_level}, score: {ranking.priority_score})")
            else:
                print(f"⏭️  {task.content[:50]}...")
        
        if len(excluded_tasks) > 10:
            print(f"   ... and {len(excluded_tasks) - 10} more task(s)")
        print()
    
    print("=" * 60 + "\n")


def organize_today_view(
    todoist_client: TodoistClient,
    ai_ranker: AIRanker,
    settings,
    limit: int,
    dry_run: bool = False,
    project_id: Optional[str] = None,
    label: Optional[str] = None,
    verbose: bool = False
) -> int:
    """Organize Today view with optimal task distribution.
    
    Args:
        todoist_client: Todoist API client
        ai_ranker: AI ranker instance
        settings: Application settings
        limit: Maximum number of tasks to include in organized view
        dry_run: If True, don't actually update tasks
        project_id: Optional project ID to filter tasks
        label: Optional label to filter tasks
        verbose: If True, show detailed output
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Fetch tasks filtered to Today view
        logger.info("fetching_today_tasks")
        print("📥 Fetching tasks from Today view...")
        
        # Build filter query - combine "today" with any additional filters
        filter_parts = ["today"]
        if project_id:
            # Note: project_id is handled separately, but we can add it to filter if needed
            pass
        if label:
            filter_parts.append(f"@{label}")
        
        filter_query = " & ".join(filter_parts) if len(filter_parts) > 1 else "today"
        
        tasks = todoist_client.get_tasks(
            project_id=project_id,
            label=label,
            filter_query=filter_query
        )
        
        if not tasks:
            print("✅ No tasks found in Today view!")
            return 0
        
        print(f"   Found {len(tasks)} task(s) in Today view\n")
        
        # Rank all Today tasks with AI
        logger.info("ranking_today_tasks")
        print("🤖 Ranking tasks with AI...")
        rankings, summary = ai_ranker.rank_tasks_with_summary(tasks)
        
        print(f"   Ranked {summary['ranked_tasks']} task(s)")
        print()
        
        # Select top N tasks using priority-first approach
        # Group tasks by priority level
        tasks_by_priority = {'P1': [], 'P2': [], 'P3': [], 'P4': []}
        task_map = {t.id: t for t in tasks}
        
        for ranking in rankings.rankings:
            if ranking.task_id in task_map:
                task = task_map[ranking.task_id]
                tasks_by_priority[ranking.priority_level].append((task, ranking))
        
        # Sort each priority group by score (descending)
        for priority_level in tasks_by_priority:
            tasks_by_priority[priority_level].sort(
                key=lambda x: x[1].priority_score,
                reverse=True
            )
        
        # Select tasks priority-first until limit is reached
        selected_tasks = []
        selected_task_ids = set()
        
        for priority_level in ['P1', 'P2', 'P3', 'P4']:
            if len(selected_tasks) >= limit:
                break
            
            for task, ranking in tasks_by_priority[priority_level]:
                if len(selected_tasks) >= limit:
                    break
                selected_tasks.append(task)
                selected_task_ids.add(task.id)
        
        # Determine excluded tasks
        excluded_tasks = [t for t in tasks if t.id not in selected_task_ids]
        
        # Display summary
        print_today_organization_summary(
            all_tasks=tasks,
            selected_tasks=selected_tasks,
            excluded_tasks=excluded_tasks,
            rankings=rankings,
            limit=limit,
            dry_run=dry_run
        )
        
        if dry_run:
            print("ℹ️  This was a dry run. No tasks were updated.")
            print("   Remove --dry-run to apply changes.\n")
            return 0
        
        # Confirm before updating
        print("Do you want to organize your Today view with these tasks? (y/N): ", end="")
        confirmation = input().strip().lower()
        
        if confirmation != 'y':
            print("\n❌ Organization cancelled.\n")
            return 0
        
        # Update priorities for selected tasks (if needed)
        logger.info("updating_selected_task_priorities")
        print("\n📤 Updating task priorities...")
        
        updates = []
        for task in selected_tasks:
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
        
        # Reorder tasks so selected ones appear first
        print("\n🔄 Reordering tasks...")
        
        # Build ordered list: selected tasks first (by priority and score), then excluded tasks
        ordered_tasks_list = []
        
        # Add selected tasks in priority order
        for priority_level in ['P1', 'P2', 'P3', 'P4']:
            for task, ranking in tasks_by_priority[priority_level]:
                if task.id in selected_task_ids:
                    ordered_tasks_list.append({
                        'task': task,
                        'priority': ranking.todoist_priority,
                        'score': ranking.priority_score
                    })
        
        # Sort selected tasks by priority and score
        ordered_tasks_list.sort(
            key=lambda x: (x['priority'], x['score']),
            reverse=True
        )
        
        # Add excluded tasks (keep their current order or sort by their rankings)
        excluded_with_rankings = []
        for task in excluded_tasks:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking:
                excluded_with_rankings.append({
                    'task': task,
                    'priority': ranking.todoist_priority,
                    'score': ranking.priority_score
                })
            else:
                excluded_with_rankings.append({
                    'task': task,
                    'priority': task.priority,
                    'score': 0
                })
        
        excluded_with_rankings.sort(
            key=lambda x: (x['priority'], x['score']),
            reverse=True
        )
        
        # Combine: selected first, then excluded
        final_ordered_tasks = (
            [item['task'] for item in ordered_tasks_list] +
            [item['task'] for item in excluded_with_rankings]
        )
        
        if todoist_client.reorder_tasks(final_ordered_tasks):
            print("   ✅ Tasks reordered successfully")
            print(f"   📋 Selected {len(selected_tasks)} task(s) appear first in Today view")
        else:
            print("   ❌ Failed to reorder tasks")
        
        print("\n✨ Done!\n")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user.\n")
        return 1
    except Exception as e:
        logger.error("organize_today_error", error=str(e), exc_info=True)
        print(f"\n❌ Error: {e}\n")
        return 1


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
    verbose: bool = False,
    organize_today: bool = False,
    today_limit: Optional[int] = None
) -> int:
    """Main application logic.
    
    Args:
        dry_run: If True, don't actually update tasks
        project_id: Optional project ID to filter tasks
        label: Optional label to filter tasks
        filter_query: Optional Todoist filter query
        verbose: If True, show detailed output
        organize_today: If True, organize Today view with optimal task distribution
        today_limit: Optional limit for Today view organization (overrides config)
        
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
        
        # Handle Today view organization
        if organize_today:
            limit = today_limit if today_limit is not None else settings.today_view_limit
            return organize_today_view(
                todoist_client=todoist_client,
                ai_ranker=ai_ranker,
                settings=settings,
                limit=limit,
                dry_run=dry_run,
                project_id=project_id,
                label=label,
                verbose=verbose
            )
        
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
    parser.add_argument(
        "--organize-today",
        action="store_true",
        help="Organize Today view with optimal task distribution"
    )
    parser.add_argument(
        "--today-limit",
        type=int,
        help="Maximum number of tasks to include in organized Today view (overrides config default)"
    )
    
    args = parser.parse_args()
    
    sys.exit(main(
        dry_run=args.dry_run,
        project_id=args.project,
        label=args.label,
        filter_query=args.filter,
        verbose=args.verbose,
        organize_today=args.organize_today,
        today_limit=args.today_limit
    ))
