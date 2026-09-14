"""AIHOT v1 boundary. Validate the whole snapshot before touching SQLite."""
from datetime import date, datetime
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Schedule(Model):
    precision: str
    from_: AwareDatetime | None = Field(default=None, alias="from")
    through: AwareDatetime | None = None
    label: str = ""


class Post(Model):
    id: str
    publishedAt: AwareDatetime
    stage: str
    text: str
    originalText: str | None = None
    url: str


class Event(Model):
    id: str = Field(min_length=1)
    type: Literal["direct_reset", "reset_credit"]
    status: Literal["announced", "confirmed"]
    title: str
    scope: str = ""
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    confirmedAt: AwareDatetime | None = None
    occurredOn: date | None = None
    confirmationBasis: str | None = None
    schedule: Schedule | None = None
    posts: list[Post]
    url: str


class Snapshot(Model):
    schemaVersion: Literal[1]
    timezone: Literal["Asia/Shanghai"]
    checkedAt: AwareDatetime | None
    historyFrom: AwareDatetime
    count: int = Field(ge=0, le=10000)
    events: list[Event]

    @model_validator(mode="after")
    def complete(self):
        if self.count != len(self.events):
            raise ValueError("snapshot count mismatch")
        if len({e.id for e in self.events}) != self.count:
            raise ValueError("duplicate event ID")
        return self
