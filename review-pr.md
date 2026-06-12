## PR Reviewer Guide 🔍

#### (Review updated until commit https://github.com/AI20K-Build-Cohort-2/C2-App-079/commit/9b09f5b889efcbfe809fec2821bde541682e562c)


Here are some key observations to aid the review process:

<table>
<tr><td>⏱️&nbsp;<strong>Estimated effort to review</strong>: 4 🔵🔵🔵🔵⚪</td></tr>
<tr><td>🧪&nbsp;<strong>PR contains tests</strong></td></tr>
<tr><td>🔒&nbsp;<strong>Security concerns</strong><br><br>

No. The PR actually improves security by replacing `eval()`-like behavior in the calculator with a restricted AST walker and implementing `O_NOFOLLOW` logic in the document search tool to prevent symlink traversal attacks. The use of Pydantic for tool input validation also mitigates injection risks.</td></tr>
<tr><td>⚡&nbsp;<strong>Recommended focus areas for review</strong><br><br>

<details><summary><a href='https://github.com/AI20K-Build-Cohort-2/C2-App-079/pull/23/files#diff-0e3c19439eb304fecfd9822ca5a2045b8960d470537f464e7c6841df17abdf66R69-R104'><strong>Race Condition</strong></a>

The `_read_document` function uses `os.open` with `O_NOFOLLOW` to prevent symlink attacks, but it then uses `os.fstat` and `os.read` on the resulting file descriptor. While this is generally safe, the manual traversal of path components using `os.open(part, ..., dir_fd=...)` is complex and might still be susceptible to TOCTOU (Time-of-Check Time-of-Use) issues if a directory component is swapped for a symlink during the loop.
</summary>

```python
def _read_document(root: Path, relative: Path, max_file_bytes: int) -> str | None:
    """Open each path component without following symlinks."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec
    file_flags = os.O_RDONLY | nofollow | cloexec
    directory_fds: list[int] = []
    file_fd: int | None = None
    try:
        directory_fd = os.open(root, directory_flags)
        directory_fds.append(directory_fd)
        for part in relative.parts[:-1]:
            directory_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            directory_fds.append(directory_fd)

        file_fd = os.open(relative.name, file_flags, dir_fd=directory_fd)
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > max_file_bytes:
            return None
        chunks: list[bytes] = []
        remaining = max_file_bytes + 1
        while remaining:
            chunk = os.read(file_fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > max_file_bytes:
            return None
        return content.decode("utf-8", errors="replace")
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)
```

</details>

<details><summary><a href='https://github.com/AI20K-Build-Cohort-2/C2-App-079/pull/23/files#diff-058cb6d675a29ddc5efe978e9f658bc22f577159246dae8f10e4c8a9f205f52bR407-R411'><strong>Infinite Loop Risk</strong></a>

The `AgentLoop` detects duplicate tool calls using a `calls` set containing a hash of the tool name and input. However, if the reasoner is non-deterministic or slightly varies the input (e.g., adding a space), it could bypass this check and continue looping until `max_iterations` is reached, potentially incurring high LLM costs.
</summary>

```python
call_key = f"{action.tool}:{json.dumps(action.input, sort_keys=True)}"
if call_key in calls:
    reason = "no_progress"
    break
calls.add(call_key)
```

</details>

<details><summary><a href='https://github.com/AI20K-Build-Cohort-2/C2-App-079/pull/23/files#diff-6f5f891f3fda8565bdadb7fba8ad40b02da07f67848272cf6c5e2490711a629cR45-R62'><strong>Resource Exhaustion</strong></a>

The calculator uses `ast.parse` and a recursive `_evaluate` function. While it limits recursion depth and exponent size, it does not limit the total number of nodes in the AST. A very wide (but shallow) expression could still consume significant CPU or memory during parsing and traversal.
</summary>

```python
def _evaluate(node: ast.AST, depth: int = 0) -> float:
    if depth > 20:
        raise ValueError("Expression is too deep")
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        value = float(node.value)
    elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and abs(right) > 20:
            raise ValueError("Exponent is too large")
        value = float(_BINARY[type(node.op)](left, right))
    elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        value = float(_UNARY[type(node.op)](_evaluate(node.operand, depth + 1)))
    else:
        raise ValueError("Unsupported expression")
    if not math.isfinite(value) or abs(value) > MAX_ABS_VALUE:
        raise ValueError("Result is too large")
    return value
```

</details>

</td></tr>
</table>

