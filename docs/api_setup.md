# API Setup Guide

## Step 1: Copy environment template

```bash
cp .env.example .env
```

## Step 2: Fill in your API keys

Edit `.env` and replace placeholder values with your actual keys.

## Step 3: Verify

```python
from dotenv import load_dotenv
import os

load_dotenv()
print("Market API:", "OK" if os.getenv("MARKET_DATA_API_KEY") else "MISSING")
print("Sentiment API:", "OK" if os.getenv("SENTIMENT_API_KEY") else "MISSING")
```

## Security Reminders

- **Never** commit `.env` to Git
- **Never** hardcode API keys in source code
- Rotate keys if accidentally exposed
