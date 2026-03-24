## Dependencies
- fastapi
- python-dotenv
- uvicorn
- websocket


stt_chunk	  STT → Client	| Partial transcription (real-time feedback)
stt_output	  STT → Agent |	Final transcription
agent_chunk	  Agent → TTS	| Text chunk from agent response
tool_call	  Agent → Client|	Tool invocation
tool_result	Agent → Client|	Tool execution result
agent_end	    Agent → TTS	|   Signals end of agent turn
tts_chunk	   TTS → Client |	Audio chunk for playback