import os
import asyncio
import argparse
import concurrent.futures
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from marker.logger import configure_logging  # Import logging configuration
from marker.models import load_all_models  # Import function to load models
from marker_api.routes import (
    process_pdf_file,
)
from marker_api.utils import print_markerapi_text_art
import gradio as gr
from marker_api.model.schema import (
    BatchConversionResponse,
    ConversionResponse,
    HealthResponse,
    ServerType,
)
from marker_api.demo import marker_ui
from typing import Union
from marker_api import cache as conversion_cache


# Initialize logging
configure_logging()
logger = logging.getLogger(__name__)

# Global variable to hold model list
model_list = None


# Event that runs on startup to load all models
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model_list
    logger.debug("--------------------- Loading OCR Model -----------------------")
    print_markerapi_text_art()
    model_list = load_all_models()
    yield


# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# 转换失败时返回 JSON(而不是 uvicorn 默认的纯文本 "Internal Server Error"),
# 否则调用方(如 marker-ui) response.json() 会抛出难以定位的 JSONDecodeError。
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "Error", "error": f"{type(exc).__name__}: {exc}"},
    )



@app.get("/health", response_model=HealthResponse)
def server():
    """
    Root endpoint to check server status.
    """
    return HealthResponse(message="Welcome to Marker-api", type=ServerType.simple)


# Endpoint to convert a single PDF to markdown
@app.post("/convert", response_model=ConversionResponse)
async def convert_pdf_to_markdown(pdf_file: UploadFile, max_pages: Union[int, None] = 10,
                                  start_page: Union[int, None] = 0, langs: Union[str, None] = None,
                                  batch_multiplier: Union[int, None] =  2):
    """
    Endpoint to convert a single PDF to markdown.
    """
    logger.info(f"Received file: {pdf_file.filename}")
    file = await pdf_file.read()
    key = conversion_cache.make_cache_key(file, max_pages, start_page, langs)

    cached = conversion_cache.load(key)
    if cached is not None:
        logger.info(f"Cache hit: {key}")
        # 返回本次请求的 Upload Name,而不是首次转换时的名字
        cached["filename"] = pdf_file.filename
        return ConversionResponse(status="Success", result=cached)

    response = process_pdf_file(file, pdf_file.filename, model_list,
                                max_pages=max_pages, start_page=start_page,
                                langs=langs, batch_multiplier=batch_multiplier)
    if conversion_cache.save(key, response):
        logger.debug(f"Saved cache: {key}")
    return ConversionResponse(status="Success", result=response)


# Endpoint to convert multiple PDFs to markdown
@app.post("/batch_convert", response_model=BatchConversionResponse)
async def convert_pdfs_to_markdown(pdf_files: List[UploadFile] = File(...)):
    """
    Endpoint to convert multiple PDFs to markdown.
    """
    logger.debug(f"Received {len(pdf_files)} files for batch conversion")

    async def process_files(files):
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            coroutines = [
                loop.run_in_executor(
                    pool, process_pdf_file, await file.read(), file.filename, model_list
                )
                for file in files
            ]
            return await asyncio.gather(*coroutines)

    responses = await process_files(pdf_files)
    return BatchConversionResponse(results=responses)

app = gr.mount_gradio_app(app, marker_ui, path="/ui", root_path="/ui")

# Main function to run the server
def main():
    parser = argparse.ArgumentParser(description="Run the marker-api server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host IP address")
    parser.add_argument("--port", type=int, default=8080, help="Port number")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("server:app", host=args.host, port=args.port)


# Entry point to start the server
if __name__ == "__main__":
    main()
