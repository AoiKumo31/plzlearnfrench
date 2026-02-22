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
    task_text: str = Field(description="The French learning task instruction to send to the user. Should be short and clear.")
    target_grammar: str = Field(description="The specific grammar or vocabulary topic focused on.")
    estimated_minutes: int = Field(description="Estimated time to complete the task in minutes (1-15).")

class EvaluationResult(BaseModel):
    score: int = Field(description="Score from 0 to 100 on accuracy and effort.")
    feedback: str = Field(description="Friendly, encouraging feedback in English with specific corrections.")
    corrected_french: str = Field(description="The user's response corrected for perfect grammar/spelling.")
    adaptation_decision: str = Field(description="Must be exactly 'level_up', 'maintain', or 'simplify'.")

async def generate_task(difficulty_level: int, state: str, focus: str = "general") -> GeneratedTask:
    """
    Generate a personalized French learning task using the LLM.
    """
    
    # Define state context
    state_ctx = {
        "🟢": "The user is doing great! Give them a challenging task.",
        "🟡": "The user struggled recently or missed a day. Keep the task simple and reinforcing.",
        "🔴": "The user missed multiple days. Give a very fast, 2-minute 'restart protocol' task to get them back on track."
    }.get(state, "Give a standard task.")
    
    prompt = f"""
    You are an expert, encouraging French language coach for a Telegram bot.
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
                {"role": "system", "content": "You are a helpful French tutor. Respond completely in JSON matching the schema."},
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
    The user was assigned this task: "{task_text}"
    The user submitted this response: "{user_response}"
    
    Evaluate their response. 
    1. Score it 0-100 based on effort and accuracy.
    2. Provide brief, friendly feedback explaining any mistakes.
    3. Provide the corrected version of their French.
    4. Make an adaptation decision:
       - 'level_up' if the score > 85 and it was very accurate.
       - 'maintain' if they made some mistakes (score 50-85).
       - 'simplify' if they completely misunderstood, used out-of-bounds translator, or scored < 50.
    """
    
    try:
        response = await client.beta.chat.completions.parse(
            model="llama3.1-70b",
            messages=[
                {"role": "system", "content": "You are an expert French tutor reviewing homework. Respond completely in JSON matching the schema."},
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
            feedback="Thanks for submitting! (LLM evaluation temporarily unavailable).",
            corrected_french=user_response,
            adaptation_decision="maintain"
        )

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
        print(f"Feedback: {eval_result.feedback}")
        print(f"Corrected: {eval_result.corrected_french}")
        print(f"Decision: {eval_result.adaptation_decision}")

    if os.getenv("CEREBRAS_API_KEY"):
        asyncio.run(test())
    else:
        print("Set CEREBRAS_API_KEY to run the standalone test.")
