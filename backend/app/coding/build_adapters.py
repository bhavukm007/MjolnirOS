"""Replaceable local Docker, package, language, and template adapters."""
from __future__ import annotations
from pathlib import Path
import subprocess
from typing import Callable
from backend.app.domain.build import BuildLanguage, PackageManager

Runner = Callable[..., subprocess.CompletedProcess[str]]

class DockerAdapter:
    """Run narrowly scoped local Docker CLI operations."""
    def __init__(self, runner: Runner) -> None: self._runner = runner
    def execute(self, args: list[str], path: Path) -> subprocess.CompletedProcess[str]:
        return self._runner(["docker", *args], cwd=str(path), text=True, capture_output=True, check=False)

class DependencyAdapter:
    """Translate supported package managers into non-global local commands."""
    def command(self, manager: PackageManager, global_install: bool) -> list[str]:
        if manager == "pip": return ["python", "-m", "pip", "install", "-r", "requirements.txt"]
        if manager == "npm": return ["npm", "install", *( ["--global"] if global_install else [])]
        if manager == "maven": return ["mvn", "dependency:resolve"]
        return ["gradle", "dependencies"]

class LanguageAdapter:
    """Provide deterministic compile and run commands for supported languages."""
    def commands(self, language: BuildLanguage) -> tuple[list[str] | None, list[str]]:
        mapping = {
            "python": (None, ["python", "main.py"]), "flask": (None, ["flask", "--app", "app", "run"]),
            "fastapi": (None, ["uvicorn", "main:app"]), "cpp": (["g++", "main.cpp", "-o", "app"], [".\\app"]),
            "java": (["javac", "Main.java"], ["java", "Main"]), "javascript": (None, ["npm", "run", "start"]),
            "sql": (None, ["sqlite3", "database.db", ".read schema.sql"]),
        }
        return mapping[language]

class TemplateGenerator:
    """Write minimal runnable local project templates without network access."""
    def generate(self, root: Path, language: BuildLanguage, name: str) -> list[Path]:
        project = root / name
        project.mkdir(parents=True, exist_ok=False)
        files = self._files(language, name)
        for relative, content in files.items():
            target = project / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content, encoding="utf-8")
        return [project / relative for relative in files]
    @staticmethod
    def _files(language: BuildLanguage, name: str) -> dict[str, str]:
        common = {"README.md": f"# {name}\n\nGenerated locally by MjolnirOS.\n"}
        templates: dict[BuildLanguage, dict[str, str]] = {
            "python": {"main.py": "def main() -> None:\n    print('Hello from Python')\n\nif __name__ == '__main__':\n    main()\n"},
            "flask": {"app.py": "from flask import Flask\n\napp = Flask(__name__)\n\n@app.get('/')\ndef health() -> dict[str, str]:\n    return {'status': 'ok'}\n", "requirements.txt": "Flask\n"},
            "fastapi": {"main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health() -> dict[str, str]:\n    return {'status': 'ok'}\n", "requirements.txt": "fastapi\nuvicorn\n"},
            "cpp": {"main.cpp": "#include <iostream>\nint main() { std::cout << \"Hello from C++\\n\"; }\n", "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\nproject(app)\nadd_executable(app main.cpp)\n"},
            "java": {"Main.java": "public class Main { public static void main(String[] args) { System.out.println(\"Hello from Java\"); } }\n"},
            "javascript": {"index.js": "console.log('Hello from JavaScript');\n", "package.json": '{"name":"' + name + '","private":true,"scripts":{"start":"node index.js"}}\n'},
            "sql": {"schema.sql": "CREATE TABLE IF NOT EXISTS health (status TEXT NOT NULL);\nINSERT INTO health(status) VALUES ('ok');\n"},
        }
        return {**common, **templates[language]}
