from src.parser import tokenize, parse_pdx, serialize_pdx, PdxNode, TokenType


class TestTokenize:
    def test_simple_assignment(self):
        tokens = tokenize("key = value")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert types == [TokenType.IDENT, TokenType.EQUALS, TokenType.IDENT]

    def test_quoted_string(self):
        tokens = tokenize('name = "Hello World"')
        vals = [t.value for t in tokens if t.type != TokenType.EOF]
        assert vals == ["name", "=", "Hello World"]

    def test_number(self):
        tokens = tokenize("id = 42")
        vals = [(t.value, t.type) for t in tokens if t.type != TokenType.EOF]
        assert vals == [
            ("id", TokenType.IDENT),
            ("=", TokenType.EQUALS),
            ("42", TokenType.NUMBER),
        ]

    def test_float(self):
        tokens = tokenize("factor = 0.5")
        vals = [(t.value, t.type) for t in tokens if t.type != TokenType.EOF]
        assert vals == [
            ("factor", TokenType.IDENT),
            ("=", TokenType.EQUALS),
            ("0.5", TokenType.NUMBER),
        ]

    def test_braces(self):
        tokens = tokenize("block = { }")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert types == [
            TokenType.IDENT,
            TokenType.EQUALS,
            TokenType.LBRACE,
            TokenType.RBRACE,
        ]

    def test_comment_stripped(self):
        tokens = tokenize("key = value # comment")
        vals = [t.value for t in tokens if t.type not in (TokenType.EOF, TokenType.COMMENT)]
        assert vals == ["key", "=", "value"]

    def test_nested_blocks(self):
        tokens = tokenize("a = { b = { c = 1 } }")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert types == [
            TokenType.IDENT,
            TokenType.EQUALS,
            TokenType.LBRACE,
            TokenType.IDENT,
            TokenType.EQUALS,
            TokenType.LBRACE,
            TokenType.IDENT,
            TokenType.EQUALS,
            TokenType.NUMBER,
            TokenType.RBRACE,
            TokenType.RBRACE,
        ]


class TestParsePdx:
    def test_simple_key_value(self):
        root = parse_pdx("key = value")
        assert root.find("key").value == "value"

    def test_quoted_value(self):
        root = parse_pdx('name = "Hello"')
        assert root.find("name").value == "Hello"

    def test_numeric_value(self):
        root = parse_pdx("id = 42")
        assert root.find("id").value == "42"
        assert root.get_int("id") == 42

    def test_block(self):
        root = parse_pdx("block = { x = 1 y = 2 }")
        block = root.get_block("block")
        assert block is not None
        assert block.get_int("x") == 1
        assert block.get_int("y") == 2

    def test_find_all(self):
        root = parse_pdx("a = 1\nb = 2\na = 3")
        all_a = root.find_all("a")
        assert len(all_a) == 2

    def test_set_value_existing(self):
        root = parse_pdx("key = old")
        root.set_value("key", "new")
        assert root.find("key").value == "new"

    def test_set_value_new(self):
        root = parse_pdx("key = old")
        root.set_value("new_key", "val")
        assert root.find("new_key").value == "val"

    def test_remove(self):
        root = parse_pdx("a = 1\nb = 2")
        root.remove("a")
        assert root.find("a") is None
        assert root.find("b") is not None

    def test_get_value_default(self):
        root = parse_pdx("a = 1")
        assert root.get_value("missing", "default") == "default"

    def test_get_float(self):
        root = parse_pdx("factor = 0.75")
        assert root.get_float("factor") == 0.75

    def test_add_child(self):
        root = parse_pdx("")
        root.add_child(PdxNode(key="x", value="10"))
        assert root.find("x").value == "10"


class TestSerializePdx:
    def test_simple_roundtrip(self):
        text = "key = value\n"
        root = parse_pdx(text)
        result = serialize_pdx(root)
        assert "key = value" in result

    def test_block_roundtrip(self):
        text = 'state = {\n\tid = 1\n\tname = "Test"\n}\n'
        root = parse_pdx(text)
        result = serialize_pdx(root)
        assert "state" in result
        assert "id = 1" in result
        assert "name = Test" in result

    def test_nested_block(self):
        text = "outer = {\n\tinner = {\n\t\tx = 1\n\t}\n}\n"
        root = parse_pdx(text)
        result = serialize_pdx(root)
        assert "outer" in result
        assert "inner" in result
        assert "x = 1" in result

    def test_value_with_spaces_quoted(self):
        root = PdxNode(key="name", value="Hello World")
        result = serialize_pdx(root)
        assert '"Hello World"' in result

    def test_comment_preservation(self):
        text = "# header comment\nkey = value\n# footer comment\n"
        root = parse_pdx(text)
        result = serialize_pdx(root)
        assert "# header comment" in result
        assert "# footer comment" in result
        assert "key = value" in result

    def test_comment_inside_block(self):
        text = "block = {\n\t# inside comment\n\tx = 1\n}\n"
        root = parse_pdx(text)
        block = root.get_block("block")
        assert block is not None
        assert block.get_int("x") == 1
        result = serialize_pdx(root)
        assert "# inside comment" in result

    def test_inline_comment_preservation(self):
        text = "owner = GER # the owner\n"
        root = parse_pdx(text)
        assert root.find("owner").value == "GER"
        result = serialize_pdx(root)
        assert "owner = GER" in result
        assert "# the owner" in result
