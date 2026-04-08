import chromadb
import json

# 1. Connect to our persistent local ChromaDB storage
client = chromadb.PersistentClient(path="./data/chroma")

# 2. List all existing collections (CodeMind maps one collection per User+Repository)
collections = client.list_collections()
print("Available Collections:")
for c in collections:
    print(f" - {c.name}")

if not collections:
    print("\nNo repositories have been indexed yet!")
    exit()

# 3. Pick the first collection and query its data
collection = collections[0]
print(f"\n👉 Inspecting data inside: {collection.name}")

# .get() fetches the raw documents and metadata. We must ask for embeddings explicitly.
data = collection.get(include=["documents", "metadatas", "embeddings"])

total_chunks = len(data['ids'])
print(f"Total code chunks stored: {total_chunks}\n")

if total_chunks > 0:
    print("--- SAMPLE OF THE FIRST STORED CHUNK ---")
    print(f"🆔 ID: {data['ids'][0]}")
    
    # Metadata contains the file path, language, and line numbers we injected
    print(f"📊 Metadata:\n{json.dumps(data['metadatas'][0], indent=2)}")
    
    
    # Documents contain the literal raw python/js/etc. code chunk
    raw_code = data['documents'][0]
    print(f"📄 Raw Code Document:\n{raw_code[:300]}...\n[truncated for readability]\n")
    
    # Embeddings represent the semantic meaning of the code block as a 384-dimensional array
    embedding = data['embeddings'][0]
    print(f"🧠 Vector Embedding (Length: {len(embedding)} dimensions):")
    print(f"[{embedding[0]:.6f}, {embedding[1]:.6f}, {embedding[2]:.6f}, {embedding[3]:.6f}, ..., {embedding[-2]:.6f}, {embedding[-1]:.6f}]")
