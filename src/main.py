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


def print_missing_tasks(
    tasks: list[TodoistTask],
    rankings: PriorityRankings,
    show_all: bool = False
) -> None:
    """Print tasks that didn't receive rankings.
    
    Args:
        tasks: All tasks that were sent for ranking
        rankings: Rankings returned from AI
        show_all: If True, show all missing tasks. If False, show first 20.
    """
    ranked_ids = {r.task_id for r in rankings.rankings}
    task_ids = {t.id for t in tasks}
    missing_task_ids = task_ids - ranked_ids
    
    if missing_task_ids:
        print("\n" + "!" * 60)
        print("  ⚠️  Ranking Mismatch Detected")
        print("!" * 60 + "\n")
        
        print(f"❌ {len(missing_task_ids)} task(s) did not receive rankings")
        print(f"   ({len(ranked_ids)} ranked / {len(task_ids)} total)\n")
        
        # Sort missing tasks by ID for consistent display
        missing_tasks = sorted(
            [t for t in tasks if t.id in missing_task_ids],
            key=lambda t: t.id
        )
        
        # Show tasks (limit to first 20 unless show_all is True)
        display_count = len(missing_tasks) if show_all else min(20, len(missing_tasks))
        
        print("Missing task details:\n")
        for task in missing_tasks[:display_count]:
            due_info = f" (due: {task.due.string or task.due.date})" if task.due else " (no due date)"
            labels_info = f" [Labels: {', '.join(task.labels)}]" if task.labels else ""
            priority_info = f" [Priority: {task.priority_label}]"
            print(f"   • ID: {task.id}")
            print(f"     Content: {task.content[:70]}")
            print(f"     {due_info}{labels_info}{priority_info}")
            print()
        
        if len(missing_tasks) > display_count:
            print(f"   ... and {len(missing_tasks) - display_count} more task(s)\n")
        
        print("   Possible reasons:")
        print("   - Batch processing failed (JSON parse error, API timeout, etc.)")
        print("   - AI response validation failed")
        print("   - Network/API errors during batch processing")
        print()
        print("   Recommendation:")
        print("   - Run the command again (may succeed on retry)")
        print("   - If persistent, try using gpt-4 model for better reliability")
        print("   - Check logs for specific batch error messages")
        print()
        
        # Show task IDs in a format that can be easily copied
        print("   Missing Task IDs:")
        print("   " + ", ".join([f"'{tid}'" for tid in sorted(missing_task_ids)]))
        print()
        print("!" * 60 + "\n")


