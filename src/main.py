import asyncio
import contextlib
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableGenerator
from langgraph.checkpoint.memory import InMemorySaver
from starlette.staticfiles import StaticFiles

from assemblyai_stt import AssemblyAISTT
from components.python.src.cartesia_tts import CartesiaTTS
from events import (
    AgentChunkEvent,
    AgentEndEvent,
    ToolCallEvent,
    ToolResultEvent,
    VoiceAgentEvent,
    event_to_dict,
)
from utils import merge_async_iters


load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

system_prompt = ""

# stt stream
# send audio background task

# agent stream

# tts stream
# process upstream tts events

# pipeline
pipeline = pipeline(
    RunnableGenerator(_stt_stream),
)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def websocket_audio_stream() -> AsyncGenerator[bytes]:
        while True:
            data = await websocket.receive_bytes()
            yield data
            
    output_audio_stream = pipeline.atransform(websocket_audio_stream())

    # Process events from pipeline and send back to client
    async for event in output_audio_stream:
        await websocket.send_json(event_to_dict(event))

if __name__ == "__main__":
    uvicorn.run(main:app, host="0.0.0.0", port=8000, reload=True)