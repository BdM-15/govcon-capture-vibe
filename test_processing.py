import asyncio
from app import extract_text_from_files, process_rfp_files

async def test_processing():
    print("Testing RFP processing with debug output...")

    # Simulate uploaded files
    class MockUploadedFile:
        def __init__(self, file_path):
            self.name = file_path.split('/')[-1]  # Just the filename
            self._content = None

        def getvalue(self):
            if self._content is None:
                with open(f'docs/{self.name}', 'rb') as f:
                    self._content = f.read()
            return self._content

    uploaded_files = [MockUploadedFile('docs/Shipley Proposal Guide.pdf')]

    # Process the files
    result = await process_rfp_files(uploaded_files)

    if result:
        print(f"Processing complete. Requirements: {len(result['requirements'])}")
        print(f"First requirement: {result['requirements'][0] if result['requirements'] else 'None'}")
    else:
        print("Processing failed")

if __name__ == "__main__":
    asyncio.run(test_processing())