from __future__ import annotations

SymbolRow = tuple[str, str, str, str, int]
ScoredSymbol = tuple[float, SymbolRow]
ChannelResults = list[ScoredSymbol]
ChannelName = str
ChannelBundle = tuple[ChannelName, ChannelResults]
ReferenceRow = tuple[str, int]
CodeContext = tuple[str | None, str | None, list[str]]
