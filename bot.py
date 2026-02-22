import os
import logging
import random
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from aiohttp import web
import db
from ai_engine import generate_task, evaluate_response, generate_chat_response

# Load environment variables (.env file)
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable.")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    chat_id = update.message.chat_id
    username = user.first_name or user.username
    
    is_new = db.register_user(chat_id, username)
    user_state = db.get_user(chat_id)
    
    welcome_msg = (
        f"Salut {username}!\n\n"
        "I'm your French learning companion. I'll send you a short (5–10 min) task every morning, "
        "and you can always chat with me anytime—ask questions, practice, or just say hi.\n\n"
        "Reply in French when you do the tasks and I'll give you feedback. No pressure though; "
        "we'll go at your pace.\n\n"
        f"You're starting at Level {user_state['difficulty_level']}. On y va!"
    )
    
    await update.message.reply_text(welcome_msg)
    
    if is_new:
        # Trigger the first task immediately for new users
        await send_daily_task_to_user(context.bot, chat_id)


async def send_daily_task_to_user(bot, chat_id: int):
    """Generate and send a daily task to a specific user."""
    user = db.get_user(chat_id)
    if not user:
        return

    try:
        logging.info(f"Generating task for {chat_id} (Level {user['difficulty_level']})")
        task = await generate_task(
            difficulty_level=user['difficulty_level'],
            state=user['state'],
            focus=user['learning_focus']
        )
        
        # Log the assignment in DB
        db.log_daily_task(chat_id, task.task_text)
        
        msg = (
            "Bonjour! Voici une petite pratique pour aujourd'hui:\n\n"
            f"{task.task_text}\n\n"
            f"Temps estime: {task.estimated_minutes} min\n"
            f"Niveau actuel: {user['difficulty_level']} | Streak: {user['streak']}\n"
            "Reponds quand tu veux, et je t'aiderai etape par etape."
        )
        
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Failed to send task to {chat_id}: {e}")

