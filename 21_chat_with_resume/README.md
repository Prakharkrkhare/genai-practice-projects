# 📄 Chat with Your Resume — RAG Pipeline

A local Retrieval-Augmented Generation (RAG) system that lets you have a conversation with one or multiple resumes using OpenAI embeddings, Qdrant vector database, and GPT-4o.

---

## 🗂️ Folder Structure

```
resume_rag/
├── .env                  # API keys (never commit to git)
├── resumes/
│   ├── alice.pdf         # Add your resume PDFs here
│   ├── bob.pdf
│   └── charlie.pdf
├── index.py              # Indexing script — run once per resume change
└── query.py              # Interactive Q&A loop
```

---

## ⚙️ Tech Stack

| Component | Tool | Purpose |
|---|---|---|
| PDF Loading | `PyPDFLoader` (langchain-community) | Parses PDF page by page |
| Chunking | `RecursiveCharacterTextSplitter` | Splits text into overlapping chunks |
| Embeddings | `text-embedding-3-large` (OpenAI) | Converts text to 3072-dim vectors |
| Vector DB | Qdrant (local, port 6333) | Stores and searches vectors |
| LLM | `gpt-4o` (OpenAI) | Answers questions from retrieved context |
| Env Mgmt | `python-dotenv` | Loads API keys from `.env` |

---

## 🔄 Project Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                        INDEXING FLOW                        │
│                       (index.py)                            │
└─────────────────────────────────────────────────────────────┘

  resume.pdf
      │
      ▼
  PyPDFLoader          ← splits by page, stores page number in metadata
      │
      ▼
  RecursiveCharacterTextSplitter
  (chunk_size=1000, chunk_overlap=400)
      │
      ▼
  tag each chunk with resume_id  ← e.g. metadata["resume_id"] = "alice"
      │
      ▼
  OpenAIEmbeddings
  (text-embedding-3-large → 3072-dim vectors)
      │
      ▼
  Qdrant Collection: "resume_rag"
  (stored locally on localhost:6333)


┌─────────────────────────────────────────────────────────────┐
│                        QUERY FLOW                           │
│                       (query.py)                            │
└─────────────────────────────────────────────────────────────┘

  User Question
      │
      ▼
  OpenAIEmbeddings     ← embeds question into same vector space
      │
      ▼
  Qdrant similarity_search(k=4)
  [optional: filter by resume_id]
      │
      ▼
  Top 4 matching chunks
  (with metadata: resume_id, page number)
      │
      ▼
  Build context string
  e.g. "[Alice, Page 2]\n<chunk text>"
      │
      ▼
  GPT-4o
  SystemMessage: answer only from context, cite page numbers
  HumanMessage: context + question
      │
      ▼
  Answer printed to terminal
```

---

## 🚀 Setup & Installation

### 1. Install dependencies

```bash
pip install python-dotenv langchain langchain-openai \
            langchain-qdrant langchain-community pypdf openai qdrant-client
```

### 2. Set up your `.env` file

```env
OPENAI_API_KEY=sk-...your-key-here...
```

### 3. Start Qdrant locally (Docker)

```bash
# Without persistence (data lost on container stop)
docker run -p 6333:6333 qdrant/qdrant

# With persistence (recommended)
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

### 4. Add your resumes

Drop PDF files into the `resumes/` folder and list them in `index.py`:

```python
RESUME_FILES = [
    "resumes/alice.pdf",
    "resumes/bob.pdf",
]
```

### 5. Run the indexing script

```bash
python index.py
```

Expected output:
```
  alice: 38 chunks
  bob: 42 chunks

Total indexed: 80 chunks across 2 resumes.
```

### 6. Start the Q&A loop

```bash
python query.py
```

---

## 💬 Query Commands

| Command | What it does |
|---|---|
| Any question | Searches all resumes and answers |
| `filter: alice` | Restricts all future searches to Alice's resume only |
| `filter: all` | Removes filter, searches all resumes again |
| `exit` | Exits the program |

### Example session

```
You: filter: alice
  → Now searching only: alice

You: What is her highest qualification?
Assistant: According to Alice, Page 1, her highest qualification is a B.Tech in...

You: filter: all
  → Now searching all resumes.

You: Who has experience with Kubernetes?
Assistant: Bob (Page 3) and Charlie (Page 2) both have Kubernetes experience...

You: exit
Goodbye!
```

