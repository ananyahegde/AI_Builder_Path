import os
import numpy as np
from groq import Groq
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

os.environ["GROQ_API_KEY"] = "your_key_here"
client = Groq(api_key=os.environ["GROQ_API_KEY"])
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

def load_pdf(filepath):
    reader = PdfReader(filepath)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def retrieve(query, chunks, chunk_embeddings, top_k=3):
    query_embedding = embed_model.encode([query])[0]
    scores = np.dot(chunk_embeddings, query_embedding) / (
        np.linalg.norm(chunk_embeddings, axis=1) * np.linalg.norm(query_embedding)
    )
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [chunks[i] for i in top_indices]

def generate_answer(query, retrieved_chunks):
    context = "\n\n".join(retrieved_chunks)
    prompt = f"""Answer the question based only on the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {query}

Answer:"""
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def chat(chunks, chunk_embeddings):
    print("RAG Chatbot ready. Type 'exit' to quit.\n")
    while True:
        query = input("You: ")
        if query.lower() == "exit":
            break
        retrieved = retrieve(query, chunks, chunk_embeddings)
        answer = generate_answer(query, retrieved)
        print("Bot:", answer, "\n")

if __name__ == "__main__":
    filepath = "your_paper.pdf"
    text = load_pdf(filepath)
    chunks = chunk_text(text)
    chunk_embeddings = embed_model.encode(chunks)
    chat(chunks, chunk_embeddings)