def print_today_organization_summary(
    all_tasks: list[TodoistTask],
    selected_tasks: list[TodoistTask],
    tasks_to_add: list[TodoistTask],
    tasks_to_remove: list[TodoistTask],
    current_today_tasks: list[TodoistTask],
    rankings: PriorityRankings,
    limit: int,
    dry_run: bool = False
) -> None:
    """Print summary of Today view organization.
    
    Args:
        all_tasks: All tasks in Todoist
        selected_tasks: Tasks selected for Today view
        tasks_to_add: Tasks being added to Today view
        tasks_to_remove: Tasks being removed from Today view
        current_today_tasks: Tasks currently in Today view
        rankings: AI-determined rankings
        limit: Maximum number of tasks in organized view
        dry_run: Whether this is a dry run
    """
    print("\n" + "=" * 60)
    print("  Today View Organization" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60 + "\n")
    
    # Count recurring tasks
    recurring_to_add = [t for t in tasks_to_add if t.is_recurring]
    recurring_to_remove = [t for t in tasks_to_remove if t.is_recurring]
    non_recurring_to_add = [t for t in tasks_to_add if not t.is_recurring]
    non_recurring_to_remove = [t for t in tasks_to_remove if not t.is_recurring]
    
    print(f"📊 Summary:")
    print(f"   Total tasks analyzed: {len(all_tasks)}")
    print(f"   Current tasks in Today: {len(current_today_tasks)}")
    print(f"   New Today view size: {len(selected_tasks)} (limit: {limit})")
    print(f"   Tasks to add to Today: {len(non_recurring_to_add)} (non-recurring)")
    if recurring_to_add:
        print(f"   Recurring tasks to add: {len(recurring_to_add)} (will keep their schedule)")
    print(f"   Tasks to remove from Today: {len(non_recurring_to_remove)} (non-recurring)")
    if recurring_to_remove:
        print(f"   Recurring tasks to remove: {len(recurring_to_remove)} (will keep their schedule)")
    print()
    
    # Calculate priority distribution of selected tasks
    priority_counts = {'P1': 0, 'P2': 0, 'P3': 0, 'P4': 0}
    for task in selected_tasks:
        ranking = rankings.get_ranking_for_task(task.id)
        if ranking:
            priority_counts[ranking.priority_level] += 1
    
    if selected_tasks:
        print("📈 Priority Distribution (New Today View):")
        for level in ['P1', 'P2', 'P3', 'P4']:
            count = priority_counts[level]
            if count > 0:
                percentage = (count / len(selected_tasks)) * 100
                print(f"   {level}: {count} task(s) ({percentage:.1f}%)")
        print()
    
    # Show tasks being added to Today
    if tasks_to_add:
        print("-" * 60)
        print("  📥 Tasks to ADD to Today")
        print("-" * 60 + "\n")
        
        tasks_with_rankings = []
        for task in tasks_to_add:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking:
                tasks_with_rankings.append((task, ranking))
        
        tasks_with_rankings.sort(
            key=lambda x: (x[1].todoist_priority, x[1].priority_score),
            reverse=True
        )
        
        for task, ranking in tasks_with_rankings:
            due_info = f" (due: {task.due.string or task.due.date})" if task.due else " (no due date)"
            recurring_note = " [RECURRING - will keep schedule]" if task.is_recurring else ""
            print(f"➕ {task.content[:45]}...{due_info}{recurring_note}")
            print(f"   {ranking.priority_level} (score: {ranking.priority_score})")
            print()
    
    # Show tasks staying in Today
    staying_in_today = [t for t in selected_tasks if t.id not in {task.id for task in tasks_to_add}]
    if staying_in_today:
        print("-" * 60)
        print("  ✅ Tasks STAYING in Today")
        print("-" * 60 + "\n")
        
        tasks_with_rankings = []
        for task in staying_in_today:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking:
                tasks_with_rankings.append((task, ranking))
        
        tasks_with_rankings.sort(
            key=lambda x: (x[1].todoist_priority, x[1].priority_score),
            reverse=True
        )
        
        for task, ranking in tasks_with_rankings:
            print(f"✅ {task.content[:50]}...")
            print(f"   {ranking.priority_level} (score: {ranking.priority_score})")
            print()
    
    # Show tasks being removed from Today
    if tasks_to_remove:
        print("-" * 60)
        print("  📤 Tasks to REMOVE from Today (→ tomorrow)")
        print("-" * 60 + "\n")
        
        for task in tasks_to_remove[:10]:
            ranking = rankings.get_ranking_for_task(task.id)
            recurring_note = " [RECURRING - will keep schedule]" if task.is_recurring else ""
            if ranking:
                print(f"➖ {task.content[:50]}... ({ranking.priority_level}, score: {ranking.priority_score}){recurring_note}")
            else:
                print(f"➖ {task.content[:50]}...{recurring_note}")
        
        if len(tasks_to_remove) > 10:
            print(f"   ... and {len(tasks_to_remove) - 10} more task(s)")
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
    """Organize Today view by selecting the most important tasks from all tasks.
    
    This function:
    1. Fetches ALL tasks from Todoist
    2. Ranks them using AI
    3. Selects the top N most important tasks
    4. Schedules selected tasks for Today
    5. Removes tasks currently in Today that didn't make the cut (reschedules to tomorrow)
    
    Args:
        todoist_client: Todoist API client
        ai_ranker: AI ranker instance
        settings: Application settings
        limit: Maximum number of tasks to include in Today view
        dry_run: If True, don't actually update tasks
        project_id: Optional project ID to filter tasks
        label: Optional label to filter tasks
        verbose: If True, show detailed output
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Step 1: Fetch ALL tasks from Todoist
        logger.info("fetching_all_tasks")
        print("📥 Fetching all tasks from Todoist...")
        
        all_tasks = todoist_client.get_tasks(
            project_id=project_id,
            label=label,
            filter_query=None  # No filter - get ALL tasks
        )
        
        if not all_tasks:
            print("✅ No tasks found!")
            return 0
        
        print(f"   Found {len(all_tasks)} total task(s)\n")
        
        # Step 2: Fetch current Today view tasks (to know what to remove)
        logger.info("fetching_current_today_tasks")
        print("📅 Fetching current Today view...")
        
        current_today_tasks = todoist_client.get_tasks(
            filter_query="today",
            project_id=project_id,
            label=label
        )
        current_today_ids = {t.id for t in current_today_tasks}
        
        print(f"   Found {len(current_today_tasks)} task(s) currently in Today\n")
        
        # Step 3: Rank ALL tasks with AI
        logger.info("ranking_all_tasks")
        print("🤖 Ranking all tasks with AI...")
        rankings, summary = ai_ranker.rank_tasks_with_summary(all_tasks)
        
        print(f"   Ranked {summary['ranked_tasks']} task(s)")
        
        # Check for and display missing tasks
        if summary['ranked_tasks'] < summary['total_tasks']:
            print_missing_tasks(all_tasks, rankings)
        
        print()
        
        # Step 4: Select top N tasks using priority-first approach
        # Group tasks by priority level
        tasks_by_priority = {'P1': [], 'P2': [], 'P3': [], 'P4': []}
        task_map = {t.id: t for t in all_tasks}
        
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
        
        # Step 5: Determine tasks to add and remove
        # Tasks to add: selected tasks that are NOT currently in Today
        tasks_to_add = [t for t in selected_tasks if t.id not in current_today_ids]
        
        # Tasks to remove: tasks currently in Today that are NOT selected
        tasks_to_remove = [t for t in current_today_tasks if t.id not in selected_task_ids]
        
        # Display summary
        print_today_organization_summary(
            all_tasks=all_tasks,
            selected_tasks=selected_tasks,
            tasks_to_add=tasks_to_add,
            tasks_to_remove=tasks_to_remove,
            current_today_tasks=current_today_tasks,
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
        
        # Step 6: Update due dates - Add tasks to Today
        # Skip recurring tasks as they manage their own schedule
        if tasks_to_add:
            logger.info("adding_tasks_to_today")
            print("\n📥 Adding tasks to Today...")
            
            # Filter out recurring tasks
            non_recurring_to_add = [task for task in tasks_to_add if not task.is_recurring]
            recurring_to_add = [task for task in tasks_to_add if task.is_recurring]
            
            if recurring_to_add:
                print(f"   ⏭️  Skipped {len(recurring_to_add)} recurring task(s) (recurring tasks keep their schedule)")
                for task in recurring_to_add:
                    print(f"      • {task.content[:50]}...")
            
            if non_recurring_to_add:
                add_updates = [(task.id, "today") for task in non_recurring_to_add]
                results = todoist_client.batch_update_due_dates(add_updates)
                print(f"   ✅ Added to Today: {results['successful']} task(s)")
                if results['failed'] > 0:
                    print(f"   ❌ Failed to add: {results['failed']} task(s)")
            elif recurring_to_add:
                print("   ℹ️  No non-recurring tasks to add.")
        
        # Step 7: Update due dates - Remove tasks from Today (reschedule to tomorrow)
        # Skip recurring tasks as they manage their own schedule
        if tasks_to_remove:
            logger.info("removing_tasks_from_today")
            print("\n📤 Removing tasks from Today (→ tomorrow)...")
            
            # Filter out recurring tasks
            non_recurring_to_remove = [task for task in tasks_to_remove if not task.is_recurring]
            recurring_to_remove = [task for task in tasks_to_remove if task.is_recurring]
            
            if recurring_to_remove:
                print(f"   ⏭️  Skipped {len(recurring_to_remove)} recurring task(s) (recurring tasks keep their schedule)")
                for task in recurring_to_remove:
                    print(f"      • {task.content[:50]}...")
            
            if non_recurring_to_remove:
                remove_updates = [(task.id, "tomorrow") for task in non_recurring_to_remove]
                results = todoist_client.batch_update_due_dates(remove_updates)
                print(f"   ✅ Moved to tomorrow: {results['successful']} task(s)")
                if results['failed'] > 0:
                    print(f"   ❌ Failed to move: {results['failed']} task(s)")
            elif recurring_to_remove:
                print("   ℹ️  No non-recurring tasks to move.")
        
        # Step 8: Update priorities for selected tasks (if needed)
        logger.info("updating_selected_task_priorities")
        print("\n🎯 Updating task priorities...")
        
        priority_updates = []
        for task in selected_tasks:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking and task.priority != ranking.todoist_priority:
                priority_updates.append((task.id, ranking.todoist_priority))
        
        if priority_updates:
            results = todoist_client.batch_update_priorities(priority_updates)
            print(f"   ✅ Updated priorities: {results['successful']} task(s)")
            if results['failed'] > 0:
                print(f"   ❌ Failed to update: {results['failed']} task(s)")
        else:
            print("   ℹ️  No priority updates needed.")
        
        # Step 9: Reorder tasks in Today view
        print("\n🔄 Reordering Today view...")
        
        # Build ordered list by priority and score
        ordered_tasks_list = []
        for task in selected_tasks:
            ranking = rankings.get_ranking_for_task(task.id)
            if ranking:
                ordered_tasks_list.append({
                    'task': task,
                    'priority': ranking.todoist_priority,
                    'score': ranking.priority_score
                })
        
        # Sort by priority (P1 first) and score (descending)
        ordered_tasks_list.sort(
            key=lambda x: (x['priority'], x['score']),
            reverse=True
        )
        
        final_ordered_tasks = [item['task'] for item in ordered_tasks_list]
        
        if final_ordered_tasks and todoist_client.reorder_tasks(final_ordered_tasks):
            print("   ✅ Tasks reordered successfully")
        elif not final_ordered_tasks:
            print("   ℹ️  No tasks to reorder.")
        else:
            print("   ❌ Failed to reorder tasks")
        
        print(f"\n✨ Done! Your Today view now has {len(selected_tasks)} optimized task(s).\n")
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
        
        # Check for and display missing tasks
        if summary['ranked_tasks'] < summary['total_tasks']:
            print_missing_tasks(tasks, rankings)
        
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
