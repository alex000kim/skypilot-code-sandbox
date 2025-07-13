import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional

from docker.types import Mount
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from llm_sandbox import SandboxSession
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authentication setup
security = HTTPBearer()

def get_auth_token() -> str:
    """Get the authentication token from environment variables."""
    token = os.getenv("AUTH_TOKEN")
    if not token:
        raise ValueError("AUTH_TOKEN environment variable not set")
    return token

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """Verify the provided token against the configured auth token."""
    expected_token = get_auth_token()
    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True

class CodeExecutionRequest(BaseModel):
    code: str
    language: str = "python"
    libraries: Optional[List[str]] = None
    timeout: Optional[int] = 30
    session_id: Optional[str] = None

class CodeExecutionResponse(BaseModel):
    success: bool
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    execution_time: Optional[float] = None
    error: Optional[str] = None
    session_id: Optional[str] = None

class SessionPoolConfig(BaseModel):
    max_sessions_per_language: int = 5
    session_timeout: int = 300
    cleanup_interval: int = 60

@dataclass
class PooledSession:
    session: SandboxSession
    last_used: float
    language: str
    libraries: List[str]
    session_id: str
    created_at: float

class SessionPool:
    def __init__(self, config: SessionPoolConfig):
        self.config = config
        self.sessions: Dict[str, Dict[str, PooledSession]] = defaultdict(dict)
        self.lock = Lock()
        self.cleanup_task = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        async def cleanup_expired_sessions():
            while True:
                try:
                    await asyncio.sleep(self.config.cleanup_interval)
                    await self._cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")

        self.cleanup_task = asyncio.create_task(cleanup_expired_sessions())

    async def _cleanup_expired_sessions(self):
        current_time = time.time()
        expired_sessions = []
        
        with self.lock:
            for lang, lang_sessions in self.sessions.items():
                for session_id, pooled_session in list(lang_sessions.items()):
                    if current_time - pooled_session.last_used > self.config.session_timeout:
                        expired_sessions.append((lang, session_id, pooled_session))
                        del lang_sessions[session_id]

        for lang, session_id, pooled_session in expired_sessions:
            try:
                pooled_session.session.__exit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing session {session_id}: {e}")

    def get_session(self, language: str, libraries: List[str], session_id: Optional[str] = None) -> PooledSession:
        libraries = libraries or []
        current_time = time.time()

        with self.lock:
            lang_sessions = self.sessions[language]
            
            if session_id and session_id in lang_sessions:
                pooled_session = lang_sessions[session_id]
                if set(pooled_session.libraries) == set(libraries):
                    pooled_session.last_used = current_time
                    return pooled_session
                else:
                    old_session = lang_sessions.pop(session_id)
                    try:
                        old_session.session.__exit__(None, None, None)
                    except Exception as e:
                        logger.error(f"Error closing session: {e}")

            for sid, pooled_session in lang_sessions.items():
                if set(pooled_session.libraries) == set(libraries):
                    pooled_session.last_used = current_time
                    return pooled_session

            if len(lang_sessions) < self.config.max_sessions_per_language:
                return self._create_new_session(language, libraries, current_time)
            
            oldest_session = min(lang_sessions.values(), key=lambda s: s.last_used)
            old_session = lang_sessions.pop(oldest_session.session_id)
            try:
                old_session.session.__exit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing session: {e}")
            
            return self._create_new_session(language, libraries, current_time)

    def _create_new_session(self, language: str, libraries: List[str], current_time: float) -> PooledSession:
        session_id = str(uuid.uuid4())
        
        try:
            session = SandboxSession(
                lang=language,
                keep_template=True,
                verbose=False,
                mounts=[
                    Mount(
                        type="bind",
                        source="/bucket_data",
                        target="/data",
                        read_only=True
                    )
                ]
            )
            session.__enter__()
            
            if libraries:
                try:
                    result = session.run("", libraries=libraries)
                    if result.exit_code != 0:
                        logger.warning(f"Failed to install libraries: {result.stderr}")
                except Exception as e:
                    logger.warning(f"Error installing libraries: {e}")
            
            pooled_session = PooledSession(
                session=session,
                last_used=current_time,
                language=language,
                libraries=libraries,
                session_id=session_id,
                created_at=current_time
            )
            
            self.sessions[language][session_id] = pooled_session
            return pooled_session
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def return_session(self, session_id: str, language: str):
        with self.lock:
            lang_sessions = self.sessions.get(language, {})
            if session_id in lang_sessions:
                lang_sessions[session_id].last_used = time.time()

    def get_pool_stats(self) -> Dict[str, Any]:
        with self.lock:
            stats = {
                "total_sessions": sum(len(lang_sessions) for lang_sessions in self.sessions.values()),
                "sessions_by_language": {
                    lang: len(lang_sessions) for lang, lang_sessions in self.sessions.items()
                },
                "config": {
                    "max_sessions_per_language": self.config.max_sessions_per_language,
                    "session_timeout": self.config.session_timeout,
                    "cleanup_interval": self.config.cleanup_interval
                }
            }
        return stats

    async def shutdown(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        with self.lock:
            for lang, lang_sessions in self.sessions.items():
                for session_id, pooled_session in lang_sessions.items():
                    try:
                        pooled_session.session.__exit__(None, None, None)
                    except Exception as e:
                        logger.error(f"Error closing session {session_id}: {e}")
            self.sessions.clear()

session_pool = SessionPool(SessionPoolConfig())

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting API")
    # Verify auth token is configured
    try:
        get_auth_token()
        logger.info("Authentication token configured successfully")
    except ValueError as e:
        logger.error(f"Authentication setup failed: {e}")
        raise
    yield
    await session_pool.shutdown()

app = FastAPI(title="Remote Code Execution API", lifespan=lifespan)

@app.get("/health")
async def health_check(authenticated: bool = Depends(verify_token)):
    return {"status": "healthy"}

@app.get("/pool/stats")
async def get_pool_stats(authenticated: bool = Depends(verify_token)):
    return session_pool.get_pool_stats()

@app.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(request: CodeExecutionRequest, authenticated: bool = Depends(verify_token)):
    try:
        pooled_session = session_pool.get_session(
            request.language, 
            request.libraries or [], 
            request.session_id
        )
        
        result = await asyncio.get_event_loop().run_in_executor(
            None, _execute_code_with_session, pooled_session, request
        )
        
        session_pool.return_session(pooled_session.session_id, request.language)
        result.session_id = pooled_session.session_id
        
        return result
        
    except Exception as e:
        logger.error(f"Error executing code: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def _execute_code_with_session(pooled_session: PooledSession, request: CodeExecutionRequest) -> CodeExecutionResponse:
    start_time = time.time()
    
    try:
        result = pooled_session.session.run(request.code)
        execution_time = time.time() - start_time
        
        return CodeExecutionResponse(
            success=result.exit_code == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            execution_time=execution_time
        )
        
    except Exception as e:
        execution_time = time.time() - start_time
        return CodeExecutionResponse(
            success=False,
            error=str(e),
            execution_time=execution_time
        )

@app.post("/session/create")
async def create_session(language: str = "python", libraries: Optional[List[str]] = None, authenticated: bool = Depends(verify_token)):
    try:
        pooled_session = session_pool.get_session(language, libraries or [])
        return {
            "session_id": pooled_session.session_id,
            "language": language,
            "libraries": libraries or [],
            "created_at": pooled_session.created_at
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/session/{session_id}")
async def close_session(session_id: str, authenticated: bool = Depends(verify_token)):
    try:
        with session_pool.lock:
            for lang, lang_sessions in session_pool.sessions.items():
                if session_id in lang_sessions:
                    pooled_session = lang_sessions.pop(session_id)
                    try:
                        pooled_session.session.__exit__(None, None, None)
                        return {"message": f"Session {session_id} closed"}
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=str(e))
            
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/languages")
async def get_supported_languages(authenticated: bool = Depends(verify_token)):
    return {
        "languages": [
            "python",
            "javascript", 
            "java",
            "cpp",
            "go",
            "r"
        ]
    }

@app.get("/")
async def root():
    return {
        "message": "Remote Code Execution API",
        "version": "1.0.0",
        "authentication": "required"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)