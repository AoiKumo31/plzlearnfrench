import os
import json
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

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
            model="llama3.1-70b",
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
            model="llama3.1-70b",
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

async def generate_chat_response(messages: list) -> str:
    """
    Generate a free-form conversational response using chat history.
    messages: list of dicts like [{"role": "user", "content": "hi"}, ...]
    """
    
    # System prompt specifically for companionship
    sys_prompt = {
        "role": "system",
        "content": (
            "You are an encouraging, AI conversational companion helping the user learn French. "
            "You should respond naturally to their messages. If they speak in English, reply in a mix "
            "of simple French and English. If they speak in French, reply mainly in French, offering "
            "gentle corrections if they make glaring errors, but prioritize keeping the conversation flowing. "
            "IMPORTANT: Do not use any emojis in your response."
        )
    }
    
    # Prepend the system prompt to the history
    full_messages = [sys_prompt] + messages
    
    try:
        response = await client.chat.completions.create(
            model="llama3.1-70b",
            messages=full_messages,
            temperature=0.6,
            max_tokens=250
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating chat response: {e}")
        return "Excusez-moi, je suis un peu fatigué. (I'm having trouble connecting right now, let's talk later!)"

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
