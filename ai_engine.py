import os
import json
import inspect
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Any, Callable

load_dotenv()

# Initialize Cerebras async client
# Requires CEREBRAS_API_KEY to be set in the environment or .env file
client = AsyncOpenAI(
    base_url="https://api.cerebras.ai/v1",
    api_key=os.getenv("CEREBRAS_API_KEY")
)

# Pydantic models for structured output parsing
class GeneratedTask(BaseModel):
    task_text: str = Field(description="The French learning task instruction to send to the user. Should be short and clear. No emojis.")
    target_grammar: str = Field(description="The specific grammar or vocabulary topic focused on.")
    estimated_minutes: int = Field(description="Estimated time to complete the task in minutes (1-15).")

class EvaluationResult(BaseModel):
    score: int = Field(description="Score from 0 to 100 on accuracy and effort.")
    grammar_analysis: str = Field(description="Clear, concise explanation of grammatical errors made, without emojis.")
    vocabulary_suggestions: str = Field(description="1-2 alternative vocabulary words or more natural ways to phrase the sentence.")
    corrected_french: str = Field(description="The user's response corrected for perfect grammar/spelling.")
    adaptation_decision: str = Field(description="Must be exactly 'level_up', 'maintain', or 'simplify'.")

async def generate_task(difficulty_level: int, state: str, focus: str = "general") -> GeneratedTask:
    """
    Generate a personalized French learning task using the LLM.
    """
    
    # Define state context
    state_ctx = {
        "green": "The user is doing great! Give them a challenging task.",
        "yellow": "The user struggled recently or missed a day. Keep the task simple and reinforcing.",
        "red": "The user missed multiple days. Give a very fast, 2-minute 'restart protocol' task to get them back on track."
    }.get(state, "Give a standard task.")
    
    prompt = f"""
    You are an expert, encouraging French language coach for a Telegram bot. 
    CRITICAL INSTRUCTION: Do not use any emojis anywhere in your response.
    The user's current difficulty level is {difficulty_level}/10 (1=Beginner A1, 10=Fluent C2).
    Their current performance state is '{state}'. Context: {state_ctx}
    Their learning focus is: {focus}.
    
    Generate a specific, actionable daily French task that takes less than 15 minutes.
    Examples format: 
    - "Translate these 3 sentences into the imparfait..."
    - "Write 3 sentences about your breakfast using the passé composé."
    - "Conjugate the verb 'aller' in the present tense."
    
    Do not include the answers in the task text.
    """
    
    try:
        response = await client.beta.chat.completions.parse(
            model="llama3.1-8b",
            messages=[
                {"role": "system", "content": "You are a helpful French tutor. Respond completely in JSON matching the schema. DO NOT USE EMOJIS."},
                {"role": "user", "content": prompt}
            ],
            response_format=GeneratedTask,
            temperature=0.7
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error generating task: {e}")
        # Fallback task
        return GeneratedTask(
            task_text=f"Write 3 simple sentences in French about your day today.",
            target_grammar="General",
            estimated_minutes=5
        )

async def evaluate_response(task_text: str, user_response: str) -> EvaluationResult:
    """
    Evaluate the user's French response using the LLM.
    """
    prompt = f"""
    You are an expert, encouraging French language coach for a Telegram bot.
    CRITICAL INSTRUCTION: Do not use any emojis anywhere in your response.
    The user was assigned this task: "{task_text}"
    The user submitted this response: "{user_response}"
    
    Evaluate their response. 
    1. Score it 0-100 based on effort and accuracy.
    2. Provide a 'grammar_analysis' explaining grammatical mistakes in English (no emojis).
    3. Provide 'vocabulary_suggestions' showing a more natural or advanced way to phrase it (no emojis).
    4. Provide the corrected version of their French.
    5. Make an adaptation decision:
       - 'level_up' if the score > 85 and it was very accurate.
       - 'maintain' if they made some mistakes (score 50-85).
       - 'simplify' if they completely misunderstood, used out-of-bounds translator, or scored < 50.
    """
    
    try:
        response = await client.beta.chat.completions.parse(
            model="llama3.1-8b",
            messages=[
                {"role": "system", "content": "You are an expert French tutor reviewing homework. Respond completely in JSON matching the schema. DO NOT USE EMOJIS."},
                {"role": "user", "content": prompt}
            ],
            response_format=EvaluationResult,
            temperature=0.3
        )
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error evaluating response: {e}")
        # Fallback evaluation
        return EvaluationResult(
            score=70,
            grammar_analysis="Unable to generate detailed analysis at this time.",
            vocabulary_suggestions="Try testing again shortly.",
            corrected_french=user_response,
            adaptation_decision="maintain"
        )

def get_companion_tools() -> list[dict[str, Any]]:
    """Return tool schemas used by the companion."""
    return [
        {
            "type": "function",
            "function": {
                "name": "suggest_task",
                "strict": True,
                "description": "Generate and assign a new short French learning task for the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "focus": {
                            "type": "string",
                            "description": "Optional focus area like grammar, vocabulary, speaking, travel, food.",
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_vocabulary",
                "strict": True,
                "description": "Save a vocabulary pair for spaced repetition.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "french": {"type": "string", "description": "French word or short phrase."},
                        "english": {"type": "string", "description": "English meaning or translation."},
                    },
                    "required": ["french", "english"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "evaluate_french",
                "strict": True,
                "description": "Evaluate the user's French response and return score plus corrections.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_response": {"type": "string", "description": "The user's French response to evaluate."},
                        "task_context": {
                            "type": "string",
                            "description": "Task prompt or context to evaluate against. Can be empty for general evaluation.",
                        },
                    },
                    "required": ["user_response"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_user_status",
                "strict": True,
                "description": "Get the learner status: level, streak, and current state.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_due_vocabulary",
                "strict": True,
                "description": "Get vocabulary items that are due for review today.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_vocab_translation",
                "strict": True,
                "description": "Check whether the user's French translation is correct for a due vocabulary item.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vocab_id": {"type": "integer", "description": "Vocabulary ID from due list."},
                        "user_french": {"type": "string", "description": "User translation attempt in French."},
                    },
                    "required": ["vocab_id", "user_french"],
                    "additionalProperties": False,
                },
            },
        },
    ]


