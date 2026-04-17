import re

with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all @bot.command decorators and their functions
pattern = r'@bot\.command\([^)]*\)\s*(?:async\s+)?def\s+(\w+)\s*\('
matches = re.finditer(pattern, content)

commands = []
for match in matches:
    func_name = match.group(1)
    start_pos = match.start()
    # Find the next @bot/def after this function
    next_decorator = content.find('@bot.command', start_pos + 1)
    next_def = content.find('\n@', start_pos + 1)
    if next_def == -1:
        next_def = next_decorator if next_decorator != -1 else len(content)
    elif next_decorator != -1:
        next_def = min(next_def, next_decorator)
    
    func_code = content[start_pos:next_def]
    send_count = func_code.count('await ctx.send')
    
    # Get line number
    line_num = content[:start_pos].count('\n') + 1
    
    commands.append({
        'name': func_name,
        'line': line_num,
        'sends': send_count
    })

# Sort by sends
commands.sort(key=lambda x: x['sends'], reverse=True)

print("COMMAND ANALYSIS - Multiple ctx.send() Calls:\n")
print(f"{'Command':<20} {'Line':<8} {'sends':<8} {'Risk'}")
print("=" * 60)

for cmd in commands:
    risk = "HIGH" if cmd['sends'] > 1 else "OK"
    if cmd['sends'] > 1:
        print(f"{cmd['name']:<20} {cmd['line']:<8} {cmd['sends']:<8} {risk}")

print("\n" + "=" * 60)
high_risk = [c for c in commands if c['sends'] > 1]
print(f"\nHIGH RISK COMMANDS ({len(high_risk)}):")
for cmd in sorted(high_risk, key=lambda x: -x['sends']):
    print(f"   - {cmd['name']} (line {cmd['line']}) - {cmd['sends']} sends")

print(f"\nTOTAL COMMANDS: {len(commands)}")
print(f"COMMANDS WITH MULTIPLE SENDS: {len(high_risk)}")