---

## 🧠 Important Concepts

### Chunking strategy
- `chunk_size=1000` — each chunk is at most 1000 characters
- `chunk_overlap=400` — 400-character overlap between consecutive chunks so context isn't lost at boundaries
- `RecursiveCharacterTextSplitter` splits on `\n\n` → `\n` → space → character (in that order of preference)

### Page number handling
PyPDFLoader uses **0-based indexing** for pages. The code adds `+1` when displaying so page numbers match what you see in a PDF viewer:
```python
page_num = doc.metadata.get("page", 0) + 1
```

### resume_id tagging
Every chunk is tagged before being stored in Qdrant:
```python
chunk.metadata["resume_id"] = "alice"
```
This enables Qdrant's `FieldCondition` filter to narrow searches to a single candidate without affecting other chunks.

### Why k=4 chunks?
Four chunks (~4000 chars) gives GPT-4o enough context without hitting token limits. Tune this:
- Increase to `k=6` if answers seem incomplete
- Decrease to `k=2` if you want to reduce cost/latency

---

## 🗑️ Managing the Qdrant Collection

```python
from qdrant_client import QdrantClient
client = QdrantClient(host="localhost", port=6333)

# Delete a collection
client.delete_collection("resume_rag")

# List all collections
client.get_collections()

# Inspect a collection
client.get_collection("resume_rag")
```

Or via curl:
```bash
# Delete
curl -X DELETE http://localhost:6333/collections/resume_rag

# List all
curl http://localhost:6333/collections
```

Or via the **Qdrant Web Dashboard** at `http://localhost:6333/dashboard`

> **Note:** `index.py` calls `recreate_collection()` which wipes and rebuilds the collection automatically. Re-run `index.py` whenever you add, remove, or update a resume.

---

## 🖼️ Using Images Instead of PDFs

If your input is images (scanned resumes, photos), convert them to PDF first using `img2pdf`:

```bash
pip install img2pdf
```

```python
import img2pdf

# Single image
with open("resume.pdf", "wb") as f:
    f.write(img2pdf.convert("resume.png"))

# Multiple images → one PDF
with open("resume.pdf", "wb") as f:
    f.write(img2pdf.convert(["page1.png", "page2.png"]))
```

Then feed the output PDF into `index.py` as normal. No quality loss, no API needed.

---

## ⚠️ Common Pitfalls

| Problem | Cause | Fix |
|---|---|---|
| `Collection not found` error in query.py | index.py hasn't been run yet | Run `python index.py` first |
| Wrong page numbers in answers | PyPDFLoader is 0-indexed | The `+1` in query.py handles this — don't remove it |
| Duplicate chunks on re-index | Running index.py multiple times | `recreate_collection()` handles this automatically |
| Filter returns no results | `resume_id` doesn't match filename | Check exact filename without extension e.g. `filter: alice` for `alice.pdf` |
| Qdrant connection refused | Docker container not running | Run the docker command in Setup step 3 |

---

## 🔭 Possible Extensions

- **Streamlit UI** — wrap `query.py` in a web interface
- **Vision/Multimodal RAG** — send page images directly to GPT-4o instead of extracted text (search: `multimodal RAG langchain`, `image_url HumanMessage`)
- **Reranking** — add a reranker after similarity search for better chunk selection
- **Metadata filtering UI** — dropdown to select candidate instead of typing `filter:`
- **Score threshold** — reject chunks below a similarity score to avoid hallucination on irrelevant questions

---

## 📚 Key LangChain Docs to Bookmark

| Topic | Search term |
|---|---|
| Image loaders | `UnstructuredImageLoader` |
| Vision/multimodal input | `multimodal inputs HumanMessage image_url` |
| PDF loaders | `PyPDFLoader` |
| Qdrant integration | `QdrantVectorStore` |
| Prompt engineering | `SystemMessage HumanMessage` |
| Text splitters | `RecursiveCharacterTextSplitter` |

- https://python.langchain.com/docs/integrations/vectorstores/qdrant
- https://python.langchain.com/docs/integrations/document_loaders/pypdf
- https://python.langchain.com/docs/how_to/multimodal_inputs
