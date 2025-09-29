import asyncio
from src.rfp_rag import get_rfp_rag

async def debug_processing():
    rag = await get_rfp_rag()

    # Check available methods
    print('Available methods with enqueue/process/doc:')
    methods = [method for method in dir(rag.rag) if any(keyword in method.lower() for keyword in ['enqueue', 'process', 'doc', 'insert'])]
    print(methods)

    # Try the synchronous version
    print('\nTesting synchronous enqueue_documents...')
    try:
        track_id = rag.rag.enqueue_documents(['temp__N6945025R0003.pdf'])
        print(f'Sync Track ID: {track_id}')
    except Exception as e:
        print(f'Sync failed: {e}')

if __name__ == "__main__":
    asyncio.run(debug_processing())