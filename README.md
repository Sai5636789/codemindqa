# 🧠 CodeMind: AI-Powered Codebase Q&A Platform

CodeMind is a production-ready, full-stack application that allows developers to interactively chat with entire GitHub repositories. Powered by **Meta LLaMA 3** (via Groq), **LangChain**, and **ChromaDB**, CodeMind ingests your codebase, chunks the source code, generates semantic embeddings, and uses Retrieval-Augmented Generation (RAG) to provide highly accurate, code-cited answers to your architectural and debugging questions.

## ✨ Features

- **Multi-User Authentication**: Secure user registration and login system with JWT tokens and bcrypt password hashing.
- **Private Repository Support**: Securely index private GitHub repositories by supplying a Personal Access Token (PAT).
- **Incremental Indexing**: Uses efficient `git pull` logic to fetch only new commits when re-indexing an existing repository, saving bandwidth and time.
- **Persistent Chat History**: All conversations and AI-generated code citations are stored in a SQLite database, allowing you to resume past sessions anytime.
- **Advanced Code Parsing**: Uses `tree-sitter` (where supported) to intelligently chunk code at the function and class level for extremely precise semantic search context.
- **Lightning Fast LLM**: Utilizes Groq's high-speed inference engine for near-instant LLaMA 3 responses.

---

## 🛠️ Technology Stack

### Backend
* **FastAPI** (Python 3.9+) - High-performance asynchronous REST API.
* **LangChain** - Orchestration framework mapping LLM requests to vector retrieval.
* **ChromaDB** - Local vector database holding document embeddings.
* **Sentence-Transformers** - (`all-MiniLM-L6-v2`) Generates dense vector embeddings.
* **SQLAlchemy & SQLite** - Relational database for Users, Repo states, and Chat Histories.
* **GitPython** - Native Python git interface for cloning and pulling repositories.
* **PyJWT & passlib** - Secure authentication and token management.

### Frontend
* **React 18 & Vite** - Lightning-fast frontend development environment.
* **Axios** - Intercepted HTTP client handling JWT Bearer tokens automatically.
* **Lucide React** - SVG icon library for a clean, modern UI.
* **CSS3 Vanilla** - Custom glassmorphism and modern gradient design system.

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.9 or higher
- Node.js 18+
- Git installed on your machine
- A [Groq API Key](https://console.groq.com/keys) (Free tier available)
- C++ Build tools (required for compiling ChromaDB/Tree-Sitter locally)

### 1. Clone the project
```bash
git clone <your-repo-url>
cd codebase-qa
```

### 2. Configure Environment Variables
Inside the `backend` folder, copy the example environment file and add your Groq API key:
```bash
cd backend
cp .env.example .env
```
Open `backend/.env` and configure:
```env
GROQ_API_KEY=gsk_your_key_here
JWT_SECRET=super-secret-key-change-me-in-production
```

### 3. Install Dependencies & Start the App
For your convenience, the project includes an automated startup script that will:
1. Initialize the Python virtual environment.
2. Install all `requirements.txt` dependencies.
3. Install frontend `npm` dependencies.
4. Launch both servers concurrently.

Run the startup script from the project root:
```bash
chmod +x start.sh
./start.sh
```

- **Frontend Application:** [http://localhost:5173](http://localhost:5173)
- **Backend API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 💻 Usage Guide

1. **Register an Account:** Open the frontend app and create a new secure account.
2. **Index a Repository:** 
   - Paste a GitHub URL (e.g., `https://github.com/encode/starlette`) into the sidebar.
   - If the repository is **Private**, expand the "Advanced Settings" and provide a GitHub Personal Access Token (with `repo` permissions).
   - Click "Index Repository". CodeMind will clone the code, chunk it, generate embeddings, and store it in ChromaDB.
3. **Chat:** Select the indexed repository from the sidebar. You can now ask questions like:
   - *"How is authentication handled in this app?"*
   - *"Where is the main database connection established?"*
   - *"Explain the data flow of the `index_repo` function."*
4. **Incremental Updates:** If the source repository receives new commits, simply click the **Re-Index (Refresh)** button next to the repo in your sidebar. CodeMind will exclusively pull the latest changes!

---
*Built with ❤️ utilizing the power of LangChain and open-source models.*