async def send_daily_tasks_job(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to send daily tasks to all users."""
    users = db.get_all_users()
    for chat_id in users:
        await send_daily_task_to_user(context.bot, chat_id)

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all conversational text as an AI companion."""
    chat_id = update.effective_user.id
    user_response = update.message.text
    
    user = db.get_user(chat_id)
    if not user:
        user_info = update.effective_user
        username = user_info.first_name or user_info.username or "friend"
        db.register_user(chat_id, username)
        user = db.get_user(chat_id)
        
    today = datetime.now().date().isoformat()
    with db.get_db() as database:
        recent_log = database.execute(
            'SELECT * FROM daily_logs WHERE chat_id = ? AND date = ? ORDER BY id DESC LIMIT 1',
            (chat_id, today)
        ).fetchone()

    pending_task = None
    if recent_log and not recent_log['user_response']:
        pending_task = recent_log['task_assigned']
    due_vocab = db.get_due_vocabulary(chat_id)

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    db.save_chat_message(chat_id, "user", user_response)
    history = db.get_recent_chat_history(chat_id, limit=12)

    async def execute_tool(tool_name: str, tool_args: dict):
        nonlocal user, pending_task

        if tool_name == "suggest_task":
            focus = tool_args.get("focus") or user.get("learning_focus", "general")
            task = await generate_task(
                difficulty_level=user["difficulty_level"],
                state=user["state"],
                focus=focus,
            )
            db.log_daily_task(chat_id, task.task_text)
            pending_task = task.task_text
            return {
                "task_text": task.task_text,
                "target_grammar": task.target_grammar,
                "estimated_minutes": task.estimated_minutes,
            }

        if tool_name == "save_vocabulary":
            french = (tool_args.get("french") or "").strip()
            english = (tool_args.get("english") or "").strip()
            if not french or not english:
                return {"ok": False, "error": "Both french and english are required."}
            db.save_vocabulary(chat_id, french, english)
            return {"ok": True, "saved": {"french": french, "english": english}}

        if tool_name == "get_user_status":
            refreshed = db.get_user(chat_id)
            return {
                "difficulty_level": refreshed["difficulty_level"],
                "streak": refreshed["streak"],
                "state": refreshed["state"],
                "learning_focus": refreshed["learning_focus"],
            }

        if tool_name == "get_due_vocabulary":
            words = db.get_due_vocabulary(chat_id)
            return {"count": len(words), "items": words[:8]}

        if tool_name == "check_vocab_translation":
            vocab_id = tool_args.get("vocab_id")
            user_french = (tool_args.get("user_french") or "").strip().lower()
            vocab_row = db.get_vocabulary_by_id(vocab_id) if vocab_id is not None else None
            if not vocab_row or vocab_row["chat_id"] != chat_id:
                return {"ok": False, "error": "Vocabulary item not found for this user."}

            expected = vocab_row["french_word"].strip().lower()
            correct = user_french == expected
            db.update_vocabulary_review(vocab_id, correct)
            return {
                "ok": True,
                "correct": correct,
                "correct_answer": vocab_row["french_word"],
                "english_prompt": vocab_row["english_translation"],
            }

        if tool_name == "evaluate_french":
            response_text = (tool_args.get("user_response") or "").strip()
            task_context = (tool_args.get("task_context") or "").strip() or pending_task or "General French practice."
            if not response_text:
                return {"ok": False, "error": "user_response is required."}

            eval_result = await evaluate_response(task_context, response_text)
            feedback_text = (
                f"Grammar: {eval_result.grammar_analysis}\n"
                f"Vocabulary: {eval_result.vocabulary_suggestions}\n"
                f"Corrected: {eval_result.corrected_french}"
            )

            if pending_task:
                db.update_daily_log_response(
                    chat_id=chat_id,
                    response=response_text,
                    feedback=feedback_text,
                    score=eval_result.score,
                    decision=eval_result.adaptation_decision,
                )
                pending_task = None

            refreshed = db.get_user(chat_id)
            new_streak = refreshed["streak"] + 1
            new_level = refreshed["difficulty_level"]
            new_state = refreshed["state"]

            if eval_result.adaptation_decision == "level_up":
                new_state = "green"
                if eval_result.score > 90:
                    new_level = min(10, new_level + 1)
            elif eval_result.adaptation_decision == "maintain":
                new_state = "yellow"
            elif eval_result.adaptation_decision == "simplify":
                new_state = "red"

            db.update_user_state(chat_id, new_streak, new_level, new_state)
            user = db.get_user(chat_id)

            return {
                "ok": True,
                "score": eval_result.score,
                "grammar_analysis": eval_result.grammar_analysis,
                "vocabulary_suggestions": eval_result.vocabulary_suggestions,
                "corrected_french": eval_result.corrected_french,
                "adaptation_decision": eval_result.adaptation_decision,
                "new_level": new_level,
                "new_streak": new_streak,
                "new_state": new_state,
            }

        return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    bot_reply = await generate_chat_response(
        history,
        companion_context={
            "user": user,
            "pending_task": pending_task,
            "due_vocab": due_vocab[:8],
        },
        tool_executor=execute_tool,
    )

    db.save_chat_message(chat_id, "assistant", bot_reply)
    await update.message.reply_text(bot_reply)

async def health_check(request):
    """Simple health check endpoint to satisfy Render's port binding requirement."""
    return web.Response(text="Bot is running!")

async def start_web_server():
    """Start dummy web server for Render."""
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Dummy web server started on port {port}")

async def send_nightly_vocab_job(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to test vocabulary spaced repetition at 8 PM."""
    users = db.get_all_users()
    for chat_id in users:
        words = db.get_due_vocabulary(chat_id)
        if not words: continue
        
        try:
            message = "Petit rappel vocabulaire pour ce soir:\n\nTraduis ces mots quand tu veux:\n"
            for w in words:
                message += f"- {w['english_translation']}\n"
            message += "\nEnvoie-moi tes reponses et je corrigerai avec toi."
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            logger.error(f"Failed to send vocab review to {chat_id}: {e}")


async def send_learning_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Friendly reminder to learn or practice—companion style."""
    reminders = [
        "Hey! Got a minute? Want to learn a new word or two? Just ask me anything.",
        "Petit rappel: tu veux apprendre un nouveau mot? Dis-moi et on fait ensemble.",
        "Quick nudge: ready for a tiny French moment? Ask me for a word, a phrase, or a practice tip.",
    ]
    message = random.choice(reminders)
    users = db.get_all_users()
    for chat_id in users:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            logger.error(f"Failed to send reminder to {chat_id}: {e}")


def main() -> None:
    """Start the bot and the web server."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))

    # on non command i.e message - handle the response
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response))

    # Add scheduling (all times UTC)
    job_queue = application.job_queue
    job_queue.run_daily(send_daily_tasks_job, time=time(hour=9, minute=0))
    job_queue.run_daily(send_nightly_vocab_job, time=time(hour=20, minute=0))
    # Gentle learning reminders mid-day and afternoon
    job_queue.run_daily(send_learning_reminder_job, time=time(hour=14, minute=0))
    job_queue.run_daily(send_learning_reminder_job, time=time(hour=17, minute=30))

    # Run the bot until the user presses Ctrl-C
    logger.info("Starting bot polling...")
    
    # We must run both the web server and the bot polling
    import asyncio
    
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    db.init_db()  # Ensure DB is created
    main()
