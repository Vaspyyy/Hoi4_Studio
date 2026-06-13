"""
HOI4 Modding Studio - Paradox Script Parser

Tokenizer and parser for Paradox script files (.txt, .gfx, .mod, .yml).
Handles nested braces, quoted strings, comments, and bare identifiers.

TODO: Save Importer (src/save_importer.py)
  HOI4 saves are 50-400 MB (uncompressed: 200 MB - 2 GB). This parser
  loads the entire tree in memory — unusable for saves. Need a streaming
  scanner that:
  1. Byte-scans for top-level section boundaries (countries={, states={, date=)
  2. Brace-extracts each section substring (extract_braced_block)
  3. Feeds individual sub-blocks to the existing parser (1-20 MB each)
  4. Writes extracted data as mod files via existing export functions

  Easy targets: date, state history, country tags, equipment counts.
  Medium: completed focuses (IDs only, not tree layout), technologies.
  Hard/impossible: map pixels (not in saves), full focus tree definitions.
  Binary/ironman saves: need external library (hoi4save) or binary decoder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TokenType(Enum):
    STRING = auto()
    NUMBER = auto()
    IDENT = auto()
    LBRACE = auto()
    RBRACE = auto()
    EQUALS = auto()
    COMMENT = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int = 0
    col: int = 0


def tokenize(text: str) -> list[Token]:
    # TODO: split into _tokenize_string, _tokenize_number_or_ident, _tokenize_comment
    # helpers ; currently 72 lines of deeply nested conditionals with 6 if-c branches.
    tokens: list[Token] = []
    i = 0
    line = 1
    col = 1

    while i < len(text):
        c = text[i]

        if c == "\n":
            line += 1
            col = 1
            i += 1
            continue

        if c in " \t\r":
            col += 1
            i += 1
            continue

        if c == "#":
            start = i
            start_col = col
            while i < len(text) and text[i] != "\n":
                i += 1
                col += 1
            tokens.append(Token(TokenType.COMMENT, text[start:i], line, start_col))
            continue

        if c == "{":
            tokens.append(Token(TokenType.LBRACE, "{", line, col))
            i += 1
            col += 1
            continue

        if c == "}":
            tokens.append(Token(TokenType.RBRACE, "}", line, col))
            i += 1
            col += 1
            continue

        if c == "=":
            tokens.append(Token(TokenType.EQUALS, "=", line, col))
            i += 1
            col += 1
            continue

        if c == '"':
            start_col = col
            i += 1
            col += 1
            start = i
            while i < len(text) and text[i] != '"':
                if text[i] == "\n":
                    line += 1
                    col = 0
                i += 1
                col += 1
            if i >= len(text):
                raise ParseError(
                    f"Unterminated quoted string starting at column {start_col}",
                    line=line,
                    col=start_col,
                )
            tokens.append(Token(TokenType.STRING, text[start:i], line, start_col))
            i += 1
            col += 1
            continue

        start = i
        start_col = col
        while i < len(text) and text[i] not in ' \t\r\n{}=#"':
            i += 1
            col += 1
        word = text[start:i]

        if re.match(r"^-?\d+(\.\d+)?$", word):
            tokens.append(Token(TokenType.NUMBER, word, line, start_col))
        else:
            tokens.append(Token(TokenType.IDENT, word, line, start_col))

    tokens.append(Token(TokenType.EOF, "", line, col))
    return tokens


@dataclass
class PdxNode:
    key: Optional[str] = None
    value: Optional[str] = None
    children: list["PdxNode"] = field(default_factory=list)
    is_comment: bool = False

    def is_block(self) -> bool:
        return len(self.children) > 0

    def is_assignment(self) -> bool:
        return self.value is not None and not self.is_block()

    def is_bare(self) -> bool:
        return self.key is None and self.value is not None

    def find(self, key: str) -> Optional["PdxNode"]:
        for child in self.children:
            if child.key == key:
                return child
        return None

    def find_all(self, key: str) -> list["PdxNode"]:
        return [c for c in self.children if c.key == key]

    def get_value(self, key: str, default: str = "") -> str:
        node = self.find(key)
        if node and node.value is not None:
            return node.value
        return default

    def get_int(self, key: str, default: int = 0) -> int:
        v = self.get_value(key)
        try:
            return int(v)
        except ValueError:
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        v = self.get_value(key)
        try:
            return float(v)
        except ValueError:
            return default

    def get_block(self, key: str) -> Optional["PdxNode"]:
        node = self.find(key)
        if node and node.is_block():
            return node
        return None

    def set_value(self, key: str, value: str) -> None:
        for child in self.children:
            if child.key == key:
                child.value = value
                child.children = []
                return
        self.children.append(PdxNode(key=key, value=value))

    def remove(self, key: str) -> None:
        self.children = [c for c in self.children if c.key != key]

    def add_child(self, node: "PdxNode") -> None:
        self.children.append(node)


class ParseError(ValueError):
    """Raised when Paradox script parsing fails."""

    def __init__(self, message: str, line: int = 0, col: int = 0):
        self.line = line
        self.col = col
        loc = f" at line {line}, col {col}" if line > 0 else ""
        super().__init__(f"Parse error{loc}: {message}")


class PdxParser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenType.EOF, "")

    def advance(self) -> Token:
        t = self.current()
        self.pos += 1
        return t

    def parse(self) -> PdxNode:
        root = PdxNode()
        root.children = self._parse_statements()
        return root

    def _parse_statements(self, end_token: TokenType = TokenType.EOF) -> list[PdxNode]:
        stmts: list[PdxNode] = []
        while self.current().type not in (end_token, TokenType.EOF):
            stmt = self._parse_statement()
            if stmt:
                stmts.append(stmt)
        return stmts

    def _parse_statement(self) -> Optional[PdxNode]:
        tok = self.current()

        if tok.type == TokenType.COMMENT:
            self.advance()
            return PdxNode(value=tok.value, is_comment=True)

        if tok.type == TokenType.RBRACE:
            return None

        if tok.type in (TokenType.IDENT, TokenType.STRING, TokenType.NUMBER):
            value = self.advance().value
            if self.current().type == TokenType.EQUALS:
                self.advance()
                return self._parse_rhs(value)
            return PdxNode(key=None, value=value)

        if tok.type == TokenType.LBRACE:
            self.advance()
            children = self._parse_statements(TokenType.RBRACE)
            if self.current().type == TokenType.RBRACE:
                self.advance()
            node = PdxNode()
            node.children = children
            return node

        self.advance()
        return None

    def _parse_rhs(self, key: str) -> PdxNode:
        while self.current().type == TokenType.COMMENT:
            self.advance()
        tok = self.current()
        if tok.type == TokenType.LBRACE:
            self.advance()
            children = self._parse_statements(TokenType.RBRACE)
            if self.current().type == TokenType.RBRACE:
                self.advance()
            node = PdxNode(key=key)
            node.children = children
            return node
        if tok.type in (TokenType.IDENT, TokenType.STRING, TokenType.NUMBER):
            val = self.advance().value
            return PdxNode(key=key, value=val)
        return PdxNode(key=key, value="")


def parse_pdx(text: str) -> PdxNode:
    tokens = tokenize(text)
    parser = PdxParser(tokens)
    return parser.parse()


def serialize_pdx(node: PdxNode, indent: int = 0) -> str:
    parts: list[str] = []
    tab = "\t" * indent

    if node.is_comment:
        parts.append(f"{tab}{node.value}\n")
        return "".join(parts)

    if node.is_block():
        if node.key is not None:
            parts.append(f"{tab}{node.key} = {{\n")
            for child in node.children:
                parts.append(serialize_pdx(child, indent + 1))
            parts.append(f"{tab}}}\n")
        else:
            for child in node.children:
                parts.append(serialize_pdx(child, indent))
    elif node.value is not None:
        if node.key is not None:
            v = node.value
            if " " in v or '"' in v or "\n" in v or "\t" in v or "#" in v:
                escaped = (
                    v.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                    .replace("\t", "\\t")
                )
                v = f'"{escaped}"'
            parts.append(f"{tab}{node.key} = {v}\n")
        else:
            parts.append(f"{tab}{node.value}\n")

    return "".join(parts)


def extract_braced_block(text: str, start_index: int) -> tuple[str, int]:
    depth = 1
    i = start_index
    in_quote = False
    while i < len(text) and depth > 0:
        c = text[i]
        if c == '"':
            in_quote = not in_quote
        elif not in_quote:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
        i += 1
    if depth != 0:
        raise ValueError("Unbalanced braces")
    return text[start_index : i - 1], i
