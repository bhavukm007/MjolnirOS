"""High-level memory commands, selective ingestion, and response generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.domain.memory import MemoryCategory, MemoryCreate, MemoryRecord, MemoryType
from backend.app.memory.importance import ImportanceScorer
from backend.app.memory.store import MemoryStore


@dataclass(frozen=True)
class ExtractedFact:
    key: str | None
    value: str
    memory_type: MemoryType
    category: MemoryCategory


class MemoryService:
    """Own memory policy so routing, storage, and responses remain consistent."""

    _NAME_QUERY = re.compile(r"^(?:what(?:'s| is) my name|who am i)\??$", re.I)
    _PROFILE_QUERY = re.compile(r"^what do you know about me\??$", re.I)
    _PROJECT_QUERY = re.compile(r"^what projects? am i working on\??$", re.I)
    _PREFERENCE_QUERY = re.compile(r"^what are my preferences\??$", re.I)
    _FAVOURITE_QUERY = re.compile(r"^what(?:'s| is) my favou?rite\s+(.+?)\??$", re.I)

    def __init__(self, store: MemoryStore, scorer: ImportanceScorer | None = None) -> None:
        self.store = store
        self.scorer = scorer or ImportanceScorer()

    def handle_command(self, message: str) -> str | None:
        """Execute explicit memory/task commands or answer memory queries."""
        cleaned = message.strip()
        normalized = cleaned.rstrip(".?!").strip()
        if match := re.match(r"^forget\s+(.+)$", normalized, re.I):
            forgotten = self.store.forget(match.group(1).strip())
            return (
                f"I forgot {len(forgotten)} matching memory item{'s' if len(forgotten) != 1 else ''}, Boss."
                if forgotten
                else "I couldn't find a matching memory to forget, Boss."
            )
        if match := re.match(r"^(?:remind me to|add (?:a )?todo(?: to)?|add to my todo list)\s+(.+)$", normalized, re.I):
            task = match.group(1).strip()
            self._save_fact(
                ExtractedFact(None, task, MemoryType.TODO, MemoryCategory.TASK),
                explicit=True,
                source="reminder_command",
            )
            return f"I'll remember this task: {task}, Boss."
        if match := re.match(r"^(?:remember(?: that)?\s+)(.+)$", normalized, re.I):
            statement = match.group(1).strip()
            facts = self.extract(statement)
            if not facts:
                facts = [
                    ExtractedFact(None, statement, MemoryType.FACT, MemoryCategory.LONG_TERM)
                ]
            for fact in facts:
                self._save_fact(fact, explicit=True, source="explicit_memory_command")
            return self._remembered_response(facts)
        if match := re.match(r"^update my name to\s+(.+)$", normalized, re.I):
            fact = ExtractedFact(
                "real_name", _clean_value(match.group(1)), MemoryType.PROFILE, MemoryCategory.USER_PROFILE
            )
            self._save_fact(fact, explicit=True, source="profile_update")
            return f"I've updated your name to {fact.value}, Boss."
        if self._NAME_QUERY.match(normalized):
            name = self._profile_value("real_name") or self._profile_value("preferred_name")
            if name:
                return f"Your name is {name}, but I'll continue calling you Boss."
            return "I don't have your name stored yet, Boss."
        if self._PROFILE_QUERY.match(normalized):
            return self._describe_profile()
        if self._PROJECT_QUERY.match(normalized):
            projects = self.store.list(MemoryType.PROJECT, limit=20)
            if not projects:
                return "I don't have any active projects stored for you, Boss."
            return "You're working on: " + ", ".join(item.content for item in projects) + ", Boss."
        if self._PREFERENCE_QUERY.match(normalized):
            preferences = self.store.list(MemoryType.PREFERENCE, limit=20)
            if not preferences:
                return "I don't have any preferences stored yet, Boss."
            return "Your stored preferences are: " + "; ".join(item.content for item in preferences) + "."
        if match := self._FAVOURITE_QUERY.match(normalized):
            subject = _normalize_key(match.group(1))
            memory = self.store.get_by_key(f"favourite_{subject}")
            if memory:
                return f"Your favourite {match.group(1)} is {memory.metadata.get('value', memory.content)}, Boss."
            return f"I don't have your favourite {match.group(1)} stored yet, Boss."
        facts = self.extract(normalized)
        if facts:
            saved = [
                self._save_fact(fact, explicit=False, source="profile_statement")
                for fact in facts
            ]
            saved = [item for item in saved if item is not None]
            if saved:
                return self._remembered_response(facts)
        return None

    def ingest(self, message: str) -> list[MemoryRecord]:
        """Promote only durable facts discovered in otherwise normal conversation."""
        records: list[MemoryRecord] = []
        for fact in self.extract(message):
            saved = self._save_fact(fact, explicit=False, source="automatic_extraction")
            if saved:
                records.append(saved)
        return records

    def record_conversation(self, role: str, content: str) -> MemoryRecord:
        record = self.store.save(
            MemoryCreate(
                memory_type=MemoryType.CONVERSATION,
                category=MemoryCategory.CONVERSATION,
                content=content,
                metadata={"role": role},
                importance=self.scorer.score(
                    content,
                    category=MemoryCategory.CONVERSATION,
                    memory_type=MemoryType.CONVERSATION,
                ),
                source="chat",
            )
        )
        self.store.prune_conversation()
        self._maybe_update_summary()
        return record

    def remember_installed_application(self, name: str, executable: str | None = None) -> None:
        normalized = _normalize_key(name)
        self.store.save(
            MemoryCreate(
                memory_type=MemoryType.INSTALLED_APPLICATION,
                category=MemoryCategory.USER_PROFILE,
                key=f"installed_application_{normalized}",
                content=name,
                metadata={"value": name, "executable": executable},
                importance=0.8,
                source="verified_launcher",
            )
        )

    def extract(self, statement: str) -> list[ExtractedFact]:
        value = statement.strip().rstrip(".?!")
        patterns: tuple[tuple[str, MemoryType, MemoryCategory, str], ...] = (
            (r"^(?:my name is|i am named)\s+(.+)$", MemoryType.PROFILE, MemoryCategory.USER_PROFILE, "real_name"),
            (r"^call me\s+(.+)$", MemoryType.PROFILE, MemoryCategory.USER_PROFILE, "preferred_name"),
            (r"^my nickname is\s+(.+)$", MemoryType.PROFILE, MemoryCategory.USER_PROFILE, "nickname"),
            (r"^(?:my college is|i study at|i go to)\s+(.+)$", MemoryType.PROFILE, MemoryCategory.USER_PROFILE, "college"),
            (r"^(?:my degree is|i am pursuing|i am studying)\s+(.+)$", MemoryType.PROFILE, MemoryCategory.USER_PROFILE, "degree"),
            (r"^my birthday is\s+(.+)$", MemoryType.PROFILE, MemoryCategory.USER_PROFILE, "birthday"),
        )
        for pattern, memory_type, category, key in patterns:
            if match := re.match(pattern, value, re.I):
                return [ExtractedFact(key, _clean_value(match.group(1)), memory_type, category)]
        if match := re.match(r"^(?:my )?favou?rite\s+(.+?)\s+is\s+(.+)$", value, re.I):
            subject, preference = match.groups()
            return [
                ExtractedFact(
                    f"favourite_{_normalize_key(subject)}",
                    _clean_value(preference),
                    MemoryType.PREFERENCE,
                    MemoryCategory.USER_PROFILE,
                )
            ]
        if match := re.match(r"^i prefer\s+(.+)$", value, re.I):
            preference = _clean_value(match.group(1))
            return [
                ExtractedFact(
                    f"preference_{_normalize_key(preference)[:80]}",
                    preference,
                    MemoryType.PREFERENCE,
                    MemoryCategory.USER_PROFILE,
                )
            ]
        if match := re.match(r"^(?:i am working on|i'm working on|my project is)\s+(.+)$", value, re.I):
            project = _clean_value(match.group(1))
            return [
                ExtractedFact(
                    f"project_{_normalize_key(project)[:80]}",
                    project,
                    MemoryType.PROJECT,
                    MemoryCategory.TASK,
                )
            ]
        if match := re.match(r"^(?:my goal is|i want to achieve)\s+(.+)$", value, re.I):
            goal = _clean_value(match.group(1))
            return [ExtractedFact(f"goal_{_normalize_key(goal)[:80]}", goal, MemoryType.GOAL, MemoryCategory.TASK)]
        if match := re.match(r"^(?:my deadline is|the deadline is)\s+(.+)$", value, re.I):
            deadline = _clean_value(match.group(1))
            return [ExtractedFact(f"deadline_{_normalize_key(deadline)[:80]}", deadline, MemoryType.DEADLINE, MemoryCategory.TASK)]
        if " is " in value and len(value) <= 300:
            subject, fact_value = value.split(" is ", 1)
            if re.match(r"^(?:my|our)\s+", subject, re.I):
                return [
                    ExtractedFact(
                        _normalize_key(subject),
                        _clean_value(fact_value),
                        MemoryType.FACT,
                        MemoryCategory.LONG_TERM,
                    )
                ]
        return []

    def _save_fact(
        self, fact: ExtractedFact, *, explicit: bool, source: str
    ) -> MemoryRecord | None:
        score = self.scorer.score(
            fact.value,
            explicit=explicit,
            category=fact.category,
            memory_type=fact.memory_type,
        )
        if not explicit and not self.scorer.should_promote(score):
            return None
        label = fact.key.replace("_", " ") if fact.key else "fact"
        content = (
            f"{label}: {fact.value}"
            if fact.category is MemoryCategory.USER_PROFILE and fact.key
            else fact.value
        )
        return self.store.save(
            MemoryCreate(
                memory_type=fact.memory_type,
                category=fact.category,
                key=fact.key,
                content=content,
                metadata={"value": fact.value},
                importance=score,
                source=source,
            )
        )

    def _profile_value(self, key: str) -> str | None:
        item = self.store.get_by_key(key)
        if not item:
            return None
        return str(item.metadata.get("value", item.content))

    def _describe_profile(self) -> str:
        profile = self.store.profile()
        if not profile.fields and not profile.facts:
            return "I don't have any durable profile information stored yet, Boss."
        labels = {
            key.replace("_", " "): value
            for key, value in profile.fields.items()
            if not key.startswith("installed_application_")
        }
        details = [f"{label}: {value}" for label, value in labels.items()]
        details.extend(profile.facts)
        return "Here's what I know about you: " + "; ".join(details) + "."

    def _remembered_response(self, facts: list[ExtractedFact]) -> str:
        if len(facts) == 1:
            fact = facts[0]
            if fact.key == "real_name":
                return f"I'll remember that your name is {fact.value}, Boss."
            if fact.key and fact.key.startswith("favourite_"):
                subject = fact.key.removeprefix("favourite_").replace("_", " ")
                return f"I'll remember that your favourite {subject} is {fact.value}, Boss."
            return f"I'll remember that, Boss: {fact.value}."
        return f"I've saved {len(facts)} important details, Boss."

    def _maybe_update_summary(self) -> None:
        turns = self.store.recent_conversation(limit=8)
        if len(turns) < 8:
            return
        user_turns = [item for item in turns if item.metadata.get("role") == "user"]
        if len(user_turns) < 4:
            return
        summary = " | ".join(
            f"{item.metadata.get('role', 'unknown')}: {item.content[:400]}" for item in turns
        )
        self.store.save(
            MemoryCreate(
                memory_type=MemoryType.CONVERSATION_SUMMARY,
                category=MemoryCategory.CONVERSATION,
                key="rolling_conversation_summary",
                content=summary[:4000],
                importance=0.6,
                source="conversation_summarizer",
            )
        )


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _clean_value(value: str) -> str:
    return value.strip().strip('"\'').rstrip(".?!")