async def generate_chat_response(
    messages: list,
    companion_context: dict[str, Any] | None = None,
    tool_executor: Callable[[str, dict[str, Any]], Any] | None = None,
) -> str:
    """
    Generate a free-form conversational response using chat history.
    messages: list of dicts like [{"role": "user", "content": "hi"}, ...]
    pending_task: if set, the user has a daily task waiting; gently offer help or encouragement.
    """
    
    companion_instruction = (
        "You are a warm, supportive AI companion helping someone learn French. "
        "You are friendly, patient, and encouraging—like a kind tutor who enjoys chatting. "
        "Respond naturally and keep the tone light. If they speak in English, reply in a mix of "
        "simple French and English. If they speak in French, reply mainly in French with gentle "
        "corrections when helpful, but always prioritize keeping the conversation flowing. "
        "Be conversational, not robotic. Keep replies concise (1–3 sentences usually). "
        "You can use tools to suggest tasks, save vocabulary, evaluate French, and review progress. "
        "Prefer natural conversation over giving command-style instructions. "
        "IMPORTANT: Do not use any emojis in your response."
    )
    if companion_context:
        user_ctx = companion_context.get("user", {})
        pending_task = companion_context.get("pending_task")
        due_vocab = companion_context.get("due_vocab", [])
        companion_instruction += (
            f"\n\nUser context: level={user_ctx.get('difficulty_level')}, "
            f"streak={user_ctx.get('streak')}, state={user_ctx.get('state')}."
        )
        if due_vocab:
            companion_instruction += f" They currently have {len(due_vocab)} due vocabulary item(s)."
        if pending_task:
            task_preview = pending_task[:70] + "..." if len(pending_task) > 70 else pending_task
            companion_instruction += (
                f"\nPending task context: « {task_preview} ». "
                "If they seem stuck, help gently and offer small steps."
            )

    if companion_context and companion_context.get("pending_task"):
        pending_task = companion_context["pending_task"]
        task_preview = pending_task[:70] + "..." if len(pending_task) > 70 else pending_task
        companion_instruction += (
            f"\n\nContext: The user has a daily task waiting (« {task_preview} »). "
            "If they seem stuck, confused, or sent something casual (like 'idk', 'hello'), "
            "offer a friendly nudge, a small hint, or just chat. Don't pressure them—invite them "
            "to try when ready, or to ask for help."
        )

    tools = get_companion_tools() if tool_executor else None
    full_messages = [{"role": "system", "content": companion_instruction}] + messages

    try:
        for _ in range(6):
            response = await client.chat.completions.create(
                model="llama3.1-8b",
                messages=full_messages,
                tools=tools,
                parallel_tool_calls=False,
                temperature=0.6,
                max_tokens=300,
            )
            assistant_message = response.choices[0].message
            tool_calls = getattr(assistant_message, "tool_calls", None)

            if tool_calls and tool_executor:
                full_messages.append(assistant_message.model_dump())
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        tool_args = {}

                    tool_result = tool_executor(tool_name, tool_args)
                    if inspect.isawaitable(tool_result):
                        tool_result = await tool_result

                    full_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result, ensure_ascii=True),
                        }
                    )
                continue

            return assistant_message.content or "Let's keep practicing together."
    except Exception as e:
        print(f"Error generating chat response: {e}")
        return "Excusez-moi, je suis un peu fatigue. (I'm having trouble connecting right now, let's talk later!)"

    return "Let's continue. Tell me what you want to practice next."

if __name__ == '__main__':
    # Simple manual test if run directly (requires API key)
    import asyncio
    
    async def test():
        print("Testing Task Generation...")
        task = await generate_task(3, "🟢")
        print(f"Task: {task.task_text}")
        
        print("\nTesting Evaluation...")
        eval_result = await evaluate_response(
            task.task_text,
            "Je a mangé un pomme ce matin."
        )
        print(f"Score: {eval_result.score}")
        print(f"Grammar: {eval_result.grammar_analysis}")
        print(f"Vocab: {eval_result.vocabulary_suggestions}")
        print(f"Corrected: {eval_result.corrected_french}")
        print(f"Decision: {eval_result.adaptation_decision}")

    if os.getenv("CEREBRAS_API_KEY"):
        asyncio.run(test())
    else:
        print("Set CEREBRAS_API_KEY to run the standalone test.")
