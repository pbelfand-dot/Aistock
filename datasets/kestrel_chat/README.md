# Kestrel chat dataset: make a custom AI that knows Kestrel

Questions an owner asks about Kestrel, and accurate answers written from the app's own docs and code
(each one names its source in `kestrel_qa.csv`). Three topics: **using the app**, **how it trades**, and
**safety, research and money**. The answers are plain English, honest about limits, and never include keys.

## The files

| File | Use it for |
|---|---|
| `kestrel_knowledge.md` | The whole reference in one file: upload it as "knowledge" (no training needed) |
| `instructions.md` | The assistant's instructions (its system prompt) |
| `kestrel_chat_train.jsonl` / `kestrel_chat_val.jsonl` | Fine-tuning: example conversations, 90% to train and 10% to check |
| `kestrel_chat.jsonl` | All the examples in one file |
| `kestrel_qa.csv` | The same questions and answers as a spreadsheet, to read or edit |

## Three ways to use it

**1. A ChatGPT GPT or a Claude Project (easiest, no training).** Create a GPT (ChatGPT → Explore GPTs →
Create) or a Claude Project. Paste `instructions.md` into its instructions, and upload `kestrel_knowledge.md`
(and optionally `kestrel_qa.csv`) as knowledge. It answers from the docs, so update the files when Kestrel changes.

**2. Fine-tune a model.** Upload `kestrel_chat_train.jsonl` as the training file and `kestrel_chat_val.jsonl`
as the validation file to a fine-tuning service that takes chat-format JSONL (one `{"messages": [...]}`
conversation per line; OpenAI's needs at least 10). Every example uses the same system message, as recommended.
Fine-tuning teaches the *style* and common answers; for facts that change, still give it the knowledge file.

**3. A local model on your Mac.** Local tools (for example Ollama or LM Studio) can use the instructions as
the system prompt and the knowledge file as context; fine-tuning a local model needs a training tool that
reads chat JSONL and produces a model file for it.

## Keep it up to date

The answers describe Kestrel as it is now. When a feature changes, edit the matching answers in `sources/*.json`
(or ask Claude to redo them) and rebuild:

```
python3 datasets/kestrel_chat/build.py
```

The build refuses duplicate questions and anything that looks like a key, a token or an email address.
