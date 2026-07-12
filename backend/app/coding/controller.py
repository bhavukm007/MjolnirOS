"""Local terminal, analysis, and project-generation controller."""
from pathlib import Path
import subprocess
from backend.app.domain.coding import CodingRequest,CodingResult
class CodingController:
    """Perform explicit local development actions without cloud execution."""
    def execute(self,r:CodingRequest)->CodingResult:
        path=Path(r.project_path or ".").resolve()
        if r.action=="terminal":
            if not r.confirmed:return CodingResult(success=False,message="Confirmation is required before running a terminal command.",confirmation_required=True)
            result=subprocess.run(r.command or "",cwd=path,shell=True,text=True,capture_output=True)
            return CodingResult(success=result.returncode==0,message="Command completed." if result.returncode==0 else "Command failed.",data={"stdout":result.stdout,"stderr":result.stderr,"returncode":result.returncode,"compilation_error":self._error(result.stderr)})
        if r.action=="explain":return CodingResult(success=True,message="Code explained.",data={"explanation":self._explain(r.code or "",r.language)})
        if r.action=="debug":return CodingResult(success=True,message="Debug analysis completed.",data={"suggestion":self._debug(r.prompt or r.code or "")})
        if r.action=="generate_project":
            name=(r.prompt or "project").replace(" ","_"); target=path/name; target.mkdir(parents=True,exist_ok=True); (target/"README.md").write_text(f"# {name}\n",encoding="utf-8")
            return CodingResult(success=True,message="Project generated.",data={"path":str(target)})
        if r.action=="dependencies":
            if not r.confirmed:return CodingResult(success=False,message="Confirmation is required before changing dependencies.",confirmation_required=True)
            return CodingResult(success=True,message="Dependency command approved for local execution.")
        return CodingResult(success=False,message="Unsupported coding action.")
    @staticmethod
    def _error(stderr:str)->str|None:return stderr.strip() or None
    @staticmethod
    def _explain(code:str,language:str)->str:return f"{language} code with {len(code.splitlines())} line(s)."
    @staticmethod
    def _debug(text:str)->str:return "Review the reported error, validate inputs, and run the smallest reproducible command: " + text[:500]
