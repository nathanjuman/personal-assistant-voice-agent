import asyncio
import contextlib
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import uvicorn
from IPython.core.magic_arguments import argument_group
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableGenerator
from langchain_core.tracers import event_stream
from langgraph.checkpoint.memory import InMemorySaver
from starlette.staticfiles import StaticFiles

from assemblyai_stt import AssemblyAISTT
from cartesia_tts import CartesiaTTS
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

# Static files are served from the shared web build output
STATIC_DIR = Path(__file__).parent.parent.parent / "web" / "dist"

if not STATIC_DIR.exists():
    raise RuntimeError(
        f"Web build not found at {STATIC_DIR}. "
        "Run 'make build-web' or 'make dev-py' from the project root."
    )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

system_prompt = ""

agent = create_agent(
    model=None,
    tools=[],
    system_prompt=system_prompt,
    checkpointer=InMemorySaver()
)



async def _stt_stream(audio_stream: AsyncIterator[bytes]) -> AsyncIterator[VoiceAgentEvent]:
    """Comment"""
    stt = AssemblyAISTT(sample_rate=16000)

    async def send_audio():
        """
        Background task that pumps audio chunks to Assembly (Producer).

        """
        try:
            # Stream each audio chunk to Assembly as it arrives
            async for audio_chunk in audio_stream:
                await stt.send_audio(audio_chunk)
        finally:
            await stt.close()

    # Launch audio sending task in background to simultaneously receive transcripts in main coroutine
    send_task = asyncio.create_task(send_audio())

    # Consumer loop: receive and yield transcription events as they arrive from AssemblyAI.
    try:
        # listens on the WebSocket for transcript events and yields them as they become available.
        async for event in stt.receive_events():
            yield event
    finally:
            # Cleanup: ensure background task is cancelled and awaited
            with contextlib.suppress(asyncio.CancelledError):
                send_task.cancel()
                await send_task
            # ensure ws connection is closed
            await stt.close()



async def _agent_stream(event_stream: AsyncIterator[VoiceAgentEvent]) -> AsyncIterator[VoiceAgentEvent]:
    """Comment"""

    thread_id = str(uuid4())  # Unique thread id to maintain conversation context across multiple turns (using agent checkpointer arg.)

    # Process each event as it arrives from upstream STT stage
    async for event in event_stream:
        yield event

        # When final transcript received -> invoke agent, stream agent response asynchronously
        if event.type == "stt_output":
            stream = agent.astream(
                {"messages": [HumanMessage(content=event.transcript)]},
                {"configurable": {"thread_id": thread_id}},
                stream_mode="messages" # Yields message chunks as they're generated
            )

        # Iterate through agent's streaming response
        # The response yields tuples of (message, metadata), we only need message
        async for message, metadata in stream:
            if isinstance(message, AIMessage): # Emit agent chunks
                # Extract and yield text from each message chunk
                yield AgentChunkEvent.create(message.text)
                # Emit tool calls if present
                if hasattr(message, "tool_calls") and message.tool_calls:
                    for tc in message.tool_calls:
                        yield ToolCallEvent.create(
                            id=tc.get("id", str(uuid4())),
                            name=tc.get("name", "unknown"),
                            args=tc.get("args", {})
                        )

            # Emit tool results (messages)
            if isinstance(message, ToolMessage):
                yield ToolResultEvent.create(
                    tool_call_id=getattr(message, "tool_call_id", ""),
                    name=getattr(message, "name", "unknown"),
                    result=str(message.content) if message.content else ""
                )

        # Signal end of agent response turn
        yield AgentEndEvent.create()


async def _tts_stream(event_stream: AsyncIterator[VoiceAgentEvent]) -> AsyncIterator[VoiceAgentEvent]:
    """Comment"""
    tts = CartesiaTTS()

    async def process_upstream() -> AsyncIterator[VoiceAgentEvent]:
        """Comment"""
        buffer: list[str] = []
        async for event in event_stream:
            yield event
            # Buffer agent text chunks
            if event.type == "agent_chunk":
                buffer.append(event.text)
            # Send all buffered text to Cartesia when agent finishes
            if event.type == "agent_end":
                await tts.send_text("".join(buffer))
                buffer = []

    try:
        # Merge the processed upstream events with TTS audio events, both streams run concurrently -> yielding events as they arrive
        async for event in merge_async_iters(process_upstream(), tts.receive_events()):
            yield event
    finally:
        await tts.close()

# pipeline
pipeline = (
    RunnableGenerator(_stt_stream)
    | RunnableGenerator(_agent_stream)
    | RunnableGenerator(_tts_stream)
)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def websocket_audio_stream() -> AsyncIterator[bytes]:
        while True:
            data = await websocket.receive_bytes()
            yield data

    output_audio_stream = pipeline.atransform(websocket_audio_stream())

    # Process events from pipeline and send back to client
    async for event in output_audio_stream:
        await websocket.send_json(event_to_dict(event))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host= "0.0.0.0", port=8000, reload=True)