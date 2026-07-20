from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    REVIEWING = "reviewing"
    BLOCKED = "blocked"
    DONE = "done"


class WriteStatus(str, Enum):
    NOT_WRITTEN = "not_written"
    WRITING = "writing"
    SUCCESS = "success"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


class RuleMatchMode(str, Enum):
    KEYWORD = "keyword"
    REGEX = "regex"
    SEMANTIC = "semantic"
