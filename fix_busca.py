import re

with open('margo_server.py', 'r') as f:
    c = f.read()

# 1. Adicionar tipos compostos ANTES dos tipos simples no _place_types
old_types = '''        "restaurante":"restaurant","restaurant":"restaurant","churrascaria":"steakhouse",'''
new_types = '''        "sushi bar":"sushi bar","sushi":"sushi restaurant","ramen":"ramen restaurant",
        "hamburgueria":"burger place","pizzaria":"pizzeria","churrascaria":"steakhouse",
        "restaurante":"restaurant","restaurant":"restaurant",'''

c = c.replace(old_types, new_types)

# 2. Procurar adjetivo ANTES do tipo também
old_adj = '''        adj_match = _re.search(found_type + r'\\s+(\\w+)', msg)
        adj = adj_match.group(1) if adj_match else ""'''
new_adj = '''        # Pega palavra depois do tipo (ex: "restaurante indiano")
        adj_match = _re.search(found_type + r'\\s+(\\w+)', msg)
        adj = adj_match.group(1) if adj_match else ""
        # Se não achou depois, pega palavra antes do tipo (ex: "indian restaurant", "sushi bar")
        if not adj:
            before_match = _re.search(r'(\\w+)\\s+' + found_type, msg)
            if before_match:
                adj = before_match.group(1)'''

c = c.replace(old_adj, new_adj)

with open('margo_server.py', 'w') as f:
    f.write(c)

print('OK - busca corrigida')
