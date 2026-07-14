"""Small CDP probe for validating the running MjolnirOS Electron renderer."""

from __future__ import annotations

import argparse
import base64
import json
import wave
from urllib.request import urlopen

import websocket


def evaluate(expression: str) -> object:
    pages = json.load(urlopen("http://127.0.0.1:9222/json/list", timeout=5))
    page = next(item for item in pages if item.get("type") == "page")
    connection = websocket.create_connection(
        page["webSocketDebuggerUrl"], suppress_origin=True, timeout=120
    )
    try:
        connection.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                }
            )
        )
        response = json.loads(connection.recv())
    finally:
        connection.close()
    if "exceptionDetails" in response.get("result", {}):
        raise RuntimeError(response["result"]["exceptionDetails"])
    return response["result"]["result"].get("value")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("body", "state", "resources", "pause-voice", "resume-voice", "reset-voice", "submit", "inject-wav", "inject-wav-runtime"))
    parser.add_argument("text", nargs="?", default="")
    arguments = parser.parse_args()
    if arguments.action == "body":
        print(evaluate("document.body.innerText"))
        return
    if arguments.action == "state":
        print(evaluate("window.__mjolnirVoiceRuntime?.voiceState"))
        return
    if arguments.action == "resources":
        print(evaluate("(() => { const r=window.__mjolnirVoiceRuntime; return {sessionId:r?.sessionId ?? null, stream:Boolean(r?.stream), liveTracks:r?.stream?.getTracks().filter(t=>t.readyState==='live').length ?? 0, mediaRecorder:Boolean(r?.mediaRecorder), audioContext:r?.audioContext?.state ?? null, processor:Boolean(r?.processor)}; })()"))
        return
    if arguments.action == "pause-voice":
        print(evaluate("(async () => { const r=window.__mjolnirVoiceRuntime; await r.pause(); return {state:r.voiceState,sessionId:r.sessionId,stream:Boolean(r.stream),audioContext:r.audioContext?.state ?? null,processor:Boolean(r.processor)}; })()"))
        return
    if arguments.action == "resume-voice":
        print(evaluate("(async () => { const r=window.__mjolnirVoiceRuntime; await r.resume(); return {state:r.voiceState,sessionId:r.sessionId,stream:Boolean(r.stream),liveTracks:r.stream?.getTracks().filter(t=>t.readyState==='live').length ?? 0,audioContext:r.audioContext?.state ?? null,processor:Boolean(r.processor)}; })()"))
        return
    if arguments.action == "reset-voice":
        print(
            evaluate(
                "(async () => { const runtime = window.__mjolnirVoiceRuntime; "
                "await runtime.stop(); await runtime.start(); return runtime.voiceState; })()"
            )
        )
        return
    if arguments.action in {"inject-wav", "inject-wav-runtime"}:
        with wave.open(arguments.text, "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                raise ValueError("Voice fixture must be 16 kHz mono signed 16-bit PCM.")
            pcm = source.readframes(source.getnframes())
        # Feed deterministic trailing silence so the live Vosk recognizer emits
        # a final hypothesis just as it does after a user stops speaking.
        pcm += b"\x00\x00" * 16_000
        chunks = [base64.b64encode(pcm[index:index + 8192]).decode("ascii") for index in range(0, len(pcm), 8192)]
        payload = json.dumps(chunks)
        if arguments.action == "inject-wav-runtime":
            print(evaluate(
                f"(async () => {{ const r=window.__mjolnirVoiceRuntime; const context=r.audioContext; "
                "const callback=r.processor?.onaudioprocess; if(r.processor) r.processor.onaudioprocess=null; "
                "r.capturePaused=false; r.audioContext={sampleRate:16000}; try { "
                f"for(const encoded of {payload}) {{ const raw=atob(encoded); const samples=new Float32Array(raw.length/2); "
                "for(let i=0;i<samples.length;i++){let value=raw.charCodeAt(i*2)|(raw.charCodeAt(i*2+1)<<8);if(value>=32768)value-=65536;samples[i]=value/32768;} "
                "r.process(samples); await r.chain; } return r.voiceState; "
                "} finally { r.audioContext=context; if(r.processor) r.processor.onaudioprocess=callback; r.capturePaused=r.manuallyPaused||r.pipelineBusy; } })()"
            ))
            return
        print(evaluate(
            f"(async () => {{ const r=window.__mjolnirVoiceRuntime; "
            f"const prior=r.capturePaused; r.capturePaused=true; const out=[]; try {{ for (const audio_base64 of {payload}) {{ "
            "const response=await fetch('http://127.0.0.1:8000/api/v1/voice/sessions/'+r.sessionId+'/audio',"
            "{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({audio_base64})});"
            "out.push(await response.json()); } return out; } finally { r.capturePaused=prior; } })()"
        ))
        return
    message = json.dumps(arguments.text)
    expression = f"""
    (() => {{
      const input = document.querySelector('input[placeholder="Type a command or say Mjolnir"]');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, {message});
      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
      input.form.requestSubmit();
      return 'submitted';
    }})()
    """
    print(evaluate(expression))


if __name__ == "__main__":
    main()
