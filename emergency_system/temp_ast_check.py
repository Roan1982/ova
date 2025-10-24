import ast
p = r'c:/Users/angel.steklein/Documents/desarrollo/ova/emergency_system/demo_emergency_parking.py'
with open(p, 'r', encoding='utf-8') as f:
    src = f.read()
ast.parse(src)
print('ast_ok')
