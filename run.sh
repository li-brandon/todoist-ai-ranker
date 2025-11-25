#!/bin/bash
# Activate virtual environment and run the application
# 
# Usage examples:
#   ./run.sh                          # Rank all tasks
#   ./run.sh --dry-run                # Preview changes
#   ./run.sh --organize-today         # Organize Today view (selects top 5 tasks from all tasks)
#   ./run.sh --organize-today --dry-run  # Preview Today organization
#   ./run.sh --organize-today --today-limit 10  # Custom limit for Today view
#   ./run.sh --filter "today"         # Filter tasks
#   ./run.sh --organize-today --label "work"  # Organize Today view with label filter

source venv/bin/activate
python3 -m src.main "$@"
