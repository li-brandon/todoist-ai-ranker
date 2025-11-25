# Todoist AI Ranker

Automatically prioritize your Todoist tasks using AI. This Python script fetches your tasks, analyzes them with GPT, and updates priorities based on urgency, impact, effort, and due dates.

## Features

- 🤖 **AI-Powered Ranking**: Uses OpenAI GPT models to intelligently prioritize tasks
- 🎯 **Smart Analysis**: Considers urgency, due dates, impact, and effort
- 🔄 **Automatic Updates**: Directly updates task priorities in Todoist
- 📅 **Today View Organization**: Automatically populate your Today view with the most important tasks from your entire task list
- 🔒 **Safe**: Dry-run mode to preview changes before applying
- 🎨 **Flexible Filtering**: Filter by project, label, or custom queries
- ⚡ **Rate Limited**: Respects API rate limits with automatic throttling
- 📈 **Scalable**: Uses batching to handle hundreds of tasks without hitting AI token limits
- 🛡️ **Robust**: Built-in retry logic and error handling

## Prerequisites

- Python 3.9 or higher
- Todoist account and API token
- OpenAI API key

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/li-brandon/todoist-ai-ranker.git
   cd todoist-ai-ranker
   ```

2. **Create a virtual environment** (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your API keys:

   - **TODOIST_API_TOKEN**: Get from [Todoist Settings → Integrations](https://todoist.com/app/settings/integrations)
   - **OPENAI_API_KEY**: Get from [OpenAI API Keys](https://platform.openai.com/api-keys)

## Configuration

### Environment Variables

Edit your `.env` file:

```env
# Required
TODOIST_API_TOKEN=your_todoist_token_here
OPENAI_API_KEY=your_openai_key_here

# Optional
AI_MODEL=gpt-3.5-turbo              # or gpt-4, gpt-4-turbo-preview
AI_TEMPERATURE=0.7                   # 0.0-1.0, lower = more deterministic
LOG_LEVEL=INFO                       # DEBUG, INFO, WARNING, ERROR
TODAY_VIEW_LIMIT=5                   # Maximum tasks in organized Today view (default: 5)
```

### AI Model Selection

- **gpt-3.5-turbo** (default): Fast and cost-effective (~$0.001 per ranking)
- **gpt-4**: More sophisticated reasoning (~$0.03 per ranking)
- **gpt-4-turbo-preview**: Balance of cost and performance

## Usage

### Basic Usage

Rank all your tasks:

```bash
./run.sh
# OR manually
python -m src.main
```

### Dry Run (Preview Only)

See what changes would be made without updating:

```bash
./run.sh --dry-run
# OR manually
python -m src.main --dry-run
```

### List Projects

List all your Todoist projects with their IDs:

```bash
python -m src.main --list-projects
```

This will display all projects, including:

- Project names and IDs (needed for `--project` filter)
- Favorite projects (marked with ⭐)
- Archived projects
- Sub-projects (nested under parent projects)
- Project colors and view styles

### List Inbox Tasks

List all tasks currently in your Inbox:

```bash
python -m src.main --list-inbox
```

With detailed information:

```bash
python -m src.main --list-inbox --verbose
```

This will display:

- All tasks in the Inbox
- Task priorities (P1-P4) with visual markers
- Due dates (if set)
- Labels (if any)
- Task IDs and URLs
- Summary statistics

### Organize Inbox

Automatically organize all tasks in your Inbox using AI. This feature will:

1. **Assign tasks to the best project** based on task name and description
2. **Set appropriate due dates** based on urgency and importance
3. **Update priorities** using the Eisenhower Matrix

**Basic usage:**

```bash
python -m src.main --organize-inbox
```

**Dry run (preview only):**

```bash
python -m src.main --organize-inbox --dry-run
```

**With verbose output:**

```bash
python -m src.main --organize-inbox --verbose
```

The organize-inbox feature will:

1. Fetch all tasks from your Inbox
2. Fetch all available projects (excluding archived projects)
3. Use AI to analyze each task and suggest:
   - The best project to move the task to (or keep in Inbox)
   - An appropriate due date (or remove if not needed)
   - Priority level (P1-P4) based on urgency and importance
4. Display a summary of all suggested changes
5. Ask for confirmation before applying changes
6. Apply all changes (move tasks, set due dates, update priorities)

**Example output:**

```
============================================================
  Todoist AI Task Ranker
  Automatically prioritize your tasks using AI
============================================================

📥 Finding Inbox...
   Found Inbox (ID: 123456789)

📋 Fetching tasks from Inbox...
   Found 8 task(s) in Inbox

📁 Fetching available projects...
   Found 12 available project(s)

🤖 Analyzing tasks with AI...
   This may take a moment...
   Organized 8 task(s)

