import asyncio
from ai_engine import evaluate_response
async def main():
    res = await evaluate_response("Write 3 simple sentences in French about your day today.", "kjkj")
    print("FINISHED")
    print(res)
asyncio.run(main())
