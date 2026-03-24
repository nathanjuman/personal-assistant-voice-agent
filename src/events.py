import base64
import time
from dataclasses import dataclass
from typing import Literal, Union

def _now_ms() -> int:
    """Returns current Unix timestamp in ms"""
    return int(time.time() * 1000)

@dataclass
class UserInputEvent:
    """
    Event is produced when raw audio data is received from the user.
    This is the entry point of the voice agent pipeline. Audio should be in PCM format processing by the STT stage.
    """
    type: Literal["user_input"]
    audio: bytes
    """
    PCM audio data from user microphone.
    Expected format: 16-bit signed int, mono channel, 16 kHz sample rate
    """
    ts: int # unix timestamp

    @classmethod
    def create(cls, audio: bytes) -> "UserInputEvent":
        """Creates UserInputEvent with current timestamp."""
        return cls(type="user_input", audio=audio, ts=_now_ms())

@dataclass
class STTChunkEvent:
    """
    Event produced during STT processing for partial transcription results, allowing for real-time display of transcription progress to user
    """
    type: Literal["stt_chunk"]
    transcript: str # Partial transcript from STT service, not final as it may be revised as more audio context becomes available
    ts: int

    @classmethod
    def create(cls, transcript: str) -> "STTChunkEvent":
        return cls(type="stt_chunk", transcript=transcript, ts=_now_ms())

@dataclass
class STTOutputEvent:
    """Event produced when final transcription result is processed."""
    type: Literal["stt_output"]
    transcript: str # Final Transcript
    ts: int

    @classmethod
    def create(cls, transcript: str) -> "STTOutputEvent":
        return cls(type="stt_output", transcript=transcript, ts=_now_ms())

STTEvent = Union[STTChunkEvent, STTOutputEvent]

@dataclass
class AgentChunkEvent:
    """Event produced during agent response generation, enables real time display of agents response"""
    type: Literal["agent_chunk"]
    text: str # Partial text chunk from agent's streaming response
    ts: int

    @classmethod
    def create(cls, text: str) -> "AgentChunkEvent":
        return cls(type="agent_chunk", text=text, ts=_now_ms())

@dataclass
class AgentEndEvent:
    """Event produced after agent's response is finished generating, signals downstream that turn is over (no more text is coming)"""
    type: Literal["agent_end"]
    ts: int

    @classmethod
    def create(cls, text: str) -> "AgentEndEvent":
        return cls(type="agent_end", ts=_now_ms())

@dataclass
class ToolCallEvent:
    """Event produced when tool is invoked, provides visibility into which tools are being called by the agent."""
    type: Literal["tool_call"]
    id: str # Unique id for tool invocation
    name: str # Name of the tool
    args: dict # Arguments passed into the tool
    ts: int

    @classmethod
    def create(cls, id: str, name: str, args: dict) -> "ToolCallEvent":
        return cls(type="tool_call", id=id, name=name, args=args, ts=_now_ms())

@dataclass
class ToolResultEvent:
    """Event produced when tool completes execution and returns result"""
    type: Literal["tool_result"]
    tool_call_id: str
    name: str
    result: str
    ts: int

    @classmethod
    def create(cls, tool_call_id: str, name: str, result: str) -> "ToolResultEvent":
        return cls(
            type="tool_result",
            tool_call_id=tool_call_id,
            name=name,
            result=result,
            ts=_now_ms(),
        )

AgentEvent = Union[AgentChunkEvent, AgentEndEvent, ToolCallEvent, ToolResultEvent]
"""
Union type of all agent-related events, enables type-safe handling of the stages in the agent response generation.
"""

@dataclass
class TTSChunkEvent:
    """Event produced during TTS synthesis for streaming audio chunks, enables real-time playback of the agents response while the synthesis is still finishing."""
    type: Literal["tts_chunk"]
    audio: bytes # encoded as base64 when serialized to JSON for transition, can be played immediately as it arrives.
    ts: int

    @classmethod
    def create(cls, audio: bytes) -> "TTSChunkEvent":
        return cls(type="tts_chunk", audio=audio, ts=_now_ms())

VoiceAgentEvent = Union[UserInputEvent, STTEvent, AgentEvent, TTSChunkEvent]

def event_to_dict(event: VoiceAgentEvent) -> dict:
    """Converts VoiceAgentEvent to JSON-serializable dict."""
    if isinstance(event, UserInputEvent):
        return {"type": event.type, "ts": event.ts}
    elif isinstance(event, STTChunkEvent):
        return {"type": event.type, "transcript": event.transcript, "ts": event.ts}
    elif isinstance(event, STTOutputEvent):
        return {"type": event.type, "transcript": event.transcript, "ts": event.ts}
    elif isinstance(event, AgentChunkEvent):
        return {"type": event.type, "text": event.text, "ts": event.ts}
    elif isinstance(event, AgentEndEvent):
        return {"type": event.type, "ts": event.ts}
    elif isinstance(event, ToolCallEvent):
        return {
            "type": event.type,
            "id": event.id,
            "name": event.name,
            "args": event.args,
            "ts": event.ts,
        }
    elif isinstance(event, ToolResultEvent):
        return {
            "type": event.type,
            "tool_call_id": event.tool_call_id,
            "name": event.name,
            "result": event.result,
            "ts": event.ts,
        }
    elif isinstance(event, TTSChunkEvent):
        return {
            "type": event.type,
            "audio": base64.b64encode(event.audio).decode("ascii"),
            "ts": event.ts,
        }
    else:
        raise ValueError(f"Unknown event type: {type(event)}")