============================================================
  Inbox Organization
============================================================

📊 Summary:
   Total tasks: 8
   Tasks to move: 5
   Tasks staying in Inbox: 3
   Due dates to set: 6
   Due dates to remove: 1
   Priority updates: 7

------------------------------------------------------------
  📤 Tasks to Move to Projects
------------------------------------------------------------

📝 Finish quarterly report...
   → Move to: Work
   Priority: P1 (score: 95)
   Due date: tomorrow
   Reasoning: Priority: Urgent and important work task...

Do you want to organize your Inbox with these suggestions? (y/N):
```

This feature helps you quickly process your Inbox by automatically categorizing tasks and setting them up for success.

### Filter Tasks

Rank tasks in a specific project:

```bash
python -m src.main --project PROJECT_ID
```

Use `--list-projects` first to find the project ID you need.

Rank tasks with a specific label:

```bash
python -m src.main --label "work"
```

Use Todoist filter syntax:

```bash
python -m src.main --filter "today | overdue"
python -m src.main --filter "p1 & @work"
```

### Combined Options

```bash
python -m src.main --dry-run --filter "today" --label "important" --verbose
```

### Verbose Output

To see the ranking details for every task:

```bash
python -m src.main --verbose
```

### Organize Today View

Automatically populate your Today view with the most important tasks from your entire Todoist. The feature analyzes ALL your tasks using AI and selects the top N most important ones to focus on today.

**Basic usage:**

```bash
python -m src.main --organize-today
```

**With custom limit:**

```bash
python -m src.main --organize-today --today-limit 10
```

**Dry run (preview only):**

```bash
python -m src.main --organize-today --dry-run
```

**With additional filters:**

```bash
python -m src.main --organize-today --label "work" --today-limit 8
```

The organize-today feature will:

1. Fetch ALL tasks from your Todoist (not just Today view)
2. Rank all tasks using AI based on importance and urgency
3. Select the top N tasks (default: 5) using priority-first selection
4. **Add** selected tasks to Today view (sets due date to today)
5. **Remove** tasks currently in Today that didn't make the cut (reschedules to tomorrow)
6. Update priorities and reorder tasks in your Today view

This ensures your Today view always contains only the most important tasks you should focus on.

## How It Works

1. **Fetch Tasks**: Retrieves all active tasks from Todoist (with optional filtering)
2. **AI Analysis**: Sends task details to OpenAI for intelligent prioritization
   - **Batching**: Tasks are processed in batches of 20 to handle large lists efficiently and avoid token limits.
3. **Priority Mapping**: Converts AI scores (0-100) to Todoist priorities:
   - **P1 (Urgent)**: Critical, time-sensitive tasks
   - **P2 (High)**: Important tasks with near-term deadlines
   - **P3 (Medium)**: Standard priority tasks
   - **P4 (Normal)**: Lower priority or background tasks
4. **Update**: Applies new priorities to Todoist (with your confirmation)

## Priority System

Todoist uses an inverse priority system:

- P1 = Priority 4 (Urgent) - Red flag
- P2 = Priority 3 (High) - Orange flag
- P3 = Priority 2 (Medium) - Yellow flag
- P4 = Priority 1 (Normal) - No flag

The AI considers:

- ⏰ **Urgency**: Time-sensitive nature of the task
- 📅 **Due Date**: Proximity to deadline
- 💪 **Impact**: Importance and value of completion
- ⚡ **Effort**: Required work relative to value

## Example Output

```
============================================================
  Todoist AI Task Ranker
  Automatically prioritize your tasks using AI
============================================================

📥 Fetching tasks from Todoist...
   Found 12 task(s)

🤖 Ranking tasks with AI...
   Ranked 12 task(s)
   Priority distribution:
     P1: 3 task(s)
     P2: 4 task(s)
     P3: 5 task(s)

------------------------------------------------------------
  Priority Changes
------------------------------------------------------------

📝 Finish quarterly report...
   P3 → P1 (score: 95)
   Reasoning: Due tomorrow, high impact on team goals

📝 Review pull requests...
   P4 → P2 (score: 75)
   Reasoning: Blocking team members, moderate effort

------------------------------------------------------------
Tasks to update: 5
Tasks unchanged: 7
------------------------------------------------------------

Do you want to update these priorities in Todoist? (y/N): y

📤 Updating task priorities...
   ✅ Successfully updated: 5 task(s)

✨ Done!
```

### Example: Organize Today View

```
============================================================
  Todoist AI Task Ranker
  Automatically prioritize your tasks using AI
============================================================

📥 Fetching all tasks from Todoist...
   Found 47 total task(s)

📅 Fetching current Today view...
   Found 8 task(s) currently in Today

🤖 Ranking all tasks with AI...
   Ranked 47 task(s)

