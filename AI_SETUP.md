# AI Notes Setup

Version 0.3.0 adds AI-ready production notes.

The app still works without an AI account. By default it generates structured local notes from metadata, tags, status, and your custom prompt.

## Enable AI Mode

Set these environment variables before starting the app:

```text
VMI_AI_PROVIDER=openai
VMI_OPENAI_API_KEY=your_key_here
VMI_OPENAI_MODEL=gpt-4o-mini
```

Then restart:

```text
uvicorn app.main:app --reload
```

Open the AI Notes page:

```text
http://127.0.0.1:8000/ai
```

Open a media detail page, check **Use AI provider**, and generate a preset note.

## Safety

Do not commit API keys to GitHub. The app sends metadata, filename, tags, existing notes, and your prompt to the configured provider. It does not upload the video file itself.
