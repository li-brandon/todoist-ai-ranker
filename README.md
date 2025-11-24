# Todoist AI Ranker

Automatically prioritize your Todoist tasks using AI. This Python script fetches your tasks, analyzes them with GPT, and updates priorities based on urgency, impact, effort, and due dates.

## Features

- 🤖 **AI-Powered Ranking**: Uses OpenAI GPT models to intelligently prioritize tasks
- 🎯 **Smart Analysis**: Considers urgency, due dates, impact, and effort
- 🔄 **Automatic Updates**: Directly updates task priorities in Todoist
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

### Filter Tasks

Rank tasks in a specific project:

```bash
python -m src.main --project PROJECT_ID
```

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

### Verbose Output

To see the ranking details for every task:

```bash
python -m src.main --verbose
```

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
