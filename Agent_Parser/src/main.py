import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from routers.parser_post import router as parser_router

app = FastAPI(title="Facebook Parser API", version="1.0.0")

# Cấu hình CORS cho phép tất cả các địa chỉ (bao gồm cả 127.0.0.1) truy cập đến
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các origin
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các phương thức POST, GET, v.v.
    allow_headers=["*"],  # Cho phép tất cả các header
)

# đăng ký router
app.include_router(parser_router)


@app.get("/")
def root():
    return {"status": "running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
