from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
load_dotenv()

loader=PyPDFLoader("E:/Coding/AI_ML/Full_Stack_AI/proj/projects/21_chat_with_resume/resume.pdf")
docs=loader.load()

text_splitter=RecursiveCharacterTextSplitter(
  chunk_size=700,chunk_overlap=350
)
chunks=text_splitter.split_documents(documents=docs)

vector_store=QdrantVectorStore.from_documents(
  documents=chunks,
  embedding=OpenAIEmbeddings(model="text-embedding-3-large"),
  url="http://localhost:6333",
  collection_name="resume_rag"
)
print("Indexing of the documents is done successfully")

