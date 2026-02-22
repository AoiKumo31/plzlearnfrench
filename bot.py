import os
import logging
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
        "I am your new Adaptive French Coach. I will send you a short (5-10 min) task every morning.\n"
        "Your goal is simply to reply in French. I will evaluate your response, help fix your mistakes, "
        "and automatically adjust the difficulty of tomorrow's task.\n\n"
        f"You are currently starting at Level {user_state['difficulty_level']}. Let's get started!"
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
        
        status_emoji = {"green": "[Excellent]", "yellow": "[Reviewing]", "red": "[Struggling]"}.get(user['state'], "[Normal]")
        
        msg = (
            f"Bonjour! Here is today's task:\n\n"
            f"Task: {task.task_text}\n\n"
            f"Estimated time: {task.estimated_minutes} min\n"
            f"Current Level: {user['difficulty_level']} | Streak: {user['streak']}\n"
            f"Just reply to this message in French!"
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
    """Handle incoming messages (evaluate task or chat normally)."""
    chat_id = update.effective_user.id
    user_response = update.message.text
    
    user = db.get_user(chat_id)
    if not user:
        await update.message.reply_text("Please send /start first.")
        return
        
    # Get today's assigned task from logs
    today = datetime.now().date().isoformat()
    with db.get_db() as database:
        recent_log = database.execute(
            'SELECT * FROM daily_logs WHERE chat_id = ? AND date = ? ORDER BY id DESC LIMIT 1',
            (chat_id, today)
        ).fetchone()
        
    # If there is no task or the task is already completed, route to conversational companion
    if not recent_log or recent_log['user_response']:
        await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        
        # Save user message to history
        db.save_chat_message(chat_id, "user", user_response)
        
        # Get history and purely conversational response
        history = db.get_recent_chat_history(chat_id, limit=10)
        bot_reply = await generate_chat_response(history)
        
        # Save bot response to history
        db.save_chat_message(chat_id, "assistant", bot_reply)
        
        await update.message.reply_text(bot_reply)
        return
        
    task_assigned = recent_log['task_assigned']
    
    # Show typing indicator while LLM processes
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    # Evaluate via LLM
    eval_result = await evaluate_response(task_assigned, user_response)
    
    # Save to DB
    db.update_daily_log_response(
        chat_id=chat_id,
        response=user_response,
        feedback=eval_result.feedback,
        score=eval_result.score,
        decision=eval_result.adaptation_decision
    )
    
    # Update Streak and Level based on adaptation
    new_streak = user['streak'] + 1
    new_level = user['difficulty_level']
    new_state = user['state']
    
    if eval_result.adaptation_decision == 'level_up':
        new_state = 'green'
        if eval_result.score > 90:
            new_level = min(10, new_level + 1)
    elif eval_result.adaptation_decision == 'maintain':
        new_state = 'yellow'
    elif eval_result.adaptation_decision == 'simplify':
        new_state = 'red'
        # Reset streak if they totally bombed it or used a translator? Optional.
    
    db.update_user_state(chat_id, new_streak, new_level, new_state)
    
    # Save recommended vocabulary if it exists (very naive parsing, but demonstrates the concept)
    # Ideally, the LLM should output a structured list of Dicts for vocabulary.
    # For now, we will let the user explicitly use /vocab to save words, keeping it simple.
    
    # Send feedback
    status_msg = "Level Up!" if new_level > user['difficulty_level'] else "Keep going!"
    if eval_result.adaptation_decision == 'simplify':
        status_msg = "Let's take it easy tomorrow."
        
    reply_msg = (
        f"Evaluation: {eval_result.score}/100\n\n"
        f"Grammar Analysis:\n{eval_result.grammar_analysis}\n\n"
        f"Vocabulary Suggestions:\n{eval_result.vocabulary_suggestions}\n\n"
        f"Corrected Version:\n{eval_result.corrected_french}\n\n"
        f"Streak: {new_streak} | {status_msg}"
    )
    
    await update.message.reply_text(reply_msg)

async def force_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger a task (useful for testing)."""
    chat_id = update.message.chat_id
    await send_daily_task_to_user(context.bot, chat_id)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check current status."""
    chat_id = update.message.chat_id
    user = db.get_user(chat_id)
    if user:
        msg = (
            f"Status:\n"
            f"Level: {user['difficulty_level']}/10\n"
            f"Streak: {user['streak']}\n"
            f"State: {user['state'].capitalize()}\n"
        )
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Please use /start first.")

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
            message = "Evening Vocabulary Review!\n\nTranslate these words:\n"
            for w in words:
                message += f"- {w['english_translation']}\n"
            message += "\n(Check if you got them right using /eval, or just practice them!)"
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            logger.error(f"Failed to send vocab review to {chat_id}: {e}")

async def vocab_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save a vocabulary word using /vocab french word - english translation"""
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("Usage: /vocab [french word] - [english translation]")
        return
        
    text = " ".join(context.args)
    if " - " not in text:
        await update.message.reply_text("Please use a hyphen to separate the French and English. Example: /vocab pomme - apple")
        return
        
    french, english = text.split(" - ", 1)
    db.save_vocabulary(chat_id, french, english)
    await update.message.reply_text(f"Saved: {french} = {english} (Added to spaced repetition queue)")

async def eval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Evaluate a random sentence using /eval [french sentence]"""
    if not context.args:
        await update.message.reply_text("Usage: /eval [your french sentence]")
        return
        
    sentence = " ".join(context.args)
    await update.message.reply_text("Evaluating sentence...")
    
    try:
        eval_result = await evaluate_response("User requested random evaluation, no specific context.", sentence)
        response_msg = (
            f"Score: {eval_result.score}/100\n\n"
            f"Grammar Analysis:\n{eval_result.grammar_analysis}\n\n"
            f"Vocabulary Suggestions:\n{eval_result.vocabulary_suggestions}\n\n"
            f"Corrected Version:\n{eval_result.corrected_french}"
        )
        await update.message.reply_text(response_msg)
    except Exception as e:
        logger.error(f"Error evaluating: {e}")
        await update.message.reply_text("Sorry, evaluation failed.")

def main() -> None:
    """Start the bot and the web server."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("task", force_task))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("vocab", vocab_cmd))
    application.add_handler(CommandHandler("eval", eval_cmd))

    # on non command i.e message - handle the response
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response))

    # Add scheduling for 9:00 AM UTC every day
    job_queue = application.job_queue
    job_queue.run_daily(send_daily_tasks_job, time=time(hour=9, minute=0))
    job_queue.run_daily(send_nightly_vocab_job, time=time(hour=20, minute=0))

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
