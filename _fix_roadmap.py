import pathlib

p = pathlib.Path("docs/sec-expansion-roadmap.md")
text = p.read_text(encoding="utf-8")
lines = text.split("\n")
start = None
end = None
for i, line in enumerate(lines):
    if line.strip() == "### Deferred: Structured Executive Compensation Persistence":
        start = i
    if start is not None and "Until this lands" in line:
        end = i
        break
print(f"start={start}, end={end}")
if start is not None and end is not None:
    keep = lines[:start] + lines[end + 1:]
    p.write_text("\n".join(keep), encoding="utf-8")
    print("Done")
else:
    print("Block not found")
