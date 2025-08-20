import asyncio
import os
from dotenv import load_dotenv
from hugging_face_service import HuggingFaceService

load_dotenv()

async def quick_test():
    os.environ['ENABLE_AI_FEATURES'] = 'true'
    
    service = HuggingFaceService()
    
    print("Testing sentiment analysis...")
    result = await service.analyze_sentiment('Bu kitap harika!')
    print('Sentiment:', result.to_dict() if result else 'Failed')

if __name__ == "__main__":
    asyncio.run(quick_test())