============================================================
  Today View Organization
============================================================

📊 Summary:
   Total tasks analyzed: 47
   Current tasks in Today: 8
   New Today view size: 5 (limit: 5)
   Tasks to add to Today: 3
   Tasks to remove from Today: 6

📈 Priority Distribution (New Today View):
   P1: 2 task(s) (40.0%)
   P2: 2 task(s) (40.0%)
   P3: 1 task(s) (20.0%)

------------------------------------------------------------
  📥 Tasks to ADD to Today
------------------------------------------------------------

➕ Finish quarterly report... (due: next week)
   P1 (score: 95)

➕ Prepare client presentation... (no due date)
   P1 (score: 92)

➕ Review contract terms... (due: Friday)
   P2 (score: 85)

------------------------------------------------------------
  ✅ Tasks STAYING in Today
------------------------------------------------------------

✅ Submit expense report...
   P2 (score: 80)

✅ Team standup meeting...
   P3 (score: 70)

------------------------------------------------------------
  📤 Tasks to REMOVE from Today (→ tomorrow)
------------------------------------------------------------

➖ Update documentation... (P3, score: 45)
➖ Organize desk... (P4, score: 20)
   ... and 4 more task(s)

============================================================

Do you want to organize your Today view with these tasks? (y/N): y

📥 Adding tasks to Today...
   ✅ Added to Today: 3 task(s)

📤 Removing tasks from Today (→ tomorrow)...
   ✅ Moved to tomorrow: 6 task(s)

🎯 Updating task priorities...
   ✅ Updated priorities: 2 task(s)

🔄 Reordering Today view...
   ✅ Tasks reordered successfully

✨ Done! Your Today view now has 5 optimized task(s).
```

## Project Structure

```
todoist-ai-ranker/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── config.py            # Configuration and settings
│   ├── models.py            # Pydantic data models
│   ├── todoist_client.py    # Todoist API client
│   ├── ai_ranker.py         # OpenAI integration
│   └── main.py              # Main application logic
├── .env                     # Environment variables (not in git)
├── .env.example             # Example environment file
├── .gitignore               # Git ignore rules
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Troubleshooting

### "TODOIST_API_TOKEN is not set"

Make sure you've created a `.env` file and added your Todoist API token.

### "OPENAI_API_KEY is not set"

Add your OpenAI API key to the `.env` file.

### Rate Limit Errors

The script includes automatic rate limiting, but if you have many tasks, it may take a few minutes to process them all.

### API Timeout

If you see timeout errors, check your internet connection. The script will automatically retry failed requests.

### JSON Parse Errors

Occasionally the AI might return invalid JSON. The script will retry automatically. If it persists, try using `gpt-4` instead of `gpt-3.5-turbo`.

## Cost Estimates

Costs depend on the number of tasks and AI model:

- **GPT-3.5-Turbo**: ~$0.001 per 20 tasks
- **GPT-4**: ~$0.03 per 20 tasks
- **GPT-4-Turbo**: ~$0.01 per 20 tasks

Running daily on 50 tasks costs approximately:

- GPT-3.5-Turbo: ~$0.10/month
- GPT-4: ~$2.70/month

## Automation

### Daily Cron Job

Add to your crontab to run daily at 9 AM:

```bash
0 9 * * * cd /path/to/todoist-ai-ranker && /path/to/venv/bin/python -m src.main >> logs/cron.log 2>&1
```

### Filter for Fresh Tasks Only

Rank only today's and overdue tasks:

```bash
0 9 * * * cd /path/to/todoist-ai-ranker && /path/to/venv/bin/python -m src.main --filter "today | overdue" >> logs/cron.log 2>&1
```

### Organize Today View Daily

Automatically organize your Today view each morning:

```bash
0 9 * * * cd /path/to/todoist-ai-ranker && /path/to/venv/bin/python -m src.main --organize-today >> logs/cron.log 2>&1
```

With a custom limit:

```bash
0 9 * * * cd /path/to/todoist-ai-ranker && /path/to/venv/bin/python -m src.main --organize-today --today-limit 7 >> logs/cron.log 2>&1
```

## Contributing

Contributions are welcome! Feel free to:

- Report bugs
- Suggest new features
- Submit pull requests

## License

MIT License - feel free to use and modify as needed.

## Acknowledgments

- Built with [Todoist API](https://developer.todoist.com/)
- Powered by [OpenAI](https://openai.com/)
- Uses [Pydantic](https://docs.pydantic.dev/) for data validation

## Support

For issues or questions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review [Todoist API docs](https://developer.todoist.com/rest/v2/)
3. Check [OpenAI API docs](https://platform.openai.com/docs/)
4. Open an issue on GitHub

---

**Happy prioritizing! 🎯✨**
