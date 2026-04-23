# API Key Setup Instructions

To use the Stamdata ESG API client included in this project, you must provide a valid API key. Follow these steps to set it up:

## 1. Obtain your API Key
Ensure you have a valid API key provided by Stamdata.

## 2. Create the API Key File
The scripts are configured to read the API key from a plain text file in the root directory of the project.

1. Create a new file named `APIKey.txt` in the project root directory:
   ```bash
   touch APIKey.txt
   ```
2. Open `APIKey.txt` and paste your API key into it. 
3. **Important**: Ensure there are no extra spaces or line breaks. The file should contain *only* the key string.

## 3. Security Warning
- **Never commit your `APIKey.txt` file to version control.**
- The `.gitignore` file in this repository is already configured to ignore `APIKey.txt` to prevent accidental leaks.
- If you suspect your API key has been compromised, revoke it immediately through the Stamdata portal.

## 4. Verification
Once the file is created, you can verify the setup by running the test script:
```bash
source .venv/bin/activate
python3 tests/APITest.py
```

If the key is missing or the file cannot be found, the script will provide a clear error message:
- `FileNotFoundError: API key file not found at: APIKey.txt`
- `ValueError: API key file is empty.`
