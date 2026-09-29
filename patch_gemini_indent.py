with open("ai/providers/gemini.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.startswith("@retry"):
        new_lines.append("    " + line)
    else:
        new_lines.append(line)

with open("ai/providers/gemini.py", "w") as f:
    f.writelines(new_lines)
