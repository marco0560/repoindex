"""Shared type aliases used across repoindex modules."""

from __future__ import annotations

import ast
from pathlib import Path

SymbolRow = tuple[str, str, str, str, int]
ScoredSymbol = tuple[float, SymbolRow]
ChannelResults = list[ScoredSymbol]
ChannelName = str
ChannelBundle = tuple[ChannelName, ChannelResults]
ReferenceRow = tuple[str, int]
IncludeEdgeRow = tuple[str, str, str, int]
CodeContext = tuple[str | None, str | None, list[str]]
CacheType = dict[Path, tuple[str, list[str], ast.Module]]
