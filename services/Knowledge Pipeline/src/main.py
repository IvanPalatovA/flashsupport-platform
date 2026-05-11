from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid, json, os, re, io
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import pypdf
from docx import Document

app = FastAPI(title="Knowledge Pipeline", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = None
DB_URL = f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_async_engine(DB_URL, pool_size=int(os.getenv("DB_POOL_SIZE",10)), max_overflow=int(os.getenv("DB_MAX_OVERFLOW",20)), echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

def get_model():
    global MODEL
    if MODEL is None:
        MODEL = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return MODEL

@app.get("/health")
async def health():
    return {"status": "healthy"}

def extract_pdf(data: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(data))
    text = "\n".join([page.extract_text() or "" for page in reader.pages])
    return re.sub(r"\s+", " ", text).strip()

def extract_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    text = "\n".join([p.text for p in doc.paragraphs])
    return re.sub(r"\s+", " ", text).strip()

def extract_text(content: bytes) -> str:
    text = content.decode("utf-8", errors="ignore")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

@app.post("/ingest/file")
async def ingest_file(file: UploadFile = File(...), collection: str = Form("default")):
    content = await file.read()
    raw = ""
    
    if file.content_type == "application/pdf":
        raw = extract_pdf(content)
    elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        raw = extract_docx(content)
    else:
        raw = extract_text(content)
    
    if not raw or len(raw) < 50:
        raise HTTPException(status_code=400, detail="Empty or too short document")
    
    splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)
    docs = splitter.create_documents([raw])
    
    model = get_model()
    vectors = model.encode([d.page_content for d in docs], convert_to_numpy=True, show_progress_bar=False).tolist()
    
    doc_id = str(uuid.uuid4())
    
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text("INSERT INTO documents (doc_id, source, collection) VALUES (:id, :src, :col) ON CONFLICT DO NOTHING"),
                {"id": doc_id, "src": file.filename, "col": collection}
            )
            for i, chunk in enumerate(docs):
                await session.execute(
                    text("INSERT INTO chunks (doc_id, chunk_index, text, metadata, embedding) VALUES (:id, :idx, :txt, :meta, :emb::vector) ON CONFLICT DO NOTHING"),
                    {
                        "id": doc_id,
                        "idx": i,
                        "txt": chunk.page_content,
                        "meta": json.dumps(chunk.metadata),
                        "emb": json.dumps(vectors[i])
                    }
                )
        await session.commit()
    
    return {"doc_id": doc_id, "chunks_count": len(docs)}

@app.post("/learn/approve")
async def learn_approve(question: str, answer: str, operator_id: str):
    raw = f"Вопрос: {question}\nОтвет: {answer}"
    splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)
    docs = splitter.create_documents([raw])
    
    model = get_model()
    vectors = model.encode([d.page_content for d in docs], convert_to_numpy=True).tolist()
    
    doc_id = str(uuid.uuid4())
    
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text("INSERT INTO documents (doc_id, source, collection) VALUES (:id, :src, :col) ON CONFLICT DO NOTHING"),
                {"id": doc_id, "src": f"learned_{operator_id}", "col": "learned"}
            )
            for i, chunk in enumerate(docs):
                await session.execute(
                    text("INSERT INTO chunks (doc_id, chunk_index, text, embedding) VALUES (:id, :idx, :txt, :emb::vector) ON CONFLICT DO NOTHING"),
                    {"id": doc_id, "idx": i, "txt": chunk.page_content, "emb": json.dumps(vectors[i])}
                )
        await session.commit()
    
    return {"status": "learned", "doc_id": doc_id}